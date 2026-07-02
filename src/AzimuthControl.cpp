#include "AzimuthControl.h"

static float clampFloat(float value, float minValue, float maxValue) {
    if (value < minValue) {
        return minValue;
    }
    if (value > maxValue) {
        return maxValue;
    }
    return value;
}

static float absFloat(float value) {
    return value < 0.0f ? -value : value;
}

static bool calibrationLooksValid(const RcChannelCalibration& calibration) {
    return calibration.minUs < calibration.centerUs && calibration.centerUs < calibration.maxUs;
}

static bool pulseLooksValid(uint16_t pulseUs, const RcChannelCalibration& calibration) {
    if (!calibrationLooksValid(calibration)) {
        return false;
    }

    const uint16_t lower = calibration.minUs > 300 ? calibration.minUs - 300 : 0;
    const uint16_t upper = calibration.maxUs + 300;
    return pulseUs >= lower && pulseUs <= upper;
}

static float normalizeAxis(uint16_t pulseUs, const RcChannelCalibration& calibration) {
    if (!calibrationLooksValid(calibration)) {
        return 0.0f;
    }

    const int16_t delta = static_cast<int16_t>(pulseUs) - static_cast<int16_t>(calibration.centerUs);

    if (delta >= -static_cast<int16_t>(calibration.deadbandUs) &&
        delta <= static_cast<int16_t>(calibration.deadbandUs)) {
        return 0.0f;
    }

    if (delta > 0) {
        const float usable = static_cast<float>(calibration.maxUs - calibration.centerUs - calibration.deadbandUs);
        const float adjusted = static_cast<float>(delta - calibration.deadbandUs);
        return usable <= 0.0f ? 0.0f : clampFloat(adjusted / usable, 0.0f, 1.0f);
    }

    const float usable = static_cast<float>(calibration.centerUs - calibration.minUs - calibration.deadbandUs);
    const float adjusted = static_cast<float>(delta + calibration.deadbandUs);
    return usable <= 0.0f ? 0.0f : clampFloat(adjusted / usable, -1.0f, 0.0f);
}

float normalizeAngle360(float angleDeg) {
    while (angleDeg < 0.0f) {
        angleDeg += 360.0f;
    }
    while (angleDeg >= 360.0f) {
        angleDeg -= 360.0f;
    }
    return angleDeg;
}

float signedShortestDeltaDeg(float fromDeg, float toDeg) {
    float delta = normalizeAngle360(toDeg - fromDeg);
    if (delta > 180.0f) {
        delta -= 360.0f;
    }
    return delta;
}

float stepTowardAngleDeg(float currentDeg, float targetDeg, float maxStepDeg) {
    const float current = normalizeAngle360(currentDeg);
    const float target = normalizeAngle360(targetDeg);
    const float delta = signedShortestDeltaDeg(current, target);
    const float limitedStep = maxStepDeg < 0.0f ? 0.0f : maxStepDeg;

    if (absFloat(delta) <= limitedStep) {
        return target;
    }

    return normalizeAngle360(current + (delta < 0.0f ? -limitedStep : limitedStep));
}

AzimuthControl::AzimuthControl(const AzimuthConfig& config) : config_(config) {
    reset(config_.forwardReferenceDeg, 0);
}

void AzimuthControl::setConfig(const AzimuthConfig& config) {
    config_ = config;
}

void AzimuthControl::reset(float currentAngleDeg, uint32_t nowMs) {
    state_.mode = AzimuthMode::Forward;
    state_.steeringDeg = 0.0f;
    state_.targetAngleDeg = normalizeAngle360(config_.forwardReferenceDeg);
    state_.commandAngleDeg = normalizeAngle360(currentAngleDeg);
    state_.failsafeActive = true;
    initialized_ = true;
    lastUpdateMs_ = nowMs;
}

AzimuthState AzimuthControl::update(const AzimuthSample& sample) {
    if (!initialized_) {
        reset(config_.forwardReferenceDeg, sample.nowMs);
    }

    const bool verticalOk = sample.verticalFresh && pulseLooksValid(sample.verticalUs, config_.vertical);
    const bool horizontalOk = sample.horizontalFresh && pulseLooksValid(sample.horizontalUs, config_.horizontal);

    if (verticalOk) {
        updateModeFromVertical(sample.verticalUs);
    }

    const float steeringDeg = horizontalOk ? steeringFromHorizontal(sample.horizontalUs) : 0.0f;
    const float baseAngleDeg =
        state_.mode == AzimuthMode::Reverse ? config_.reverseReferenceDeg : config_.forwardReferenceDeg;
    const float targetAngleDeg = normalizeAngle360(baseAngleDeg + steeringDeg);

    const uint32_t elapsedMs = sample.nowMs - lastUpdateMs_;
    const float maxStepDeg = config_.maxRateDegPerSecond * static_cast<float>(elapsedMs) / 1000.0f;

    state_.steeringDeg = steeringDeg;
    state_.targetAngleDeg = targetAngleDeg;
    state_.commandAngleDeg = stepTowardAngleDeg(state_.commandAngleDeg, targetAngleDeg, maxStepDeg);
    state_.failsafeActive = !verticalOk || !horizontalOk;

    lastUpdateMs_ = sample.nowMs;
    return state_;
}

AzimuthState AzimuthControl::state() const {
    return state_;
}

void AzimuthControl::updateModeFromVertical(uint16_t verticalUs) {
    const uint16_t center = config_.vertical.centerUs;
    const uint16_t deadband = config_.vertical.deadbandUs;
    const bool high = verticalUs > center + deadband;
    const bool low = verticalUs < center - deadband;

    if (!high && !low) {
        return;
    }

    const bool reverseRequested = config_.reverseWhenVerticalIsHigh ? high : low;
    state_.mode = reverseRequested ? AzimuthMode::Reverse : AzimuthMode::Forward;
}

float AzimuthControl::steeringFromHorizontal(uint16_t horizontalUs) const {
    float axis = normalizeAxis(horizontalUs, config_.horizontal);
    if (config_.invertHorizontal) {
        axis = -axis;
    }
    return axis * config_.maxSteeringDeg;
}
