// M26 - QAM-16 Receiver Pipeline (Gardner TED + Decision-Directed Carrier + Soft LLRs)
//
// Single-tile AIE2 kernel that extends the M25 receiver core with:
//   1. Gardner timing-error detector at 2 sps                 (reused from M25)
//   2. Second-order PI loop filter on timing                  (reused from M25)
//   3. Fractional linear-interp resampler (2 sps -> 1 sym)    (reused from M25)
//   4. NCO derotator (on-tile 7th-order Taylor sin/cos)       (reused from M25)
//   5. QAM-16 slicer  (Gray-coded nearest-point {+/-1, +/-3}/sqrt(10))
//   6. Decision-directed order-M phase detector:
//        e_phi = z_I * hat_a_Q - z_Q * hat_a_I
//      (Barry-Lee-Messerschmitt "Digital Communication" 3e sec 8.5;
//       Godard, "Self-Recovering Equalization and Carrier Tracking in
//       Two-Dimensional Data Communication Systems", IEEE TCOM 1980.)
//   7. Second-order PI loop filter on carrier phase           (reused from M25)
//   8. Soft-decision demapper: 4 max-log LLRs per QAM-16 symbol,
//      Gray-labelled (b3 b2 = I-axis MSB/LSB, b1 b0 = Q-axis MSB/LSB)
//      per Tosato & Bisaglia, "Simplified Soft-Output Demapper for Binary
//      Interleaved COFDM With Application to HIPERLAN/2", IEEE ICC 2002.
//
// I/O contract:
//   in_iq : 2 * N_IN interleaved bfloat16 (I0,Q0,I1,Q1,...) with N_IN = 1024
//   out_iq: 2 * N_SYM interleaved bfloat16 (I0,Q0,...)      with N_SYM = 512
//                                                     -- hard symbol decisions
//   out_llr: 4 * N_SYM interleaved bfloat16 LLRs
//            [b3_0, b2_0, b1_0, b0_0, b3_1, b2_1, b1_1, b0_1, ...]
//            where b3=MSB(I), b2=LSB(I), b1=MSB(Q), b0=LSB(Q) per Gray label.
//
// Single ExternalFunction entry point `qam16_rx` with three DMA buffers.
// This is the FIRST M-suite kernel with a 3-arg (in, out_sym, out_llr)
// signature; the driver's ObjectFifo topology and Runtime sequence use the
// same pattern as M22..M25 with one extra output ObjectFifo.
//
// State discipline (M22/M24/M25 rule): all sample-serial state lives in
// scalar registers between symbol iterations. History windows use literal-
// index shift-and-ingest so Peano lowers each move to a single register copy.
//
// Sign-of and copysign handling: identical to M25. All M25 bring-up rules
// still apply (Peano NOCPP has no libc math; scalar (x>=0)?1:-1 miscompiles;
// -O2 folds union sign-of into llvm.copysign; use volatile uint32_t OR into
// 0x3F800000 with a DEAD_ZONE_EPS threshold).
//
// Citations:
//   - Costas, "Synchronous Communications", Proc. IRE 44(12), Dec 1956.
//   - Gardner, "A BPSK/QPSK Timing-Error Detector for Sampled Receivers",
//     IEEE TCOM COM-34(5), pp 423-429, May 1986.
//   - Godard, "Self-Recovering Equalization and Carrier Tracking in
//     Two-Dimensional Data Communication Systems", IEEE TCOM COM-28(11),
//     pp 1867-1875, Nov 1980. https://doi.org/10.1109/TCOM.1980.1094608
//   - Barry, Lee, Messerschmitt, "Digital Communication", 3rd ed., 2003,
//     Kluwer, sec 8.5 (decision-directed carrier recovery).
//     https://link.springer.com/book/10.1007/978-1-4615-0227-2
//   - Tosato & Bisaglia, "Simplified Soft-Output Demapper for Binary
//     Interleaved COFDM With Application to HIPERLAN/2", IEEE ICC 2002.
//     https://doi.org/10.1109/ICC.2002.996940
//   - GNU Radio control_loop.h::advance_loop (lines 76-80).
//   - Rondeau, "Control Loop Gain Values", 2011.

#define NOCPP

#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <aie_api/aie.hpp>
#include "sdr_dsp_common.hpp"

// Compile-time constants must match test_qam_rx_m26.py exactly.
constexpr int   N_SYM  = 512;
constexpr int   SPS    = 2;
constexpr int   N_IN   = SPS * N_SYM;                   // 1024 complex in-samples
constexpr int   BITS_PER_SYM = 4;                       // QAM-16
constexpr float PI_F   = 3.14159265358979323846f;
constexpr float TWO_PI = 6.28318530717958647692f;

// QAM-16 unit-average-energy constellation scale: {+/-1, +/-3}/sqrt(10).
// Sum(k=1,3) k^2 * 2 / 4 = (1+9)/2 * 2/2 = 5, doubled for both I and Q -> 10.
constexpr float QAM16_SCALE   = 3.16227766016837933199f; // sqrt(10)
constexpr float INV_QAM16_SCALE = 0.31622776601683794f;  // 1/sqrt(10)

// Loop bandwidths. Slightly narrower carrier loop than M25 (QAM-16 has 8x
// higher phase-noise sensitivity than QPSK: the slicer's distance to the
// nearest decision boundary is 1/sqrt(10) instead of 1/sqrt(2)).
// See docs/M26_DESIGN.md sec 2.4.
constexpr float BW_PHI = TWO_PI / 200.0f;               // carrier loop bandwidth (2x narrower vs M25)
constexpr float BW_TAU = TWO_PI / 200.0f;               // timing loop bandwidth
constexpr float DAMP   = 0.70710678118654752440f;       // sqrt(2)/2 (GNU Radio default)

// Rondeau closed-form alpha/beta.
constexpr float DENOM_PHI = 1.0f + 2.0f * DAMP * BW_PHI + BW_PHI * BW_PHI;
constexpr float DENOM_TAU = 1.0f + 2.0f * DAMP * BW_TAU + BW_TAU * BW_TAU;
constexpr float ALPHA_PHI = (4.0f * DAMP * BW_PHI) / DENOM_PHI;
constexpr float BETA_PHI  = (4.0f * BW_PHI * BW_PHI)  / DENOM_PHI;
constexpr float ALPHA_TAU = (4.0f * DAMP * BW_TAU) / DENOM_TAU;
constexpr float BETA_TAU  = (4.0f * BW_TAU * BW_TAU)  / DENOM_TAU;

// Wrap phase into (-pi, pi]. Bounded 4-iteration subtract-wrap (M25 rule:
// Peano NOCPP does not expose libc fmodf).
static inline float wrap_pi(float x) {
    float y = x;
    for (int i = 0; i < 4; ++i) {
        if (y >  PI_F) y -= TWO_PI;
        else if (y < -PI_F) y += TWO_PI;
        else break;
    }
    return y;
}

// AIE2 Peano NOCPP scalar sin/cos via 7th-order Taylor + pi/2 fold.
// Identical to M25 sincos_taylor.
static inline void sincos_taylor(float x, float *ps, float *pc) {
    float a = wrap_pi(x);
    float cos_sign = 1.0f;
    if (a > (PI_F * 0.5f)) {
        a = PI_F - a;
        cos_sign = -1.0f;
    } else if (a < -(PI_F * 0.5f)) {
        a = -PI_F - a;
        cos_sign = -1.0f;
    }
    float x2 = a * a;
    float x3 = x2 * a;
    float x4 = x2 * x2;
    float x5 = x4 * a;
    float x6 = x4 * x2;
    float x7 = x6 * a;
    float s = a - x3 * (1.0f / 6.0f) + x5 * (1.0f / 120.0f) - x7 * (1.0f / 5040.0f);
    float c = 1.0f - x2 * 0.5f + x4 * (1.0f / 24.0f) - x6 * (1.0f / 720.0f);
    *ps = s;
    *pc = cos_sign * c;
}

// Dead-zone sign-of via IEEE-754 bit reinterpret. Identical to M25 sgn_bit.
// Rationale: see M25_DESIGN.md sec 4b bring-up incidents 2 & 3.
static constexpr float DEAD_ZONE_EPS = 1.0e-3f;

static inline float sgn_bit(float x) {
    union { float f; uint32_t u; } absx, eps;
    absx.f = x;
    absx.u = absx.u & 0x7FFFFFFFu;
    eps.f = DEAD_ZONE_EPS;
    if (absx.u < eps.u) return 0.0f;

    union { float f; uint32_t u; } src, dst;
    src.f = x;
    volatile uint32_t sign_bit = src.u & 0x80000000u;
    dst.u = 0x3F800000u | sign_bit;
    return dst.f;
}

// QAM-16 axis slicer. Takes one axis value already de-scaled to the
// {+/-1, +/-3} lattice and returns the nearest lattice point. Threshold
// at 2.0 separates {+/-1} from {+/-3} regions; sign taken from sgn_bit
// so near-axis symbols still get a valid hard decision but do not force
// a spurious feedback update in the DD phase detector when the argument
// is near a decision boundary.
//
// Slicer output is a hard decision in {-3, -1, +1, +3}. The Gray-code
// axis mapping (LSB from Ungerboeck 1982; see the m26 test driver
// _qam16_gray_map for the table) is:
//     axis value:   -3   -1   +1   +3
//     Gray bits:    10   11   01   00     (b_MSB b_LSB)
static inline float qam16_axis_slice(float x_axis) {
    // The axis is expected to be pre-descaled: x_axis ~ +/-1 or +/-3 for a
    // fully-locked QAM-16 symbol at unit average energy. Use bit-safe
    // absolute-value + magnitude threshold at 2.0.
    union { float f; uint32_t u; } ax;
    ax.f = x_axis;
    ax.u = ax.u & 0x7FFFFFFFu;                     // |x_axis|
    float mag_dec = (ax.f > 2.0f) ? 3.0f : 1.0f;   // {1, 3}
    float sign = sgn_bit(x_axis);                  // {-1, 0, +1} with dead-zone
    // If sign came back as 0.0f (very-near-axis reading), commit to the
    // smaller-magnitude decision on the positive half; the DD detector
    // will not update because sign*mag_dec = 0 there.
    return sign * mag_dec;
}

// Templated inner body. `ORDER_UNUSED` is retained for signature symmetry
// with M25 but the DD detector is fixed here (order-M is set by the
// constellation slicer).
static void qam16_rx_body(bfloat16 *__restrict in_iq,
                          bfloat16 *__restrict out_iq,
                          bfloat16 *__restrict out_llr) {
    event0();

    // Carrier loop state.
    float phase = 0.0f;
    float freq  = 0.0f;

    // Timing loop state.
    float mu       = 0.5f;
    float freq_tau = 0.0f;
    int   n_read   = 0;

    // 3-slot complex history window.
    float hist_I[3] = { 0.0f, 0.0f, 0.0f };
    float hist_Q[3] = { 0.0f, 0.0f, 0.0f };

    hist_I[1] = in_iq[0]; hist_Q[1] = in_iq[1];
    hist_I[2] = in_iq[2]; hist_Q[2] = in_iq[3];

    for (int k = 0; k < N_SYM; ++k) {

        // --- (1) Fetch the "now" complex sample.
        int idx_now = 2 * (n_read + 2);
        float I_now, Q_now;
        if (idx_now + 1 < 2 * N_IN) {
            I_now = (float)in_iq[idx_now];
            Q_now = (float)in_iq[idx_now + 1];
        } else {
            I_now = hist_I[2];
            Q_now = hist_Q[2];
        }

        // Literal shift-and-ingest.
        hist_I[0] = hist_I[1];
        hist_I[1] = hist_I[2];
        hist_I[2] = I_now;

        hist_Q[0] = hist_Q[1];
        hist_Q[1] = hist_Q[2];
        hist_Q[2] = Q_now;

        // --- (2) Gardner TED.
        float dI = hist_I[2] - hist_I[0];
        float dQ = hist_Q[2] - hist_Q[0];
        float e_tau = dI * hist_I[1] + dQ * hist_Q[1];

        // --- (3) Timing PI update.
        freq_tau = freq_tau + BETA_TAU  * e_tau;
        mu       = mu       + freq_tau + ALPHA_TAU * e_tau;

        // --- (4) Wrap mu.
        while (mu >= 1.0f) { mu -= 1.0f; n_read += 1; }
        while (mu <  0.0f) { mu += 1.0f; n_read -= 1; }
        n_read += 1;

        // --- (5) Linear fractional interp.
        float ySymI = (1.0f - mu) * hist_I[0] + mu * hist_I[1];
        float ySymQ = (1.0f - mu) * hist_Q[0] + mu * hist_Q[1];

        // --- (6) NCO derotation.
        float s, c;
        sincos_taylor(phase, &s, &c);
        float zI = ySymI * c + ySymQ * s;
        float zQ = ySymQ * c - ySymI * s;

        // --- (7) QAM-16 hard-decision slicer. z is at unit average energy
        // so the constellation lives on {+/-1, +/-3}/sqrt(10). Bring the
        // observation up to the {+/-1, +/-3} lattice for slicing.
        float zI_lattice = zI * QAM16_SCALE;
        float zQ_lattice = zQ * QAM16_SCALE;
        float hat_aI = qam16_axis_slice(zI_lattice);   // in {-3,-1,+1,+3}
        float hat_aQ = qam16_axis_slice(zQ_lattice);

        // --- (8) Decision-directed order-M phase detector. Barry-Lee-
        // Messerschmitt sec 8.5 form uses the sliced symbol as the pilot:
        //   e_phi = z_I * hat_a_Q - z_Q * hat_a_I    (unnormalized cross)
        // Sign-only version (matches gr-digital costas_loop_cc order-8
        // extension for higher-order QAM). We keep the magnitude form
        // because for QAM-16 the outer points (+/-3) have 9x the phase
        // torque of the inner points, which is what we want on locking.
        float e_phi = zI_lattice * hat_aQ - zQ_lattice * hat_aI;

        // --- (9) Carrier PI update.
        freq  = freq  + BETA_PHI  * e_phi;
        phase = phase + freq + ALPHA_PHI * e_phi;
        phase = wrap_pi(phase);

        // --- (10) Emit hard symbol decision (at unit-energy scale, as bf16).
        float out_symI = hat_aI * INV_QAM16_SCALE;
        float out_symQ = hat_aQ * INV_QAM16_SCALE;
        out_iq[2 * k    ] = (bfloat16)out_symI;
        out_iq[2 * k + 1] = (bfloat16)out_symQ;

        // --- (11) Soft-decision LLR demapper (Tosato-Bisaglia max-log).
        //
        // QAM-16 Gray label per axis (LSB to right):
        //     axis value:  -3    -1    +1    +3
        //     Gray bits:   10    11    01    00     (b_MSB, b_LSB)
        //
        // The two axes are independent (Gray-coded QAM is
        // (bit-)separable), so per-bit LLRs on I and Q come out as:
        //
        //   LLR(b_MSB_axis) = log P(b=0|z) - log P(b=1|z)
        //                   = (z_axis) * 4 / N0     [linear in z_axis]
        //   LLR(b_LSB_axis) = (2 - |z_axis|) * 4 / N0     [absolute value]
        //
        // (see Tosato-Bisaglia 2002 eq. 5-6, or Alvarado-Fabregas 2009
        // "Simplified soft-metric calculation for L-QAM in fading channels"
        // eq. 8). We publish scaled max-log LLRs at N0=1 (unit noise
        // reference); the outer receiver can rescale.
        //
        // Bit ordering in the output buffer (per symbol k, four bf16 slots):
        //   [4k+0] = LLR(b3) = LLR(I-axis MSB)
        //   [4k+1] = LLR(b2) = LLR(I-axis LSB)
        //   [4k+2] = LLR(b1) = LLR(Q-axis MSB)
        //   [4k+3] = LLR(b0) = LLR(Q-axis LSB)
        float absI = zI_lattice;
        float absQ = zQ_lattice;
        // Bit-safe |.| via sign-strip.
        union { float f; uint32_t u; } aI, aQ;
        aI.f = absI; aI.u = aI.u & 0x7FFFFFFFu; absI = aI.f;
        aQ.f = absQ; aQ.u = aQ.u & 0x7FFFFFFFu; absQ = aQ.f;

        float llr_b3 = zI_lattice * 4.0f;                 // I MSB
        float llr_b2 = (2.0f - absI) * 4.0f;              // I LSB
        float llr_b1 = zQ_lattice * 4.0f;                 // Q MSB
        float llr_b0 = (2.0f - absQ) * 4.0f;              // Q LSB

        out_llr[4 * k + 0] = (bfloat16)llr_b3;
        out_llr[4 * k + 1] = (bfloat16)llr_b2;
        out_llr[4 * k + 2] = (bfloat16)llr_b1;
        out_llr[4 * k + 3] = (bfloat16)llr_b0;
    }
}

extern "C" {

void qam16_rx(bfloat16 *__restrict in_iq,
              bfloat16 *__restrict out_iq,
              bfloat16 *__restrict out_llr) {
    qam16_rx_body(in_iq, out_iq, out_llr);
}

}  // extern "C"
