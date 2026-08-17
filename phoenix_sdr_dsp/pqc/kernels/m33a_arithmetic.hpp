// SPDX-License-Identifier: Apache-2.0
// Production-local M33a transform arithmetic for the DR0 resident graph.
//
// Adapted at baseline e77e7ed2783d88b5451394866d7ddfccd9db4f69 from the
// repository's silicon-validated M33a implementation.  It is intentionally
// self-contained in phoenix_sdr_dsp/pqc/kernels: production compilation does
// not include, import, or otherwise depend on any test-tree artifact.
//
// The constants, zeta table, forward NTT, pointwise Montgomery multiplication,
// inverse NTT, and defined low-32-bit Montgomery reduction are retained
// verbatim in arithmetic behavior.  In particular, mont_reduce reconstructs
// the signed low 32-bit QINV product without overflowing signed int64_t.
#pragma once

#include <cstdint>

namespace phoenix_sdr_dsp::pqc::m33a {


// Buffer sizes for aiecc kernel signature (matches M32b template).
constexpr int32_t N          = 256;   // polynomial degree
constexpr int32_t Q          = 8380417;
constexpr int32_t QINV       = 58728449;      // Q * QINV = 1 mod 2^32
constexpr int32_t MONT_R_MOD = 4193792;       // 2^32 mod Q
constexpr int32_t F_MONT     = 41978;         // mont^2 / 256 mod Q (signed)
constexpr int32_t MAX_COEFFS = 256;

// Montgomery-scaled zetas in bit-reversed order (signed int32 in (-q, q)).
// Generated as: zetas_mont[i] = center((1753^br8(i) * 2^32) mod q), zetas[0]=0.
// Verified identical to pq-crystals ref-C ntt.c for i in [1, 255].
static const int32_t ZETAS_MONT[256] = {
             0,      25847,   -2608894,    -518909,     237124,    -777960,    -876248,     466468,
       1826347,    2353451,    -359251,   -2091905,    3119733,   -2884855,    3111497,    2680103,
       2725464,    1024112,   -1079900,    3585928,    -549488,   -1119584,    2619752,   -2108549,
      -2118186,   -3859737,   -1399561,   -3277672,    1757237,     -19422,    4010497,     280005,
       2706023,      95776,    3077325,    3530437,   -1661693,   -3592148,   -2537516,    3915439,
      -3861115,   -3043716,    3574422,   -2867647,    3539968,    -300467,    2348700,    -539299,
      -1699267,   -1643818,    3505694,   -3821735,    3507263,   -2140649,   -1600420,    3699596,
        811944,     531354,     954230,    3881043,    3900724,   -2556880,    2071892,   -2797779,
      -3930395,   -1528703,   -3677745,   -3041255,   -1452451,    3475950,    2176455,   -1585221,
      -1257611,    1939314,   -4083598,   -1000202,   -3190144,   -3157330,   -3632928,     126922,
       3412210,    -983419,    2147896,    2715295,   -2967645,   -3693493,    -411027,   -2477047,
       -671102,   -1228525,     -22981,   -1308169,    -381987,    1349076,    1852771,   -1430430,
      -3343383,     264944,     508951,    3097992,      44288,   -1100098,     904516,    3958618,
      -3724342,      -8578,    1653064,   -3249728,    2389356,    -210977,     759969,   -1316856,
        189548,   -3553272,    3159746,   -1851402,   -2409325,    -177440,    1315589,    1341330,
       1285669,   -1584928,    -812732,   -1439742,   -3019102,   -3881060,   -3628969,    3839961,
       2091667,    3407706,    2316500,    3817976,   -3342478,    2244091,   -2446433,   -3562462,
        266997,    2434439,   -1235728,    3513181,   -3520352,   -3759364,   -1197226,   -3193378,
        900702,    1859098,     909542,     819034,     495491,   -1613174,     -43260,    -522500,
       -655327,   -3122442,    2031748,    3207046,   -3556995,    -525098,    -768622,   -3595838,
        342297,     286988,   -2437823,    4108315,    3437287,   -3342277,    1735879,     203044,
       2842341,    2691481,   -2590150,    1265009,    4055324,    1247620,    2486353,    1595974,
      -3767016,    1250494,    2635921,   -3548272,   -2994039,    1869119,    1903435,   -1050970,
      -1333058,    1237275,   -3318210,   -1430225,    -451100,    1312455,    3306115,   -1962642,
      -1279661,    1917081,   -2546312,   -1374803,    1500165,     777191,    2235880,    3406031,
       -542412,   -2831860,   -1671176,   -1846953,   -2584293,   -3724270,     594136,   -3776993,
      -2013608,    2432395,    2454455,    -164721,    1957272,    3369112,     185531,   -1207385,
      -3183426,     162844,    1616392,    3014001,     810149,    1652634,   -3694233,   -1799107,
      -3038916,    3523897,    3866901,     269760,    2213111,    -975884,    1717735,     472078,
       -426683,    1723600,   -1803090,    1910376,   -1667432,   -1104333,    -260646,   -3833893,
      -2939036,   -2235985,    -420899,   -2286327,     183443,    -976891,    1612842,   -3545687,
       -554416,    3919660,     -48306,   -1362209,    3937738,    1400424,    -846154,    1976782
};

// Montgomery reduction: input a in (-2^31 * q, 2^31 * q), returns t
// with t congruent to a * R^-1 mod q, t in (-q, q).
static inline int32_t mont_reduce(int64_t a) {
    // Dilithium needs the signed low 32-bit word of `a`, multiplied by QINV.
    // Express that conversion explicitly instead of overflowing signed int64
    // in `a * QINV` before narrowing.
    const uint32_t low = static_cast<uint32_t>(static_cast<uint64_t>(a));
    const uint32_t t_low = static_cast<uint32_t>(
        static_cast<uint64_t>(low) * static_cast<uint32_t>(QINV));
    const int64_t t =
        t_low <= 0x7fffffffU ? static_cast<int64_t>(t_low)
                             : static_cast<int64_t>(t_low) - (INT64_C(1) << 32);
    return static_cast<int32_t>(
        (a - t * static_cast<int64_t>(Q)) >> 32);
}

// Reduce to representative in (-6283009, 6283008) then to (-q/2, q/2].
static inline int32_t reduce32(int32_t a) {
    int32_t t = (a + (1 << 22)) >> 23;
    t = a - t * Q;
    return t;
}

// MODE_NTT: forward NTT in place. Input: standard order coeffs (signed int32).
// Output: bit-reversed NTT domain coeffs (signed int32, |c| < 9q on entry
// bound not required; typical usage keeps coeffs in (-q, q)).
static void ntt_kernel(int32_t coeffs[N]) {
    int32_t len, start, j, k;
    int32_t zeta, t;
    k = 0;
    for (len = 128; len > 0; len >>= 1) {
        for (start = 0; start < N; start = j + len) {
            zeta = ZETAS_MONT[++k];
            for (j = start; j < start + len; ++j) {
                t = mont_reduce(static_cast<int64_t>(zeta) * coeffs[j + len]);
                coeffs[j + len] = coeffs[j] - t;
                coeffs[j]       = coeffs[j] + t;
            }
        }
    }
}

// MODE_INTT: inverse NTT in place. Input: bit-reversed NTT-domain coeffs.
// Output: standard-order coeffs multiplied by F_MONT (= mont^2/n).
static void invntt_kernel(int32_t coeffs[N]) {
    int32_t start, len, j, k;
    int32_t t, zeta;
    k = 256;
    for (len = 1; len < N; len <<= 1) {
        for (start = 0; start < N; start = j + len) {
            zeta = -ZETAS_MONT[--k];
            for (j = start; j < start + len; ++j) {
                t = coeffs[j];
                coeffs[j]       = t + coeffs[j + len];
                coeffs[j + len] = t - coeffs[j + len];
                coeffs[j + len] = mont_reduce(static_cast<int64_t>(zeta) * coeffs[j + len]);
            }
        }
    }
    for (j = 0; j < N; ++j) {
        coeffs[j] = mont_reduce(static_cast<int64_t>(F_MONT) * coeffs[j]);
    }
}

// MODE_BASEMUL: pointwise Montgomery multiply. c[i] = (a[i] * b[i]) * R^-1 mod q.
static void basemul_kernel(int32_t out_c[N], const int32_t a[N], const int32_t b[N]) {
    for (int32_t i = 0; i < N; ++i) {
        out_c[i] = mont_reduce(static_cast<int64_t>(a[i]) * static_cast<int64_t>(b[i]));
    }
}

// MODE_REDUCE: reduce coeffs to representative in (-q/2, q/2].
static void reduce_kernel(int32_t coeffs[N]) {
    for (int32_t i = 0; i < N; ++i) {
        coeffs[i] = reduce32(coeffs[i]);
    }
}


}  // namespace phoenix_sdr_dsp::pqc::m33a
