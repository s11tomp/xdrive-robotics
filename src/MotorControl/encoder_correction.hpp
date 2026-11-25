#pragma once
// The harmonic filter ENCODER_CORRECTION_CALIBRATION (Encoder::run_correction_calibration) applies
// to the encoder error it measures, before the error goes into encoder.config.correction_table.
// The table has one entry per 1/256 of a turn, at the bin centers raw = (k + 0.5) * cpr / 256.
//
// Pure function, no firmware dependencies: src/tests compiles this header on the host.

#include "utils.hpp"  // M_PI, our_arm_cos_f32, our_arm_sin_f32

namespace encoder_correction {

// Replaces e[0..255] (one value per bin center) with its harmonics 1..hmax per turn: a DFT over the
// bin centers, then the rebuild into `scratch`, which is copied back. Harmonic 0 (the mean) and the
// harmonics above hmax are dropped. hmax must be at most 127; hmax <= 0 leaves e unchanged.
inline void keep_harmonics(float* e, int hmax, float* scratch) {
    if (hmax > 0) {
        for (int k = 0; k < 256; ++k) scratch[k] = 0.0f;
        for (int h = 1; h <= hmax; ++h) {
            float c = 0.0f, s = 0.0f;
            for (int k = 0; k < 256; ++k) {
                float a = 2.0f * M_PI * (float)h * ((float)k + 0.5f) / 256.0f;
                c += e[k] * our_arm_cos_f32(a);
                s += e[k] * our_arm_sin_f32(a);
            }
            c *= 2.0f / 256.0f;
            s *= 2.0f / 256.0f;
            for (int k = 0; k < 256; ++k) {
                float a = 2.0f * M_PI * (float)h * ((float)k + 0.5f) / 256.0f;
                scratch[k] += c * our_arm_cos_f32(a) + s * our_arm_sin_f32(a);
            }
        }
        for (int k = 0; k < 256; ++k) e[k] = scratch[k];
    }
}

}  // namespace encoder_correction
