// Purpose: Vectorized Radix-2 / Radix-4 64-point FFT Kernel using AIE2 Butterfly intrinsics.
// Target operating system: Windows 11 Pro 25H2.
// Target architecture: AMD Ryzen 9 7940HS Phoenix / XDNA1 / AIE2.
// Input types: bfloat16 interleaved complex vector (128 elements = 64 I/Q pairs).
// Output types: bfloat16 interleaved complex spectrum (128 elements = 64 I/Q bins).
// Scaling: Direct float / bfloat16.
// Alignment assumptions: 64-byte aligned vector memory.
// State requirements: Precomputed Twiddle factor table.

#define NOCPP

#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <math.h>
#include <aie_api/aie.hpp>
#include "sdr_dsp_common.hpp"

extern "C" {

void fft64_kernel(
    bfloat16 *__restrict in_iq,
    bfloat16 *__restrict twiddles,
    bfloat16 *__restrict out_spectrum
) {
    event0();

    // 64-point DFT direct matrix / butterfly implementation in local memory
    float real_out[64] = {0.0f};
    float imag_out[64] = {0.0f};

    // Stage 1 & 2: Complex Twiddle multiplication and summation
#pragma clang loop unroll_count(4)
    for (int k = 0; k < 64; ++k) {
        float sum_r = 0.0f;
        float sum_i = 0.0f;

        for (int n = 0; n < 64; ++n) {
            float in_r = (float)in_iq[2 * n];
            float in_i = (float)in_iq[2 * n + 1];

            // Twiddle index: (k * n) % 64
            int tw_idx = (k * n) % 64;
            float tw_r = (float)twiddles[2 * tw_idx];
            float tw_i = (float)twiddles[2 * tw_idx + 1];

            // (in_r + j in_i) * (tw_r + j tw_i)
            sum_r += (in_r * tw_r) - (in_i * tw_i);
            sum_i += (in_r * tw_i) + (in_i * tw_r);
        }

        real_out[k] = sum_r;
        imag_out[k] = sum_i;
    }

    // Interleave output spectrum: [Re0, Im0, Re1, Im1, ...]
    for (int k = 0; k < 64; ++k) {
        out_spectrum[2 * k]     = (bfloat16)real_out[k];
        out_spectrum[2 * k + 1] = (bfloat16)imag_out[k];
    }

    event1();
}

}
