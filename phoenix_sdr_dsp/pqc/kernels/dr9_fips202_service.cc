// SPDX-License-Identifier: Apache-2.0
// Device-resident NIST FIPS 202 Reusable Cryptographic Service on AMD Phoenix NPU (AIE2).
// Implements SHA3-224, SHA3-256, SHA3-384, SHA3-512, SHAKE128, and SHAKE256 on-device.

#include <stdint.h>
#include <new>

#include "dr1_keccak_f1600.hpp"

#if defined(__clang__)
#define DR9_DISABLE_UNROLL _Pragma("clang loop unroll(disable)")
#else
#define DR9_DISABLE_UNROLL
#endif

namespace phoenix_sdr_dsp::pqc::dr9 {

constexpr uint32_t kOk = 0u;
constexpr uint32_t kBadDescriptor = 2u;
constexpr uint32_t kBadToken = 3u;
constexpr uint32_t kLimitExceeded = 4u;

static inline void clear_bytes(uint8_t *destination, uint32_t bytes) {
  DR9_DISABLE_UNROLL
  for (uint32_t index = 0; index < bytes; ++index) destination[index] = 0u;
}

static inline uint32_t load_le32(const uint8_t *in) {
  return static_cast<uint32_t>(in[0]) | (static_cast<uint32_t>(in[1]) << 8) |
         (static_cast<uint32_t>(in[2]) << 16) | (static_cast<uint32_t>(in[3]) << 24);
}

static inline uint16_t load_le16(const uint8_t *in) {
  return static_cast<uint16_t>(in[0]) | (static_cast<uint16_t>(in[1]) << 8);
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

static inline uint32_t compute_crc32(const uint8_t *data, uint32_t length) {
  uint32_t crc = 0xFFFFFFFFu;
  DR9_DISABLE_UNROLL
  for (uint32_t i = 0; i < length; ++i) {
    crc ^= data[i];
    DR9_DISABLE_UNROLL
    for (uint32_t j = 0; j < 8; ++j) {
      crc = (crc >> 1) ^ (0xEDB88320u & (-(crc & 1u)));
    }
  }
  return ~crc;
}

} // namespace phoenix_sdr_dsp::pqc::dr9

using namespace phoenix_sdr_dsp::pqc::dr9;

// Ingress Request buffer: 2048 B
// Descriptor: 16 B
// Result buffer: 1044 B (20 B Header + up to 1024 B output)
extern "C" void dr9_fips202_service(
    const uint8_t request[2048],
    const uint8_t descriptor[16],
    uint8_t result[1044]) {

  if (!word_aligned(request) || !word_aligned(descriptor) || !word_aligned(result)) {
    clear_bytes(result, 1044);
    store_le32(result, 0);
    store_le32(result + 4, kBadToken);
    return;
  }

  const uint32_t request_id = load_le32(descriptor + 8);
  const uint8_t func_id = descriptor[4];
  const uint16_t msg_len = load_le16(descriptor + 12);
  uint16_t out_len = load_le16(descriptor + 14);

  // Validate limits
  if (msg_len > 2048) {
    clear_bytes(result, 1044);
    store_le32(result + 0, 0x4839524Du);
    store_le32(result + 4, request_id);
    store_le32(result + 8, kLimitExceeded);
    return;
  }

  uint32_t rate = 0;
  uint8_t suffix = 0;

  switch (func_id) {
    case 1: // SHA3-224
      rate = 144; suffix = 0x06; out_len = 28;
      break;
    case 2: // SHA3-256
      rate = 136; suffix = 0x06; out_len = 32;
      break;
    case 3: // SHA3-384
      rate = 104; suffix = 0x06; out_len = 48;
      break;
    case 4: // SHA3-512
      rate = 72;  suffix = 0x06; out_len = 64;
      break;
    case 5: // SHAKE128
      rate = 168; suffix = 0x1F;
      break;
    case 6: // SHAKE256
      rate = 136; suffix = 0x1F;
      break;
    default:
      clear_bytes(result, 1044);
      store_le32(result + 0, 0x4839524Du);
      store_le32(result + 4, request_id);
      store_le32(result + 8, kBadDescriptor);
      return;
  }

  if (out_len > 1024) {
    clear_bytes(result, 1044);
    store_le32(result + 0, 0x4839524Du);
    store_le32(result + 4, request_id);
    store_le32(result + 8, kLimitExceeded);
    return;
  }

  // Keccak State (200 B)
  alignas(8) uint8_t state[200];
  clear_bytes(state, sizeof(state));

  // 1. Absorb full blocks
  uint32_t offset = 0;
  while (offset + rate <= msg_len) {
    DR9_DISABLE_UNROLL
    for (uint32_t i = 0; i < rate; ++i) {
      state[i] ^= request[offset + i];
    }
    phoenix_sdr_dsp::pqc::dr1::keccak_f1600(state);
    offset += rate;
  }

  // 2. Absorb remaining partial block and apply domain suffix & 10*1 padding
  const uint32_t rem = msg_len - offset;
  DR9_DISABLE_UNROLL
  for (uint32_t i = 0; i < rem; ++i) {
    state[i] ^= request[offset + i];
  }

  // Padding
  state[rem] ^= suffix;
  state[rate - 1] ^= 0x80;
  phoenix_sdr_dsp::pqc::dr1::keccak_f1600(state);

  // 3. Squeeze output
  uint8_t *digest_out = result + 20;
  uint32_t sq_offset = 0;
  uint32_t rem_sq = out_len;

  while (rem_sq > 0) {
    const uint32_t chunk = (rem_sq < rate) ? rem_sq : rate;
    DR9_DISABLE_UNROLL
    for (uint32_t i = 0; i < chunk; ++i) {
      digest_out[sq_offset + i] = state[i];
    }
    sq_offset += chunk;
    rem_sq -= chunk;
    if (rem_sq > 0) {
      phoenix_sdr_dsp::pqc::dr1::keccak_f1600(state);
    }
  }

  // 4. Pack Header & CRC32
  store_le32(result + 0, 0x4839524Du); // b"MR9H"
  store_le32(result + 4, request_id);
  store_le32(result + 8, kOk);
  store_le32(result + 12, out_len);

  const uint32_t crc = compute_crc32(digest_out, out_len);
  store_le32(result + 16, crc);

  // Zeroize sensitive internal state
  clear_bytes(state, sizeof(state));
}
