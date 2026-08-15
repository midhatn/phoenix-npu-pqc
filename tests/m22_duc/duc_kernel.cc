// Purpose: Bit-accurate fused Digital Up-Converter (DUC) kernel for AIE2
//          (Milestone 22). The mathematical symmetric of M21 DDC:
//            Stage 1 (interp): 512 complex I/Q baseband -> 2048 complex I/Q
//                              via zero-stuff-by-L + 16-tap Kaiser LPF,
//                              expressed as an L=4 polyphase filter with
//                              taps scaled by L (scipy resample_poly).
//            Stage 2 (mix):    complex NCO at f_c = +f_s/8 shifts the
//                              interpolated baseband up to +f_s/8. LUT is
//                              8 samples, cordic-free (Analog Devices MT-085).
//          Signal chain: x_bb[m] @ f_s/L -> interp(L) -> mix(+f_s/8)
//                        -> x_if[n] @ f_s.
// Target operating system: Windows 11 Pro 25H2.
// Target architecture: AMD Ryzen 9 7940HS Phoenix / XDNA1 / AIE2.
// Input types: bfloat16 I/Q interleaved baseband (4096 slots; first 1024
//              slots = 512 complex baseband pairs, rest zero).
// Output types: bfloat16 I/Q interleaved intermediate-frequency
//               (4096 slots = 2048 complex pairs at f_s, fully populated).
// Scaling: Direct bfloat16 operand load, float32 multiply-accumulate,
//          single bfloat16 truncation on final store, matching M8/M20/M21.
//
// Polyphase interpolation (Vaidyanathan 1993 chapter 4 Eq. 4.3.13,
//   Harris 2004 chapter 7 Fig. 7.16):
//   For each input baseband sample m in [0, 512) produce L=4 output samples
//   using the L polyphase branches of the same 16-tap Kaiser prototype:
//       y_bb[m*L + k] = sum_{r=0..3} hi[r*L + k] * x_bb[m - r],  k = 0..3
//   The 4-slot shift register holds the last 4 baseband pairs and the
//   4 polyphase branches select 4-tap subsets of the 16-tap prototype.
//
// Interpolator tap scaling (scipy.signal.resample_poly `taps *= up`
//   convention; also GNU Radio pfb docs):
//   hi = h_prototype * L. This compensates the 1/L amplitude loss from
//   zero-insertion upsampling so unity DC gain end-to-end.
//
// Upconversion mix (Harris 2004 chapter 8, section 8.4 "The Digital
//   Up-Converter"; GNU Radio Frequency Xlating FIR Filter with negative
//   decimation):
//   x_if[n] = y_bb[n] * e^{+j 2 pi f_c n / f_s}
//           = y_bb[n] * (cos_lo[n] + j sin_lo[n])
//   with cos_lo[n] = cos(+2 pi f_c n / f_s), sin_lo[n] = sin(+2 pi f_c n / f_s).
//
// Complex multiply identity (Oppenheim & Schafer 3e section 2.2;
//   NIST DLMF section 1.9):
//   (I_y + j Q_y)(cos_lo + j sin_lo)
//        = (I_y cos_lo - Q_y sin_lo) + j (I_y sin_lo + Q_y cos_lo).
//
// LO derivation (Analog Devices MT-085 "Fundamentals of DDS", Table 1):
//   At f_c = +f_s/8 the LO repeats every 8 output samples so only 8 unique
//   (cos, sin) pairs are stored. This is the M21 LO with sin negated
//   (positive-frequency mix vs M21's negative-frequency mix).
//
// Alignment assumptions: 64-byte aligned vector memory (IRON XRTTensor).
// State requirements: Stateless across kernel invocations. Local state on
//                     stack: hi[16], lo_cos[8], lo_sin[8], xi[4], xq[4].
//                     Well inside the 16 KB stack_size override.
// Error handling: Zero-history warmup (first N_out/L - 1 output samples
//                 are transient responses to an implicit zero baseband
//                 history), matching M8 / M20 / M21 pipeline convention.
//
// Program-memory sizing note: this kernel follows M20's revision-2
// lesson (docs/M20_DESIGN.md section 8.1) and M21 (docs/M21_DESIGN.md
// section 4.2): dot products are compact for-loops with no
// #pragma clang loop unroll_count hint, keeping the program image safely
// below the AIE2 core's 16 KB program memory even with the LO LUT and
// Kaiser*L LPF taps baked in as constexpr floats.
//
// Fused-pipeline pattern reference: tests/m8_pipeline/pipeline_kernel.cc
//   (mix + FIR + power), tests/m20_polyphase/polyphase_kernel.cc
//   (decim + interp), tests/m21_ddc/ddc_kernel.cc (mix + LPF + decim).
// Kaiser*L prototype LPF reference: docs/M20_DESIGN.md section 3.1,
//   stage-2 interpolator taps `hi`.
// Stack-size override reference: docs/M19_DESIGN.md section 5.3.
//
// External references:
//   * Harris, "Multirate Signal Processing for Communication Systems",
//     Prentice Hall 2004, section 8.4 (DUC).
//     https://ieeexplore.ieee.org/book/9448967
//   * Vaidyanathan, "Multirate Systems and Filter Banks", Prentice Hall
//     1993, chapter 4.
//     https://dl.acm.org/doi/10.5555/151045
//   * Analog Devices MT-085 "Fundamentals of Direct Digital Synthesis":
//     https://www.analog.com/media/en/training-seminars/tutorials/MT-085.pdf
//   * GNU Radio Frequency Xlating FIR Filter (with negative decim = interp):
//     https://wiki.gnuradio.org/index.php/Frequency_Xlating_FIR_Filter
//   * scipy.signal.resample_poly (interpolator tap scaling convention):
//     https://docs.scipy.org/doc/scipy/reference/generated/scipy.signal.resample_poly.html
//   * Kaiser 1974 "Nonrecursive digital filter design using I_0-sinh":
//     https://ieeexplore.ieee.org/document/1451724

#define NOCPP

#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <aie_api/aie.hpp>
#include "sdr_dsp_common.hpp"

extern "C" {

void duc_kernel(
    bfloat16 *__restrict in_iq,
    bfloat16 *__restrict out_iq
) {
    event0();

    // Kaiser-window prototype LPF (beta = 6, cutoff pi/L = pi/4) scaled
    // by L=4 for interpolation (scipy.signal.resample_poly convention).
    // sum(hi) ~ 4.00 -> unity DC gain end-to-end after the 1/L
    // amplitude drop from zero-stuff upsampling. Identical to the M20
    // stage-2 interp taps (tests/m20_polyphase/polyphase_kernel.cc).
    // Bfloat16-quantized values so the host reference matches
    // term-for-term.
    const float hi[16] = {
        -0.000969f, -0.013123f, -0.038574f, -0.036865f,
        +0.074707f, +0.345703f, +0.703125f, +0.964844f,
        +0.964844f, +0.703125f, +0.345703f, +0.074707f,
        -0.036865f, -0.038574f, -0.013123f, -0.000969f
    };

    // LO look-up table for f_c = +f_s/8. Values are cos / sin of
    // +2 pi k / 8 for k = 0..7, bfloat16-quantized so the host reference
    // matches term-for-term. Standard "cordic-free" quarter-wave DDS
    // (Analog Devices MT-085 "Fundamentals of DDS", Table 1).
    //
    // This is the M21 DDC LO with sin_lo negated (positive-frequency
    // upconvert versus M21's negative-frequency downconvert).
    const float lo_cos[8] = {
        +1.000000f,  +0.707031f,  +0.000000f,  -0.707031f,
        -1.000000f,  -0.707031f,  +0.000000f,  +0.707031f
    };
    const float lo_sin[8] = {
         0.000000f,  +0.707031f,  +1.000000f,  +0.707031f,
         0.000000f,  -0.707031f,  -1.000000f,  -0.707031f
    };

    // 4-slot shift register on the baseband stream. Matches the M20
    // stage-2 polyphase-interp schedule: one shift-and-ingest per input
    // baseband pair, then L=4 output samples produced by 4 different
    // 4-tap subsets of the same 16-tap prototype (Vaidyanathan Eq.
    // 4.3.13, commutator model).
    float xi[4] = {0.0f, 0.0f, 0.0f, 0.0f};
    float xq[4] = {0.0f, 0.0f, 0.0f, 0.0f};

    const int N_bb = 512;   // baseband input pairs (first 1024 input slots)
    const int L = 4;        // interpolation factor

    for (int m = 0; m < N_bb; ++m) {
        // Shift-1-and-ingest one baseband pair.
        xi[0] = xi[1]; xi[1] = xi[2]; xi[2] = xi[3];
        xq[0] = xq[1]; xq[1] = xq[2]; xq[2] = xq[3];
        xi[3] = (float)in_iq[2 * m    ];
        xq[3] = (float)in_iq[2 * m + 1];

        // Four polyphase output phases (L=4). Each phase is a 4-tap
        // dot product on the same 4-slot shift register with a
        // different tap subset (k, k+4, k+8, k+12). Newest xi[3] pairs
        // with hi[k]; oldest xi[0] pairs with hi[k+12].
        for (int k = 0; k < 4; ++k) {
            float Iacc = xi[3] * hi[k    ]
                       + xi[2] * hi[k + 4]
                       + xi[1] * hi[k + 8]
                       + xi[0] * hi[k +12];
            float Qacc = xq[3] * hi[k    ]
                       + xq[2] * hi[k + 4]
                       + xq[1] * hi[k + 8]
                       + xq[0] * hi[k +12];

            // Stage 2: complex multiply by NCO(+f_s/8) at the output
            // (interpolated) rate. LO indexed by (n_out & 7).
            int n_out = m * L + k;
            float cos_lo = lo_cos[n_out & 7];
            float sin_lo = lo_sin[n_out & 7];
            float I_if = Iacc * cos_lo - Qacc * sin_lo;
            float Q_if = Iacc * sin_lo + Qacc * cos_lo;

            // Single bfloat16 truncation on final store (matches
            // M8/M20/M21). Output buffer is 2048 pairs wide, fully
            // populated by this loop; no zero-tail needed.
            out_iq[2 * n_out    ] = (bfloat16)I_if;
            out_iq[2 * n_out + 1] = (bfloat16)Q_if;
        }
    }

    event1();
}

}
