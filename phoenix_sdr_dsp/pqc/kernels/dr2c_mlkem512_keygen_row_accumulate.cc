// SPDX-License-Identifier: Apache-2.0
// DR2c consumes the private expansion token and emits only one t-hat row.
#include <cstdint>

#if defined(__clang__)
#define DR2C_DISABLE_UNROLL _Pragma("clang loop unroll(disable)")
#else
#define DR2C_DISABLE_UNROLL
#endif

namespace {
constexpr uint32_t kN = 256, kQ = 3329, kTokenBytes = 2576, kResultBytes = 528;
constexpr uint32_t kHeaderBytes = 16, kResultMagic = 0x4332524D;
constexpr uint32_t kOk = 0, kBadDescriptor = 2, kBadToken = 3;
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
static void clear_bytes(void *address, uint32_t bytes) { volatile uint8_t *out = static_cast<volatile uint8_t *>(address); DR2C_DISABLE_UNROLL for (uint32_t i = 0; i < bytes; ++i) out[i] = 0; }
static uint16_t load_le16(const uint8_t *in) { return static_cast<uint16_t>(in[0]) | (static_cast<uint16_t>(in[1]) << 8); }
static uint32_t load_le32(const uint8_t *in) { return static_cast<uint32_t>(in[0]) | (static_cast<uint32_t>(in[1]) << 8) | (static_cast<uint32_t>(in[2]) << 16) | (static_cast<uint32_t>(in[3]) << 24); }
static void store_le16(uint8_t *out, uint16_t x) { out[0] = static_cast<uint8_t>(x); out[1] = static_cast<uint8_t>(x >> 8); }
static void store_le32(uint8_t *out, uint32_t x) { out[0] = static_cast<uint8_t>(x); out[1] = static_cast<uint8_t>(x >> 8); out[2] = static_cast<uint8_t>(x >> 16); out[3] = static_cast<uint8_t>(x >> 24); }
static uint32_t mod_mul(uint32_t a, uint32_t b) { return (a * b) % kQ; }
static void write_result(uint8_t result[kResultBytes], uint32_t request_id, uint8_t row, uint32_t status, const uint32_t r[kN]) {
    clear_bytes(result, kResultBytes); store_le32(result, kResultMagic); store_le32(result + 4, request_id); store_le32(result + 8, status); store_le16(result + 12, status == kOk ? kN : 0); result[14] = row;
    if (status == kOk) { DR2C_DISABLE_UNROLL for (uint32_t i = 0; i < kN; ++i) store_le16(result + 16 + 2 * i, static_cast<uint16_t>(r[i])); }
}
static bool load_poly(const uint8_t token[kTokenBytes], uint32_t polynomial, uint32_t out[kN]) {
    DR2C_DISABLE_UNROLL
    for (uint32_t i = 0; i < kN; ++i) { const uint32_t value = load_le16(token + kHeaderBytes + 2 * (polynomial * kN + i)); if (value >= kQ) return false; out[i] = value; }
    return true;
}
static void multiply_ntts(const uint32_t a[kN], const uint32_t b[kN], uint32_t r[kN]) {
    DR2C_DISABLE_UNROLL
    for (uint32_t i = 0; i < 64; ++i) {
        const uint32_t gamma = kZetas[64 + i]; const uint32_t a0 = a[4 * i], a1 = a[4 * i + 1], a2 = a[4 * i + 2], a3 = a[4 * i + 3]; const uint32_t b0 = b[4 * i], b1 = b[4 * i + 1], b2 = b[4 * i + 2], b3 = b[4 * i + 3];
        r[4 * i] = (mod_mul(a0, b0) + mod_mul(gamma, mod_mul(a1, b1))) % kQ; r[4 * i + 1] = (mod_mul(a0, b1) + mod_mul(a1, b0)) % kQ;
        r[4 * i + 2] = (mod_mul(a2, b2) + mod_mul(kQ - gamma, mod_mul(a3, b3))) % kQ; r[4 * i + 3] = (mod_mul(a2, b3) + mod_mul(a3, b2)) % kQ;
    }
}
static void accumulate(uint8_t token[kTokenBytes], uint8_t result[kResultBytes]) {
    const uint32_t request_id = load_le32(token); const uint32_t status = load_le32(token + 4); const uint8_t row = token[8];
    if (row > 1 || token[9] != 0 || token[10] != 0 || token[11] != 0 || token[12] != 0 || token[13] != 0 || token[14] != 0 || token[15] != 0) { write_result(result, request_id, row, kBadToken, nullptr); clear_bytes(token, kTokenBytes); return; }
    if (status != kOk) { write_result(result, request_id, row, status == 1 || status == kBadDescriptor ? status : kBadToken, nullptr); clear_bytes(token, kTokenBytes); return; }
    uint32_t a0[kN], a1[kN], s0[kN], s1[kN], e[kN], p0[kN], p1[kN], out[kN];
    const bool valid = load_poly(token, 0, a0) && load_poly(token, 1, a1) && load_poly(token, 2, s0) && load_poly(token, 3, s1) && load_poly(token, 4, e);
    if (!valid) { write_result(result, request_id, row, kBadToken, nullptr); } else { multiply_ntts(a0, s0, p0); multiply_ntts(a1, s1, p1); DR2C_DISABLE_UNROLL for (uint32_t i = 0; i < kN; ++i) out[i] = (p0[i] + p1[i] + e[i]) % kQ; write_result(result, request_id, row, kOk, out); }
    clear_bytes(a0, sizeof(a0)); clear_bytes(a1, sizeof(a1)); clear_bytes(s0, sizeof(s0)); clear_bytes(s1, sizeof(s1)); clear_bytes(e, sizeof(e)); clear_bytes(p0, sizeof(p0)); clear_bytes(p1, sizeof(p1)); clear_bytes(out, sizeof(out)); clear_bytes(token, kTokenBytes);
}
}  // namespace
extern "C" void dr2c_keygen_row_accumulate(uint8_t token[2576], uint8_t result[528]) { accumulate(token, result); }
