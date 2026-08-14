// Purpose: Vectorized Power Meter / Energy Detector Kernel on AIE2.
// Target operating system: Windows 11 Pro 25H2.
// Target architecture: AMD Ryzen 9 7940HS Phoenix / XDNA1 / AIE2.
// Input types: bfloat16 interleaved I/Q input (4096 elements = 2048 complex pairs).
// Output types: bfloat16 real power output (2048 elements).
// Scaling: Direct float / bfloat16 magnitude squared: Power = I^2 + Q^2.
// Alignment assumptions: 64-byte aligned vector pointers.
// State requirements: Stateless vector magnitude squaring.
// Error handling: Strict loop bounds.

#define NOCPP

#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <aie_api/aie.hpp>
#include "sdr_dsp_common.hpp"

extern "C" {

void power_detector_kernel(
    bfloat16 *__restrict in_iq,
    bfloat16 *__restrict out_power
) {
    event0();

    // 4096 interleaved elements (2048 I/Q pairs) -> 2048 Power elements
#pragma clang loop unroll_count(8)
    for (int i = 0; i < 2048; ++i) {
        float i_sample = (float)in_iq[2 * i];
        float q_sample = (float)in_iq[2 * i + 1];

        float power = (i_sample * i_sample) + (q_sample * q_sample);
        out_power[i] = (bfloat16)power;
    }

    event1();
}

}
