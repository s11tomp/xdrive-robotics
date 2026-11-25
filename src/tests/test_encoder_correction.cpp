#include <doctest.h>

#include <cmath>

#include "MotorControl/encoder_correction.hpp"

// The firmware's table-based versions (arm_cos_f32.c, arm_sin_f32.c) agree with these to about 1e-6.
extern "C" float our_arm_cos_f32(float x) { return std::cos(x); }
extern "C" float our_arm_sin_f32(float x) { return std::sin(x); }

namespace {

// One harmonic per turn, sampled at the 256 bin centers as run_correction_calibration samples the error.
float harmonic(int k, int h, float amplitude, float phase) {
    return amplitude * std::cos(2.0f * M_PI * (float)h * ((float)k + 0.5f) / 256.0f + phase);
}

}  // namespace

TEST_SUITE("encoder correction") {
    TEST_CASE("keep_harmonics keeps harmonics 1..hmax and drops the mean and the rest") {
        float e[256], scratch[256];
        for (int k = 0; k < 256; ++k) {
            e[k] = 5.0f + harmonic(k, 1, 3.0f, 0.2f) + harmonic(k, 4, 2.0f, -1.1f) + harmonic(k, 12, 1.5f, 0.7f)
                   + harmonic(k, 13, 1.0f, 2.0f) + harmonic(k, 42, 0.8f, 0.0f);
        }
        encoder_correction::keep_harmonics(e, 12, scratch);
        for (int k = 0; k < 256; ++k) {
            float kept = harmonic(k, 1, 3.0f, 0.2f) + harmonic(k, 4, 2.0f, -1.1f) + harmonic(k, 12, 1.5f, 0.7f);
            CHECK(e[k] == doctest::Approx(kept).epsilon(1e-4));
        }
    }

    TEST_CASE("keep_harmonics with hmax 0 leaves the raw bins") {
        float e[256], raw[256], scratch[256];
        for (int k = 0; k < 256; ++k) {
            e[k] = raw[k] = (float)((k * 37) % 11) - 5.0f;
        }
        encoder_correction::keep_harmonics(e, 0, scratch);
        for (int k = 0; k < 256; ++k) {
            CHECK(e[k] == raw[k]);
        }
    }

    TEST_CASE("keep_harmonics up to 127 rebuilds any zero-mean error but the Nyquist term") {
        // 127 is the largest hmax run_correction_calibration passes. Harmonic 128 alternates sign
        // between bins and is the only one the filter can't represent.
        float e[256], scratch[256];
        float input[256];
        float mean = 0.0f;
        for (int k = 0; k < 256; ++k) {
            input[k] = (float)((k * 73) % 29) * 0.1f;
            mean += input[k] / 256.0f;
        }
        float nyquist = 0.0f;
        for (int k = 0; k < 256; ++k) {
            input[k] -= mean;
            nyquist += (k % 2 ? -input[k] : input[k]) / 256.0f;
        }
        for (int k = 0; k < 256; ++k) {
            e[k] = input[k];
        }
        encoder_correction::keep_harmonics(e, 127, scratch);
        for (int k = 0; k < 256; ++k) {
            float expected = input[k] - (k % 2 ? -nyquist : nyquist);
            CHECK(e[k] == doctest::Approx(expected).epsilon(1e-3).scale(1.0));
        }
    }
}
