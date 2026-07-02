#include <Arduino.h>
#include <Servo.h>

#include "AzimuthControl.h"

namespace Pins {
const uint8_t receiverVertical = 18;   // Mega external interrupt pin. Suggested FS-A6 CH3.
const uint8_t receiverHorizontal = 19; // Mega external interrupt pin. Suggested FS-A6 CH1.
const uint8_t azimuthServo = 9;
} // namespace Pins

enum class ServoOutputMode : uint8_t {
    ReceiverMonitorOnly = 0,
    Position360Servo = 1
};

const ServoOutputMode servoOutputMode = ServoOutputMode::ReceiverMonitorOnly;

const uint16_t verticalMinUs = 1000;
const uint16_t verticalCenterUs = 1500;
const uint16_t verticalMaxUs = 2000;
const uint16_t horizontalMinUs = 1000;
const uint16_t horizontalCenterUs = 1500;
const uint16_t horizontalMaxUs = 2000;
const uint16_t rcDeadbandUs = 45;

const uint16_t pulseCaptureMinUs = 700;
const uint16_t pulseCaptureMaxUs = 2300;

const bool reverseWhenVerticalIsHigh = true;
const bool invertHorizontal = false;

const uint32_t signalTimeoutUs = 250000UL;
const uint32_t controlPeriodMs = 20;

const int servoPosition0Us = 1000;
const int servoPosition360Us = 2000;
const float servoZeroOffsetDeg = 0.0f;

const bool serialDebugEnabled = true;
const bool printRcCalibrationStats = true;
const uint32_t serialDebugPeriodMs = 250;

struct PulseStats {
    bool hasSample = false;
    uint16_t minUs = 65535;
    uint16_t maxUs = 0;
};

volatile uint32_t verticalRiseUs = 0;
volatile uint32_t horizontalRiseUs = 0;
volatile uint32_t verticalLastPulseAtUs = 0;
volatile uint32_t horizontalLastPulseAtUs = 0;
volatile uint16_t verticalPulseUs = verticalCenterUs;
volatile uint16_t horizontalPulseUs = horizontalCenterUs;

Servo azimuthServo;
PulseStats verticalStats;
PulseStats horizontalStats;

void updateStats(PulseStats& stats, uint16_t pulseUs, bool fresh) {
    if (!fresh) {
        return;
    }

    if (!stats.hasSample) {
        stats.hasSample = true;
        stats.minUs = pulseUs;
        stats.maxUs = pulseUs;
        return;
    }

    if (pulseUs < stats.minUs) {
        stats.minUs = pulseUs;
    }
    if (pulseUs > stats.maxUs) {
        stats.maxUs = pulseUs;
    }
}

AzimuthConfig makeAzimuthConfig() {
    AzimuthConfig config;
    config.vertical.minUs = verticalMinUs;
    config.vertical.centerUs = verticalCenterUs;
    config.vertical.maxUs = verticalMaxUs;
    config.vertical.deadbandUs = rcDeadbandUs;
    config.horizontal.minUs = horizontalMinUs;
    config.horizontal.centerUs = horizontalCenterUs;
    config.horizontal.maxUs = horizontalMaxUs;
    config.horizontal.deadbandUs = rcDeadbandUs;
    config.forwardReferenceDeg = 0.0f;
    config.reverseReferenceDeg = 180.0f;
    config.maxSteeringDeg = 45.0f;
    config.maxRateDegPerSecond = 180.0f;
    config.reverseWhenVerticalIsHigh = reverseWhenVerticalIsHigh;
    config.invertHorizontal = invertHorizontal;
    return config;
}

AzimuthControl azimuthControl(makeAzimuthConfig());

bool servoOutputEnabled() {
    return servoOutputMode == ServoOutputMode::Position360Servo;
}

float axisPercent(uint16_t pulseUs, uint16_t minUs, uint16_t centerUs, uint16_t maxUs) {
    if (pulseUs >= centerUs) {
        const uint16_t span = maxUs > centerUs ? maxUs - centerUs : 1;
        return 100.0f * static_cast<float>(pulseUs - centerUs) / static_cast<float>(span);
    }

    const uint16_t span = centerUs > minUs ? centerUs - minUs : 1;
    return -100.0f * static_cast<float>(centerUs - pulseUs) / static_cast<float>(span);
}

uint16_t midpoint(uint16_t minUs, uint16_t maxUs) {
    return static_cast<uint16_t>((static_cast<uint32_t>(minUs) + static_cast<uint32_t>(maxUs)) / 2UL);
}

void capturePulse(uint8_t pin, volatile uint32_t& riseUs, volatile uint32_t& lastPulseAtUs,
                  volatile uint16_t& pulseUs) {
    const uint32_t nowUs = micros();

    if (digitalRead(pin) == HIGH) {
        riseUs = nowUs;
        return;
    }

    const uint32_t widthUs = nowUs - riseUs;
    if (widthUs >= pulseCaptureMinUs && widthUs <= pulseCaptureMaxUs) {
        pulseUs = static_cast<uint16_t>(widthUs);
        lastPulseAtUs = nowUs;
    }
}

void onVerticalPulseChange() {
    capturePulse(Pins::receiverVertical, verticalRiseUs, verticalLastPulseAtUs, verticalPulseUs);
}

void onHorizontalPulseChange() {
    capturePulse(Pins::receiverHorizontal, horizontalRiseUs, horizontalLastPulseAtUs, horizontalPulseUs);
}

AzimuthSample readReceiverSample() {
    uint16_t verticalUs;
    uint16_t horizontalUs;
    uint32_t verticalAtUs;
    uint32_t horizontalAtUs;

    noInterrupts();
    verticalUs = verticalPulseUs;
    horizontalUs = horizontalPulseUs;
    verticalAtUs = verticalLastPulseAtUs;
    horizontalAtUs = horizontalLastPulseAtUs;
    interrupts();

    const uint32_t nowUs = micros();

    AzimuthSample sample;
    sample.verticalUs = verticalUs;
    sample.horizontalUs = horizontalUs;
    sample.verticalFresh = verticalAtUs != 0UL && nowUs - verticalAtUs <= signalTimeoutUs;
    sample.horizontalFresh = horizontalAtUs != 0UL && nowUs - horizontalAtUs <= signalTimeoutUs;
    sample.nowMs = millis();
    return sample;
}

int angleToPositionServoPulseUs(float angleDeg) {
    const float servoAngleDeg = normalizeAngle360(angleDeg + servoZeroOffsetDeg);
    const float ratio = servoAngleDeg / 360.0f;
    return servoPosition0Us + static_cast<int>((servoPosition360Us - servoPosition0Us) * ratio + 0.5f);
}

void printSeenRange(const __FlashStringHelper* label, const PulseStats& stats) {
    Serial.print(label);
    if (!stats.hasSample) {
        Serial.print(F("--..--"));
        return;
    }

    Serial.print(stats.minUs);
    Serial.print(F(".."));
    Serial.print(stats.maxUs);
    Serial.print(F(" mid="));
    Serial.print(midpoint(stats.minUs, stats.maxUs));
}

void printDebug(const AzimuthState& state, const AzimuthSample& sample, int servoPulseUs) {
    static uint32_t lastPrintMs = 0;
    const uint32_t nowMs = millis();

    if (!serialDebugEnabled || nowMs - lastPrintMs < serialDebugPeriodMs) {
        return;
    }

    lastPrintMs = nowMs;
    Serial.print(F("out="));
    Serial.print(servoOutputEnabled() ? F("position360") : F("monitor"));
    Serial.print(F(" mode="));
    Serial.print(state.mode == AzimuthMode::Reverse ? F("reverse") : F("forward"));
    Serial.print(F(" steering="));
    Serial.print(state.steeringDeg);
    Serial.print(F(" target="));
    Serial.print(state.targetAngleDeg);
    Serial.print(F(" command="));
    Serial.print(state.commandAngleDeg);
    Serial.print(F(" servoUs="));
    Serial.print(servoPulseUs);
    Serial.print(F(" vUs="));
    Serial.print(sample.verticalUs);
    if (!sample.verticalFresh) {
        Serial.print(F("!"));
    }
    Serial.print(F(" vPct="));
    Serial.print(axisPercent(sample.verticalUs, verticalMinUs, verticalCenterUs, verticalMaxUs));
    Serial.print(F(" hUs="));
    Serial.print(sample.horizontalUs);
    if (!sample.horizontalFresh) {
        Serial.print(F("!"));
    }
    Serial.print(F(" hPct="));
    Serial.print(axisPercent(sample.horizontalUs, horizontalMinUs, horizontalCenterUs, horizontalMaxUs));
    Serial.print(F(" failsafe="));
    Serial.print(state.failsafeActive ? F("yes") : F("no"));

    if (printRcCalibrationStats) {
        Serial.print(F(" "));
        printSeenRange(F("vSeen="), verticalStats);
        Serial.print(F(" "));
        printSeenRange(F("hSeen="), horizontalStats);
    }

    Serial.println();
}

void setup() {
    Serial.begin(115200);

    pinMode(Pins::receiverVertical, INPUT);
    pinMode(Pins::receiverHorizontal, INPUT);

    attachInterrupt(digitalPinToInterrupt(Pins::receiverVertical), onVerticalPulseChange, CHANGE);
    attachInterrupt(digitalPinToInterrupt(Pins::receiverHorizontal), onHorizontalPulseChange, CHANGE);

    azimuthControl.reset(0.0f, millis());

    if (servoOutputEnabled()) {
        azimuthServo.attach(Pins::azimuthServo, servoPosition0Us, servoPosition360Us);
        azimuthServo.writeMicroseconds(angleToPositionServoPulseUs(0.0f));
    }

    Serial.println(F("Azimutal Minerva ready"));
    Serial.println(F("Move both sticks through their full travel and copy vSeen/hSeen into the calibration constants."));
}

void loop() {
    static uint32_t lastControlMs = 0;
    const uint32_t nowMs = millis();

    if (nowMs - lastControlMs < controlPeriodMs) {
        return;
    }

    lastControlMs = nowMs;

    const AzimuthSample sample = readReceiverSample();
    updateStats(verticalStats, sample.verticalUs, sample.verticalFresh);
    updateStats(horizontalStats, sample.horizontalUs, sample.horizontalFresh);

    const AzimuthState state = azimuthControl.update(sample);
    const int servoPulseUs = angleToPositionServoPulseUs(state.commandAngleDeg);

    if (servoOutputEnabled() && !state.failsafeActive) {
        azimuthServo.writeMicroseconds(servoPulseUs);
    }

    printDebug(state, sample, servoPulseUs);
}
