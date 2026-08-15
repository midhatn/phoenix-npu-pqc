// Purpose: Bit-accurate Barker-13 matched-filter correlator kernel for AIE2
//          (Milestone 24). Slides a length-13 real preamble against an
//          interleaved bfloat16 complex I/Q input vector (4096 bf16 =
//          2048 complex pairs), producing an interleaved bfloat16 I/Q
//          output vector of the same shape carrying the correlator's
//          complex output stream y[n] = sum_k s[k] * x[n+k].
// Target operating system: Windows 11 Pro 25H2.
// Target architecture: AMD Ryzen 9 7940HS Phoenix / XDNA1 / AIE2.
// Input types: bfloat16 I/Q interleaved input (4096 samples = 2048 complex pairs).
// Output types: bfloat16 I/Q interleaved output (4096 samples = 2048 complex pairs).
// Scaling: Direct bfloat16 operand load, float32 multiply-accumulate,
//          single bfloat16 truncation on store, matching M5/M6/M19.
// Preamble: length-13 Barker sequence
//   s = (+1, +1, +1, +1, +1, -1, -1, +1, +1, -1, +1, -1, +1)
// which has aperiodic autocorrelation peak 13 and |c_v| <= 1 for all
// nonzero shifts (peak-to-sidelobe ratio 13:1 = 22.3 dB power).
//   Wikipedia "Barker code": https://en.wikipedia.org/wiki/Barker_code
//   Barker 1953 original paper: https://ieeexplore.ieee.org/document/6773685
//   IEEE 802.11 DSSS: https://standards.ieee.org/ieee/802.11/7028/
//
// Correlator equation:
//   y[n] = sum_{k=0..L-1} conj(s[k]) * x[n+k]
// Because s in {-1, +1} is real, conj(s) = s, and the complex correlator
// splits into two independent real FIRs on I and Q:
//   Iy[n] = sum_k s[k] * Ix[n+k]
//   Qy[n] = sum_k s[k] * Qx[n+k]
//   Reference: Proakis & Salehi, Digital Communications 5e sec 5.1.5;
//   GNU Radio corr_est_cc:
//     https://www.gnuradio.org/doc/doxygen-v3.7.10/corr__est__cc_8h_source.html
//
// Correlator-as-reverse-FIR identity (Oppenheim & Schafer DTSP 3e sec 2.6.2):
//   A sliding correlator with taps s[k] and forward indexing x[n+k]
//   produces the same output stream, with fixed group delay L-1, as a
//   CAUSAL FIR filter with reversed taps h[k] = s[L-1-k] applied to the
//   same input via the standard past-history convolution
//     y[i] = sum_{k=0..L-1} h[k] * x[i-k].
//   The kernel therefore reuses the M8/M19 shift-and-ingest schedule
//   verbatim, with taps stored in REVERSED Barker-13 order:
//     s_rev = (+1, -1, +1, -1, +1, +1, -1, -1, +1, +1, +1, +1, +1)
//   ("newest sample hist[L-1] pairs with s_rev[0]").
//
// Design note: M22-style hand-unrolled dot product.
//
// The 13-term Barker-13 FIR is written as a single 13-term expression
// with literal `hist_i[N]` indices (matching M22's `xi[3] * hi[k+8]`
// literal-index MAC discipline). The 12-slot shift-and-ingest is
// likewise 12 explicit statements. No `#pragma clang loop unroll_count`
// hint is used; the outer sample loop is 2048 iterations. This shape
// keeps the program image small and mirrors the M19/M22/M23 template.
// See docs/M24_DESIGN.md section 5.3 for the bring-up incident that
// motivated the driver's `@iron.jit` decorator (unrelated to the
// kernel loop shape but tied together in project history).
//
// Alignment assumptions: 64-byte aligned vector memory (IRON XRTTensor).
// State requirements: Stateless across kernel invocations; internal
//                     state is two 13-float shift registers (hist_i, hist_q).
// Error handling: Zero-history warmup (first L-1 outputs are transient),
//                 matching the M8/M19 convention. The host reference
//                 walks the same schedule and produces term-for-term
//                 matching output through the transient.

#define NOCPP

#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <aie_api/aie.hpp>
#include "sdr_dsp_common.hpp"

extern "C" {

void correlator_kernel(
    bfloat16 *__restrict in_iq,
    bfloat16 *__restrict out_iq
) {
    event0();

    // Barker-13 in REVERSED order (FIR convention: hist[L-1] pairs with s_rev[0]).
    // Original s = (+1,+1,+1,+1,+1,-1,-1,+1,+1,-1,+1,-1,+1)
    // Reversed  = (+1,-1,+1,-1,+1,+1,-1,-1,+1,+1,+1,+1,+1)
    // All values are exactly representable in bfloat16 and float32 (no
    // quantization step needed, unlike M23's Kaiser prototype).
    const int L = 13;
    const float s_rev[13] = {
        +1.0f, -1.0f, +1.0f, -1.0f, +1.0f, +1.0f, -1.0f,
        -1.0f, +1.0f, +1.0f, +1.0f, +1.0f, +1.0f
    };

    // 13-slot shift registers. Zero-history warmup: for i < L-1 some slots
    // are still zero, matching the host reference in test_correlator_m24.py
    // which walks the identical schedule.
    float hist_i[13] = {0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f,
                        0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f};
    float hist_q[13] = {0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f,
                        0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f};

    // Barker-13 reversed taps as literal constants (mirrors the s_rev
    // array above; kept separate so Peano lowers each MAC term against a
    // compile-time constant instead of an indexed load).
    // s_rev = (+1,-1,+1,-1,+1,+1,-1,-1,+1,+1,+1,+1,+1)
    const float t0  = +1.0f;
    const float t1  = -1.0f;
    const float t2  = +1.0f;
    const float t3  = -1.0f;
    const float t4  = +1.0f;
    const float t5  = +1.0f;
    const float t6  = -1.0f;
    const float t7  = -1.0f;
    const float t8  = +1.0f;
    const float t9  = +1.0f;
    const float t10 = +1.0f;
    const float t11 = +1.0f;
    const float t12 = +1.0f;

    const int N_PAIRS = 2048;

    for (int i = 0; i < N_PAIRS; ++i) {
        float ii = (float)in_iq[2 * i    ];
        float qq = (float)in_iq[2 * i + 1];

        // M8/M22-style explicit shift-and-ingest: 12 literal statements
        // instead of a nested loop. Newest sample lands at hist[12].
        hist_i[0]  = hist_i[1];
        hist_i[1]  = hist_i[2];
        hist_i[2]  = hist_i[3];
        hist_i[3]  = hist_i[4];
        hist_i[4]  = hist_i[5];
        hist_i[5]  = hist_i[6];
        hist_i[6]  = hist_i[7];
        hist_i[7]  = hist_i[8];
        hist_i[8]  = hist_i[9];
        hist_i[9]  = hist_i[10];
        hist_i[10] = hist_i[11];
        hist_i[11] = hist_i[12];
        hist_i[12] = ii;

        hist_q[0]  = hist_q[1];
        hist_q[1]  = hist_q[2];
        hist_q[2]  = hist_q[3];
        hist_q[3]  = hist_q[4];
        hist_q[4]  = hist_q[5];
        hist_q[5]  = hist_q[6];
        hist_q[6]  = hist_q[7];
        hist_q[7]  = hist_q[8];
        hist_q[8]  = hist_q[9];
        hist_q[9]  = hist_q[10];
        hist_q[10] = hist_q[11];
        hist_q[11] = hist_q[12];
        hist_q[12] = qq;

        // Textbook direct-form FIR, fully unrolled:
        // y[i] = sum_{k=0..12} s_rev[k] * x[i-k]
        //      = t0*hist[12] + t1*hist[11] + ... + t12*hist[0]
        // Newest sample hist[12] pairs with s_rev[0]; oldest hist[0]
        // pairs with s_rev[12]. Identical to the sliding correlator
        // y[n] = sum s[k]*x[n+k] evaluated at n = i - 12 (group delay).
        float Iacc = hist_i[12] * t0
                   + hist_i[11] * t1
                   + hist_i[10] * t2
                   + hist_i[9]  * t3
                   + hist_i[8]  * t4
                   + hist_i[7]  * t5
                   + hist_i[6]  * t6
                   + hist_i[5]  * t7
                   + hist_i[4]  * t8
                   + hist_i[3]  * t9
                   + hist_i[2]  * t10
                   + hist_i[1]  * t11
                   + hist_i[0]  * t12;

        float Qacc = hist_q[12] * t0
                   + hist_q[11] * t1
                   + hist_q[10] * t2
                   + hist_q[9]  * t3
                   + hist_q[8]  * t4
                   + hist_q[7]  * t5
                   + hist_q[6]  * t6
                   + hist_q[5]  * t7
                   + hist_q[4]  * t8
                   + hist_q[3]  * t9
                   + hist_q[2]  * t10
                   + hist_q[1]  * t11
                   + hist_q[0]  * t12;

        out_iq[2 * i    ] = (bfloat16)Iacc;
        out_iq[2 * i + 1] = (bfloat16)Qacc;
    }

    event1();
}

}
