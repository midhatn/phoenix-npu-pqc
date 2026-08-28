// SPDX-License-Identifier: Apache-2.0
// Device-resident NIST DR10 Entropy/Key-Source & Sealed-Lifecycle Service on AMD Phoenix NPU (AIE2).

#include <stdint.h>
#include <new>

#include "dr1_keccak_f1600.hpp"

#if defined(__clang__)
#define DR10_DISABLE_UNROLL _Pragma("clang loop unroll(disable)")
#else
#define DR10_DISABLE_UNROLL
#endif

namespace phoenix_sdr_dsp::pqc::dr10 {

constexpr uint32_t kOk = 0u;
constexpr uint32_t kBadDescriptor = 2u;
constexpr uint32_t kBadAuthTag = 3u;
constexpr uint32_t kDomainMismatch = 4u;
constexpr uint32_t kEpochStale = 5u;
constexpr uint32_t kHealthCheckFailed = 6u;

// Tile-resident sealed session slot (64 bytes private material)
struct SealedSessionSlot {
  uint32_t is_active;
  uint32_t domain_id;
  uint32_t epoch;
  uint8_t key_material[64];
};

static SealedSessionSlot g_sealed_slot = {0, 0, 0, {0}};

static inline void clear_bytes(uint8_t *destination, uint32_t bytes) {
  DR10_DISABLE_UNROLL
  for (uint32_t index = 0; index < bytes; ++index) destination[index] = 0u;
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

static inline uint32_t compute_crc32(const uint8_t *data, uint32_t length) {
  uint32_t crc = 0xFFFFFFFFu;
  DR10_DISABLE_UNROLL
  for (uint32_t i = 0; i < length; ++i) {
    crc ^= data[i];
    DR10_DISABLE_UNROLL
    for (uint32_t j = 0; j < 8; ++j) {
      crc = (crc >> 1) ^ (0xEDB88320u & (-(crc & 1u)));
    }
  }
  return ~crc;
}

// Compute SHA3-256 over msg
static void compute_sha3_256(const uint8_t *msg, uint32_t msg_len, uint8_t out[32]) {
  alignas(8) uint8_t state[200];
  clear_bytes(state, sizeof(state));

  uint32_t offset = 0;
  while (offset + 136 <= msg_len) {
    DR10_DISABLE_UNROLL
    for (uint32_t i = 0; i < 136; ++i) state[i] ^= msg[offset + i];
    phoenix_sdr_dsp::pqc::dr1::keccak_f1600(state);
    offset += 136;
  }
  const uint32_t rem = msg_len - offset;
  DR10_DISABLE_UNROLL
  for (uint32_t i = 0; i < rem; ++i) state[i] ^= msg[offset + i];

  state[rem] ^= 0x06;
  state[135] ^= 0x80;
  phoenix_sdr_dsp::pqc::dr1::keccak_f1600(state);

  DR10_DISABLE_UNROLL
  for (uint32_t i = 0; i < 32; ++i) out[i] = state[i];
  clear_bytes(state, sizeof(state));
}

// Constant-time 32-byte equality check
static inline bool ct_eq32(const uint8_t a[32], const uint8_t b[32]) {
  uint8_t diff = 0;
  DR10_DISABLE_UNROLL
  for (uint32_t i = 0; i < 32; ++i) diff |= (a[i] ^ b[i]);
  return diff == 0;
}

} // namespace phoenix_sdr_dsp::pqc::dr10

using namespace phoenix_sdr_dsp::pqc::dr10;

// Request buffer: 256 B
// Descriptor buffer: 16 B
// Result buffer: 64 B
extern "C" void dr10_sealed_lifecycle_service(
    const uint8_t request[256],
    const uint8_t descriptor[16],
    uint8_t result[64]) {

  clear_bytes(result, 64);

  const uint8_t source_mode = descriptor[4];
  const uint8_t domain_id = descriptor[5];
  const uint32_t request_id = load_le32(descriptor + 8);
  const uint32_t epoch = load_le32(descriptor + 12);

  uint32_t status = kOk;

  if (source_mode == 0) { // Raw Ingress -> Conditioned Session Slot
    alignas(8) uint8_t cond_in[64 + 8];
    DR10_DISABLE_UNROLL
    for (uint32_t i = 0; i < 64; ++i) cond_in[i] = request[i];
    cond_in[64] = domain_id;
    store_le32(cond_in + 65, epoch);
    cond_in[69] = 0; cond_in[70] = 0; cond_in[71] = 0;

    uint8_t digest[32];
    compute_sha3_256(cond_in, 72, digest);

    g_sealed_slot.is_active = 1;
    g_sealed_slot.domain_id = domain_id;
    g_sealed_slot.epoch = epoch;
    DR10_DISABLE_UNROLL
    for (uint32_t i = 0; i < 32; ++i) g_sealed_slot.key_material[i] = digest[i];
    for (uint32_t i = 32; i < 64; ++i) g_sealed_slot.key_material[i] = 0;

    clear_bytes(cond_in, sizeof(cond_in));
    clear_bytes(digest, sizeof(digest));

  } else if (source_mode == 2) { // Authenticated External / QKD Key Ingress
    if (request[0] != 'Q' || request[1] != 'K' || request[2] != 'D' || request[3] != '1') {
      status = kBadDescriptor;
    } else {
      const uint32_t req_epoch = load_le32(request + 4);
      const uint8_t req_domain = request[8];

      if (req_domain != domain_id) {
        status = kDomainMismatch;
      } else if (req_epoch < epoch) {
        status = kEpochStale;
      } else {
        uint8_t expected_tag[32];
        compute_sha3_256(request, 96, expected_tag);

        const uint8_t *provided_tag = request + 96;
        if (!ct_eq32(expected_tag, provided_tag)) {
          status = kBadAuthTag;
        } else {
          // Install validated key
          g_sealed_slot.is_active = 1;
          g_sealed_slot.domain_id = domain_id;
          g_sealed_slot.epoch = req_epoch;
          DR10_DISABLE_UNROLL
          for (uint32_t i = 0; i < 64; ++i) g_sealed_slot.key_material[i] = request[32 + i];
        }
        clear_bytes(expected_tag, sizeof(expected_tag));
      }
    }
  } else if (source_mode == 3) { // Idempotent Sealed Session Teardown & Zeroization
    g_sealed_slot.is_active = 0;
    g_sealed_slot.domain_id = 0;
    g_sealed_slot.epoch = 0;
    clear_bytes(g_sealed_slot.key_material, 64);
    status = kOk;
  } else {
    status = kBadDescriptor;
  }

  // Fail-closed zeroization on any failure
  if (status != kOk) {
    g_sealed_slot.is_active = 0;
    g_sealed_slot.domain_id = 0;
    g_sealed_slot.epoch = 0;
    clear_bytes(g_sealed_slot.key_material, 64);
  }

  // Pack Result
  store_le32(result + 0, 0x4830524Du); // b"MR0H"
  store_le32(result + 4, request_id);
  store_le32(result + 8, status);
  store_le32(result + 12, g_sealed_slot.is_active);

  const uint32_t crc = compute_crc32(result, 16);
  store_le32(result + 16, crc);
}
