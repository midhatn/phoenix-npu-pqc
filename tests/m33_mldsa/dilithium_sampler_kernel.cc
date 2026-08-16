// SPDX-License-Identifier: Apache-2.0
// M33b - Dilithium rounding / hint primitives for FIPS 204 ML-DSA
// (Post-Quantum Cryptography).
//
// Coefficient-wise rounding, decomposition, and hint operations on 256-element
// int32 polynomials over Z_q with q = 8380417. These are the primitives called
// by ML-DSA KeyGen (Power2Round on t), Sign (Decompose on w, MakeHint on w0/w1,
// CheckNormBound on z and h), and Verify (UseHint on w'). All operations are
// fully data-parallel over the 256 coefficients - a good NPU fit.
//
// SampleInBall is intentionally NOT in this kernel. It is inherently a
// sequential rejection-sample-and-swap state machine driven by SHAKE256
// output, and lives in the host composer (mlkem-style) rather than on tiles.
//
// Modes (u8):
//   MODE_POWER2ROUND = 0 : split r into (r1, r0) with r = r1*2^d + r0,
//                          r0 in (-2^(d-1), 2^(d-1)]. Fixed d = 13.
//                          out_c = r1, out_d = r0.
//   MODE_DECOMPOSE   = 1 : split r into (r1, r0) with r = r1*alpha + r0,
//                          r0 in (-alpha/2, alpha/2] plus the r0 = -1 edge case
//                          when r1*alpha == q-1. alpha selected by param u32.
//                          out_c = r1, out_d = r0.
//   MODE_MAKEHINT    = 2 : bit vector h[i] = (HighBits(r) != HighBits(r+z)).
//                          in_a = z (int32), in_b = r (int32), out_c = h
//                          (int32 in {0,1}). alpha selected by param u32.
//   MODE_USEHINT     = 3 : given h and r, recover HighBits of r + z.
//                          in_a = h ({0,1}), in_b = r (int32), out_c = r1'.
//                          alpha selected by param u32.
//   MODE_CHECKNORM   = 4 : per-coefficient predicate |reduce_mod_pm(r,q)| < b,
//                          out_c[0] = 1 if ALL coeffs pass, else 0. Rest of
//                          out_c is undefined. b selected by param u32.
//   MODE_REDUCE_PM   = 5 : coefficient-wise centered reduce to (-q/2, q/2].
//                          in_a = r, out_c = reduced.
//
// Kernel signature keeps the M32/M33 4-buffer convention (in_a, in_b, out_c,
// out_d) plus a scalar param slot; MakeHint and Decompose need both output
// buffers.
//
// References
//   FIPS 204, https://nvlpubs.nist.gov/nistpubs/fips/nist.fips.204.pdf
//     Alg 29 Power2Round, Alg 30 Decompose, Alg 31 HighBits, Alg 32 LowBits,
//     Alg 33 MakeHint, Alg 34 UseHint.
//   pq-crystals dilithium ref: rounding.c
//     https://github.com/pq-crystals/dilithium/blob/master/ref/rounding.c

#include <cstdint>

extern "C" {

constexpr int32_t Q          = 8380417;
constexpr int32_t N          = 256;
constexpr int32_t D_BITS     = 13;
constexpr int32_t POW2D      = 1 << D_BITS;   // 8192
constexpr int32_t POW2D_HALF = 1 << (D_BITS - 1);  // 4096

// Reduce r mod pm N: input r in [0, n), output in (-n/2, n/2].
static inline int32_t reduce_mod_pm_signed(int32_t r, int32_t n) {
    int32_t rr = r;
    if (rr > (n >> 1)) rr -= n;
    return rr;
}

// Bring signed r into [0, q).
static inline int32_t canonicalize(int32_t r) {
    int32_t x = r % Q;
    if (x < 0) x += Q;
    return x;
}

// Power2Round: r in Z_q, produces r1, r0 with r = r1 * 2^d + r0 mod q,
// r0 in (-2^(d-1), 2^(d-1)]. Follows FIPS 204 Alg 29.
static inline void power2round_coeff(int32_t r_in, int32_t& r1_out, int32_t& r0_out) {
    int32_t rp = canonicalize(r_in);
    int32_t r0 = rp & (POW2D - 1);      // rp mod 2^d
    if (r0 > POW2D_HALF) r0 -= POW2D;
    r1_out = (rp - r0) >> D_BITS;
    r0_out = r0;
}

// Decompose: r = r1*alpha + r0 mod q, r0 in (-alpha/2, alpha/2].
// Follows FIPS 204 Alg 30 including the r1*alpha == q-1 edge case.
static inline void decompose_coeff(int32_t r_in, int32_t alpha,
                                   int32_t& r1_out, int32_t& r0_out) {
    int32_t rp = canonicalize(r_in);
    int32_t half = alpha >> 1;
    int32_t r0 = rp % alpha;
    if (r0 > half) r0 -= alpha;
    int32_t r1;
    if (rp - r0 == Q - 1) {
        r1 = 0;
        r0 = r0 - 1;
    } else {
        r1 = (rp - r0) / alpha;
    }
    r1_out = r1;
    r0_out = r0;
}

static inline int32_t high_bits_coeff(int32_t r_in, int32_t alpha) {
    int32_t r1, r0;
    decompose_coeff(r_in, alpha, r1, r0);
    return r1;
}

// UseHint: recover approximate HighBits(r + z) using 1-bit hint h.
// Follows FIPS 204 Alg 34.
static inline int32_t use_hint_coeff(int32_t h, int32_t r_in, int32_t alpha) {
    int32_t m = (Q - 1) / alpha;
    int32_t r1, r0;
    decompose_coeff(r_in, alpha, r1, r0);
    if (h != 0) {
        if (r0 > 0) return (r1 + 1) % m;
        return (r1 - 1 + m) % m;
    }
    return r1;
}

// Dispatch entry point.
void dilithium_sampler(uint8_t mode,
                       int32_t param,
                       int32_t in_a[N],
                       int32_t in_b[N],
                       int32_t out_c[N],
                       int32_t out_d[N]) {
    switch (mode) {
        case 0: {  // POWER2ROUND
            for (int32_t i = 0; i < N; ++i) {
                int32_t r1, r0;
                power2round_coeff(in_a[i], r1, r0);
                out_c[i] = r1;
                out_d[i] = r0;
            }
            break;
        }
        case 1: {  // DECOMPOSE
            int32_t alpha = param;
            for (int32_t i = 0; i < N; ++i) {
                int32_t r1, r0;
                decompose_coeff(in_a[i], alpha, r1, r0);
                out_c[i] = r1;
                out_d[i] = r0;
            }
            break;
        }
        case 2: {  // MAKEHINT
            int32_t alpha = param;
            for (int32_t i = 0; i < N; ++i) {
                int32_t hb_r  = high_bits_coeff(in_b[i], alpha);
                int32_t hb_rz = high_bits_coeff(in_b[i] + in_a[i], alpha);
                out_c[i] = (hb_r != hb_rz) ? 1 : 0;
            }
            break;
        }
        case 3: {  // USEHINT
            int32_t alpha = param;
            for (int32_t i = 0; i < N; ++i) {
                out_c[i] = use_hint_coeff(in_a[i], in_b[i], alpha);
            }
            break;
        }
        case 4: {  // CHECKNORM: reduce_mod_pm(r, q) magnitude vs bound
            int32_t bound = param;
            int32_t all_ok = 1;
            for (int32_t i = 0; i < N; ++i) {
                int32_t rp = canonicalize(in_a[i]);
                int32_t rc = reduce_mod_pm_signed(rp, Q);
                int32_t mag = rc < 0 ? -rc : rc;
                if (mag >= bound) { all_ok = 0; }
            }
            out_c[0] = all_ok;
            break;
        }
        case 5: {  // REDUCE_PM
            for (int32_t i = 0; i < N; ++i) {
                int32_t rp = canonicalize(in_a[i]);
                out_c[i] = reduce_mod_pm_signed(rp, Q);
            }
            break;
        }
        default:
            for (int32_t i = 0; i < N; ++i) {
                out_c[i] = 0;
                out_d[i] = 0;
            }
            break;
    }
}

}  // extern "C"
