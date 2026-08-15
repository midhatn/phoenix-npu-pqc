// Purpose: Bit-accurate fused Digital Down-Converter (DDC) kernel for AIE2
//          (Milestone 21). Three stages fused in one kernel on one AIE2 core:
//            Stage 1 (mix): complex NCO at f_c = -f_s/8 shifts a tone at
//                           +f_s/8 down to DC. LUT is 8 samples,
//                           cordic-free (Analog Devices MT-085).
//            Stage 2 (LPF): 16-tap real-tap Kaiser-window low-pass filter
//                           applied to each of I and Q. Cutoff pi/M = pi/4,
//                           unity DC gain, reuses the M20 prototype exactly.
//            Stage 3 (decim): keep every M=4-th filtered output.
//          Only computes filter outputs at the decimated rate, so the fused
//          kernel does 4x less arithmetic than filter-then-decimate.
// Target operating system: Windows 11 Pro 25H2.
// Target architecture: AMD Ryzen 9 7940HS Phoenix / XDNA1 / AIE2.
// Input types: bfloat16 I/Q interleaved input (4096 samples = 2048 complex
//              pairs).
// Output types: bfloat16 I/Q interleaved output (4096 samples). Only the
//               first 1024 entries (512 complex pairs at f_s/M) are
//               populated; the remaining slots are zero, so the output
//               buffer has the same shape as prior milestones (M8/M19/M20)
//               for XRTTensor plumbing consistency.
// Scaling: Direct bfloat16 operand load, float32 multiply-accumulate,
//          single bfloat16 truncation on final store, matching M8/M19/M20.
//
// Complex multiply identity (M6, M19, M20 reference):
//   (I_x + j Q_x) * (I_lo + j Q_lo) = (I_x*I_lo - Q_x*Q_lo)
//                                   + j*(I_x*Q_lo + Q_x*I_lo).
// (Oppenheim & Schafer, DTSP 3e, Section 2.2; NIST DLMF Section 1.9.)
//
// LO derivation (Analog Devices MT-085 "Fundamentals of DDS", Table 1;
//                Harris 2004 Section 8.3 "The Digital Down-Converter"):
//   For downconversion, LO = e^{-j 2 pi n / 8}, i.e. cos_lo[n] = cos(-2 pi n/8),
//   sin_lo[n] = sin(-2 pi n/8). Only 8 unique LO samples exist because the
//   sequence repeats every 8 input samples (f_c = f_s/8). The LO LUT is
//   baked as constexpr floats and indexed by (n & 7). This is the standard
//   "cordic-free" quarter-wave DDS trick.
//
// Real-tap FIR + decim (Harris 2004 Section 8.3, Vaidyanathan 1993
// Section 4.3 "Efficient Structures"): rather than run the 16-tap FIR at
// input rate and drop 3/4 of the outputs, we compute the FIR only at the
// M=4 decimated rate. The shift register still ingests 4 samples per output.
// For each output m in [0, N_out):
//   y[m] = sum_{k=0..15} h[k] * y_mix[m*M - k]
// with h[15-0] pairing with the newest y_mix sample.
//
// Alignment assumptions: 64-byte aligned vector memory (IRON XRTTensor).
// State requirements: Stateless across kernel invocations. Local state on
//                     stack: hd[16], lo_cos[8], lo_sin[8], hist_i[16],
//                     hist_q[16]. Total ~ 224 bytes float32 on stack,
//                     well inside the 16 KB stack_size override.
// Error handling: Zero-history warmup (first N_taps/M - 1 outputs are
//                 transient responses to an implicit zero mixed-signal
//                 history), matching M8 / M19 / M20 pipeline convention.
//
// Program-memory sizing note: this kernel follows M20's revision-2
// lesson (docs/M20_DESIGN.md section 8.1). Dot products are expressed as
// compact for-loops with no #pragma clang loop unroll_count hint, keeping
// the program image safely below the AIE2 core's 16 KB program memory even
// with the LO LUT and Kaiser LPF taps baked in as constexpr floats.
//
// Fused-pipeline pattern reference: tests/m8_pipeline/pipeline_kernel.cc
// (mix + FIR + power) and tests/m20_polyphase/polyphase_kernel.cc
// (decim + interp).
// Kaiser prototype LPF reference: docs/M20_DESIGN.md section 3.1.
// Stack-size override reference: docs/M19_DESIGN.md section 5.3.
//
// External references:
//   * Harris, "Multirate Signal Processing for Communication Systems"
//     Prentice Hall 2004, Section 8.3 (DDC).
//     https://ieeexplore.ieee.org/book/9448967
//   * Analog Devices MT-085 "Fundamentals of Direct Digital Synthesis":
//     https://www.analog.com/media/en/training-seminars/tutorials/MT-085.pdf
//   * GNU Radio Frequency Xlating FIR Filter:
//     https://wiki.gnuradio.org/index.php/Frequency_Xlating_FIR_Filter
//   * Kaiser 1974 "Nonrecursive digital filter design using I_0-sinh":
//     https://ieeexplore.ieee.org/document/1451724

#define NOCPP

#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <aie_api/aie.hpp>
#include "sdr_dsp_common.hpp"

extern "C" {

void ddc_kernel(
    bfloat16 *__restrict in_iq,
    bfloat16 *__restrict out_iq
) {
    event0();

    // Kaiser-window prototype LPF (beta = 6, cutoff pi/M = pi/4, unity DC
    // gain sum(h) ~ 1). Identical to the M20 decimator taps
    // (tests/m20_polyphase/polyphase_kernel.cc). Bfloat16-quantized values
    // so the host reference matches term-for-term.
    const float h[16] = {
        -0.000242f, -0.003281f, -0.009644f, -0.009216f,
        +0.018677f, +0.086426f, +0.175781f, +0.241211f,
        +0.241211f, +0.175781f, +0.086426f, +0.018677f,
        -0.009216f, -0.009644f, -0.003281f, -0.000242f
    };

    // LO look-up table for f_c = -f_s/8. Values are cos / sin of
    // -2 pi k / 8 for k = 0..7, bfloat16-quantized so the host reference
    // matches term-for-term. Standard "cordic-free" quarter-wave DDS
    // (Analog Devices MT-085 "Fundamentals of DDS", Table 1).
    const float lo_cos[8] = {
        +1.000000f,  +0.707031f,  +0.000000f,  -0.707031f,
        -1.000000f,  -0.707031f,  +0.000000f,  +0.707031f
    };
    const float lo_sin[8] = {
         0.000000f,  -0.707031f,  -1.000000f,  -0.707031f,
         0.000000f,  +0.707031f,  +1.000000f,  +0.707031f
    };

    // 16-slot shift register on the *mixed* stream. The three-stage
    // pipeline is fused into one iteration space: for each decimated
    // output m in [0, 512), we ingest 4 fresh input pairs, mix each one,
    // append the mixed pair to the shift register, then run the 16-tap
    // dot product once. This is the M8 fused-pipeline pattern applied
    // to a DDC (Harris 2004 Section 8.3).
    float hist_i[16] = {0.0f};
    float hist_q[16] = {0.0f};

    const int N_out = 512;   // 2048 / M with M = 4
    const int M = 4;

    for (int m = 0; m < N_out; ++m) {
        // Shift the 16-slot window left by M and ingest M new samples
        // (mixed I/Q pairs). Newest slot after ingest is hist[15].
        for (int k = 0; k < 12; ++k) {
            hist_i[k] = hist_i[k + 4];
            hist_q[k] = hist_q[k + 4];
        }
        for (int j = 0; j < 4; ++j) {
            int n_in = m * M + j;                    // input-rate index
            float ix = (float)in_iq[2 * n_in    ];
            float qx = (float)in_iq[2 * n_in + 1];
            float cos_lo = lo_cos[n_in & 7];         // 8-sample LO LUT
            float sin_lo = lo_sin[n_in & 7];
            // Complex multiply (Ix + jQx) * (cos_lo + j sin_lo)
            //   with cos_lo, sin_lo already carrying the negative-frequency
            //   sign of the DDC LO.
            hist_i[12 + j] = ix * cos_lo - qx * sin_lo;
            hist_q[12 + j] = ix * sin_lo + qx * cos_lo;
        }

        // 16-tap real-tap FIR dot product on the mixed shift register.
        // Newest sample hist[15] pairs with h[0]; oldest hist[0] pairs
        // with h[15]. This is decimate-by-M "for free" because we only
        // execute the dot product once per M input samples.
        float Iacc = 0.0f;
        float Qacc = 0.0f;
        for (int k = 0; k < 16; ++k) {
            Iacc += hist_i[15 - k] * h[k];
            Qacc += hist_q[15 - k] * h[k];
        }

        // Single bfloat16 truncation on final store, matching M8/M19/M20.
        out_iq[2 * m    ] = (bfloat16)Iacc;
        out_iq[2 * m + 1] = (bfloat16)Qacc;
    }

    // Zero-fill the unused tail of the output buffer so the XRT plumbing
    // sees a fully-defined 4096-element output. First 1024 slots hold
    // the 512 decimated complex pairs; the rest is guaranteed zero.
    for (int i = 2 * N_out; i < 4096; ++i) {
        out_iq[i] = (bfloat16)0.0f;
    }

    event1();
}

}
