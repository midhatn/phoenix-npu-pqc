// Purpose: Bit-accurate sliding-window FIR filter for AIE2 using scalar inner loop or aligned sliding register.
// Target operating system: Windows 11 Pro 25H2.
// Target architecture: AMD Ryzen 9 7940HS Phoenix / XDNA1 / AIE2.
// Input types: bfloat16 input vector (4096 samples).
// Output types: bfloat16 output vector (4096 samples).
// Scaling: Direct bfloat16 arithmetic.
// Alignment assumptions: 64-byte aligned vector memory.
// State requirements: 8-tap symmetric FIR filter kernel.
// Error handling: Strict vector loop bounds.

#define NOCPP

#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <aie_api/aie.hpp>
#include "sdr_dsp_common.hpp"

extern "C" {

void fir_filter_kernel(
    bfloat16 *__restrict in,
    bfloat16 *__restrict out
) {
    event0();

    // 8-tap filter coefficients
    const float c0 = 0.05f;
    const float c1 = 0.10f;
    const float c2 = 0.20f;
    const float c3 = 0.30f;
    const float c4 = 0.30f;
    const float c5 = 0.20f;
    const float c6 = 0.10f;
    const float c7 = 0.05f;

#pragma clang loop unroll_count(8)
    for (int i = 0; i < 4088; ++i) {
        float sum = 0.0f;
        sum += (float)in[i + 0] * c0;
        sum += (float)in[i + 1] * c1;
        sum += (float)in[i + 2] * c2;
        sum += (float)in[i + 3] * c3;
        sum += (float)in[i + 4] * c4;
        sum += (float)in[i + 5] * c5;
        sum += (float)in[i + 6] * c6;
        sum += (float)in[i + 7] * c7;
        out[i] = (bfloat16)sum;
    }

    // Boundary elements
    for (int i = 4088; i < 4096; ++i) {
        float sum = 0.0f;
        for (int k = 0; k < 8; ++k) {
            if (i + k < 4096) {
                float coeff = (k==0?c0: k==1?c1: k==2?c2: k==3?c3: k==4?c4: k==5?c5: k==6?c6: c7);
                sum += (float)in[i + k] * coeff;
            }
        }
        out[i] = (bfloat16)sum;
    }

    event1();
}

}
