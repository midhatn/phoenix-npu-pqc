// SPDX-License-Identifier: Apache-2.0
/**
 * Internal constants, memory layouts, and cryptographic routines for Milestone DR5 (ML-KEM-512 ML-KEM.KeyGen).
 */
#ifndef DR5_MLKEM512_KEYGEN_INTERNAL_HPP
#define DR5_MLKEM512_KEYGEN_INTERNAL_HPP

#include <stdint.h>
#include <stddef.h>
#include <new>

#include "dr1_keccak_f1600.hpp"

#if defined(__clang__)
#define DR5_DISABLE_UNROLL _Pragma("clang loop unroll(disable)")
#else
#define DR5_DISABLE_UNROLL
#endif

namespace mlkem512_dr5 {

constexpr uint32_t kN = 256u, kQ = 3329u;
constexpr uint32_t kRate128 = 168u, kRate256 = 136u, kRateG = 72u;
constexpr uint32_t kBlockCap = 5u, kPrfBytes = 192u;

constexpr uint32_t kDescriptorMagic = 0x00525101u;
constexpr uint32_t kResultMagic = 0x4735524Du; // b"MR5G"

// Token byte sizes
constexpr uint32_t kSecretTokenBytes = 2128u;      // header[16] + rho[32] + z[32] + s0[512] + s1[512] + e0[512] + e1[512]
constexpr uint32_t kMatrixTokenBytes = 3152u;      // secret[2128] + A0[512] + A1[512]
constexpr uint32_t kRowStateTokenBytes = 2128u;    // header[16] + rho[32] + z[32] + s0[512] + s1[512] + t0[512] + e1[512]
constexpr uint32_t kFinalTokenBytes = 2144u;       // header[16] + rho[32] + z[32] + s0[512] + s1[512] + t0[512] + t1[512] + pad[16]
constexpr uint32_t kResultBytes = 2452u;           // header[20] + ek[800] + dk[1632]

// Token byte offsets
constexpr uint32_t kRhoOffset = 16u;
constexpr uint32_t kZOffset = 48u;
constexpr uint32_t kSecretS0Offset = 80u;
constexpr uint32_t kSecretS1Offset = 592u;
constexpr uint32_t kSecretE0Offset = 1104u;
constexpr uint32_t kSecretE1Offset = 1616u;

constexpr uint32_t kStateSecretOffset = 80u;
constexpr uint32_t kStateS1Offset = 592u;
constexpr uint32_t kStateT0Offset = 1104u;
constexpr uint32_t kStateE1Offset = 1616u;

constexpr uint32_t kMatrixA0Offset = 2128u;
constexpr uint32_t kMatrixA1Offset = 2640u;

constexpr uint32_t kFinalRhoOffset = 16u;
constexpr uint32_t kFinalZOffset = 48u;
constexpr uint32_t kFinalS0Offset = 80u;
constexpr uint32_t kFinalS1Offset = 592u;
constexpr uint32_t kFinalT0Offset = 1104u;
constexpr uint32_t kFinalT1Offset = 1616u;

// Official FIPS 203 kZetas in 32-bit aligned words
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

static inline void clear_bytes(void *address, uint32_t bytes) {
    volatile uint8_t *out = static_cast<volatile uint8_t *>(address);
    DR5_DISABLE_UNROLL
    for (uint32_t i = 0; i < bytes; ++i) out[i] = 0;
}

static inline uint16_t load_le16(const uint8_t *in) {
    return static_cast<uint16_t>(in[0]) | (static_cast<uint16_t>(in[1]) << 8);
}

static inline uint32_t load_le32(const uint8_t *in) {
    return static_cast<uint32_t>(in[0]) | (static_cast<uint32_t>(in[1]) << 8) |
           (static_cast<uint32_t>(in[2]) << 16) | (static_cast<uint32_t>(in[3]) << 24);
}

static inline void store_pair_word(uint8_t *out, uint32_t pair, uint32_t a, uint32_t b) {
    const uint32_t word = (a & 0xffffu) | ((b & 0xffffu) << 16);
    ::new (static_cast<void *>(out + 4 * pair)) uint32_t(word);
}

static inline bool word_aligned(const void *address) {
    constexpr uintptr_t kWordAlignmentMask = alignof(uint32_t) - 1u;
    return (reinterpret_cast<uintptr_t>(address) & kWordAlignmentMask) == 0;
}

static inline bool copy_words(uint8_t *destination, const uint8_t *source, uint32_t bytes) {
    if ((bytes & 3u) != 0 || !word_aligned(destination) || !word_aligned(source)) return false;
    const uint32_t words = bytes / 4u;
    DR5_DISABLE_UNROLL
    for (uint32_t word = 0; word < words; ++word) {
        ::new (static_cast<void *>(destination + 4 * word)) uint32_t(load_le32(source + 4 * word));
    }
    return true;
}

static inline uint32_t mod_mul(uint32_t a, uint32_t b) {
    const uint32_t P = a * b;
    const uint32_t hi = P >> 16;
    const uint32_t lo = P - (hi << 16);
    const uint32_t Y = hi * 2285u + lo;
    uint32_t q = (Y * 314u) >> 20;
    uint32_t r = Y - q * 3329u;
    if (r >= 3329u) r -= 3329u;
    if (r >= 3329u) r -= 3329u;
    return r;
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
    for (uint32_t start = 0; start < kN; start += 2 * Len) {
        const uint32_t zeta = kZetas[k++];
        DR5_DISABLE_UNROLL
        for (uint32_t j = start; j < start + Len; ++j) {
            const uint32_t t = mod_mul(zeta, r[j + Len]);
            r[j + Len] = r[j] >= t ? r[j] - t : r[j] + kQ - t;
            const uint32_t sum = r[j] + t;
            r[j] = sum >= kQ ? sum - kQ : sum;
        }
    }
}

static inline void forward_ntt(uint32_t r[kN]) {
    uint32_t k = 1;
    ntt_stage<128>(r, k);
    ntt_stage<64>(r, k);
    ntt_stage<32>(r, k);
    ntt_stage<16>(r, k);
    ntt_stage<8>(r, k);
    ntt_stage<4>(r, k);
    ntt_stage<2>(r, k);
}

// SHA3-256 for 800 bytes
static inline void sha3_256_800(const uint8_t in[800], uint8_t out[32]) {
    alignas(8) uint8_t state[200];
    clear_bytes(state, sizeof(state));
    
    // 5 full 136-byte blocks = 680 bytes
    for (uint32_t blk = 0; blk < 5; ++blk) {
        for (uint32_t i = 0; i < 136; ++i) {
            state[i] ^= in[blk * 136 + i];
        }
        phoenix_sdr_dsp::pqc::dr1::keccak_f1600(state);
    }
    
    // Final partial block: 120 bytes (800 - 680 = 120)
    for (uint32_t i = 0; i < 120; ++i) {
        state[i] ^= in[680 + i];
    }
    // Domain separation 0x06 and padding 0x80
    state[120] ^= 0x06;
    state[135] ^= 0x80;
    phoenix_sdr_dsp::pqc::dr1::keccak_f1600(state);
    
    // Squeeze 32 bytes
    for (uint32_t i = 0; i < 32; ++i) {
        out[i] = state[i];
    }
    clear_bytes(state, sizeof(state));
}

// CRC32 Hardware Verification
static inline uint32_t compute_crc32(const uint8_t *data, size_t length) {
    uint32_t crc = 0xFFFFFFFFu;
    for (size_t i = 0; i < length; ++i) {
        crc ^= data[i];
        for (uint32_t bit = 0; bit < 8; ++bit) {
            crc = (crc >> 1) ^ (0xEDB88320u & (-(crc & 1u)));
        }
    }
    return ~crc;
}

} // namespace mlkem512_dr5

#endif // DR5_MLKEM512_KEYGEN_INTERNAL_HPP
