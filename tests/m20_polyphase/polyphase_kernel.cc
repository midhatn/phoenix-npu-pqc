// Purpose: Bit-accurate fused polyphase resampler kernel for AIE2 (Milestone 20).
//          Two stages in one kernel:
//            Stage 1 (decim, M=4):    2048 complex I/Q -> 512 complex I/Q.
//            Stage 2 (interp, L=4):    512 complex I/Q -> 2048 complex I/Q.
//          Both stages share one 16-tap Kaiser-window prototype low-pass filter
//          decomposed into M = L = 4 polyphase branches of 4 taps each.
// Target operating system: Windows 11 Pro 25H2.
// Target architecture: AMD Ryzen 9 7940HS Phoenix / XDNA1 / AIE2.
// Input types: bfloat16 I/Q interleaved input (4096 samples = 2048 complex pairs).
// Output types: bfloat16 I/Q interleaved output (4096 samples = 2048 complex pairs).
// Scaling: Direct bfloat16 operand load, float32 multiply-accumulate,
//          bfloat16 truncation on stage-2 store only. Stage-1 intermediate
//          stays in float32 in local memory to avoid double bfloat16 rounding.
// Alignment assumptions: 64-byte aligned vector memory (IRON XRTTensor).
// State requirements: Stateless across kernel invocations. Local state on
//                     stack: hd[16], hi[16], hist_i[16], hist_q[16],
//                     inter_i[512], inter_q[512], xi[4], xq[4]
//                     ~= 4288 bytes float32 stack.
// Error handling: Zero-history warmup (first N/M - 1 outputs of decim and
//                 first N/L - 1 outputs of interp are transient responses to
//                 an implicit zero history), matching the M8 pipeline
//                 kernel convention (tests/m8_pipeline/pipeline_kernel.cc).
//
// Program-memory sizing note: an earlier version of this kernel used hand-flat
// 16-term dot products with #pragma clang loop unroll_count(4). Total code size
// overflowed the AIE2 program memory (aiecc error "Overflow of program memory"
// / XAIE_INVALID_ELF). This revision keeps the shift-registers and stage
// scheduling identical (so the reference is unchanged) but expresses each
// dot product as a small loop and drops the outer unroll pragmas, matching
// M8's compact style (tests/m8_pipeline/pipeline_kernel.cc).
//
// Fused-pipeline pattern reference: tests/m8_pipeline/pipeline_kernel.cc.
// Polyphase decomposition reference: docs/M20_DESIGN.md sections 2 and 3.
// Kaiser prototype LPF reference: docs/M20_DESIGN.md section 3.1.
// Stack-size override reference: docs/M19_DESIGN.md section 5.3.
//
// Filter design and gain convention: adapted from scipy.signal.resample_poly
// (https://github.com/scipy/scipy/blob/main/scipy/signal/_signaltools.py)
// and GNU Radio pfb docs (https://www.gnuradio.org/doc/doxygen-3.7/page_pfb.html):
//   * decim taps: prototype h with sum(h) = 1 (unity DC gain).
//   * interp taps: prototype h scaled by L to compensate the 1/L amplitude
//     loss from zero-insertion upsampling.
// Combined end-to-end DC gain of decim -> interp is thus ~1.0, bit-comparable
// to scipy.signal.upfirdn on the same taps.

#define NOCPP

#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <aie_api/aie.hpp>
#include "sdr_dsp_common.hpp"

extern "C" {

void polyphase_kernel(
    bfloat16 *__restrict in_iq,
    bfloat16 *__restrict out_iq
) {
    event0();

    // Stage-1 decimator taps: 16-tap Kaiser-window prototype LPF
    // (beta=6, cutoff pi/M). Unity DC gain: sum(hd) = 0.999.
    // Bfloat16-quantized values so the host reference matches term-for-term.
    const float hd[16] = {
        -0.000242f, -0.003281f, -0.009644f, -0.009216f,
        +0.018677f, +0.086426f, +0.175781f, +0.241211f,
        +0.241211f, +0.175781f, +0.086426f, +0.018677f,
        -0.009216f, -0.009644f, -0.003281f, -0.000242f
    };

    // Stage-2 interpolator taps: same prototype scaled by L=4
    // (scipy.signal.resample_poly `taps *= up` convention;
    //  compensates the 1/L amplitude loss from zero-insertion upsampling).
    // DC gain: sum(hi) ~ 4.00.
    const float hi[16] = {
        -0.000969f, -0.013123f, -0.038574f, -0.036865f,
        +0.074707f, +0.345703f, +0.703125f, +0.964844f,
        +0.964844f, +0.703125f, +0.345703f, +0.074707f,
        -0.036865f, -0.038574f, -0.013123f, -0.000969f
    };

    // ================================================================
    // STAGE 1: polyphase decimator (M=4)
    // ================================================================
    // 16-tap FIR walked as a direct-form dot product with a 16-slot
    // shift-and-ingest register. For each decim output m in [0, 511]:
    //   y[m] = sum_{k=0..15} hd[k] * x[m*4 - k]
    // Newest hist[15] pairs with hd[0]; oldest hist[0] pairs with hd[15].
    // (Textbook direct-form; docs/M20_DESIGN.md section 5.1.)
    float hist_i[16] = {0.0f};
    float hist_q[16] = {0.0f};

    // Intermediate float32 buffer between decim and interp. Kept in
    // float rather than bfloat16 so a single bfloat16 rounding happens
    // on the stage-2 store; matches the reference contract exactly.
    float inter_i[512];
    float inter_q[512];

    for (int m = 0; m < 512; ++m) {
        // Shift the 16-slot window left by 4 and ingest 4 new samples.
        for (int k = 0; k < 12; ++k) {
            hist_i[k] = hist_i[k + 4];
            hist_q[k] = hist_q[k + 4];
        }
        for (int j = 0; j < 4; ++j) {
            hist_i[12 + j] = (float)in_iq[2 * (m * 4 + j)    ];
            hist_q[12 + j] = (float)in_iq[2 * (m * 4 + j) + 1];
        }

        // Direct-form 16-tap dot product.
        float Iacc = 0.0f;
        float Qacc = 0.0f;
        for (int k = 0; k < 16; ++k) {
            Iacc += hist_i[15 - k] * hd[k];
            Qacc += hist_q[15 - k] * hd[k];
        }

        inter_i[m] = Iacc;
        inter_q[m] = Qacc;
    }

    // ================================================================
    // STAGE 2: polyphase interpolator (L=4)
    // ================================================================
    // For each input m in [0, 511], produce L=4 output samples using
    // the L polyphase branches of the same 16-tap prototype:
    //   y[m*L + k] = sum_{r=0..3} hi[r*L + k] * x[m - r],  k = 0..3
    // (Vaidyanathan Eq. 4.3.13, commutator model.)
    // 4-slot shift register on the intermediate stream.
    float xi[4] = {0.0f, 0.0f, 0.0f, 0.0f};
    float xq[4] = {0.0f, 0.0f, 0.0f, 0.0f};

    for (int m = 0; m < 512; ++m) {
        // Shift and ingest one intermediate pair.
        xi[0] = xi[1]; xi[1] = xi[2]; xi[2] = xi[3]; xi[3] = inter_i[m];
        xq[0] = xq[1]; xq[1] = xq[2]; xq[2] = xq[3]; xq[3] = inter_q[m];

        // Four polyphase output phases, each a 4-tap dot product on the
        // same shift register with a different tap subset.
        // Newest xi[3] pairs with hi[k]; oldest xi[0] pairs with hi[k+12].
        for (int k = 0; k < 4; ++k) {
            float Iacc = xi[3] * hi[k    ]
                       + xi[2] * hi[k + 4]
                       + xi[1] * hi[k + 8]
                       + xi[0] * hi[k +12];
            float Qacc = xq[3] * hi[k    ]
                       + xq[2] * hi[k + 4]
                       + xq[1] * hi[k + 8]
                       + xq[0] * hi[k +12];
            out_iq[2 * (m * 4 + k)    ] = (bfloat16)Iacc;
            out_iq[2 * (m * 4 + k) + 1] = (bfloat16)Qacc;
        }
    }

    event1();
}

}
