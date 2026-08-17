// SPDX-License-Identifier: Apache-2.0
// DR2b fixed SHAKE256 PRF worker: SHAKE256(sigma || counter, 192 bytes).
#include <cstdint>
#include "dr1_keccak_f1600.hpp"

namespace {
constexpr uint32_t kRate = 136;
constexpr uint32_t kSigmaBytes = 32;
constexpr uint32_t kPrfBytes = 192;
constexpr uint32_t kTokenBytes = 208;
constexpr uint32_t kHeaderBytes = 16;
constexpr uint32_t kBadDescriptor = 2;
constexpr uint32_t kOk = 0;

static void clear(uint8_t *out, uint32_t bytes) {
    DR1_AIE_DISABLE_LOOP_UNROLL
    for (uint32_t i = 0; i < bytes; ++i) out[i] = 0;
}
static uint32_t load_le32(const uint8_t *in) {
    return static_cast<uint32_t>(in[0]) | (static_cast<uint32_t>(in[1]) << 8) |
           (static_cast<uint32_t>(in[2]) << 16) | (static_cast<uint32_t>(in[3]) << 24);
}
static void store_le16(uint8_t *out, uint16_t value) { out[0] = static_cast<uint8_t>(value); out[1] = static_cast<uint8_t>(value >> 8); }
static void store_le32(uint8_t *out, uint32_t value) {
    out[0] = static_cast<uint8_t>(value); out[1] = static_cast<uint8_t>(value >> 8);
    out[2] = static_cast<uint8_t>(value >> 16); out[3] = static_cast<uint8_t>(value >> 24);
}
static bool valid_descriptor(const uint8_t d[16]) {
    return d[0] == 1 && d[1] == 0x22 && d[2] == 0x52 && d[3] == 0 && d[4] <= 3 &&
           d[5] == 3 && d[6] == 192 && d[7] == 0 && d[12] == 0 && d[13] == 0 &&
           d[14] == 0 && d[15] == 0;
}
static void write_header(uint8_t out[kTokenBytes], uint32_t request_id, uint32_t status) {
    clear(out, kTokenBytes);
    store_le32(out, request_id);
    store_le16(out + 4, 0);
    store_le16(out + 6, status == kOk ? kPrfBytes : 0);
    store_le32(out + 8, status);
}
__attribute__((noinline)) static void emit(
    const uint8_t sigma[kSigmaBytes], const uint8_t descriptor[16], uint8_t out[kTokenBytes]
) {
    const uint32_t request_id = load_le32(descriptor + 8);
    if (!valid_descriptor(descriptor)) { write_header(out, request_id, kBadDescriptor); return; }
    write_header(out, request_id, kOk);
    alignas(8) uint8_t state[200];
    clear(state, sizeof(state));
    DR1_AIE_DISABLE_LOOP_UNROLL
    for (uint32_t i = 0; i < kSigmaBytes; ++i) state[i] ^= sigma[i];
    state[kSigmaBytes] ^= descriptor[4];
    state[33] ^= 0x1f;
    state[kRate - 1] ^= 0x80;
    phoenix_sdr_dsp::pqc::dr1::keccak_f1600(state);
    DR1_AIE_DISABLE_LOOP_UNROLL
    for (uint32_t i = 0; i < kRate; ++i) out[kHeaderBytes + i] = state[i];
    phoenix_sdr_dsp::pqc::dr1::keccak_f1600(state);
    DR1_AIE_DISABLE_LOOP_UNROLL
    for (uint32_t i = kRate; i < kPrfBytes; ++i) out[kHeaderBytes + i] = state[i - kRate];
    clear(state, sizeof(state));
}
}  // namespace
extern "C" void dr2b_shake256_prf_emit(const uint8_t sigma[32], const uint8_t descriptor[16], uint8_t output[208]) { emit(sigma, descriptor, output); }
