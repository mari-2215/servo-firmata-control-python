#pragma once

#include <stdint.h>

enum class AzimuthMode : uint8_t {
    Forward = 0,
    Reverse = 1
};

struct RcChannelCalibration {
    uint16_t minUs = 1000;
    uint16_t centerUs = 1500;
    uint16_t maxUs = 2000;
    uint16_t deadbandUs = 35;
};

struct AzimuthConfig {
    RcChannelCalibration vertical;
    RcChannelCalibration horizontal;
    float forwardReferenceDeg = 0.0f;
    float reverseReferenceDeg = 180.0f;
    float maxSteeringDeg = 45.0f;
    float maxRateDegPerSecond = 180.0f;
    bool reverseWhenVerticalIsHigh = true;
    bool invertHorizontal = false;
};

struct AzimuthSample {
    uint16_t verticalUs = 1500;
    uint16_t horizontalUs = 1500;
    bool verticalFresh = false;
    bool horizontalFresh = false;
    uint32_t nowMs = 0;
};

struct AzimuthState {
    AzimuthMode mode = AzimuthMode::Forward;
    float steeringDeg = 0.0f;
    float targetAngleDeg = 0.0f;
    float commandAngleDeg = 0.0f;
    bool failsafeActive = true;
};

float normalizeAngle360(float angleDeg);
float signedShortestDeltaDeg(float fromDeg, float toDeg);
float stepTowardAngleDeg(float currentDeg, float targetDeg, float maxStepDeg);

class AzimuthControl {
public:
    explicit AzimuthControl(const AzimuthConfig& config);

    void setConfig(const AzimuthConfig& config);
    void reset(float currentAngleDeg, uint32_t nowMs);
    AzimuthState update(const AzimuthSample& sample);
    AzimuthState state() const;

private:
    AzimuthConfig config_;
    AzimuthState state_;
    bool initialized_ = false;
    uint32_t lastUpdateMs_ = 0;

    void updateModeFromVertical(uint16_t verticalUs);
    float steeringFromHorizontal(uint16_t horizontalUs) const;
};
