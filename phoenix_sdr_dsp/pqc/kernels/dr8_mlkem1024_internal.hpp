// SPDX-License-Identifier: Apache-2.0
// Private DR8 token layouts and operation-local helpers for ML-KEM-1024 (k=4, eta1=2, eta2=2, du=11, dv=5).
#pragma once

#include <stdint.h>
#include <new>

#include "dr1_keccak_f1600.hpp"

#if defined(__clang__)
#define DR8_DISABLE_UNROLL _Pragma("clang loop unroll(disable)")
#else
#define DR8_DISABLE_UNROLL
#endif

namespace phoenix_sdr_dsp::pqc::dr8_1024 {

constexpr uint32_t kN = 256u, kQ = 3329u, kRate128 = 168u, kRate256 = 136u, kRate512 = 72u;
constexpr uint32_t kBlockCap = 5u;
constexpr uint32_t kOk = 0u, kLimitExceeded = 1u, kBadDescriptor = 2u, kBadToken = 3u;

// Dimensions for ML-KEM-1024
constexpr uint32_t kK = 4u;
constexpr uint32_t kEkBytes = 1568u;  // 4 * 384 + 32
constexpr uint32_t kDkPkeBytes = 1536u; // 4 * 384
constexpr uint32_t kDkBytes = 3168u;  // 1536 + 1568 + 32 + 32
constexpr uint32_t kCBytes = 1568u;   // 4 * 352 + 160
constexpr uint32_t kKeyBytes = 32u;

// kZetas table
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
  DR8_DISABLE_UNROLL
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
static inline void store_pair_word(uint8_t *out, uint32_t pair, uint32_t a, uint32_t b) {
  const uint32_t word = (a & 0xffffu) | ((b & 0xffffu) << 16);
  ::new (static_cast<void *>(out + 4 * pair)) uint32_t(word);
}
static inline void copy_words(uint8_t *dest, const uint8_t *src, uint32_t num_bytes) {
  const uint32_t num_words = num_bytes >> 2;
  const uint32_t *src_w = reinterpret_cast<const uint32_t *>(src);
  uint32_t *dest_w = reinterpret_cast<uint32_t *>(dest);
  DR8_DISABLE_UNROLL
  for (uint32_t i = 0; i < num_words; ++i) dest_w[i] = src_w[i];
}

static inline uint32_t compute_crc32(const uint8_t *data, uint32_t length) {
  uint32_t crc = 0xFFFFFFFFu;
  DR8_DISABLE_UNROLL
  for (uint32_t i = 0; i < length; ++i) {
    crc ^= data[i];
    DR8_DISABLE_UNROLL
    for (uint32_t j = 0; j < 8; ++j) {
      crc = (crc >> 1) ^ (0xEDB88320u & (-(crc & 1u)));
    }
  }
  return ~crc;
}

// SHA3-512 for G (32 B || 1 B or 32 B || 32 B)
static inline void sha3_512_33(const uint8_t in[33], uint8_t out[64]) {
  alignas(8) uint8_t state[200];
  clear_bytes(state, sizeof(state));
  for (uint32_t i = 0; i < 33; ++i) state[i] ^= in[i];
  state[33] ^= 0x06; state[71] ^= 0x80;
  phoenix_sdr_dsp::pqc::dr1::keccak_f1600(state);
  for (uint32_t i = 0; i < 64; ++i) out[i] = state[i];
  clear_bytes(state, sizeof(state));
}

static inline void sha3_512_64(const uint8_t in[64], uint8_t out[64]) {
  alignas(8) uint8_t state[200];
  clear_bytes(state, sizeof(state));
  for (uint32_t i = 0; i < 64; ++i) state[i] ^= in[i];
  state[64] ^= 0x06; state[71] ^= 0x80;
  phoenix_sdr_dsp::pqc::dr1::keccak_f1600(state);
  for (uint32_t i = 0; i < 64; ++i) out[i] = state[i];
  clear_bytes(state, sizeof(state));
}

// SHA3-256 for H(ek) (1568 B -> 32 B for ML-KEM-1024)
static inline void sha3_256_ek1024(const uint8_t ek[1568], uint8_t out[32]) {
  alignas(8) uint8_t state[200];
  clear_bytes(state, sizeof(state));

  uint32_t *state_w = reinterpret_cast<uint32_t *>(state);
  const uint32_t *ek_w = reinterpret_cast<const uint32_t *>(ek);

  // 1568 bytes = 11 blocks of 136 bytes (1496 B) + 72 bytes remainder
  for (uint32_t b = 0; b < 11; ++b) {
    const uint32_t w_off = b * 34;
    DR8_DISABLE_UNROLL
    for (uint32_t i = 0; i < 34; ++i) state_w[i] ^= ek_w[w_off + i];
    phoenix_sdr_dsp::pqc::dr1::keccak_f1600(state);
  }

  // Final 72 bytes (18 words) + padding 0x06 .. 0x80
  const uint32_t rem_w_off = 11 * 34; // 374 words = 1496 bytes
  DR8_DISABLE_UNROLL
  for (uint32_t i = 0; i < 18; ++i) state_w[i] ^= ek_w[rem_w_off + i];
  state[72] ^= 0x06; state[135] ^= 0x80;
  phoenix_sdr_dsp::pqc::dr1::keccak_f1600(state);

  for (uint32_t i = 0; i < 8; ++i) reinterpret_cast<uint32_t *>(out)[i] = state_w[i];
  clear_bytes(state, sizeof(state));
}

// SHAKE256 for J(z || c) on ML-KEM-1024 (32 B || 1568 B = 1600 B -> 32 B)
__attribute__((noinline)) static void shake256_1600(const uint8_t z[32], const uint8_t c[1568], uint8_t out[32]) {
  alignas(8) uint8_t state[200];
  clear_bytes(state, sizeof(state));

  uint32_t *state_w = reinterpret_cast<uint32_t *>(state);
  const uint32_t *z_w = reinterpret_cast<const uint32_t *>(z);
  const uint32_t *c_w = reinterpret_cast<const uint32_t *>(c);

  // Block 0: z[32] || c[0..103] (136 bytes = 34 words)
  DR8_DISABLE_UNROLL
  for (uint32_t i = 0; i < 8; ++i) state_w[i] ^= z_w[i];
  DR8_DISABLE_UNROLL
  for (uint32_t i = 0; i < 26; ++i) state_w[8 + i] ^= c_w[i];
  phoenix_sdr_dsp::pqc::dr1::keccak_f1600(state);

  // Blocks 1..10: c[104 + (b-1)*136 .. 104 + b*136] (10 blocks = 1360 B, reaching byte 1464 = 366 words)
  DR8_DISABLE_UNROLL
  for (uint32_t b = 1; b <= 10; ++b) {
    const uint32_t w_off = 26 + (b - 1) * 34;
    DR8_DISABLE_UNROLL
    for (uint32_t i = 0; i < 34; ++i) state_w[i] ^= c_w[w_off + i];
    phoenix_sdr_dsp::pqc::dr1::keccak_f1600(state);
  }

  // Block 11: remaining 104 bytes (26 words) of c (1464..1567) + padding 0x1f .. 0x80
  const uint32_t rem_w_off = 26 + 10 * 34; // 366 words
  DR8_DISABLE_UNROLL
  for (uint32_t i = 0; i < 26; ++i) state_w[i] ^= c_w[rem_w_off + i];
  state[104] ^= 0x1f; state[135] ^= 0x80;
  phoenix_sdr_dsp::pqc::dr1::keccak_f1600(state);

  DR8_DISABLE_UNROLL
  for (uint32_t i = 0; i < 8; ++i) reinterpret_cast<uint32_t *>(out)[i] = state_w[i];
  clear_bytes(state, sizeof(state));
}

// PRF for eta=2 (128 B output)
static inline void shake256_prf_128(const uint8_t seed[32], uint8_t nonce, uint8_t out[128]) {
  alignas(8) uint8_t state[200];
  clear_bytes(state, sizeof(state));
  for (uint32_t i = 0; i < 32; ++i) state[i] ^= seed[i];
  state[32] ^= nonce; state[33] ^= 0x1f; state[135] ^= 0x80;
  phoenix_sdr_dsp::pqc::dr1::keccak_f1600(state);
  for (uint32_t i = 0; i < 128; ++i) out[i] = state[i];
  clear_bytes(state, sizeof(state));
}

// CBD2 for ML-KEM-1024
static inline void cbd2(const uint8_t prf[128], uint32_t out[kN]) {
  DR8_DISABLE_UNROLL
  for (uint32_t i = 0; i < 128; ++i) {
    const uint8_t byte = prf[i];
    const int32_t v0 = static_cast<int32_t>((byte & 1u) + ((byte >> 1) & 1u)) -
                       static_cast<int32_t>(((byte >> 2) & 1u) + ((byte >> 3) & 1u));
    const int32_t v1 = static_cast<int32_t>(((byte >> 4) & 1u) + ((byte >> 5) & 1u)) -
                       static_cast<int32_t>(((byte >> 6) & 1u) + ((byte >> 7) & 1u));
    out[2 * i + 0] = static_cast<uint32_t>(v0) + (static_cast<uint32_t>(v0) >> 31) * kQ;
    out[2 * i + 1] = static_cast<uint32_t>(v1) + (static_cast<uint32_t>(v1) >> 31) * kQ;
  }
}

static inline uint32_t mod_mul(uint32_t a, uint32_t b) {
  return (a * b) % kQ;
}

static inline void basemul_pos(uint32_t a0, uint32_t a1, uint32_t b0,
                               uint32_t b1, uint32_t zeta, uint32_t &r0,
                               uint32_t &r1) {
  const uint32_t prod = mod_mul(mod_mul(a1, b1), zeta);
  r0 = (mod_mul(a0, b0) + prod) % kQ;
  r1 = (mod_mul(a0, b1) + mod_mul(a1, b0)) % kQ;
}

template <uint32_t Len>
static inline void ntt_stage(uint32_t r[kN], uint32_t &k) {
  DR8_DISABLE_UNROLL
  for (uint32_t start = 0; start < kN; start += 2 * Len) {
    const uint32_t zeta = kZetas[k++];
    DR8_DISABLE_UNROLL
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
  DR8_DISABLE_UNROLL
  for (uint32_t start = 0; start < kN; start += 2 * Len) {
    const uint32_t zeta = kZetas[k--];
    DR8_DISABLE_UNROLL
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
  DR8_DISABLE_UNROLL
  for (uint32_t i = 0; i < kN; ++i) {
    r[i] = mod_mul(r[i], kNInv);
  }
}

// 4-way NTT multiply-accumulate for k=4
__attribute__((noinline)) static void ntt_multiply_accumulate_4(
    const uint8_t p0_raw[512], const uint8_t r0_raw[512],
    const uint8_t p1_raw[512], const uint8_t r1_raw[512],
    const uint8_t p2_raw[512], const uint8_t r2_raw[512],
    const uint8_t p3_raw[512], const uint8_t r3_raw[512],
    uint32_t acc[kN]) {
  DR8_DISABLE_UNROLL
  for (uint32_t i = 0; i < 64; ++i) {
    uint32_t gamma = kZetas[64 + i];

    // p0 * r0
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

    // p1 * r1
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

    // p2 * r2
    uint32_t a2_0 = load_le16(p2_raw + 2 * (4 * i + 0));
    uint32_t a2_1 = load_le16(p2_raw + 2 * (4 * i + 1));
    uint32_t b2_0 = load_le16(r2_raw + 2 * (4 * i + 0));
    uint32_t b2_1 = load_le16(r2_raw + 2 * (4 * i + 1));
    uint32_t prod2_0, prod2_1;
    basemul_pos(a2_0, a2_1, b2_0, b2_1, gamma, prod2_0, prod2_1);

    uint32_t a2_2 = load_le16(p2_raw + 2 * (4 * i + 2));
    uint32_t a2_3 = load_le16(p2_raw + 2 * (4 * i + 3));
    uint32_t b2_2 = load_le16(r2_raw + 2 * (4 * i + 2));
    uint32_t b2_3 = load_le16(r2_raw + 2 * (4 * i + 3));
    uint32_t prod2_2, prod2_3;
    basemul_pos(a2_2, a2_3, b2_2, b2_3, kQ - gamma, prod2_2, prod2_3);

    // p3 * r3
    uint32_t a3_0 = load_le16(p3_raw + 2 * (4 * i + 0));
    uint32_t a3_1 = load_le16(p3_raw + 2 * (4 * i + 1));
    uint32_t b3_0 = load_le16(r3_raw + 2 * (4 * i + 0));
    uint32_t b3_1 = load_le16(r3_raw + 2 * (4 * i + 1));
    uint32_t prod3_0, prod3_1;
    basemul_pos(a3_0, a3_1, b3_0, b3_1, gamma, prod3_0, prod3_1);

    uint32_t a3_2 = load_le16(p3_raw + 2 * (4 * i + 2));
    uint32_t a3_3 = load_le16(p3_raw + 2 * (4 * i + 3));
    uint32_t b3_2 = load_le16(r3_raw + 2 * (4 * i + 2));
    uint32_t b3_3 = load_le16(r3_raw + 2 * (4 * i + 3));
    uint32_t prod3_2, prod3_3;
    basemul_pos(a3_2, a3_3, b3_2, b3_3, kQ - gamma, prod3_2, prod3_3);

    uint32_t s0 = (prod0_0 + prod1_0 + prod2_0 + prod3_0) % kQ;
    uint32_t s1 = (prod0_1 + prod1_1 + prod2_1 + prod3_1) % kQ;
    uint32_t s2 = (prod0_2 + prod1_2 + prod2_2 + prod3_2) % kQ;
    uint32_t s3 = (prod0_3 + prod1_3 + prod2_3 + prod3_3) % kQ;

    acc[4 * i + 0] = s0;
    acc[4 * i + 1] = s1;
    acc[4 * i + 2] = s2;
    acc[4 * i + 3] = s3;
  }
}

__attribute__((noinline)) static bool sample_matrix_store(const uint8_t rho[32], uint8_t column,
                                       uint8_t row, uint8_t out[2 * kN]) {
  if (!word_aligned(out)) return false;
  alignas(8) uint8_t state[200];
  clear_bytes(state, sizeof(state));
  DR8_DISABLE_UNROLL
  for (uint32_t i = 0; i < 32; ++i) state[i] ^= rho[i];
  state[32] ^= column; state[33] ^= row; state[34] ^= 0x1f;
  state[kRate128 - 1] ^= 0x80;
  phoenix_sdr_dsp::pqc::dr1::keccak_f1600(state);

  uint32_t accepted = 0, pending = 0;
  DR8_DISABLE_UNROLL
  for (uint32_t block = 0; block < kBlockCap && accepted < kN; ++block) {
    if (block != 0) phoenix_sdr_dsp::pqc::dr1::keccak_f1600(state);
    DR8_DISABLE_UNROLL
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

__attribute__((noinline)) static void sample_cbd2_ntt(const uint8_t seed[32], uint8_t nonce, uint8_t *out) {
  uint8_t prf[128];
  uint32_t coeff[kN];
  shake256_prf_128(seed, nonce, prf);
  cbd2(prf, coeff);
  ntt(coeff);
  DR8_DISABLE_UNROLL
  for (uint32_t pair = 0; pair < kN / 2; ++pair) {
    store_pair_word(out, pair, coeff[2 * pair], coeff[2 * pair + 1]);
  }
  clear_bytes(prf, sizeof(prf));
  clear_bytes(reinterpret_cast<uint8_t *>(coeff), sizeof(coeff));
}

__attribute__((noinline)) static void sample_cbd2_store(const uint8_t seed[32], uint8_t nonce, uint8_t *out) {
  uint8_t prf[128];
  uint32_t coeff[kN];
  shake256_prf_128(seed, nonce, prf);
  cbd2(prf, coeff);
  DR8_DISABLE_UNROLL
  for (uint32_t pair = 0; pair < kN / 2; ++pair) {
    store_pair_word(out, pair, coeff[2 * pair], coeff[2 * pair + 1]);
  }
  clear_bytes(prf, sizeof(prf));
  clear_bytes(reinterpret_cast<uint8_t *>(coeff), sizeof(coeff));
}

__attribute__((noinline)) static void sample_cbd2_add_mu(const uint8_t r_seed[32], const uint8_t msg32[32], uint8_t *out) {
  uint8_t prf[128];
  uint32_t coeff[kN];
  shake256_prf_128(r_seed, 8, prf); // nonce = 2*k = 8 for ML-KEM-1024
  cbd2(prf, coeff);
  DR8_DISABLE_UNROLL
  for (uint32_t index = 0; index < kN; ++index) {
    uint32_t bit = (msg32[index >> 3] >> (index & 7u)) & 1u;
    uint32_t mu = bit ? 1665u : 0u;
    const uint32_t s = coeff[index] + mu;
    coeff[index] = s >= kQ ? s - kQ : s;
  }
  DR8_DISABLE_UNROLL
  for (uint32_t pair = 0; pair < kN / 2; ++pair) {
    store_pair_word(out, pair, coeff[2 * pair], coeff[2 * pair + 1]);
  }
  clear_bytes(prf, sizeof(prf));
  clear_bytes(reinterpret_cast<uint8_t *>(coeff), sizeof(coeff));
}

__attribute__((noinline)) static void decode_d12(const uint8_t in[384], uint8_t *out) {
  DR8_DISABLE_UNROLL
  for (uint32_t i = 0; i < 128; ++i) {
    const uint32_t b0 = in[3 * i + 0];
    const uint32_t b1 = in[3 * i + 1];
    const uint32_t b2 = in[3 * i + 2];
    const uint32_t t0 = b0 | ((b1 & 0x0fu) << 8);
    const uint32_t t1 = (b1 >> 4) | (b2 << 4);
    store_pair_word(out, i, t0, t1);
  }
}

__attribute__((noinline)) static void encode_d12(const uint8_t in_raw[512], uint8_t out[384]) {
  DR8_DISABLE_UNROLL
  for (uint32_t i = 0; i < 128; ++i) {
    const uint32_t t0 = load_le16(in_raw + 2 * (2 * i + 0));
    const uint32_t t1 = load_le16(in_raw + 2 * (2 * i + 1));
    out[3 * i + 0] = static_cast<uint8_t>(t0 & 0xffu);
    out[3 * i + 1] = static_cast<uint8_t>((t0 >> 8) | ((t1 & 0x0fu) << 4));
    out[3 * i + 2] = static_cast<uint8_t>(t1 >> 4);
  }
}

// du=11 codecs for ML-KEM-1024 (352 bytes per polynomial)
// 8 coeffs of 11 bits each packed into 11 bytes
__attribute__((noinline)) static void decode_decompress_d11(const uint8_t in[352], uint32_t out[kN]) {
  DR8_DISABLE_UNROLL
  for (uint32_t i = 0; i < 32; ++i) {
    const uint8_t *p = in + 11 * i;
    // 11 bytes into 8 coeffs
    const uint32_t b0 = p[0], b1 = p[1], b2 = p[2], b3 = p[3], b4 = p[4];
    const uint32_t b5 = p[5], b6 = p[6], b7 = p[7], b8 = p[8], b9 = p[9], b10 = p[10];

    const uint32_t c0 = b0 | ((b1 & 0x07u) << 8);
    const uint32_t c1 = (b1 >> 3) | ((b2 & 0x3fu) << 5);
    const uint32_t c2 = (b2 >> 6) | (b3 << 2) | ((b4 & 0x01u) << 10);
    const uint32_t c3 = (b4 >> 1) | ((b5 & 0x0fu) << 7);
    const uint32_t c4 = (b5 >> 4) | ((b6 & 0x7fu) << 4);
    const uint32_t c5 = (b6 >> 7) | (b7 << 1) | ((b8 & 0x03u) << 9);
    const uint32_t c6 = (b8 >> 2) | ((b9 & 0x1fu) << 6);
    const uint32_t c7 = (b9 >> 5) | (b10 << 3);

    out[8 * i + 0] = (c0 * 3329u + 1024u) >> 11;
    out[8 * i + 1] = (c1 * 3329u + 1024u) >> 11;
    out[8 * i + 2] = (c2 * 3329u + 1024u) >> 11;
    out[8 * i + 3] = (c3 * 3329u + 1024u) >> 11;
    out[8 * i + 4] = (c4 * 3329u + 1024u) >> 11;
    out[8 * i + 5] = (c5 * 3329u + 1024u) >> 11;
    out[8 * i + 6] = (c6 * 3329u + 1024u) >> 11;
    out[8 * i + 7] = (c7 * 3329u + 1024u) >> 11;
  }
}

__attribute__((noinline)) static void compress11_encode(const uint32_t in[kN], uint8_t out[352]) {
  DR8_DISABLE_UNROLL
  for (uint32_t i = 0; i < 32; ++i) {
    const uint32_t t0 = ((in[8 * i + 0] << 11) + 1664u) / 3329u & 0x7ffu;
    const uint32_t t1 = ((in[8 * i + 1] << 11) + 1664u) / 3329u & 0x7ffu;
    const uint32_t t2 = ((in[8 * i + 2] << 11) + 1664u) / 3329u & 0x7ffu;
    const uint32_t t3 = ((in[8 * i + 3] << 11) + 1664u) / 3329u & 0x7ffu;
    const uint32_t t4 = ((in[8 * i + 4] << 11) + 1664u) / 3329u & 0x7ffu;
    const uint32_t t5 = ((in[8 * i + 5] << 11) + 1664u) / 3329u & 0x7ffu;
    const uint32_t t6 = ((in[8 * i + 6] << 11) + 1664u) / 3329u & 0x7ffu;
    const uint32_t t7 = ((in[8 * i + 7] << 11) + 1664u) / 3329u & 0x7ffu;

    out[11 * i + 0] = static_cast<uint8_t>(t0 & 0xffu);
    out[11 * i + 1] = static_cast<uint8_t>((t0 >> 8) | ((t1 & 0x1fu) << 3));
    out[11 * i + 2] = static_cast<uint8_t>((t1 >> 5) | ((t2 & 0x03u) << 6));
    out[11 * i + 3] = static_cast<uint8_t>((t2 >> 2) & 0xffu);
    out[11 * i + 4] = static_cast<uint8_t>((t2 >> 10) | ((t3 & 0x7fu) << 1));
    out[11 * i + 5] = static_cast<uint8_t>((t3 >> 7) | ((t4 & 0x0fu) << 4));
    out[11 * i + 6] = static_cast<uint8_t>((t4 >> 4) | ((t5 & 0x01u) << 7));
    out[11 * i + 7] = static_cast<uint8_t>((t5 >> 1) & 0xffu);
    out[11 * i + 8] = static_cast<uint8_t>((t5 >> 9) | ((t6 & 0x3fu) << 2));
    out[11 * i + 9] = static_cast<uint8_t>((t6 >> 6) | ((t7 & 0x07u) << 5));
    out[11 * i + 10] = static_cast<uint8_t>(t7 >> 3);
  }
}

// dv=5 codecs for ML-KEM-1024 (160 bytes per polynomial)
// 8 coeffs of 5 bits each packed into 5 bytes
__attribute__((noinline)) static void decode_decompress_d5(const uint8_t in[160], uint32_t out[kN]) {
  DR8_DISABLE_UNROLL
  for (uint32_t i = 0; i < 32; ++i) {
    const uint8_t *p = in + 5 * i;
    const uint32_t b0 = p[0], b1 = p[1], b2 = p[2], b3 = p[3], b4 = p[4];

    const uint32_t c0 = b0 & 0x1fu;
    const uint32_t c1 = (b0 >> 5) | ((b1 & 0x03u) << 3);
    const uint32_t c2 = (b1 >> 2) & 0x1fu;
    const uint32_t c3 = (b1 >> 7) | ((b2 & 0x0fu) << 1);
    const uint32_t c4 = (b2 >> 4) | ((b3 & 0x01u) << 4);
    const uint32_t c5 = (b3 >> 1) & 0x1fu;
    const uint32_t c6 = (b3 >> 6) | ((b4 & 0x07u) << 2);
    const uint32_t c7 = b4 >> 3;

    out[8 * i + 0] = (c0 * 3329u + 16u) >> 5;
    out[8 * i + 1] = (c1 * 3329u + 16u) >> 5;
    out[8 * i + 2] = (c2 * 3329u + 16u) >> 5;
    out[8 * i + 3] = (c3 * 3329u + 16u) >> 5;
    out[8 * i + 4] = (c4 * 3329u + 16u) >> 5;
    out[8 * i + 5] = (c5 * 3329u + 16u) >> 5;
    out[8 * i + 6] = (c6 * 3329u + 16u) >> 5;
    out[8 * i + 7] = (c7 * 3329u + 16u) >> 5;
  }
}

__attribute__((noinline)) static void compress5_encode(const uint32_t in[kN], uint8_t out[160]) {
  DR8_DISABLE_UNROLL
  for (uint32_t i = 0; i < 32; ++i) {
    const uint32_t t0 = ((in[8 * i + 0] << 5) + 1664u) / 3329u & 0x1fu;
    const uint32_t t1 = ((in[8 * i + 1] << 5) + 1664u) / 3329u & 0x1fu;
    const uint32_t t2 = ((in[8 * i + 2] << 5) + 1664u) / 3329u & 0x1fu;
    const uint32_t t3 = ((in[8 * i + 3] << 5) + 1664u) / 3329u & 0x1fu;
    const uint32_t t4 = ((in[8 * i + 4] << 5) + 1664u) / 3329u & 0x1fu;
    const uint32_t t5 = ((in[8 * i + 5] << 5) + 1664u) / 3329u & 0x1fu;
    const uint32_t t6 = ((in[8 * i + 6] << 5) + 1664u) / 3329u & 0x1fu;
    const uint32_t t7 = ((in[8 * i + 7] << 5) + 1664u) / 3329u & 0x1fu;

    out[5 * i + 0] = static_cast<uint8_t>(t0 | (t1 << 5));
    out[5 * i + 1] = static_cast<uint8_t>((t1 >> 3) | (t2 << 2) | (t3 << 7));
    out[5 * i + 2] = static_cast<uint8_t>((t3 >> 1) | (t4 << 4));
    out[5 * i + 3] = static_cast<uint8_t>((t4 >> 4) | (t5 << 1) | (t6 << 6));
    out[5 * i + 4] = static_cast<uint8_t>((t6 >> 2) | (t7 << 3));
  }
}

static inline void compress1(const uint32_t in[kN], uint8_t out[32]) {
  clear_bytes(out, 32);
  DR8_DISABLE_UNROLL
  for (uint32_t i = 0; i < kN; ++i) {
    const uint32_t val = in[i];
    const uint32_t bit = (val > 832u && val < 2497u) ? 1u : 0u;
    out[i >> 3] |= static_cast<uint8_t>(bit << (i & 7u));
  }
}

} // namespace phoenix_sdr_dsp::pqc::dr8_1024
