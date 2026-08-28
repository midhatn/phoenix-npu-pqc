// SPDX-License-Identifier: Apache-2.0
/**
 * Microarchitectural constants and inlined primitives for Milestone DR4 (ML-KEM-512 K-PKE.Decrypt)
 * on AMD Phoenix NPU (AIE2 / IPU 1.0).
 */
#ifndef DR4_MLKEM512_KPKE_DECRYPT_INTERNAL_HPP
#define DR4_MLKEM512_KPKE_DECRYPT_INTERNAL_HPP

#include <stdint.h>
#include <stddef.h>
#include <new>

#if defined(__clang__)
#define DR4_DISABLE_UNROLL _Pragma("clang loop unroll(disable)")
#else
#define DR4_DISABLE_UNROLL
#endif

namespace mlkem512_dr4 {

constexpr uint32_t kQ = 3329u;
constexpr uint32_t kN = 256u;
constexpr uint32_t kK = 2u;

constexpr uint32_t kDescriptorMagic = 0x00524101u;
constexpr uint32_t kResultMagic = 0x4434524Du; // b"MR4D"

// Internal token headers
constexpr uint32_t kDecompressTokenMagic = 0x54434544u; // b"DECT"
constexpr uint32_t kDecompressTokenBytes = 5136u;       // 16 B header + 5 * 1024 B polynomials

// Official FIPS 203 ML-KEM-512 Zeta Table in 32-bit aligned words
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

static inline uint32_t load_le32(const uint8_t *in) {
    return static_cast<uint32_t>(in[0]) | (static_cast<uint32_t>(in[1]) << 8) |
           (static_cast<uint32_t>(in[2]) << 16) | (static_cast<uint32_t>(in[3]) << 24);
}

static inline void store_le32(uint8_t *out, uint32_t x) {
    ::new (static_cast<void *>(out)) uint32_t(x);
}

// Barrett modulo multiplication
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

static inline void basemul(uint32_t a0, uint32_t a1, uint32_t b0, uint32_t b1, uint32_t zeta, uint32_t &c0, uint32_t &c1) {
    const uint32_t term = mod_mul(mod_mul(a1, b1), zeta);
    const uint32_t p0 = mod_mul(a0, b0) + term;
    c0 = p0 >= kQ ? p0 - kQ : p0;
    const uint32_t p1 = mod_mul(a0, b1) + mod_mul(a1, b0);
    c1 = p1 >= kQ ? p1 - kQ : p1;
}

// Template constant-stride NTT stage
template <uint32_t Len>
static inline void ntt_stage(uint32_t r[kN], uint32_t &k) {
    for (uint32_t start = 0; start < kN; start += 2 * Len) {
        const uint32_t zeta = kZetas[k++];
        DR4_DISABLE_UNROLL
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

// Template constant-stride INTT stage
template <uint32_t Len>
static inline void intt_stage(uint32_t r[kN], uint32_t &k) {
    for (uint32_t start = 0; start < kN; start += 2 * Len) {
        const uint32_t zeta = kZetas[k--];
        DR4_DISABLE_UNROLL
        for (uint32_t j = start; j < start + Len; ++j) {
            const uint32_t t = r[j];
            const uint32_t sum = t + r[j + Len];
            r[j] = sum >= kQ ? sum - kQ : sum;
            const uint32_t diff = r[j + Len] >= t ? r[j + Len] - t : r[j + Len] + kQ - t;
            r[j + Len] = mod_mul(zeta, diff);
        }
    }
}

static inline void inverse_ntt(uint32_t r[kN]) {
    uint32_t k = 127;
    intt_stage<2>(r, k);
    intt_stage<4>(r, k);
    intt_stage<8>(r, k);
    intt_stage<16>(r, k);
    intt_stage<32>(r, k);
    intt_stage<64>(r, k);
    intt_stage<128>(r, k);
    
    // Scale by 128^-1 mod 3329 = 3303
    constexpr uint32_t f = 3303u;
    DR4_DISABLE_UNROLL
    for (uint32_t i = 0; i < kN; ++i) {
        r[i] = mod_mul(r[i], f);
    }
}

// Decode 384 bytes into 256 12-bit coefficients (stored as 256 uint32_t words)
static inline void decode_12bit_to_coeffs(const uint8_t in[384], uint32_t out[256]) {
    DR4_DISABLE_UNROLL
    for (uint32_t i = 0; i < 128; ++i) {
        const uint32_t b0 = in[3 * i + 0];
        const uint32_t b1 = in[3 * i + 1];
        const uint32_t b2 = in[3 * i + 2];
        out[2 * i + 0] = b0 | ((b1 & 0x0Fu) << 8);
        out[2 * i + 1] = (b1 >> 4) | (b2 << 4);
    }
}

// Decompress 320 bytes of 10-bit coeffs into 256 uint32_t words
static inline void decompress_10bit_to_coeffs(const uint8_t in[320], uint32_t out[256]) {
    DR4_DISABLE_UNROLL
    for (uint32_t i = 0; i < 64; ++i) {
        const uint32_t b0 = in[5 * i + 0];
        const uint32_t b1 = in[5 * i + 1];
        const uint32_t b2 = in[5 * i + 2];
        const uint32_t b3 = in[5 * i + 3];
        const uint32_t b4 = in[5 * i + 4];
        
        const uint32_t w = b0 | (b1 << 8) | (b2 << 16) | (b3 << 24);
        const uint32_t c0 = w & 0x3FFu;
        const uint32_t c1 = (w >> 10) & 0x3FFu;
        const uint32_t c2 = (w >> 20) & 0x3FFu;
        const uint32_t c3 = ((w >> 30) & 3u) | (b4 << 2);
        
        out[4 * i + 0] = (c0 * 3329u + 512u) >> 10;
        out[4 * i + 1] = (c1 * 3329u + 512u) >> 10;
        out[4 * i + 2] = (c2 * 3329u + 512u) >> 10;
        out[4 * i + 3] = (c3 * 3329u + 512u) >> 10;
    }
}

// Decompress 128 bytes of 4-bit coeffs into 256 uint32_t words
static inline void decompress_4bit_to_coeffs(const uint8_t in[128], uint32_t out[256]) {
    DR4_DISABLE_UNROLL
    for (uint32_t i = 0; i < 128; ++i) {
        const uint32_t b = in[i];
        const uint32_t c0 = b & 0x0Fu;
        const uint32_t c1 = (b >> 4) & 0x0Fu;
        out[2 * i + 0] = (c0 * 3329u + 8u) >> 4;
        out[2 * i + 1] = (c1 * 3329u + 8u) >> 4;
    }
}

// Compress 256 coefficients to 32 bytes (1 bit per coeff)
static inline void compress_1bit_to_bytes(const uint32_t in[256], uint8_t out[32]) {
    DR4_DISABLE_UNROLL
    for (uint32_t i = 0; i < 32; ++i) {
        uint32_t byte_val = 0;
        for (uint32_t bit = 0; bit < 8; ++bit) {
            const uint32_t x = in[8 * i + bit];
            // FIPS 203 Compress_1: x in [833, 2496] -> 1, else 0
            if (x >= 833u && x <= 2496u) {
                byte_val |= (1u << bit);
            }
        }
        out[i] = static_cast<uint8_t>(byte_val);
    }
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

// Internal Token Layout (5136 B)
struct DecompressToken {
    uint32_t magic;
    uint32_t request_id;
    uint32_t status;
    uint32_t reserved;
    uint32_t s_hat0[256];
    uint32_t s_hat1[256];
    uint32_t u_hat0[256];
    uint32_t u_hat1[256];
    uint32_t v[256];
};

} // namespace mlkem512_dr4

#endif // DR4_MLKEM512_KPKE_DECRYPT_INTERNAL_HPP
