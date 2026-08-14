// Purpose: Vectorized Complex Mixer / NCO Frequency Shifter Kernel on AIE2.
// Target operating system: Windows 11 Pro 25H2.
// Target architecture: AMD Ryzen 9 7940HS Phoenix / XDNA1 / AIE2.
// Input types: bfloat16 I/Q interleaved input (4096 samples = 2048 complex pairs).
// Output types: bfloat16 mixed I/Q interleaved output (4096 samples).
// Scaling: Direct float / bfloat16 complex multiplication:
//          I_out = I_in * cos - Q_in * sin
//          Q_out = I_in * sin + Q_in * cos
// Alignment assumptions: 64-byte aligned vector pointers.
// State requirements: Complex LO carrier vector.
// Error handling: Strict loop bounds.

#define NOCPP

#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <aie_api/aie.hpp>
#include "sdr_dsp_common.hpp"

extern "C" {

void complex_mixer_kernel(
    bfloat16 *__restrict in_iq,
    bfloat16 *__restrict lo_carrier,
    bfloat16 *__restrict out_iq
) {
    event0();

    // 4096 interleaved elements = 2048 complex I/Q samples
    // Process pairs of (I, Q)
#pragma clang loop unroll_count(8)
    for (int i = 0; i < 4096; i += 2) {
        float i_in = (float)in_iq[i];
        float q_in = (float)in_iq[i + 1];

        float cos_lo = (float)lo_carrier[i];
        float sin_lo = (float)lo_carrier[i + 1];

        // Complex multiplication: (I + jQ) * (cos + j sin)
        float i_out = (i_in * cos_lo) - (q_in * sin_lo);
        float q_out = (i_in * sin_lo) + (q_in * cos_lo);

        out_iq[i]     = (bfloat16)i_out;
        out_iq[i + 1] = (bfloat16)q_out;
    }

    event1();
}

}
