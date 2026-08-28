// SPDX-License-Identifier: Apache-2.0
#include <stdint.h>
#include <new>

#include "dr1_keccak_f1600.hpp"

namespace {

constexpr uint32_t kN = 256u;
constexpr uint32_t kQ = 3329u;
constexpr uint32_t kStateBytes = 200u;
constexpr uint32_t kSigmaBytes = 32u;
constexpr uint32_t kPrfBytes = 192u;
constexpr uint32_t kRateG = 72u;
constexpr uint32_t kRateShake256 = 136u;
constexpr uint32_t kSecretTokenBytes = 2096u;
constexpr uint32_t kRhoOffset = 16u;
constexpr uint32_t kSecretS0Offset = 48u;
constexpr uint32_t kSecretS1Offset = 560u;
constexpr uint32_t kSecretE0Offset = 1072u;
constexpr uint32_t kSecretE1Offset = 1584u;
constexpr uint32_t kOk = 0u;
constexpr uint32_t kBadDescriptor = 2u;
constexpr uint32_t kBadToken = 3u;
constexpr uint32_t kBlockCap = 5u;

constexpr uint16_t kZetas[128] = {
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
  for (uint32_t index = 0; index < bytes; ++index) destination[index] = 0u;
}

static inline uint32_t load_le32(const uint8_t *in) {
  return static_cast<uint32_t>(in[0]) | (static_cast<uint32_t>(in[1]) << 8) |
         (static_cast<uint32_t>(in[2]) << 16) | (static_cast<uint32_t>(in[3]) << 24);
}

static inline void store_le32(uint8_t *out, uint32_t x) {
  out[0] = static_cast<uint8_t>(x); out[1] = static_cast<uint8_t>(x >> 8);
  out[2] = static_cast<uint8_t>(x >> 16); out[3] = static_cast<uint8_t>(x >> 24);
}

static inline bool valid_descriptor(const uint8_t d[16]) {
  return d[0] == 1 && d[1] == 0x24 && d[2] == 0x52 && d[3] == 0 &&
         d[4] == 2 && d[5] == 3 && d[6] == kBlockCap && d[7] == 0 &&
         d[12] == 0 && d[13] == 0 && d[14] == 0 && d[15] == 0;
}

static inline bool word_aligned(const void *address) {
  constexpr uintptr_t kWordAlignmentMask = alignof(uint32_t) - 1u;
  return (reinterpret_cast<uintptr_t>(address) & kWordAlignmentMask) == 0;
}

static inline uint32_t mod_mul(uint32_t a, uint32_t b) { return (a * b) % kQ; }

static inline uint32_t bit_at(const uint8_t *prf, uint32_t bit) {
  return (prf[bit >> 3] >> (bit & 7)) & 1u;
}

static void cbd3(const uint8_t prf[kPrfBytes], uint32_t out[kN]) {
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

__attribute__((noinline)) static void ntt(uint32_t r[kN]) {
  uint32_t k = 1;
  for (uint32_t stage = 0; stage < 7; ++stage) {
    const uint32_t length = 128u >> stage;
    for (uint32_t start = 0; start < kN; start += 2 * length) {
      const uint32_t zeta = kZetas[k++];
      for (uint32_t j = start; j < start + length; ++j) {
        const uint32_t t = mod_mul(zeta, r[j + length]);
        r[j + length] = r[j] >= t ? r[j] - t : r[j] + kQ - t;
        const uint32_t sum = r[j] + t;
        r[j] = sum >= kQ ? sum - kQ : sum;
      }
    }
  }
}

static inline void store_pair_word(uint8_t *out, uint32_t pair, uint32_t a,
                                   uint32_t b) {
  const uint32_t word = (a & 0xffffu) | ((b & 0xffffu) << 16);
  ::new (static_cast<void *>(out + 4 * pair)) uint32_t(word);
}

static inline void derive_g(const uint8_t d[32], uint8_t rho[32], uint8_t sigma[32]) {
  alignas(8) uint8_t state[kStateBytes];
  clear_bytes(state, kStateBytes);
  for (uint32_t index = 0; index < 32; ++index) state[index] ^= d[index];
  state[32] ^= 2u;
  state[33] ^= 0x06u;
  state[kRateG - 1u] ^= 0x80u;
  phoenix_sdr_dsp::pqc::dr1::keccak_f1600(state);
  for (uint32_t index = 0; index < 32; ++index) {
    rho[index] = state[index];
    sigma[index] = state[32u + index];
  }
  clear_bytes(state, kStateBytes);
}

static inline void shake256_prf_192(const uint8_t sigma[kSigmaBytes],
                                    uint8_t nonce, uint8_t output[kPrfBytes]) {
  alignas(8) uint8_t state[kStateBytes];
  clear_bytes(state, kStateBytes);
  for (uint32_t index = 0; index < kSigmaBytes; ++index)
    state[index] ^= sigma[index];
  state[32] ^= nonce;
  state[33] ^= 0x1fu;
  state[kRateShake256 - 1u] ^= 0x80u;
  phoenix_sdr_dsp::pqc::dr1::keccak_f1600(state);
  for (uint32_t index = 0; index < kRateShake256; ++index)
    output[index] = state[index];
  phoenix_sdr_dsp::pqc::dr1::keccak_f1600(state);
  for (uint32_t index = 0; index < (kPrfBytes - kRateShake256); ++index)
    output[kRateShake256 + index] = state[index];
  clear_bytes(state, kStateBytes);
}

static void sample_one_nonce(const uint8_t sigma[32], uint8_t nonce, uint8_t *out) {
  uint8_t prf[192];
  uint32_t coeff[kN];
  shake256_prf_192(sigma, nonce, prf);
  cbd3(prf, coeff);
  ntt(coeff);
  for (uint32_t pair = 0; pair < kN / 2; ++pair) {
    store_pair_word(out, pair, coeff[2 * pair], coeff[2 * pair + 1]);
  }
}

}  // namespace

extern "C" void dr2d_kpke_keygen_seed_noise(
    uint8_t d[32], uint8_t descriptor[16], uint8_t token[2096]) {
  const uint32_t id = load_le32(descriptor + 8);
  if (!valid_descriptor(descriptor)) {
    store_le32(token, id); store_le32(token + 4, kBadDescriptor);
    store_le32(token + 8, 0); store_le32(token + 12, 0);
  } else if (!word_aligned(token)) {
    store_le32(token, id); store_le32(token + 4, kBadToken);
    store_le32(token + 8, 0); store_le32(token + 12, 0);
  } else {
    store_le32(token, id); store_le32(token + 4, kOk);
    store_le32(token + 8, 0); store_le32(token + 12, 0);

    uint8_t rho[32], sigma[32];
    derive_g(d, rho, sigma);

    for (uint32_t i = 0; i < 32; ++i) token[kRhoOffset + i] = rho[i];

    sample_one_nonce(sigma, 0, token + kSecretS0Offset);
    sample_one_nonce(sigma, 1, token + kSecretS1Offset);
    sample_one_nonce(sigma, 2, token + kSecretE0Offset);
    sample_one_nonce(sigma, 3, token + kSecretE1Offset);

    clear_bytes(rho, sizeof(rho));
    clear_bytes(sigma, sizeof(sigma));
  }
  clear_bytes(d, 32);
  clear_bytes(descriptor, 16);
}
