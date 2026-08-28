// SPDX-License-Identifier: Apache-2.0
// Private DR6 token layouts and operation-local helpers for ML-KEM-512 ML-KEM.Encaps.
#pragma once

#include <stdint.h>
#include <new>

#include "dr1_keccak_f1600.hpp"

#if defined(__clang__)
#define DR6_DISABLE_UNROLL _Pragma("clang loop unroll(disable)")
#else
#define DR6_DISABLE_UNROLL
#endif

namespace phoenix_sdr_dsp::pqc::dr6 {

constexpr uint32_t kN = 256u, kQ = 3329u, kRate128 = 168u, kRate256 = 136u, kRate512 = 72u;
constexpr uint32_t kBlockCap = 5u;
constexpr uint32_t kOk = 0u, kLimitExceeded = 1u, kBadDescriptor = 2u, kBadToken = 3u;

// Token Sizes
constexpr uint32_t kDerivationTokenBytes = 1168u;
constexpr uint32_t kNoiseTokenBytes = 3664u;
constexpr uint32_t kCol0TokenBytes = 4688u;
constexpr uint32_t kU0TokenBytes = 3472u;
constexpr uint32_t kCol1TokenBytes = 4496u;
constexpr uint32_t kResultBytes = 820u;

// Derivation Token Offsets (1168 B)
// Header: 16 B
constexpr uint32_t kDerivKBarOffset = 16u;  // 32 B
constexpr uint32_t kDerivROffset = 48u;     // 32 B
constexpr uint32_t kDerivRhoOffset = 80u;   // 32 B
constexpr uint32_t kDerivMOffset = 112u;    // 32 B
constexpr uint32_t kDerivT0Offset = 144u;   // 512 B
constexpr uint32_t kDerivT1Offset = 656u;   // 512 B

// Noise Token Offsets (3664 B)
// Header: 16 B
constexpr uint32_t kKBarOffset = 16u;       // 32 B
constexpr uint32_t kRhoOffset = 48u;        // 32 B
constexpr uint32_t kR0Offset = 80u;         // 512 B
constexpr uint32_t kR1Offset = 592u;        // 512 B
constexpr uint32_t kE1_0Offset = 1104u;     // 512 B
constexpr uint32_t kE1_1Offset = 1616u;     // 512 B
constexpr uint32_t kE2MuOffset = 2128u;     // 512 B
constexpr uint32_t kT0Offset = 2640u;       // 512 B
constexpr uint32_t kT1Offset = 3152u;       // 512 B

// Col0 Token Offsets (4688 B)
constexpr uint32_t kA00Offset = 3664u;      // 512 B
constexpr uint32_t kA10Offset = 4176u;      // 512 B

// U0 Token Offsets (3472 B)
// Header: 16 B
constexpr uint32_t kU0KBarOffset = 16u;     // 32 B
constexpr uint32_t kU0RhoOffset = 48u;      // 32 B
constexpr uint32_t kU0C1_0Offset = 80u;     // 320 B
constexpr uint32_t kU0R0Offset = 400u;      // 512 B
constexpr uint32_t kU0R1Offset = 912u;      // 512 B
constexpr uint32_t kU0E1_1Offset = 1424u;   // 512 B
constexpr uint32_t kU0E2MuOffset = 1936u;   // 512 B
constexpr uint32_t kU0T0Offset = 2448u;     // 512 B
constexpr uint32_t kU0T1Offset = 2960u;     // 512 B

// Col1 Token Offsets (4496 B)
constexpr uint32_t kA01Offset = 3472u;      // 512 B
constexpr uint32_t kA11Offset = 3984u;      // 512 B

// Result Offsets (820 B)
constexpr uint32_t kResultHeaderBytes = 20u;
constexpr uint32_t kResultCiphertextOffset = 20u; // 768 B
constexpr uint32_t kResultKeyOffset = 788u;        // 32 B

// FIPS 203 kZetas in 32-bit array
constexpr uint32_t kZetas[128] = {
    1u, 1729u, 2580u, 3289u, 2642u, 630u, 1897u, 848u,
    1062u, 1919u, 193u, 797u, 2786u, 3260u, 569u, 1746u,
    296u, 2447u, 1339u, 1476u, 3046u, 56u, 2240u, 1333u,
    1426u, 2094u, 535u, 2882u, 2393u, 2879u, 1974u, 821u,
    289u, 331u, 3253u, 1756u, 1197u, 2304u, 2277u, 2055u,
    650u, 1977u, 2513u, 632u, 2865u, 33u, 1320u, 1915u,
    2319u, 1435u, 807u, 452u, 1438u, 2868u, 1534u, 2402u,
    2647u, 2617u, 1481u, 648u, 2474u, 3110u, 1227u, 910u,
    17u, 2761u, 583u, 2649u, 1637u, 723u, 2288u, 1100u,
    1409u, 2662u, 3281u, 233u, 756u, 2156u, 3015u, 3050u,
    1703u, 1651u, 2789u, 1789u, 1847u, 952u, 1461u, 2687u,
    939u, 2308u, 2437u, 2388u, 733u, 2337u, 268u, 641u,
    1584u, 2298u, 2037u, 3220u, 375u, 2549u, 2090u, 1645u,
    1063u, 319u, 2773u, 757u, 2099u, 561u, 2466u, 2594u,
    2804u, 1092u, 403u, 1026u, 1143u, 2150u, 2775u, 886u,
    1722u, 1212u, 1874u, 1029u, 2110u, 2935u, 885u, 2154u,
};

static inline void clear_bytes(uint8_t *destination, uint32_t bytes) {
  DR6_DISABLE_UNROLL
  for (uint32_t index = 0; index < bytes; ++index) destination[index] = 0u;
}
static inline uint16_t load_le16(const uint8_t *in) {
  return static_cast<uint16_t>(in[0]) | (static_cast<uint16_t>(in[1]) << 8);
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
static inline bool word_aligned(const void *address) {
  constexpr uintptr_t kWordAlignmentMask = alignof(uint32_t) - 1u;
  return (reinterpret_cast<uintptr_t>(address) & kWordAlignmentMask) == 0;
}
static inline void store_pair_word(uint8_t *out, uint32_t pair, uint32_t a,
                                   uint32_t b) {
  const uint32_t word = (a & 0xffffu) | ((b & 0xffffu) << 16);
  ::new (static_cast<void *>(out + 4 * pair)) uint32_t(word);
}
static inline void copy_words(uint8_t *dest, const uint8_t *src, uint32_t num_bytes) {
  const uint32_t num_words = num_bytes >> 2;
  const uint32_t *src_w = reinterpret_cast<const uint32_t *>(src);
  uint32_t *dest_w = reinterpret_cast<uint32_t *>(dest);
  DR6_DISABLE_UNROLL
  for (uint32_t i = 0; i < num_words; ++i) {
    dest_w[i] = src_w[i];
  }
}

static inline bool valid_descriptor(const uint8_t descriptor[16]) {
  return descriptor[0] == 1u && descriptor[1] == 0x61u &&
         descriptor[2] == 0x52u && descriptor[4] == 2u &&
         descriptor[5] == 3u && descriptor[6] == 5u;
}

// SHA3-256 for 800 bytes
static inline void sha3_256_800(const uint8_t in[800], uint8_t out[32]) {
    alignas(8) uint8_t state[200];
    clear_bytes(state, sizeof(state));
    
    for (uint32_t b = 0; b < 5; ++b) {
        for (uint32_t i = 0; i < kRate256; ++i) {
            state[i] ^= in[b * kRate256 + i];
        }
        phoenix_sdr_dsp::pqc::dr1::keccak_f1600(state);
    }
    for (uint32_t i = 0; i < 120; ++i) {
        state[i] ^= in[5 * kRate256 + i];
    }
    state[120] ^= 0x06;
    state[135] ^= 0x80;
    phoenix_sdr_dsp::pqc::dr1::keccak_f1600(state);
    
    for (uint32_t i = 0; i < 32; ++i) out[i] = state[i];
    clear_bytes(state, sizeof(state));
}

// SHA3-512 for 64 bytes (m[32] || H(ek)[32])
static inline void sha3_512_64(const uint8_t in[64], uint8_t out[64]) {
    alignas(8) uint8_t state[200];
    clear_bytes(state, sizeof(state));
    
    for (uint32_t i = 0; i < 64; ++i) {
        state[i] ^= in[i];
    }
    state[64] ^= 0x06;
    state[71] ^= 0x80;
    phoenix_sdr_dsp::pqc::dr1::keccak_f1600(state);
    
    for (uint32_t i = 0; i < 64; ++i) out[i] = state[i];
    clear_bytes(state, sizeof(state));
}

// Montgomery and NTT primitives
static inline uint32_t mod_mul(uint32_t a, uint32_t b) {
  return (a * b) % kQ;
}

static inline void basemul_pos(uint32_t a0, uint32_t a1, uint32_t b0, uint32_t b1,
                               uint32_t gamma, uint32_t &r0, uint32_t &r1) {
  const uint32_t a0b0 = mod_mul(a0, b0);
  const uint32_t a1b1 = mod_mul(a1, b1);
  const uint32_t a1b1g = mod_mul(a1b1, gamma);
  const uint32_t s0 = a0b0 + a1b1g;
  r0 = s0 >= kQ ? s0 - kQ : s0;

  const uint32_t a0b1 = mod_mul(a0, b1);
  const uint32_t a1b0 = mod_mul(a1, b0);
  const uint32_t s1 = a0b1 + a1b0;
  r1 = s1 >= kQ ? s1 - kQ : s1;
}

template <uint32_t Len>
static inline void ntt_stage(uint32_t r[kN], uint32_t &k) {
  DR6_DISABLE_UNROLL
  for (uint32_t start = 0; start < kN; start += 2 * Len) {
    const uint32_t zeta = kZetas[k++];
    DR6_DISABLE_UNROLL
    for (uint32_t j = start; j < start + Len; ++j) {
      const uint32_t t = mod_mul(zeta, r[j + Len]);
      const uint32_t sum = r[j] + t;
      const uint32_t diff = r[j] + kQ - t;
      r[j] = sum >= kQ ? sum - kQ : sum;
      r[j + Len] = diff >= kQ ? diff - kQ : diff;
    }
  }
}

__attribute__((noinline)) static void ntt(uint32_t r[kN]) {
  uint32_t k = 1;
  ntt_stage<128>(r, k);
  ntt_stage<64>(r, k);
  ntt_stage<32>(r, k);
  ntt_stage<16>(r, k);
  ntt_stage<8>(r, k);
  ntt_stage<4>(r, k);
  ntt_stage<2>(r, k);
}

template <uint32_t Len>
static inline void intt_stage(uint32_t r[kN], uint32_t &k) {
  DR6_DISABLE_UNROLL
  for (uint32_t start = 0; start < kN; start += 2 * Len) {
    const uint32_t zeta = kZetas[k--];
    DR6_DISABLE_UNROLL
    for (uint32_t j = start; j < start + Len; ++j) {
      const uint32_t t = r[j];
      const uint32_t sum = t + r[j + Len];
      const uint32_t diff = r[j + Len] + kQ - t;
      r[j] = sum >= kQ ? sum - kQ : sum;
      r[j + Len] = mod_mul(zeta, diff);
    }
  }
}

__attribute__((noinline)) static void intt(uint32_t r[kN]) {
  uint32_t k = 127;
  intt_stage<2>(r, k);
  intt_stage<4>(r, k);
  intt_stage<8>(r, k);
  intt_stage<16>(r, k);
  intt_stage<32>(r, k);
  intt_stage<64>(r, k);
  intt_stage<128>(r, k);

  constexpr uint32_t kNInv = 3303u; // 128^-1 mod 3329
  DR6_DISABLE_UNROLL
  for (uint32_t i = 0; i < kN; ++i) {
    r[i] = mod_mul(r[i], kNInv);
  }
}

__attribute__((noinline)) static void ntt_multiply_accumulate(
    const uint8_t p0_raw[512], const uint8_t r0_raw[512],
    const uint8_t p1_raw[512], const uint8_t r1_raw[512],
    uint32_t acc[kN]) {
  DR6_DISABLE_UNROLL
  for (uint32_t i = 0; i < 64; ++i) {
    uint32_t gamma = kZetas[64 + i];

    uint32_t a0_0 = load_le16(p0_raw + 2 * (4 * i + 0));
    uint32_t a0_1 = load_le16(p0_raw + 2 * (4 * i + 1));
    uint32_t b0_0 = load_le16(r0_raw + 2 * (4 * i + 0));
    uint32_t b0_1 = load_le16(r0_raw + 2 * (4 * i + 1));
    uint32_t prod0_0, prod0_1;
    basemul_pos(a0_0, a0_1, b0_0, b0_1, gamma, prod0_0, prod0_1);

    uint32_t a0_2 = load_le16(p0_raw + 2 * (4 * i + 2));
    uint32_t a0_3 = load_le16(p0_raw + 2 * (4 * i + 3));
    uint32_t b0_2 = load_le16(r0_raw + 2 * (4 * i + 2));
    uint32_t b0_3 = load_le16(r0_raw + 2 * (4 * i + 3));
    uint32_t prod0_2, prod0_3;
    basemul_pos(a0_2, a0_3, b0_2, b0_3, kQ - gamma, prod0_2, prod0_3);

    uint32_t a1_0 = load_le16(p1_raw + 2 * (4 * i + 0));
    uint32_t a1_1 = load_le16(p1_raw + 2 * (4 * i + 1));
    uint32_t b1_0 = load_le16(r1_raw + 2 * (4 * i + 0));
    uint32_t b1_1 = load_le16(r1_raw + 2 * (4 * i + 1));
    uint32_t prod1_0, prod1_1;
    basemul_pos(a1_0, a1_1, b1_0, b1_1, gamma, prod1_0, prod1_1);

    uint32_t a1_2 = load_le16(p1_raw + 2 * (4 * i + 2));
    uint32_t a1_3 = load_le16(p1_raw + 2 * (4 * i + 3));
    uint32_t b1_2 = load_le16(r1_raw + 2 * (4 * i + 2));
    uint32_t b1_3 = load_le16(r1_raw + 2 * (4 * i + 3));
    uint32_t prod1_2, prod1_3;
    basemul_pos(a1_2, a1_3, b1_2, b1_3, kQ - gamma, prod1_2, prod1_3);

    const uint32_t s0 = prod0_0 + prod1_0;
    const uint32_t s1 = prod0_1 + prod1_1;
    const uint32_t s2 = prod0_2 + prod1_2;
    const uint32_t s3 = prod0_3 + prod1_3;

    acc[4 * i + 0] = s0 >= kQ ? s0 - kQ : s0;
    acc[4 * i + 1] = s1 >= kQ ? s1 - kQ : s1;
    acc[4 * i + 2] = s2 >= kQ ? s2 - kQ : s2;
    acc[4 * i + 3] = s3 >= kQ ? s3 - kQ : s3;
  }
}

static inline bool sample_matrix_store(const uint8_t rho[32], uint8_t column,
                                       uint8_t row, uint8_t out[2 * kN]) {
  if (!word_aligned(out)) return false;
  alignas(8) uint8_t state[200];
  clear_bytes(state, sizeof(state));
  DR6_DISABLE_UNROLL
  for (uint32_t i = 0; i < 32; ++i) state[i] ^= rho[i];
  state[32] ^= column; state[33] ^= row; state[34] ^= 0x1f;
  state[kRate128 - 1] ^= 0x80;
  phoenix_sdr_dsp::pqc::dr1::keccak_f1600(state);

  uint32_t accepted = 0, pending = 0;
  DR6_DISABLE_UNROLL
  for (uint32_t block = 0; block < kBlockCap && accepted < kN; ++block) {
    if (block != 0) phoenix_sdr_dsp::pqc::dr1::keccak_f1600(state);
    DR6_DISABLE_UNROLL
    for (uint32_t offset = 0; offset < kRate128 && accepted < kN; offset += 3) {
      const uint32_t d1 = state[offset] + 256u * (state[offset + 1] & 0x0fu);
      const uint32_t d2 = (state[offset + 1] >> 4) + 16u * state[offset + 2];
      if (d1 < kQ) {
        if ((accepted & 1u) == 0) pending = d1;
        else store_pair_word(out, accepted >> 1, pending, d1);
        ++accepted;
      }
      if (d2 < kQ && accepted < kN) {
        if ((accepted & 1u) == 0) pending = d2;
        else store_pair_word(out, accepted >> 1, pending, d2);
        ++accepted;
      }
    }
  }
  pending = 0;
  clear_bytes(state, sizeof(state));
  return accepted == kN;
}

static inline void shake256_prf_192(const uint8_t seed[32], uint8_t nonce, uint8_t output[192]) {
  alignas(8) uint8_t state[200];
  clear_bytes(state, sizeof(state));
  DR6_DISABLE_UNROLL
  for (uint32_t i = 0; i < 32; ++i) state[i] ^= seed[i];
  state[32] ^= nonce; state[33] ^= 0x1f; state[kRate256 - 1] ^= 0x80;
  phoenix_sdr_dsp::pqc::dr1::keccak_f1600(state);
  DR6_DISABLE_UNROLL
  for (uint32_t i = 0; i < kRate256; ++i) output[i] = state[i];
  phoenix_sdr_dsp::pqc::dr1::keccak_f1600(state);
  DR6_DISABLE_UNROLL
  for (uint32_t i = 0; i < (192 - kRate256); ++i) output[kRate256 + i] = state[i];
  clear_bytes(state, sizeof(state));
}

static inline void shake256_prf_128(const uint8_t seed[32], uint8_t nonce, uint8_t output[128]) {
  alignas(8) uint8_t state[200];
  clear_bytes(state, sizeof(state));
  DR6_DISABLE_UNROLL
  for (uint32_t i = 0; i < 32; ++i) state[i] ^= seed[i];
  state[32] ^= nonce; state[33] ^= 0x1f; state[kRate256 - 1] ^= 0x80;
  phoenix_sdr_dsp::pqc::dr1::keccak_f1600(state);
  DR6_DISABLE_UNROLL
  for (uint32_t i = 0; i < 128; ++i) output[i] = state[i];
  clear_bytes(state, sizeof(state));
}

static inline uint32_t bit_at(const uint8_t *bytes, uint32_t bit_index) {
  return (bytes[bit_index >> 3] >> (bit_index & 7u)) & 1u;
}

static inline void cbd3(const uint8_t prf[192], uint32_t out[kN]) {
  DR6_DISABLE_UNROLL
  for (uint32_t index = 0; index < kN; ++index) {
    const uint32_t bit = 6u * index;
    const int32_t value =
        static_cast<int32_t>(bit_at(prf, bit) + bit_at(prf, bit + 1u) +
                             bit_at(prf, bit + 2u)) -
        static_cast<int32_t>(bit_at(prf, bit + 3u) + bit_at(prf, bit + 4u) +
                             bit_at(prf, bit + 5u));
    out[index] = static_cast<uint32_t>(value) +
                 (static_cast<uint32_t>(value) >> 31) * kQ;
  }
}

static inline void cbd2(const uint8_t prf[128], uint32_t out[kN]) {
  DR6_DISABLE_UNROLL
  for (uint32_t index = 0; index < kN; ++index) {
    const uint32_t bit = 4u * index;
    const int32_t value =
        static_cast<int32_t>(bit_at(prf, bit) + bit_at(prf, bit + 1u)) -
        static_cast<int32_t>(bit_at(prf, bit + 2u) + bit_at(prf, bit + 3u));
    out[index] = static_cast<uint32_t>(value) +
                 (static_cast<uint32_t>(value) >> 31) * kQ;
  }
}

__attribute__((noinline)) static void sample_cbd3_ntt(const uint8_t r_seed[32], uint8_t nonce, uint8_t *out) {
  uint8_t prf[192];
  uint32_t coeff[kN];
  shake256_prf_192(r_seed, nonce, prf);
  cbd3(prf, coeff);
  ntt(coeff);
  DR6_DISABLE_UNROLL
  for (uint32_t pair = 0; pair < kN / 2; ++pair) {
    store_pair_word(out, pair, coeff[2 * pair], coeff[2 * pair + 1]);
  }
  clear_bytes(prf, sizeof(prf));
  clear_bytes(reinterpret_cast<uint8_t *>(coeff), sizeof(coeff));
}

__attribute__((noinline)) static void sample_cbd2_store(const uint8_t r_seed[32], uint8_t nonce, uint8_t *out) {
  uint8_t prf[128];
  uint32_t coeff[kN];
  shake256_prf_128(r_seed, nonce, prf);
  cbd2(prf, coeff);
  DR6_DISABLE_UNROLL
  for (uint32_t pair = 0; pair < kN / 2; ++pair) {
    store_pair_word(out, pair, coeff[2 * pair], coeff[2 * pair + 1]);
  }
  clear_bytes(prf, sizeof(prf));
  clear_bytes(reinterpret_cast<uint8_t *>(coeff), sizeof(coeff));
}

__attribute__((noinline)) static void sample_cbd2_add_mu(const uint8_t r_seed[32], const uint8_t msg32[32], uint8_t *out) {
  uint8_t prf[128];
  uint32_t coeff[kN];
  shake256_prf_128(r_seed, 4, prf);
  cbd2(prf, coeff);
  DR6_DISABLE_UNROLL
  for (uint32_t index = 0; index < kN; ++index) {
    uint32_t mu = bit_at(msg32, index) ? 1665u : 0u;
    const uint32_t s = coeff[index] + mu;
    coeff[index] = s >= kQ ? s - kQ : s;
  }
  DR6_DISABLE_UNROLL
  for (uint32_t pair = 0; pair < kN / 2; ++pair) {
    store_pair_word(out, pair, coeff[2 * pair], coeff[2 * pair + 1]);
  }
  clear_bytes(prf, sizeof(prf));
  clear_bytes(reinterpret_cast<uint8_t *>(coeff), sizeof(coeff));
}

static inline void decode_d12(const uint8_t in[384], uint8_t *out) {
  DR6_DISABLE_UNROLL
  for (uint32_t i = 0; i < 128; ++i) {
    const uint32_t b0 = in[3 * i + 0];
    const uint32_t b1 = in[3 * i + 1];
    const uint32_t b2 = in[3 * i + 2];
    const uint32_t t0 = b0 | ((b1 & 0x0fu) << 8);
    const uint32_t t1 = (b1 >> 4) | (b2 << 4);
    store_pair_word(out, i, t0, t1);
  }
}

static inline uint32_t compress10_coeff(uint32_t val) {
  return ((val * 161271u + 261911u) >> 19) & 0x3FFu;
}

static inline uint32_t compress4_coeff(uint32_t val) {
  return ((val * 315u + 32701u) >> 16) & 0x0Fu;
}

static inline void encode_16_coeffs(const uint32_t u[16], uint8_t out[20]) {
  const uint32_t c0 = compress10_coeff(u[0]);
  const uint32_t c1 = compress10_coeff(u[1]);
  const uint32_t c2 = compress10_coeff(u[2]);
  const uint32_t c3 = compress10_coeff(u[3]);
  const uint32_t c4 = compress10_coeff(u[4]);
  const uint32_t c5 = compress10_coeff(u[5]);
  const uint32_t c6 = compress10_coeff(u[6]);
  const uint32_t c7 = compress10_coeff(u[7]);
  const uint32_t c8 = compress10_coeff(u[8]);
  const uint32_t c9 = compress10_coeff(u[9]);
  const uint32_t c10 = compress10_coeff(u[10]);
  const uint32_t c11 = compress10_coeff(u[11]);
  const uint32_t c12 = compress10_coeff(u[12]);
  const uint32_t c13 = compress10_coeff(u[13]);
  const uint32_t c14 = compress10_coeff(u[14]);
  const uint32_t c15 = compress10_coeff(u[15]);

  uint32_t *out_words = reinterpret_cast<uint32_t *>(out);
  out_words[0] = c0 | (c1 << 10) | (c2 << 20) | ((c3 & 3) << 30);
  out_words[1] = (c3 >> 2) | (c4 << 8) | (c5 << 18) | ((c6 & 15) << 28);
  out_words[2] = (c6 >> 4) | (c7 << 6) | (c8 << 16) | ((c9 & 63) << 26);
  out_words[3] = (c9 >> 6) | (c10 << 4) | (c11 << 14) | ((c12 & 255) << 24);
  out_words[4] = (c12 >> 8) | (c13 << 2) | (c14 << 12) | (c15 << 22);
}

__attribute__((noinline)) static void compress10_encode(const uint32_t u[kN], uint8_t out[320]) {
  DR6_DISABLE_UNROLL
  for (uint32_t chunk = 0; chunk < 16; ++chunk) {
    encode_16_coeffs(u + chunk * 16, out + chunk * 20);
  }
}

__attribute__((noinline)) static void compress4_encode(const uint32_t v[kN], uint8_t out[128]) {
  DR6_DISABLE_UNROLL
  for (uint32_t i = 0; i < 128; ++i) {
    const uint32_t c0 = compress4_coeff(v[2 * i]);
    const uint32_t c1 = compress4_coeff(v[2 * i + 1]);
    out[i] = static_cast<uint8_t>(c0 | (c1 << 4));
  }
}

static inline uint32_t compute_crc32(const uint8_t *data, uint32_t length) {
  uint32_t crc = 0xFFFFFFFFu;
  DR6_DISABLE_UNROLL
  for (uint32_t i = 0; i < length; ++i) {
    crc ^= data[i];
    for (uint32_t j = 0; j < 8; ++j) {
      crc = (crc >> 1) ^ (0xEDB88320u & (-(crc & 1u)));
    }
  }
  return ~crc;
}

} // namespace phoenix_sdr_dsp::pqc::dr6
