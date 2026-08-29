// SPDX-License-Identifier: Apache-2.0
// Microarchitectural and mathematical header for NIST FIPS 204 ML-DSA-44 on AMD Phoenix AIE2.

#ifndef PHOENIX_SDR_DSP_PQC_KERNELS_DR11_MLDSA44_INTERNAL_HPP_
#define PHOENIX_SDR_DSP_PQC_KERNELS_DR11_MLDSA44_INTERNAL_HPP_

#include <stdint.h>
#include <new>

#include "dr1_keccak_f1600.hpp"

#if defined(__clang__)
#define DR11_DISABLE_UNROLL _Pragma("clang loop unroll(disable)")
#else
#define DR11_DISABLE_UNROLL
#endif

namespace phoenix_sdr_dsp::pqc::dr11 {

constexpr uint32_t kN = 256;
constexpr int32_t kQ = 8380417;
constexpr int32_t kQInv = 58728449;      // Q * QInv = 1 mod 2^32
constexpr int32_t kMontRMod = 4193792;   // 2^32 mod Q
constexpr int32_t kFMont = 41978;        // mont^2 / 256 mod Q (signed)
constexpr int32_t kD = 13;
constexpr int32_t kPow2D = 8192;         // 1 << 13
constexpr int32_t kPow2DHalf = 4096;     // 1 << 12

// Zetas in Montgomery domain (bit-reversed order)
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

static inline void clear_bytes(void *dest, uint32_t bytes) {
  volatile uint8_t *out = static_cast<volatile uint8_t *>(dest);
  DR11_DISABLE_UNROLL
  for (uint32_t i = 0; i < bytes; ++i) out[i] = 0;
}

static inline uint32_t load_le32(const uint8_t *in) {
  return static_cast<uint32_t>(in[0]) | (static_cast<uint32_t>(in[1]) << 8) |
         (static_cast<uint32_t>(in[2]) << 16) | (static_cast<uint32_t>(in[3]) << 24);
}

static inline void store_le32(uint8_t *out, uint32_t val) {
  out[0] = static_cast<uint8_t>(val & 0xFFu);
  out[1] = static_cast<uint8_t>((val >> 8) & 0xFFu);
  out[2] = static_cast<uint8_t>((val >> 16) & 0xFFu);
  out[3] = static_cast<uint8_t>((val >> 24) & 0xFFu);
}

static inline uint32_t compute_crc32(const uint8_t *data, uint32_t length) {
  uint32_t crc = 0xFFFFFFFFu;
  DR11_DISABLE_UNROLL
  for (uint32_t i = 0; i < length; ++i) {
    crc ^= data[i];
    DR11_DISABLE_UNROLL
    for (uint32_t j = 0; j < 8; ++j) {
      crc = (crc >> 1) ^ (0xEDB88320u & (-(crc & 1u)));
    }
  }
  return ~crc;
}

// Montgomery reduction: input in (-2^31 * q, 2^31 * q), returns t congruent to a * R^-1 mod q in (-q, q)
static inline int32_t mont_reduce(int64_t a) {
  const uint32_t low = static_cast<uint32_t>(static_cast<uint64_t>(a));
  const uint32_t t_low = static_cast<uint32_t>(static_cast<uint64_t>(low) * static_cast<uint32_t>(kQInv));
  const int64_t t = (t_low <= 0x7FFFFFFFUL) ? static_cast<int64_t>(t_low)
                                           : static_cast<int64_t>(t_low) - (INT64_C(1) << 32);
  return static_cast<int32_t>((a - t * static_cast<int64_t>(kQ)) >> 32);
}

// Canonicalize to [0, q)
static inline int32_t canonicalize(int32_t r) {
  int32_t x = r % kQ;
  if (x < 0) x += kQ;
  return x;
}

// Forward NTT on 256 coefficients (in place)
__attribute__((noinline)) static void ntt_kernel(int32_t coeffs[256]) {
  uint32_t k = 0;
  DR11_DISABLE_UNROLL
  for (uint32_t stage = 0; stage < 8; ++stage) {
    const uint32_t len = 128u >> stage;
    DR11_DISABLE_UNROLL
    for (uint32_t start = 0; start < 256; start += 2 * len) {
      const int32_t zeta = ZETAS_MONT[++k];
      DR11_DISABLE_UNROLL
      for (uint32_t j = start; j < start + len; ++j) {
        const int32_t t = mont_reduce(static_cast<int64_t>(zeta) * coeffs[j + len]);
        coeffs[j + len] = coeffs[j] - t;
        coeffs[j]       = coeffs[j] + t;
      }
    }
  }
}

// Inverse NTT on 256 coefficients (in place)
__attribute__((noinline)) static void invntt_kernel(int32_t coeffs[256]) {
  uint32_t k = 256;
  DR11_DISABLE_UNROLL
  for (uint32_t stage = 0; stage < 8; ++stage) {
    const uint32_t len = 1u << stage;
    DR11_DISABLE_UNROLL
    for (uint32_t start = 0; start < 256; start += 2 * len) {
      const int32_t zeta = -ZETAS_MONT[--k];
      DR11_DISABLE_UNROLL
      for (uint32_t j = start; j < start + len; ++j) {
        const int32_t t = coeffs[j];
        coeffs[j]       = t + coeffs[j + len];
        coeffs[j + len] = t - coeffs[j + len];
        coeffs[j + len] = mont_reduce(static_cast<int64_t>(zeta) * coeffs[j + len]);
      }
    }
  }
  DR11_DISABLE_UNROLL
  for (uint32_t j = 0; j < 256; ++j) {
    coeffs[j] = mont_reduce(static_cast<int64_t>(kFMont) * coeffs[j]);
    coeffs[j] = canonicalize(coeffs[j]);
  }
}

// Pointwise Montgomery product: c[i] = a[i] * b[i] * R^-1 mod q
__attribute__((noinline)) static void basemul(int32_t c[256], const int32_t a[256], const int32_t b[256]) {
  DR11_DISABLE_UNROLL
  for (int32_t i = 0; i < 256; ++i) {
    c[i] = mont_reduce(static_cast<int64_t>(a[i]) * static_cast<int64_t>(b[i]));
  }
}

// Power2Round: r in Z_q -> (r1, r0) with r = r1 * 2^d + r0 mod q, r0 in (-2^(d-1), 2^(d-1)]
static inline void power2round(int32_t r_in, int32_t &r1_out, int32_t &r0_out) {
  int32_t rp = canonicalize(r_in);
  int32_t r0 = rp & (kPow2D - 1);
  if (r0 > kPow2DHalf) r0 -= kPow2D;
  r1_out = (rp - r0) >> kD;
  r0_out = r0;
}

// Sample in bounded range [-2, 2] from SHAKE256(sigma || nonce)
__attribute__((noinline)) static void sample_bounded_eta2(const uint8_t sigma[64], uint16_t nonce, int32_t out[256]) {
  alignas(8) uint8_t state[200];
  clear_bytes(state, sizeof(state));

  DR11_DISABLE_UNROLL
  for (uint32_t i = 0; i < 64; ++i) state[i] = sigma[i];
  state[64] = static_cast<uint8_t>(nonce & 0xFF);
  state[65] = static_cast<uint8_t>((nonce >> 8) & 0xFF);
  state[66] ^= 0x1F;
  state[135] ^= 0x80;
  phoenix_sdr_dsp::pqc::dr1::keccak_f1600(state);

  uint32_t accepted = 0;
  while (accepted < 256) {
    DR11_DISABLE_UNROLL
    for (uint32_t i = 0; i < 136 && accepted < 256; ++i) {
      const uint8_t b = state[i];
      const uint8_t n0 = b & 0x0F;
      const uint8_t n1 = b >> 4;
      if (n0 < 15 && accepted < 256) {
        out[accepted++] = 2 - static_cast<int32_t>(n0 % 5);
      }
      if (n1 < 15 && accepted < 256) {
        out[accepted++] = 2 - static_cast<int32_t>(n1 % 5);
      }
    }
    if (accepted < 256) {
      phoenix_sdr_dsp::pqc::dr1::keccak_f1600(state);
    }
  }
  clear_bytes(state, sizeof(state));
}

// ExpandA: SampleNTT for A[row, col] from SHAKE128(rho || col || row)
__attribute__((noinline)) static void expand_a_matrix_entry(const uint8_t rho[32], uint8_t col, uint8_t row, int32_t out[256]) {
  alignas(8) uint8_t state[200];
  clear_bytes(state, sizeof(state));

  DR11_DISABLE_UNROLL
  for (uint32_t i = 0; i < 32; ++i) state[i] = rho[i];
  state[32] = col;
  state[33] = row;
  state[34] ^= 0x1F;
  state[167] ^= 0x80;
  phoenix_sdr_dsp::pqc::dr1::keccak_f1600(state);

  uint32_t accepted = 0;
  while (accepted < 256) {
    DR11_DISABLE_UNROLL
    for (uint32_t i = 0; i < 168 && accepted < 256; i += 3) {
      const uint32_t c = (static_cast<uint32_t>(state[i]) |
                          (static_cast<uint32_t>(state[i + 1]) << 8) |
                          (static_cast<uint32_t>(state[i + 2]) << 16)) & 0x7FFFFFu;
      if (c < static_cast<uint32_t>(kQ)) {
        out[accepted++] = static_cast<int32_t>(c);
      }
    }
    if (accepted < 256) {
      phoenix_sdr_dsp::pqc::dr1::keccak_f1600(state);
    }
  }
  clear_bytes(state, sizeof(state));
}

// Encode pk t1: 256 coeffs in [0, 1023] (10 bits) -> 320 bytes
static void encode_pk_t1_poly(const int32_t t1[256], uint8_t out[320]) {
  DR11_DISABLE_UNROLL
  for (uint32_t i = 0; i < 256; i += 4) {
    const uint32_t c0 = static_cast<uint32_t>(t1[i + 0]);
    const uint32_t c1 = static_cast<uint32_t>(t1[i + 1]);
    const uint32_t c2 = static_cast<uint32_t>(t1[i + 2]);
    const uint32_t c3 = static_cast<uint32_t>(t1[i + 3]);
    const uint32_t out_idx = (i / 4) * 5;
    out[out_idx + 0] = static_cast<uint8_t>(c0 & 0xFF);
    out[out_idx + 1] = static_cast<uint8_t>((c0 >> 8) | ((c1 & 0x3F) << 2));
    out[out_idx + 2] = static_cast<uint8_t>((c1 >> 6) | ((c2 & 0x0F) << 4));
    out[out_idx + 3] = static_cast<uint8_t>((c2 >> 4) | ((c3 & 0x03) << 6));
    out[out_idx + 4] = static_cast<uint8_t>(c3 >> 2);
  }
}

// Encode sk s in [-2, 2]: (2 - c) in [0, 4] (3 bits) -> 96 bytes
static void encode_sk_s_poly(const int32_t s[256], uint8_t out[96]) {
  DR11_DISABLE_UNROLL
  for (uint32_t i = 0; i < 256; i += 8) {
    uint8_t t[8];
    for (uint32_t j = 0; j < 8; ++j) {
      t[j] = static_cast<uint8_t>(2 - s[i + j]);
    }
    const uint32_t out_idx = (i / 8) * 3;
    out[out_idx + 0] = static_cast<uint8_t>(t[0] | (t[1] << 3) | ((t[2] & 3) << 6));
    out[out_idx + 1] = static_cast<uint8_t>((t[2] >> 2) | (t[3] << 1) | (t[4] << 4) | ((t[5] & 1) << 7));
    out[out_idx + 2] = static_cast<uint8_t>((t[5] >> 1) | (t[6] << 2) | (t[7] << 5));
  }
}

// Encode sk t0 in [-2^12, 2^12]: (2^12 - t0) in [0, 8191] (13 bits) -> 416 bytes
static void encode_sk_t0_poly(const int32_t t0[256], uint8_t out[416]) {
  DR11_DISABLE_UNROLL
  for (uint32_t i = 0; i < 256; i += 8) {
    uint32_t t[8];
    for (uint32_t j = 0; j < 8; ++j) {
      t[j] = static_cast<uint32_t>(kPow2DHalf - t0[i + j]);
    }
    const uint32_t out_idx = (i / 8) * 13;
    out[out_idx + 0]  = static_cast<uint8_t>(t[0] & 0xFF);
    out[out_idx + 1]  = static_cast<uint8_t>((t[0] >> 8) | ((t[1] & 0x07) << 5));
    out[out_idx + 2]  = static_cast<uint8_t>((t[1] >> 3) & 0xFF);
    out[out_idx + 3]  = static_cast<uint8_t>((t[1] >> 11) | ((t[2] & 0x3F) << 2));
    out[out_idx + 4]  = static_cast<uint8_t>((t[2] >> 6) | ((t[3] & 0x01) << 7));
    out[out_idx + 5]  = static_cast<uint8_t>((t[3] >> 1) & 0xFF);
    out[out_idx + 6]  = static_cast<uint8_t>((t[3] >> 9) | ((t[4] & 0x0F) << 4));
    out[out_idx + 7]  = static_cast<uint8_t>((t[4] >> 4) & 0xFF);
    out[out_idx + 8]  = static_cast<uint8_t>((t[4] >> 12) | ((t[5] & 0x7F) << 1));
    out[out_idx + 9]  = static_cast<uint8_t>((t[5] >> 7) | ((t[6] & 0x03) << 6));
    out[out_idx + 10] = static_cast<uint8_t>((t[6] >> 2) & 0xFF);
    out[out_idx + 11] = static_cast<uint8_t>((t[6] >> 10) | ((t[7] & 0x1F) << 3));
    out[out_idx + 12] = static_cast<uint8_t>(t[7] >> 5);
  }
}

} // namespace phoenix_sdr_dsp::pqc::dr11

#endif // PHOENIX_SDR_DSP_PQC_KERNELS_DR11_MLDSA44_INTERNAL_HPP_
