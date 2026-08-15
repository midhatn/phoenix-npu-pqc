// M25 - BPSK/QPSK Receiver Pipeline (Gardner TED + Costas Loop)
//
// Single-tile AIE2 kernel that fuses:
//   1. Gardner timing-error detector at 2 sps
//   2. Second-order PI loop filter (GNU Radio advance_loop transliterated)
//   3. Fractional linear-interp resampler (2 sps -> 1 sample/symbol)
//   4. NCO derotator (on-tile 7th-order Taylor sin/cos)
//   5. Costas order-2 (BPSK) or order-4 (QPSK) phase-error detector
//   6. Second-order PI loop filter on carrier phase
//
// I/O contract mirrors M24 (Barker-13 correlator):
//   in_iq : 2 * N_IN interleaved bfloat16 (I0,Q0,I1,Q1,...)  with N_IN = 1024
//   out_iq: 2 * N_SYM interleaved bfloat16 (I0,Q0,I1,Q1,...) with N_SYM = 512
// Two ExternalFunction entry points (one per PSK order) so the (in, out)
// signature stays 2-arg like every other M19..M24 kernel.
//
// State discipline (M22/M24 rule): all sample-serial state lives in scalar
// registers between symbol iterations. History windows use literal-index
// shift-and-ingest so Peano lowers each move to a single register copy.
//
// Citations:
//   - Costas, "Synchronous Communications", Proc. IRE 44(12), Dec 1956.
//   - Gardner, "A BPSK/QPSK Timing-Error Detector for Sampled Receivers",
//     IEEE TCOM COM-34(5), pp 423-429, May 1986.
//   - GNU Radio control_loop.h::advance_loop (lines 76-80).
//   - Rondeau, "Control Loop Gain Values", 2011.
//   - US Patent 4344178A (Waters, 1982) - order-4 sgn(I)*Q - sgn(Q)*I.

#define NOCPP

#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <aie_api/aie.hpp>
#include "sdr_dsp_common.hpp"

// Compile-time constants must match test_bpsk_costas_m25.py exactly.
constexpr int   N_SYM  = 512;
constexpr int   SPS    = 2;
constexpr int   N_IN   = SPS * N_SYM;                   // 1024 complex in-samples
constexpr float PI_F   = 3.14159265358979323846f;
constexpr float TWO_PI = 6.28318530717958647692f;

// Loop bandwidths. See docs/M25_DESIGN.md §2.2 / §2.4.
constexpr float BW_PHI = TWO_PI / 100.0f;               // carrier loop bandwidth
constexpr float BW_TAU = TWO_PI / 200.0f;               // timing loop bandwidth (half of carrier)
constexpr float DAMP   = 0.70710678118654752440f;       // sqrt(2)/2 (GNU Radio default)

// Rondeau closed-form alpha/beta.
constexpr float DENOM_PHI = 1.0f + 2.0f * DAMP * BW_PHI + BW_PHI * BW_PHI;
constexpr float DENOM_TAU = 1.0f + 2.0f * DAMP * BW_TAU + BW_TAU * BW_TAU;
constexpr float ALPHA_PHI = (4.0f * DAMP * BW_PHI) / DENOM_PHI;
constexpr float BETA_PHI  = (4.0f * BW_PHI * BW_PHI)  / DENOM_PHI;
constexpr float ALPHA_TAU = (4.0f * DAMP * BW_TAU) / DENOM_TAU;
constexpr float BETA_TAU  = (4.0f * BW_TAU * BW_TAU)  / DENOM_TAU;

// Wrap phase into (-pi, pi]. Per-symbol phase drift is bounded well below
// pi (loop bandwidth 2*pi/100 with tiny e_phi), so a bounded subtract loop
// is safer and cheaper than pulling in fmodf, which the Peano NOCPP build
// does not expose. Same identity: repeatedly subtract/add 2*pi.
static inline float wrap_pi(float x) {
    float y = x;
    // Bound: at most a few 2*pi wraps even in worst-case transients.
    for (int i = 0; i < 4; ++i) {
        if (y >  PI_F) y -= TWO_PI;
        else if (y < -PI_F) y += TWO_PI;
        else break;
    }
    return y;
}

// AIE2 Peano NOCPP scalar sin/cos. Range-reduce to [-pi, pi] via wrap_pi,
// then fold to [-pi/2, pi/2] using the identities:
//   sin(pi - a) = sin(a),  cos(pi - a) = -cos(a)  for a > 0
//   sin(-pi - a) = -sin(-a) = sin(a),  cos(-pi - a) = -cos(a)  for a < 0
// Then evaluate a 7th-order Taylor around 0:
//   sin(x) ~ x - x^3/6 + x^5/120 - x^7/5040    (max err ~1.5e-4 on |x|<=pi/2)
//   cos(x) ~ 1 - x^2/2 + x^4/24 - x^6/720      (max err ~2.4e-5 on |x|<=pi/2)
// These accuracies are well inside the atol=0.05 silicon budget.
static inline void sincos_taylor(float x, float *ps, float *pc) {
    // Reduce to [-pi, pi].
    float a = wrap_pi(x);
    // Fold to [-pi/2, pi/2] and remember whether cos sign flips.
    float cos_sign = 1.0f;
    if (a > (PI_F * 0.5f)) {
        a = PI_F - a;      // sin unchanged, cos negated
        cos_sign = -1.0f;
    } else if (a < -(PI_F * 0.5f)) {
        a = -PI_F - a;     // sin unchanged, cos negated
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

// Order-2 (BPSK): e_phi = z_I * z_Q     -- product form, matches
// gr::digital::costas_loop_cc::phase_detector_2(sample).
static inline float costas_err_2(float zI, float zQ) {
    return zI * zQ;
}

// IEEE-754 float32 sign-of via bit reinterpret WITH DEAD-ZONE. When |x| < eps
// the decision is unreliable (any tiny rounding difference between CPU and
// AIE2 float arithmetic can flip the sign), so we return 0.0f and skip the
// feedback nudge for that symbol. This is standard practice in decision-
// directed loops; on real received signals the constellation never sits
// exactly on an axis but with a fixed-seed test one symbol will.
//
// History:
//  * Attempt 1: `(x >= 0.0f) ? 1.0f : -1.0f` -- Peano NOCPP scalar float
//               compare-select miscompiled QPSK relative to CPU (max err
//               0.447 at seed 796) while BPSK passed at 0.004.
//  * Attempt 2: `union{float f;uint32_t u;}; return (u&0x80000000)?-1:1;` --
//               Peano -O2 pattern-matched to llvm.copysign; AIE2 legalizer
//               failed with `unable to legalize G_FCOPYSIGN`.
//  * Attempt 3: same union with volatile mask, no dead-zone. Compiled but
//               QPSK still diverged at symbol 64 where silicon computed
//               zQ = -1.7e-4 while CPU computed zQ = +4.9e-4 -- both are
//               essentially zero, differing only by float32 ULPs in the
//               preceding arithmetic. sgn_bit therefore returned -1 on
//               silicon and +1 on CPU, and the closed feedback loop tracked
//               a different equilibrium from that symbol onward.
//  * Current: keep the volatile integer composition (still needed to dodge
//               copysign) but return 0.0f when |x| < DEAD_ZONE_EPS. Any
//               near-axis symbol contributes no phase update on either side,
//               so CPU and silicon can disagree by ULPs without diverging.
static constexpr float DEAD_ZONE_EPS = 1.0e-3f;

static inline float sgn_bit(float x) {
    // Dead-zone: near-axis symbols contribute no sign feedback.
    // |x| < eps by comparing bit pattern of |x| to bit pattern of eps.
    union { float f; uint32_t u; } absx, eps;
    absx.f = x;
    absx.u = absx.u & 0x7FFFFFFFu;      // strip sign bit -> |x|
    eps.f = DEAD_ZONE_EPS;
    if (absx.u < eps.u) return 0.0f;

    // Otherwise: bit-level sign-of via integer OR (dodges G_FCOPYSIGN).
    union { float f; uint32_t u; } src, dst;
    src.f = x;
    volatile uint32_t sign_bit = src.u & 0x80000000u;
    dst.u = 0x3F800000u | sign_bit;
    return dst.f;
}

// Order-4 (QPSK) decision-directed: e_phi = z_I*sgn(z_Q) - z_Q*sgn(z_I).
// This is the classic gr::digital::costas_loop_cc::phase_detector_4 form and
// matches US Patent 4344178A eq. (1).
static inline float costas_err_4(float zI, float zQ) {
    float sI = sgn_bit(zI);
    float sQ = sgn_bit(zQ);
    return zI * sQ - zQ * sI;
}

// Templated inner body. `ORDER` is a compile-time template parameter, so
// Peano constant-folds the costas_err_2 / costas_err_4 selection.
template <int ORDER>
static void psk_rx_body(bfloat16 *__restrict in_iq, bfloat16 *__restrict out_iq) {
    event0();

    // Carrier loop state.
    float phase = 0.0f;
    float freq  = 0.0f;

    // Timing loop state. mu is the fractional offset in (0, 1); n_read is the
    // integer 2-sps input index of the "previous" symbol slot.
    float mu       = 0.5f;    // start mid-symbol (matches GNU Radio init)
    float freq_tau = 0.0f;
    int   n_read   = 0;       // integer 2-sps index of x[k-1]

    // 3-slot complex history window: x_prev, x_mid, x_now.
    // Populated via literal-index shifts identical to M24's hist_i/hist_q
    // pattern. On the first iteration the shifts pull in samples 0/1/2.
    float hist_I[3] = { 0.0f, 0.0f, 0.0f };
    float hist_Q[3] = { 0.0f, 0.0f, 0.0f };

    // Prime the history with samples 0, 1 so the first iteration only needs
    // one fresh read for the "now" slot.
    hist_I[1] = in_iq[0]; hist_Q[1] = in_iq[1];   // x[k-1] slot at symbol 0
    hist_I[2] = in_iq[2]; hist_Q[2] = in_iq[3];   // x_mid   slot at symbol 0

    for (int k = 0; k < N_SYM; ++k) {

        // --- (1) Fetch the "now" complex sample = x[k] at input index 2*(n_read+1).
        int idx_now = 2 * (n_read + 2);
        // Guard: if we walked off the end, hold last x_now (stall).
        float I_now, Q_now;
        if (idx_now + 1 < 2 * N_IN) {
            I_now = (float)in_iq[idx_now];
            Q_now = (float)in_iq[idx_now + 1];
        } else {
            I_now = hist_I[2];
            Q_now = hist_Q[2];
        }

        // Literal shift-and-ingest (M22/M24 discipline): x_prev <- x_mid, x_mid <- x_now.
        // Newest sample lands at hist[2].
        hist_I[0] = hist_I[1];
        hist_I[1] = hist_I[2];
        hist_I[2] = I_now;

        hist_Q[0] = hist_Q[1];
        hist_Q[1] = hist_Q[2];
        hist_Q[2] = Q_now;

        // --- (2) Gardner complex TED:
        // e_tau = Re{(x_now - x_prev) * conj(x_mid)}
        //       = (I_now - I_prev)*I_mid + (Q_now - Q_prev)*Q_mid
        float dI = hist_I[2] - hist_I[0];
        float dQ = hist_Q[2] - hist_Q[0];
        float e_tau = dI * hist_I[1] + dQ * hist_Q[1];

        // --- (3) Timing PI update (advance_loop form).
        freq_tau = freq_tau + BETA_TAU  * e_tau;
        mu       = mu       + freq_tau + ALPHA_TAU * e_tau;

        // --- (4) Wrap mu into [0, 1) and adjust n_read by the integer drift.
        // With small e_tau, mu drifts by <<1 per symbol. This guard covers
        // multi-sample slips just in case.
        while (mu >= 1.0f) { mu -= 1.0f; n_read += 1; }
        while (mu <  0.0f) { mu += 1.0f; n_read -= 1; }
        // Normal advance: consume one symbol worth of 2-sps samples.
        n_read += 1;   // move x_prev forward by one symbol (2 sps samples)

        // --- (5) Linear fractional interp between x_prev (hist[0]) and x_mid (hist[1]).
        // This is the "on-time" complex symbol y_sym.
        float ySymI = (1.0f - mu) * hist_I[0] + mu * hist_I[1];
        float ySymQ = (1.0f - mu) * hist_Q[0] + mu * hist_Q[1];

        // --- (6) NCO derotation: z = y_sym * exp(-j*phase)
        float s, c;
        sincos_taylor(phase, &s, &c);
        float zI = ySymI * c + ySymQ * s;
        float zQ = ySymQ * c - ySymI * s;

        // --- (7) Costas phase-error detector, template branch on ORDER.
        float e_phi;
        if (ORDER == 4) {
            e_phi = costas_err_4(zI, zQ);
        } else {
            e_phi = costas_err_2(zI, zQ);
        }

        // --- (8) Carrier PI update (advance_loop form).
        freq  = freq  + BETA_PHI  * e_phi;
        phase = phase + freq + ALPHA_PHI * e_phi;
        phase = wrap_pi(phase);

        // --- (9) Emit z as symbol k.
        out_iq[2 * k    ] = (bfloat16)zI;
        out_iq[2 * k + 1] = (bfloat16)zQ;
    }
}

extern "C" {

void psk_rx_bpsk(bfloat16 *__restrict in_iq, bfloat16 *__restrict out_iq) {
    psk_rx_body<2>(in_iq, out_iq);
}

void psk_rx_qpsk(bfloat16 *__restrict in_iq, bfloat16 *__restrict out_iq) {
    psk_rx_body<4>(in_iq, out_iq);
}

}  // extern "C"
