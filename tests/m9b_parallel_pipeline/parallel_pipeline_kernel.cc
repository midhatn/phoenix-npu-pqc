// Purpose: 4-Column Parallel Multi-Stage SDR Demodulator Pipeline Kernel (Mixer -> FIR -> Power).
// Target operating system: Windows 11 Pro 25H2.
// Target architecture: AMD Ryzen 9 7940HS Phoenix / XDNA1 / AIE2 (4 Columns).
// Processing mode: Streaming block-by-block with 8-sample history register on 512 I/Q pairs per core.

#define NOCPP

#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <aie_api/aie.hpp>
#include "sdr_dsp_common.hpp"

extern "C" {

void parallel_pipeline_kernel(
    bfloat16 *__restrict in_iq,
    bfloat16 *__restrict lo_carrier,
    bfloat16 *__restrict out_power
) {
    event0();

    // 8-tap Low-Pass Filter coefficients
    const float c0 = 0.05f;
    const float c1 = 0.10f;
    const float c2 = 0.20f;
    const float c3 = 0.30f;
    const float c4 = 0.30f;
    const float c5 = 0.20f;
    const float c6 = 0.10f;
    const float c7 = 0.05f;

    // Small register shift window for I and Q FIR history (8 floats each)
    float hist_i[8] = {0.0f};
    float hist_q[8] = {0.0f};

    // 1024 interleaved elements = 512 I/Q pairs per core
#pragma clang loop unroll_count(4)
    for (int i = 0; i < 512; ++i) {
        float i_in = (float)in_iq[2 * i];
        float q_in = (float)in_iq[2 * i + 1];

        float cos_lo = (float)lo_carrier[2 * i];
        float sin_lo = (float)lo_carrier[2 * i + 1];

        // 1. Complex Mixer
        float mixed_i = (i_in * cos_lo) - (q_in * sin_lo);
        float mixed_q = (i_in * sin_lo) + (q_in * cos_lo);

        // Shift history register
        hist_i[0] = hist_i[1]; hist_i[1] = hist_i[2]; hist_i[2] = hist_i[3]; hist_i[3] = hist_i[4];
        hist_i[4] = hist_i[5]; hist_i[5] = hist_i[6]; hist_i[6] = hist_i[7]; hist_i[7] = mixed_i;

        hist_q[0] = hist_q[1]; hist_q[1] = hist_q[2]; hist_q[2] = hist_q[3]; hist_q[3] = hist_q[4];
        hist_q[4] = hist_q[5]; hist_q[5] = hist_q[6]; hist_q[6] = hist_q[7]; hist_q[7] = mixed_q;

        // 2. FIR Filter
        float filt_i = hist_i[7] * c0 + hist_i[6] * c1 + hist_i[5] * c2 + hist_i[4] * c3 +
                       hist_i[3] * c4 + hist_i[2] * c5 + hist_i[1] * c6 + hist_i[0] * c7;

        float filt_q = hist_q[7] * c0 + hist_q[6] * c1 + hist_q[5] * c2 + hist_q[4] * c3 +
                       hist_q[3] * c4 + hist_q[2] * c5 + hist_q[1] * c6 + hist_q[0] * c7;

        // 3. Power / Energy calculation
        float power = (filt_i * filt_i) + (filt_q * filt_q);
        out_power[i] = (bfloat16)power;
    }

    event1();
}

}
