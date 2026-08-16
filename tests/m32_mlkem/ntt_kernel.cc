// M32b - Post-Quantum Cryptography Foundations on AIE2:
//        NTT-domain arithmetic for ML-KEM over Z_q[X]/(X^256 + 1) with
//        q = 3329, n = 256, zeta = 17.
//
// Implements FIPS 203 (ML-KEM) Algorithms 9-12:
//   Algorithm 9  NTT             - forward negacyclic NTT, Cooley-Tukey
//                                  butterflies, standard order in / bit-reversed
//                                  order out.
//   Algorithm 10 NTT^{-1}        - inverse negacyclic NTT, Gentleman-Sande
//                                  butterflies, bit-reversed in / standard out;
//                                  matches the pq-crystals `invntt_tomont`
//                                  variant that leaves output multiplied by
//                                  2^16 mod q (Montgomery factor).
//   Algorithm 11 MultiplyNTTs    - polynomial product in the NTT domain, done
//                                  as 128 base-case multiplications over
//                                  Z_q[X]/(X^2 - gamma) with gamma = zeta^(2 br(k)+1).
//   Algorithm 12 BaseCaseMultiply- (a0 + a1 X)(b0 + b1 X) mod (X^2 - gamma).
//
// Plus two polynomial-vector helpers used by K-PKE (Alg 13-15) and ML-KEM
// KeyGen/Encaps/Decaps (Alg 19-21):
//   MODE_POLY_ADD - coefficient-wise (a + b) mod q, Barrett-reduced.
//   MODE_POLY_SUB - coefficient-wise (a - b) mod q, Barrett-reduced.
//
// Single-tile AIE2 kernel, entrypoint `ntt`, three DMA buffers (mirrors the
// M32c topology - 2 in-fifos + 1 out-fifo, an M27 lesson):
//   in_a   (int16, up to MAX_COEFFS = 768 coefficients) - polynomial A
//                                                        (or A followed by B
//                                                         for BASEMUL/ADD/SUB)
//   in_ctrl(int16, 8-element control) - {mode, n_polys, pad0, ...}
//                                        - mode in {NTT, INTT, BASEMUL,
//                                          POLY_ADD, POLY_SUB}
//                                        - n_polys is the number of length-256
//                                          polynomials laid out contiguously.
//   out_c  (int16, up to MAX_COEFFS)   - result polynomial(s)
//
// Standards, references, and prior art:
//   * FIPS 203 (Aug 2024), Module-Lattice-Based Key-Encapsulation Mechanism
//     Standard. Algorithms 9-12; ring parameters n=256, q=3329, zeta=17.
//     https://nvlpubs.nist.gov/nistpubs/fips/nist.fips.203.pdf
//   * CRYSTALS-Kyber round-3 specification (Avanzi et al., 2021), Section 1.4
//     "The number-theoretic transform".
//     https://pq-crystals.org/kyber/data/kyber-specification-round3-20210131.pdf
//   * pq-crystals/kyber reference implementation (ref/ntt.c, ref/reduce.c,
//     ref/poly.c) - the canonical bit-exact target for ntt/invntt/basemul,
//     Montgomery and Barrett reductions, and poly_basemul_montgomery.
//     https://github.com/pq-crystals/kyber/blob/main/ref/ntt.c
//     https://github.com/pq-crystals/kyber/blob/main/ref/reduce.c
//     https://github.com/pq-crystals/kyber/blob/main/ref/poly.c
//   * Kyber CFRG draft rev 04 (Schwabe et al.) - specifies bit-reversed zeta
//     order and negacyclic NTT convention.
//     https://www.ietf.org/archive/id/draft-cfrg-schwabe-kyber-04.html
//   * NIST PQC project (post-quantum cryptography programme landing page).
//     https://csrc.nist.gov/projects/post-quantum-cryptography
//
// Kernel style rules (inherited M22..M32c lineage):
//   * NOCPP, no libc <math.h>
//   * All counted loops carry #pragma clang loop unroll(disable) so the 16 KiB
//     program-memory budget is not blown (M27 lesson).
//   * ntt_forward / ntt_inverse are __attribute__((noinline)) because they are
//     called from several dispatch modes.
//   * Zeta table is a single 128-entry int16 constant (256 bytes of .rodata,
//     well under the 4 KiB data-memory budget on the tile). Values are the
//     signed Montgomery-domain representatives from pq-crystals ref/ntt.c,
//     so fqmul(zeta, x) directly implements zeta*x mod q up to a factor
//     R^{-1} = 2^{-16} mod q (see basemul comment).
//   * Every arithmetic operation is int16 in / int16 out with an int32 scratch
//     for the multiply, matching pq-crystals bit-for-bit.
//   * No branches on secret data - the sampling was done in M32c, here every
//     buffer is public (post-NTT public matrix A_hat or public compressed
//     ciphertext coefficients), so branch behaviour is not sensitive.

#define NOCPP

#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <aie_api/aie.hpp>

// ---------------------------------------------------------------------------
// Compile-time constants (must match test_ntt_m32b.py exactly).
// ---------------------------------------------------------------------------

constexpr int MAX_COEFFS = 768;    // up to 3 * 256 int16 coefficients per DMA
constexpr int CTRL_LEN   = 8;      // control block width (int16)

constexpr int16_t MODE_NTT      = 0;
constexpr int16_t MODE_INTT     = 1;
constexpr int16_t MODE_BASEMUL  = 2;
constexpr int16_t MODE_POLY_ADD = 3;
constexpr int16_t MODE_POLY_SUB = 4;

// ML-KEM ring parameters (FIPS 203, Sec 2.4.4).
constexpr int     KYBER_N = 256;
constexpr int16_t KYBER_Q = 3329;

// Montgomery constants (pq-crystals/kyber ref/reduce.h).
//   R = 2^16, MONT = R mod q = -1044 (signed), QINV = q^{-1} mod 2^16 = -3327.
//   f = mont^2 / n = 1441, used in invntt_tomont for the final scale-and-fold.
constexpr int16_t KYBER_MONT     = -1044;
constexpr int16_t KYBER_QINV     = -3327;
constexpr int16_t KYBER_INVNTT_F = 1441;   // (R^2 / 128) mod q, signed

// ---------------------------------------------------------------------------
// Signed twiddle table zetas[128], values taken verbatim from
// pq-crystals/kyber ref/ntt.c (Montgomery-domain, bit-reversed order).
//
// Semantics: zetas[k] = R * zeta^{brv7(k)} mod q, with signed representative
// in {-(q-1)/2, ..., (q-1)/2}. Verified in the host reference by an
// independent recomputation from the base value zeta = 17 and the
// 7-bit bit-reversal function.
// ---------------------------------------------------------------------------
static const int16_t ZETAS[128] = {
    -1044,  -758,  -359, -1517,  1493,  1422,   287,   202,
     -171,   622,  1577,   182,   962, -1202, -1474,  1468,
      573, -1325,   264,   383,  -829,  1458, -1602,  -130,
     -681,  1017,   732,   608, -1542,   411,  -205, -1571,
     1223,   652,  -552,  1015, -1293,  1491,  -282, -1544,
      516,    -8,  -320,  -666, -1618, -1162,   126,  1469,
     -853,   -90,  -271,   830,   107, -1421,  -247,  -951,
     -398,   961, -1508,  -725,   448, -1065,   677, -1275,
    -1103,   430,   555,   843, -1251,   871,  1550,   105,
      422,   587,   177,  -235,  -291,  -460,  1574,  1653,
     -246,   778,  1159,  -147,  -777,  1483,  -602,  1119,
    -1590,   644,  -872,   349,   418,   329,  -156,   -75,
      817,  1097,   603,   610,  1322, -1285, -1465,   384,
    -1215,  -136,  1218, -1335,  -874,   220, -1187, -1659,
    -1185, -1530, -1278,   794, -1510,  -854,  -870,   478,
     -108,  -308,   996,   991,   958, -1460,  1522,  1628,
};

// ---------------------------------------------------------------------------
// Montgomery and Barrett reductions - line-for-line pq-crystals ref/reduce.c.
// ---------------------------------------------------------------------------

// Montgomery reduction: given a in [-q * 2^15, q * 2^15 - 1], return t in
// (-q, q) with t ≡ a * R^{-1} (mod q).
static inline int16_t montgomery_reduce(int32_t a) {
    int16_t t;
    t = (int16_t)((int16_t)a * KYBER_QINV);
    t = (int16_t)((a - (int32_t)t * (int32_t)KYBER_Q) >> 16);
    return t;
}

// Barrett reduction: given a in int16, return t in (-(q-1)/2, (q-1)/2] with
// t ≡ a (mod q). Uses v = floor((2^26 + q/2) / q) = 20159.
static inline int16_t barrett_reduce(int16_t a) {
    int16_t t;
    const int16_t v = (int16_t)(((1 << 26) + KYBER_Q / 2) / KYBER_Q);
    t = (int16_t)(((int32_t)v * (int32_t)a + (1 << 25)) >> 26);
    t = (int16_t)(t * KYBER_Q);
    return (int16_t)(a - t);
}

// Fused multiply + Montgomery reduce - the workhorse of every butterfly.
static inline int16_t fqmul(int16_t a, int16_t b) {
    return montgomery_reduce((int32_t)a * (int32_t)b);
}

// ---------------------------------------------------------------------------
// Forward NTT: standard order in, bit-reversed order out.
//
// Cooley-Tukey butterfly (FIPS 203 Algorithm 9). Transliterated line-for-line
// from pq-crystals/kyber ref/ntt.c :: ntt().
// ---------------------------------------------------------------------------
__attribute__((noinline))
static void ntt_forward(int16_t *r) {
    unsigned int len, start, j, k;
    int16_t t, zeta;

    k = 1;
    #pragma clang loop unroll(disable)
    for (len = 128; len >= 2; len >>= 1) {
        #pragma clang loop unroll(disable)
        for (start = 0; start < 256; start = j + len) {
            zeta = ZETAS[k++];
            #pragma clang loop unroll(disable)
            for (j = start; j < start + len; j++) {
                t = fqmul(zeta, r[j + len]);
                r[j + len] = (int16_t)(r[j] - t);
                r[j]       = (int16_t)(r[j] + t);
            }
        }
    }
}

// ---------------------------------------------------------------------------
// Inverse NTT (+ multiplication by Montgomery factor):
//   bit-reversed in, standard-order out, output multiplied by R = 2^16 mod q.
//
// Gentleman-Sande butterfly (FIPS 203 Algorithm 10). Transliterated line-for-
// line from pq-crystals/kyber ref/ntt.c :: invntt(). The trailing loop scales
// by f = 1441 = (R^2 / 128) mod q, which composes the 1/128 factor from the
// negacyclic butterflies with the Montgomery folding (see Bos et al.,
// verified in TCHES 2020, doi 10.13154/tches.v2020.i4.343-359).
// ---------------------------------------------------------------------------
__attribute__((noinline))
static void ntt_inverse(int16_t *r) {
    unsigned int start, len, j, k;
    int16_t t, zeta;
    const int16_t f = KYBER_INVNTT_F;   // 1441 = mont^2 / 128

    k = 127;
    #pragma clang loop unroll(disable)
    for (len = 2; len <= 128; len <<= 1) {
        #pragma clang loop unroll(disable)
        for (start = 0; start < 256; start = j + len) {
            zeta = ZETAS[k--];
            #pragma clang loop unroll(disable)
            for (j = start; j < start + len; j++) {
                t          = r[j];
                r[j]       = barrett_reduce((int16_t)(t + r[j + len]));
                r[j + len] = (int16_t)(r[j + len] - t);
                r[j + len] = fqmul(zeta, r[j + len]);
            }
        }
    }

    #pragma clang loop unroll(disable)
    for (j = 0; j < 256; j++) {
        r[j] = fqmul(r[j], f);
    }
}

// ---------------------------------------------------------------------------
// Base-case multiply: (a0 + a1 X)(b0 + b1 X) mod (X^2 - gamma).
// FIPS 203 Algorithm 12. All operands in Montgomery domain; output stays in
// Montgomery domain (an extra tomont pass would fold R^2 down to R, which is
// how pq-crystals leaves it - see poly_basemul_montgomery).
// ---------------------------------------------------------------------------
static inline void basemul(int16_t *r,
                           const int16_t *a,
                           const int16_t *b,
                           int16_t zeta) {
    r[0] = fqmul(a[1], b[1]);
    r[0] = fqmul(r[0], zeta);
    r[0] = (int16_t)(r[0] + fqmul(a[0], b[0]));
    r[1] = fqmul(a[0], b[1]);
    r[1] = (int16_t)(r[1] + fqmul(a[1], b[0]));
}

// ---------------------------------------------------------------------------
// Poly-level BaseMul over the whole 256-coefficient polynomial.
// Structure taken verbatim from pq-crystals ref/poly.c :: poly_basemul_montgomery:
//   for i in 0..64:
//     basemul(&r[4i],   &a[4i],   &b[4i],    zetas[64+i])
//     basemul(&r[4i+2], &a[4i+2], &b[4i+2], -zetas[64+i])
// The +/- zetas[64+i] pair captures the two conjugate roots of unity that the
// negacyclic NTT factors X^256 + 1 into: 128 quadratic factors X^2 - zeta^{2br(k)+1}.
// ---------------------------------------------------------------------------
__attribute__((noinline))
static void poly_basemul(int16_t *r,
                         const int16_t *a,
                         const int16_t *b) {
    #pragma clang loop unroll(disable)
    for (unsigned int i = 0; i < KYBER_N / 4; i++) {
        int16_t z = ZETAS[64 + i];
        basemul(&r[4 * i],     &a[4 * i],     &b[4 * i],      z);
        basemul(&r[4 * i + 2], &a[4 * i + 2], &b[4 * i + 2], (int16_t)(-z));
    }
}

// ---------------------------------------------------------------------------
// Coefficient-wise add/sub with Barrett reduction to keep coefficients in the
// canonical signed range (-q/2, q/2].
// ---------------------------------------------------------------------------
__attribute__((noinline))
static void poly_add(int16_t *r,
                     const int16_t *a,
                     const int16_t *b) {
    #pragma clang loop unroll(disable)
    for (unsigned int i = 0; i < KYBER_N; i++) {
        r[i] = barrett_reduce((int16_t)(a[i] + b[i]));
    }
}

__attribute__((noinline))
static void poly_sub(int16_t *r,
                     const int16_t *a,
                     const int16_t *b) {
    #pragma clang loop unroll(disable)
    for (unsigned int i = 0; i < KYBER_N; i++) {
        r[i] = barrett_reduce((int16_t)(a[i] - b[i]));
    }
}

// ---------------------------------------------------------------------------
// Kernel entry point.
//
// Contract:
//   in_a[0 .. 256*n_polys)             : input coefficient stream(s)
//   in_a[256 .. 512) (BASEMUL/ADD/SUB) : second operand polynomial B
//   in_ctrl[0]                         : mode (see MODE_* constants)
//   in_ctrl[1]                         : n_polys (1..3), used only by NTT/INTT
//   out_c                              : output coefficient stream
// ---------------------------------------------------------------------------
extern "C" void ntt(int16_t *in_a,
                    int16_t *in_ctrl,
                    int16_t *out_c) {
    const int16_t mode    = in_ctrl[0];
    const int16_t n_polys = in_ctrl[1];

    if (mode == MODE_NTT || mode == MODE_INTT) {
        // Copy up to n_polys polynomials into the output buffer and transform
        // each of them in place.
        int np = (int)n_polys;
        if (np < 1) np = 1;
        if (np > 3) np = 3;

        #pragma clang loop unroll(disable)
        for (int p = 0; p < np; p++) {
            int16_t *src = &in_a[p * KYBER_N];
            int16_t *dst = &out_c[p * KYBER_N];
            #pragma clang loop unroll(disable)
            for (int j = 0; j < KYBER_N; j++) {
                dst[j] = src[j];
            }
            if (mode == MODE_NTT) {
                ntt_forward(dst);
            } else {
                ntt_inverse(dst);
            }
        }
        return;
    }

    // MODE_BASEMUL / MODE_POLY_ADD / MODE_POLY_SUB: A in in_a[0..256),
    // B in in_a[256..512), result in out_c[0..256).
    int16_t *a = &in_a[0];
    int16_t *b = &in_a[KYBER_N];
    int16_t *r = &out_c[0];

    if (mode == MODE_BASEMUL) {
        poly_basemul(r, a, b);
    } else if (mode == MODE_POLY_ADD) {
        poly_add(r, a, b);
    } else if (mode == MODE_POLY_SUB) {
        poly_sub(r, a, b);
    } else {
        // Unknown mode - zero the output so the failure is observable.
        #pragma clang loop unroll(disable)
        for (int j = 0; j < KYBER_N; j++) {
            r[j] = 0;
        }
    }
}
