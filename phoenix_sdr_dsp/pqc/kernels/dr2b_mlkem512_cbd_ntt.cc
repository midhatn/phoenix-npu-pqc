// SPDX-License-Identifier: Apache-2.0
// DR2b consumes one private SHAKE256 PRF token and emits only FIPS 203 NTT(a).
#include <cstdint>
#if defined(__clang__)
#define DR2B_DISABLE_UNROLL _Pragma("clang loop unroll(disable)")
#else
#define DR2B_DISABLE_UNROLL
#endif
namespace {
constexpr uint32_t kN = 256, kQ = 3329, kTokenBytes = 208, kHeaderBytes = 16;
constexpr uint32_t kPrfBytes = 192, kResultBytes = 528, kResultMagic = 0x4232524D;
constexpr uint32_t kOk = 0, kBadDescriptor = 2, kBadToken = 3;
// kZetas[k] = 17^BitRev7(k) mod q.  Keeping the fixed FIPS 203 twiddles in
// data avoids Peano lowering runtime bit reversal to unsupported G_CTTZ.
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
static uint16_t load_le16(const uint8_t *in) { return static_cast<uint16_t>(in[0]) | (static_cast<uint16_t>(in[1]) << 8); }
static uint32_t load_le32(const uint8_t *in) { return static_cast<uint32_t>(in[0]) | (static_cast<uint32_t>(in[1]) << 8) | (static_cast<uint32_t>(in[2]) << 16) | (static_cast<uint32_t>(in[3]) << 24); }
static void store_le16(uint8_t *out, uint16_t x) { out[0] = static_cast<uint8_t>(x); out[1] = static_cast<uint8_t>(x >> 8); }
static void store_le32(uint8_t *out, uint32_t x) { out[0] = static_cast<uint8_t>(x); out[1] = static_cast<uint8_t>(x >> 8); out[2] = static_cast<uint8_t>(x >> 16); out[3] = static_cast<uint8_t>(x >> 24); }
static uint32_t mod_mul(uint32_t a, uint32_t b) { return (a * b) % kQ; }
static uint32_t bit_at(const uint8_t *prf, uint32_t bit) { return (prf[bit >> 3] >> (bit & 7)) & 1u; }
static void cbd3(const uint8_t prf[kPrfBytes], uint32_t out[kN]) {
    DR2B_DISABLE_UNROLL
    for (uint32_t i = 0; i < kN; ++i) {
        const uint32_t bit = 6 * i;
        const int32_t value = static_cast<int32_t>(bit_at(prf, bit) + bit_at(prf, bit + 1) + bit_at(prf, bit + 2)) - static_cast<int32_t>(bit_at(prf, bit + 3) + bit_at(prf, bit + 4) + bit_at(prf, bit + 5));
        out[i] = static_cast<uint32_t>(value) + (static_cast<uint32_t>(value) >> 31) * kQ;
    }
}
__attribute__((noinline)) static void ntt(uint32_t r[kN]) {
    uint32_t k = 1;
    DR2B_DISABLE_UNROLL
    for (uint32_t stage = 0; stage < 7; ++stage) {
        const uint32_t length = 128u >> stage;
        DR2B_DISABLE_UNROLL
        for (uint32_t start = 0; start < kN; start += 2 * length) {
            const uint32_t zeta = kZetas[k++];
            DR2B_DISABLE_UNROLL
            for (uint32_t j = start; j < start + length; ++j) {
                const uint32_t t = mod_mul(zeta, r[j + length]);
                r[j + length] = r[j] >= t ? r[j] - t : r[j] + kQ - t;
                const uint32_t sum = r[j] + t;
                r[j] = sum >= kQ ? sum - kQ : sum;
            }
        }
    }
}
static void write_result(uint8_t result[kResultBytes], uint32_t request_id, uint32_t status, const uint32_t r[kN]) {
    DR2B_DISABLE_UNROLL
    for (uint32_t i = 0; i < kResultBytes; ++i) result[i] = 0;
    store_le32(result, kResultMagic); store_le32(result + 4, request_id); store_le32(result + 8, status);
    store_le16(result + 12, status == kOk ? kN : 0); result[14] = 7; result[15] = 0;
    if (status == kOk) { DR2B_DISABLE_UNROLL for (uint32_t i = 0; i < kN; ++i) store_le16(result + 16 + 2 * i, static_cast<uint16_t>(r[i])); }
}
__attribute__((noinline)) static void consume(const uint8_t token[kTokenBytes], uint8_t result[kResultBytes]) {
    const uint32_t request_id = load_le32(token); const uint16_t sequence = load_le16(token + 4); const uint16_t bytes = load_le16(token + 6); const uint32_t status = load_le32(token + 8);
    if (sequence != 0 || bytes != kPrfBytes || status != kOk || token[12] != 0 || token[13] != 0 || token[14] != 0 || token[15] != 0) { write_result(result, request_id, status == kBadDescriptor ? kBadDescriptor : kBadToken, nullptr); return; }
    uint32_t coefficients[kN]; cbd3(token + kHeaderBytes, coefficients); ntt(coefficients); write_result(result, request_id, kOk, coefficients);
    DR2B_DISABLE_UNROLL for (uint32_t i = 0; i < kN; ++i) coefficients[i] = 0;
}
}  // namespace
extern "C" void dr2b_cbd3_ntt_consume(const uint8_t token[208], uint8_t result[528]) { consume(token, result); }
