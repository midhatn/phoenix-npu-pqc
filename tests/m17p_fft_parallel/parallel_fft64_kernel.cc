// Purpose: 4-Column Parallel 64-Point FFT Kernel with embedded Twiddles (Zero extra DMA channel).
// Target operating system: Windows 11 Pro 25H2.
// Target architecture: AMD Phoenix NPU1 / XDNA1 / AIE2 (4 Columns).
// Workload: 16 frames of 64 complex points = 2048 bfloat16 elements per core.

#define NOCPP

#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <math.h>
#include <aie_api/aie.hpp>
#include "sdr_dsp_common.hpp"

extern "C" {

void parallel_fft64_kernel(
    bfloat16 *__restrict in_frames,
    bfloat16 *__restrict out_spectra
) {
    event0();

    // Constant 64-point Twiddle table in core program memory (ROM / text section)
    // Avoids requiring extra shim DMA channels
    static const float tw_r[64] = {
        1.000000f, 0.995185f, 0.980785f, 0.956940f, 0.923880f, 0.881921f, 0.831470f, 0.773010f,
        0.707107f, 0.634393f, 0.555570f, 0.471397f, 0.382683f, 0.290285f, 0.195090f, 0.098017f,
        0.000000f, -0.098017f, -0.195090f, -0.290285f, -0.382683f, -0.471397f, -0.555570f, -0.634393f,
        -0.707107f, -0.773010f, -0.831470f, -0.881921f, -0.923880f, -0.956940f, -0.980785f, -0.995185f,
        -1.000000f, -0.995185f, -0.980785f, -0.956940f, -0.923880f, -0.881921f, -0.831470f, -0.773010f,
        -0.707107f, -0.634393f, -0.555570f, -0.471397f, -0.382683f, -0.290285f, -0.195090f, -0.098017f,
        0.000000f, 0.098017f, 0.195090f, 0.290285f, 0.382683f, 0.471397f, 0.555570f, 0.634393f,
        0.707107f, 0.773010f, 0.831470f, 0.881921f, 0.923880f, 0.956940f, 0.980785f, 0.995185f
    };

    static const float tw_i[64] = {
        0.000000f, -0.098017f, -0.195090f, -0.290285f, -0.382683f, -0.471397f, -0.555570f, -0.634393f,
        -0.707107f, -0.773010f, -0.831470f, -0.881921f, -0.923880f, -0.956940f, -0.980785f, -0.995185f,
        -1.000000f, -0.995185f, -0.980785f, -0.956940f, -0.923880f, -0.881921f, -0.831470f, -0.773010f,
        -0.707107f, -0.634393f, -0.555570f, -0.471397f, -0.382683f, -0.290285f, -0.195090f, -0.098017f,
        0.000000f, 0.098017f, 0.195090f, 0.290285f, 0.382683f, 0.471397f, 0.555570f, 0.634393f,
        0.707107f, 0.773010f, 0.831470f, 0.881921f, 0.923880f, 0.956940f, 0.980785f, 0.995185f,
        1.000000f, 0.995185f, 0.980785f, 0.956940f, 0.923880f, 0.881921f, 0.831470f, 0.773010f,
        0.707107f, 0.634393f, 0.555570f, 0.471397f, 0.382683f, 0.290285f, 0.195090f, 0.098017f
    };

    // Process 16 frames (16 * 128 = 2048 bfloat16 elements) per core
#pragma clang loop unroll_count(2)
    for (int frame = 0; frame < 16; ++frame) {
        int frame_offset = frame * 128;

        float real_out[64] = {0.0f};
        float imag_out[64] = {0.0f};

        for (int k = 0; k < 64; ++k) {
            float sum_r = 0.0f;
            float sum_i = 0.0f;

            for (int n = 0; n < 64; ++n) {
                float in_r = (float)in_frames[frame_offset + 2 * n];
                float in_i = (float)in_frames[frame_offset + 2 * n + 1];

                int tw_idx = (k * n) % 64;
                float r_tw = tw_r[tw_idx];
                float i_tw = tw_i[tw_idx];

                sum_r += (in_r * r_tw) - (in_i * i_tw);
                sum_i += (in_r * i_tw) + (in_i * r_tw);
            }

            real_out[k] = sum_r;
            imag_out[k] = sum_i;
        }

        for (int k = 0; k < 64; ++k) {
            out_spectra[frame_offset + 2 * k]     = (bfloat16)real_out[k];
            out_spectra[frame_offset + 2 * k + 1] = (bfloat16)imag_out[k];
        }
    }

    event1();
}

}
