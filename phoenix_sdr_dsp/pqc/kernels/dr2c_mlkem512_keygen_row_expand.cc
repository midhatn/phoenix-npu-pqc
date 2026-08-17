// SPDX-License-Identifier: Apache-2.0
// DR2c expands one ML-KEM-512 K-PKE.KeyGen row into a private AIE token.
#include <cstdint>

#include "dr1_keccak_f1600.hpp"

#if defined(__clang__)
#define DR2C_DISABLE_UNROLL _Pragma("clang loop unroll(disable)")
#else
#define DR2C_DISABLE_UNROLL
#endif

namespace {
constexpr uint32_t kN = 256, kQ = 3329, kRate128 = 168, kRate256 = 136;
constexpr uint32_t kBlockCap = 5, kPrfBytes = 192, kTokenBytes = 2576;
constexpr uint32_t kHeaderBytes = 16, kOk = 0, kLimitExceeded = 1;
constexpr uint32_t kBadDescriptor = 2;
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

static void clear_bytes(void *address, uint32_t bytes) {
    volatile uint8_t *out = static_cast<volatile uint8_t *>(address);
    DR2C_DISABLE_UNROLL
    for (uint32_t i = 0; i < bytes; ++i) out[i] = 0;
}
static uint32_t load_le32(const uint8_t *in) {
    return static_cast<uint32_t>(in[0]) | (static_cast<uint32_t>(in[1]) << 8) |
           (static_cast<uint32_t>(in[2]) << 16) | (static_cast<uint32_t>(in[3]) << 24);
}
static void store_le16(uint8_t *out, uint16_t x) {
    out[0] = static_cast<uint8_t>(x); out[1] = static_cast<uint8_t>(x >> 8);
}
static void store_le32(uint8_t *out, uint32_t x) {
    out[0] = static_cast<uint8_t>(x); out[1] = static_cast<uint8_t>(x >> 8);
    out[2] = static_cast<uint8_t>(x >> 16); out[3] = static_cast<uint8_t>(x >> 24);
}
static uint32_t mod_mul(uint32_t a, uint32_t b) { return (a * b) % kQ; }
static bool valid_descriptor(const uint8_t d[16]) {
    return d[0] == 1 && d[1] == 0x23 && d[2] == 0x52 && d[3] == 0 && d[4] <= 1 &&
           d[5] == 3 && d[6] == kBlockCap && d[7] == 0 && d[12] == 0 &&
           d[13] == 0 && d[14] == 0 && d[15] == 0;
}
static void ntt(uint32_t r[kN]) {
    uint32_t k = 1;
    DR2C_DISABLE_UNROLL
    for (uint32_t stage = 0; stage < 7; ++stage) {
        const uint32_t length = 128u >> stage;
        DR2C_DISABLE_UNROLL
        for (uint32_t start = 0; start < kN; start += 2 * length) {
            const uint32_t zeta = kZetas[k++];
            DR2C_DISABLE_UNROLL
            for (uint32_t j = start; j < start + length; ++j) {
                const uint32_t t = mod_mul(zeta, r[j + length]);
                r[j + length] = r[j] >= t ? r[j] - t : r[j] + kQ - t;
                const uint32_t sum = r[j] + t;
                r[j] = sum >= kQ ? sum - kQ : sum;
            }
        }
    }
}
static bool sample_matrix(const uint8_t rho[32], uint8_t column, uint8_t row, uint32_t out[kN]) {
    alignas(8) uint8_t state[200];
    clear_bytes(state, sizeof(state));
    DR2C_DISABLE_UNROLL
    for (uint32_t i = 0; i < 32; ++i) state[i] ^= rho[i];
    state[32] ^= column; state[33] ^= row; state[34] ^= 0x1f; state[kRate128 - 1] ^= 0x80;
    phoenix_sdr_dsp::pqc::dr1::keccak_f1600(state);
    uint32_t accepted = 0;
    DR2C_DISABLE_UNROLL
    for (uint32_t block = 0; block < kBlockCap && accepted < kN; ++block) {
        if (block != 0) phoenix_sdr_dsp::pqc::dr1::keccak_f1600(state);
        DR2C_DISABLE_UNROLL
        for (uint32_t offset = 0; offset < kRate128 && accepted < kN; offset += 3) {
            const uint32_t d1 = state[offset] + 256u * (state[offset + 1] & 0x0fu);
            const uint32_t d2 = (state[offset + 1] >> 4) + 16u * state[offset + 2];
            if (d1 < kQ) out[accepted++] = d1;
            if (d2 < kQ && accepted < kN) out[accepted++] = d2;
        }
    }
    clear_bytes(state, sizeof(state));
    return accepted == kN;
}
static void cbd3_ntt(const uint8_t sigma[32], uint8_t counter, uint32_t out[kN]) {
    alignas(8) uint8_t state[200];
    uint8_t prf[kPrfBytes];
    clear_bytes(state, sizeof(state));
    DR2C_DISABLE_UNROLL
    for (uint32_t i = 0; i < 32; ++i) state[i] ^= sigma[i];
    state[32] ^= counter; state[33] ^= 0x1f; state[kRate256 - 1] ^= 0x80;
    phoenix_sdr_dsp::pqc::dr1::keccak_f1600(state);
    DR2C_DISABLE_UNROLL
    for (uint32_t i = 0; i < kRate256; ++i) prf[i] = state[i];
    phoenix_sdr_dsp::pqc::dr1::keccak_f1600(state);
    DR2C_DISABLE_UNROLL
    for (uint32_t i = kRate256; i < kPrfBytes; ++i) prf[i] = state[i - kRate256];
    DR2C_DISABLE_UNROLL
    for (uint32_t i = 0; i < kN; ++i) {
        const uint32_t bit = 6 * i;
        const uint32_t a = ((prf[bit >> 3] >> (bit & 7)) & 1u) +
            ((prf[(bit + 1) >> 3] >> ((bit + 1) & 7)) & 1u) +
            ((prf[(bit + 2) >> 3] >> ((bit + 2) & 7)) & 1u);
        const uint32_t b = ((prf[(bit + 3) >> 3] >> ((bit + 3) & 7)) & 1u) +
            ((prf[(bit + 4) >> 3] >> ((bit + 4) & 7)) & 1u) +
            ((prf[(bit + 5) >> 3] >> ((bit + 5) & 7)) & 1u);
        const int32_t value = static_cast<int32_t>(a) - static_cast<int32_t>(b);
        out[i] = static_cast<uint32_t>(value) + (static_cast<uint32_t>(value) >> 31) * kQ;
    }
    ntt(out);
    clear_bytes(prf, sizeof(prf)); clear_bytes(state, sizeof(state));
}
static void write_token(uint8_t token[kTokenBytes], uint32_t request_id, uint8_t row, uint32_t status, const uint32_t *a0, const uint32_t *a1, const uint32_t *s0, const uint32_t *s1, const uint32_t *e) {
    clear_bytes(token, kTokenBytes);
    store_le32(token, request_id); store_le32(token + 4, status); token[8] = row;
    if (status != kOk) return;
    const uint32_t *polynomials[5] = {a0, a1, s0, s1, e};
    DR2C_DISABLE_UNROLL
    for (uint32_t p = 0; p < 5; ++p) {
        DR2C_DISABLE_UNROLL
        for (uint32_t i = 0; i < kN; ++i) store_le16(token + kHeaderBytes + 2 * (p * kN + i), static_cast<uint16_t>(polynomials[p][i]));
    }
}
static void expand(const uint8_t seeds[64], const uint8_t descriptor[16], uint8_t token[kTokenBytes]) {
    const uint8_t *rho = seeds; const uint8_t *sigma = seeds + 32;
    const uint32_t request_id = load_le32(descriptor + 8); const uint8_t row = descriptor[4];
    if (!valid_descriptor(descriptor)) { write_token(token, request_id, row, kBadDescriptor, nullptr, nullptr, nullptr, nullptr, nullptr); return; }
    uint32_t a0[kN], a1[kN], s0[kN], s1[kN], e[kN];
    const bool complete = sample_matrix(rho, 0, row, a0) && sample_matrix(rho, 1, row, a1);
    cbd3_ntt(sigma, 0, s0); cbd3_ntt(sigma, 1, s1); cbd3_ntt(sigma, static_cast<uint8_t>(row + 2), e);
    write_token(token, request_id, row, complete ? kOk : kLimitExceeded, a0, a1, s0, s1, e);
    clear_bytes(a0, sizeof(a0)); clear_bytes(a1, sizeof(a1)); clear_bytes(s0, sizeof(s0)); clear_bytes(s1, sizeof(s1)); clear_bytes(e, sizeof(e));
}
}  // namespace
extern "C" void dr2c_keygen_row_expand(const uint8_t seeds[64], const uint8_t descriptor[16], uint8_t token[2576]) { expand(seeds, descriptor, token); }
