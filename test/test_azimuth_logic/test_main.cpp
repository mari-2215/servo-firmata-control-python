#include <unity.h>

#include "AzimuthControl.h"

static AzimuthConfig fastConfig() {
    AzimuthConfig config;
    config.vertical.minUs = 1000;
    config.vertical.centerUs = 1500;
    config.vertical.maxUs = 2000;
    config.vertical.deadbandUs = 35;
    config.horizontal.minUs = 1000;
    config.horizontal.centerUs = 1500;
    config.horizontal.maxUs = 2000;
    config.horizontal.deadbandUs = 35;
    config.forwardReferenceDeg = 0.0f;
    config.reverseReferenceDeg = 180.0f;
    config.maxSteeringDeg = 45.0f;
    config.maxRateDegPerSecond = 10000.0f;
    return config;
}

static AzimuthSample sample(uint16_t verticalUs, uint16_t horizontalUs, uint32_t nowMs) {
    AzimuthSample item;
    item.verticalUs = verticalUs;
    item.horizontalUs = horizontalUs;
    item.verticalFresh = true;
    item.horizontalFresh = true;
    item.nowMs = nowMs;
    return item;
}

static void expectAngle(float expected, float actual) {
    TEST_ASSERT_FLOAT_WITHIN(0.01f, expected, actual);
}

void test_forward_half_centers_servo() {
    AzimuthControl control(fastConfig());
    control.reset(0.0f, 0);

    const AzimuthState state = control.update(sample(1200, 1500, 100));

    TEST_ASSERT_EQUAL(static_cast<int>(AzimuthMode::Forward), static_cast<int>(state.mode));
    expectAngle(0.0f, state.targetAngleDeg);
    expectAngle(0.0f, state.commandAngleDeg);
}

void test_reverse_half_adds_180_degrees() {
    AzimuthControl control(fastConfig());
    control.reset(0.0f, 0);

    const AzimuthState state = control.update(sample(1800, 1500, 100));

    TEST_ASSERT_EQUAL(static_cast<int>(AzimuthMode::Reverse), static_cast<int>(state.mode));
    expectAngle(180.0f, state.targetAngleDeg);
    expectAngle(180.0f, state.commandAngleDeg);
}

void test_horizontal_channel_steers_45_degrees_each_side() {
    AzimuthControl control(fastConfig());
    control.reset(0.0f, 0);

    AzimuthState state = control.update(sample(1200, 1000, 100));
    expectAngle(315.0f, state.targetAngleDeg);
    expectAngle(-45.0f, state.steeringDeg);

    state = control.update(sample(1200, 2000, 200));
    expectAngle(45.0f, state.targetAngleDeg);
    expectAngle(45.0f, state.steeringDeg);
}

void test_reverse_steering_is_relative_to_reverse_reference() {
    AzimuthControl control(fastConfig());
    control.reset(0.0f, 0);

    AzimuthState state = control.update(sample(1800, 1000, 100));
    expectAngle(135.0f, state.targetAngleDeg);

    state = control.update(sample(1800, 2000, 200));
    expectAngle(225.0f, state.targetAngleDeg);
}

void test_vertical_deadband_keeps_last_mode() {
    AzimuthControl control(fastConfig());
    control.reset(0.0f, 0);

    AzimuthState state = control.update(sample(1800, 1500, 100));
    TEST_ASSERT_EQUAL(static_cast<int>(AzimuthMode::Reverse), static_cast<int>(state.mode));

    state = control.update(sample(1500, 1500, 200));
    TEST_ASSERT_EQUAL(static_cast<int>(AzimuthMode::Reverse), static_cast<int>(state.mode));
    expectAngle(180.0f, state.targetAngleDeg);
}

void test_custom_receiver_intervals_reach_full_steering() {
    AzimuthConfig config = fastConfig();
    config.vertical.minUs = 1120;
    config.vertical.centerUs = 1508;
    config.vertical.maxUs = 1890;
    config.horizontal.minUs = 1115;
    config.horizontal.centerUs = 1502;
    config.horizontal.maxUs = 1888;
    AzimuthControl control(config);
    control.reset(0.0f, 0);

    AzimuthState state = control.update(sample(1200, 1115, 100));
    TEST_ASSERT_EQUAL(static_cast<int>(AzimuthMode::Forward), static_cast<int>(state.mode));
    expectAngle(315.0f, state.targetAngleDeg);
    expectAngle(-45.0f, state.steeringDeg);

    state = control.update(sample(1800, 1888, 200));
    TEST_ASSERT_EQUAL(static_cast<int>(AzimuthMode::Reverse), static_cast<int>(state.mode));
    expectAngle(225.0f, state.targetAngleDeg);
    expectAngle(45.0f, state.steeringDeg);
}

void test_inverted_channels_can_match_reversed_radio_setup() {
    AzimuthConfig config = fastConfig();
    config.reverseWhenVerticalIsHigh = false;
    config.invertHorizontal = true;
    AzimuthControl control(config);
    control.reset(0.0f, 0);

    AzimuthState state = control.update(sample(1200, 1000, 100));
    TEST_ASSERT_EQUAL(static_cast<int>(AzimuthMode::Reverse), static_cast<int>(state.mode));
    expectAngle(225.0f, state.targetAngleDeg);
    expectAngle(45.0f, state.steeringDeg);
}

void test_failsafe_keeps_mode_and_removes_steering() {
    AzimuthControl control(fastConfig());
    control.reset(0.0f, 0);

    AzimuthState state = control.update(sample(1800, 2000, 100));
    expectAngle(225.0f, state.targetAngleDeg);

    AzimuthSample lostHorizontal = sample(1800, 2000, 200);
    lostHorizontal.horizontalFresh = false;
    state = control.update(lostHorizontal);

    TEST_ASSERT_TRUE(state.failsafeActive);
    TEST_ASSERT_EQUAL(static_cast<int>(AzimuthMode::Reverse), static_cast<int>(state.mode));
    expectAngle(180.0f, state.targetAngleDeg);
}

void test_repeated_reverse_switch_does_not_accumulate_angle() {
    AzimuthControl control(fastConfig());
    control.reset(0.0f, 0);

    uint32_t nowMs = 0;
    for (int i = 0; i < 10; ++i) {
        nowMs += 100;
        AzimuthState state = control.update(sample(1800, 1500, nowMs));
        expectAngle(180.0f, state.targetAngleDeg);

        nowMs += 100;
        state = control.update(sample(1200, 1500, nowMs));
        expectAngle(0.0f, state.targetAngleDeg);
    }
}

int main(int, char**) {
    UNITY_BEGIN();
    RUN_TEST(test_forward_half_centers_servo);
    RUN_TEST(test_reverse_half_adds_180_degrees);
    RUN_TEST(test_horizontal_channel_steers_45_degrees_each_side);
    RUN_TEST(test_reverse_steering_is_relative_to_reverse_reference);
    RUN_TEST(test_vertical_deadband_keeps_last_mode);
    RUN_TEST(test_custom_receiver_intervals_reach_full_steering);
    RUN_TEST(test_inverted_channels_can_match_reversed_radio_setup);
    RUN_TEST(test_failsafe_keeps_mode_and_removes_steering);
    RUN_TEST(test_repeated_reverse_switch_does_not_accumulate_angle);
    return UNITY_END();
}
