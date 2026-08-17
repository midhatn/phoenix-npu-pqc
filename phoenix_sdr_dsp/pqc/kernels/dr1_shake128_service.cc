// SPDX-License-Identifier: Apache-2.0
// DR1 fixed-request incremental SHAKE128 producer for rho || j || i.
//
// One C entry point is called exactly eight times by one worker.  Its
// core-local state carries SHAKE position and sequence; this avoids repeated
// ExternalFunction(source_file=...) object compilation exporting duplicate
// wrapper symbols on IRON/AIE builds.

#include <cstdint>

#include "dr1_keccak_f1600.hpp"

namespace {

constexpr uint32_t kRate = 168;
constexpr uint32_t kBlockBytes = 180;
constexpr uint32_t kDataOffset = 12;
constexpr uint32_t kBlockCap = 8;
constexpr uint32_t kBadDescriptor = 2;

struct ShakeStateV1 {
    // keccak_f1600 views this FIPS 202 byte state as little-endian uint64_t
    // lanes. Explicit alignment makes that cast defined for the static state.
    alignas(8) uint8_t state[200];
    uint16_t cursor;
    uint16_t rate;
    uint8_t suffix;
    uint8_t phase;
};

static_assert(alignof(ShakeStateV1) >= alignof(uint64_t), "Keccak state must be lane aligned");

struct ServiceStateV1 {
    ShakeStateV1 shake;
    uint8_t seed[34];
    uint8_t descriptor[16];
    uint32_t request_id;
    uint8_t next_block;
    uint8_t valid;
    uint8_t active;
};

static ServiceStateV1 g_service;

static void clear_bytes(void *address, uint32_t bytes) {
    volatile uint8_t *out = static_cast<volatile uint8_t *>(address);
    DR1_AIE_DISABLE_LOOP_UNROLL
    for (uint32_t index = 0; index < bytes; ++index) out[index] = 0;
}

static uint32_t load_le32(const uint8_t *input) {
    return static_cast<uint32_t>(input[0]) |
           (static_cast<uint32_t>(input[1]) << 8) |
           (static_cast<uint32_t>(input[2]) << 16) |
           (static_cast<uint32_t>(input[3]) << 24);
}

static void store_le16(uint8_t *output, uint16_t value) {
    output[0] = static_cast<uint8_t>(value);
    output[1] = static_cast<uint8_t>(value >> 8);
}

static void store_le32(uint8_t *output, uint32_t value) {
    output[0] = static_cast<uint8_t>(value);
    output[1] = static_cast<uint8_t>(value >> 8);
    output[2] = static_cast<uint8_t>(value >> 16);
    output[3] = static_cast<uint8_t>(value >> 24);
}

static bool valid_descriptor(const uint8_t descriptor[16]) {
    if (descriptor[0] != 1 || descriptor[1] != 0x11 || descriptor[2] != 0x44 || descriptor[3] != 0) return false;
    if (descriptor[4] > 3 || descriptor[5] > 3 || descriptor[6] != kBlockCap || descriptor[7] != 0) return false;
    return descriptor[12] == 0 && descriptor[13] == 0 && descriptor[14] == 0 && descriptor[15] == 0;
}

static void write_token_header(uint8_t output[kBlockBytes], uint32_t request_id, uint16_t sequence,
                               uint16_t bytes_valid, uint32_t status) {
    DR1_AIE_DISABLE_LOOP_UNROLL
    for (uint32_t index = 0; index < kBlockBytes; ++index) output[index] = 0;
    store_le32(output, request_id);
    store_le16(output + 4, sequence);
    store_le16(output + 6, bytes_valid);
    store_le32(output + 8, status);
}

static void absorb_byte(ShakeStateV1 *state, uint32_t position, uint8_t value) {
    state->state[position] ^= value;
}

static uint8_t squeeze_byte(const ShakeStateV1 *state, uint32_t position) {
    return state->state[position];
}

static bool same_request(const uint8_t rho[32], const uint8_t descriptor[16]) {
    if (!g_service.active) return false;
    DR1_AIE_DISABLE_LOOP_UNROLL
    for (uint32_t index = 0; index < 32; ++index) {
        if (g_service.seed[index] != rho[index]) return false;
    }
    DR1_AIE_DISABLE_LOOP_UNROLL
    for (uint32_t index = 0; index < 16; ++index) {
        if (g_service.descriptor[index] != descriptor[index]) return false;
    }
    return true;
}

static void begin_request(const uint8_t rho[32], const uint8_t descriptor[16]) {
    clear_bytes(&g_service, sizeof(g_service));
    DR1_AIE_DISABLE_LOOP_UNROLL
    for (uint32_t index = 0; index < 32; ++index) g_service.seed[index] = rho[index];
    g_service.seed[32] = descriptor[4];  // j, then i: required ExpandA wire order.
    g_service.seed[33] = descriptor[5];
    DR1_AIE_DISABLE_LOOP_UNROLL
    for (uint32_t index = 0; index < 16; ++index) g_service.descriptor[index] = descriptor[index];
    g_service.request_id = load_le32(descriptor + 8);
    g_service.active = 1;
    if (!valid_descriptor(descriptor)) return;

    g_service.shake.rate = kRate;
    g_service.shake.suffix = 0x1f;
    g_service.shake.phase = 1;
    DR1_AIE_DISABLE_LOOP_UNROLL
    for (uint32_t index = 0; index < 34; ++index) absorb_byte(&g_service.shake, index, g_service.seed[index]);
    absorb_byte(&g_service.shake, 34, g_service.shake.suffix);
    absorb_byte(&g_service.shake, kRate - 1, 0x80);
    phoenix_sdr_dsp::pqc::dr1::keccak_f1600(g_service.shake.state);
    g_service.shake.cursor = 0;
    g_service.shake.phase = 2;
    g_service.valid = 1;
}

// A shared, non-inlined dispatcher is called eight times through the one ABI
// entry point.  It protects AIE program size and keeps all request state local.
__attribute__((noinline)) static void emit_next(const uint8_t rho[32],
                                                 const uint8_t descriptor[16],
                                                 uint8_t output[kBlockBytes]) {
    // The fixed graph calls this function eight times per request.  A changed
    // rho/descriptor also resets an interrupted prior request before emitting.
    if (!same_request(rho, descriptor)) begin_request(rho, descriptor);

    const uint32_t block = g_service.next_block;
    if (!g_service.valid) {
        write_token_header(output, g_service.request_id, static_cast<uint16_t>(block), 0, kBadDescriptor);
    } else {
        write_token_header(output, g_service.request_id, static_cast<uint16_t>(block), kRate, 0);
        if (g_service.shake.cursor == kRate) {
            phoenix_sdr_dsp::pqc::dr1::keccak_f1600(g_service.shake.state);
            g_service.shake.cursor = 0;
        }
        DR1_AIE_DISABLE_LOOP_UNROLL
        for (uint32_t index = 0; index < kRate; ++index) {
            output[kDataOffset + index] = squeeze_byte(&g_service.shake, g_service.shake.cursor++);
        }
    }

    ++g_service.next_block;
    if (g_service.next_block == kBlockCap) clear_bytes(&g_service, sizeof(g_service));
}

}  // namespace

extern "C" {
void dr1_shake128_emit_next(const uint8_t rho[32], const uint8_t descriptor[16],
                            uint8_t output[kBlockBytes]) {
    emit_next(rho, descriptor, output);
}
}  // extern "C"
