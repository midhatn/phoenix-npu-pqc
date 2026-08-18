// SPDX-License-Identifier: Apache-2.0
// Diagnostic-only final-token producer for the DR2d terminal-path probe.
// It is never referenced by the production six-worker KeyGen graph.
#include "dr2d_mlkem512_kpke_keygen_internal.hpp"

#include <new>

namespace {
using namespace phoenix_sdr_dsp::pqc::dr2d;

constexpr uint32_t kProbeRequestId = 0xD2D00001u;

static uint16_t probe_lane(uint32_t polynomial, uint32_t lane, uint8_t seed) {
  const uint32_t ascending = 13u * lane + seed;
  const uint32_t shallow = 11u * lane + 3u * seed;
  if (polynomial == 0) return static_cast<uint16_t>(ascending);
  if (polynomial == 1) return static_cast<uint16_t>(kQ - 1u - ascending);
  if (polynomial == 2) return static_cast<uint16_t>(shallow);
  return static_cast<uint16_t>(kQ - 1u - shallow);
}

static bool store_probe_poly_pairs(uint8_t out[2 * kN], uint32_t polynomial,
                                   uint8_t seed) {
  constexpr uintptr_t kWordAlignmentMask = alignof(uint32_t) - 1u;
  if ((reinterpret_cast<uintptr_t>(out) & kWordAlignmentMask) != 0) return false;
  DR2D_DISABLE_UNROLL
  for (uint32_t pair = 0; pair < kN / 2; ++pair) {
    const uint32_t a = probe_lane(polynomial, 2 * pair, seed);
    const uint32_t b = probe_lane(polynomial, 2 * pair + 1, seed);
    const uint32_t word = (a & 0xffffu) | ((b & 0xffffu) << 16);
    ::new (static_cast<void *>(out + 4 * pair)) uint32_t(word);
  }
  return true;
}

static void produce(uint8_t d[32], uint8_t descriptor[16],
                    uint8_t final_token[kFinalTokenBytes]) {
  const uint32_t id = load_le32(descriptor + 8);
  if (!valid_descriptor(descriptor) || id != kProbeRequestId) {
    write_header(final_token, kFinalTokenBytes, id, kBadDescriptor,
                 kFinalHeaderBytes);
  } else {
    const uint8_t seed = descriptor[8];
    write_header(final_token, kFinalTokenBytes, id, kOk, kFinalHeaderBytes);
    DR2D_DISABLE_UNROLL
    for (uint32_t i = 0; i < 32; ++i)
      final_token[kFinalRhoOffset + i] =
          static_cast<uint8_t>(0xa5u ^ descriptor[8 + (i & 3u)] ^ i);
    const bool stored = store_probe_poly_pairs(final_token + kFinalT0Offset, 0, seed) &&
                        store_probe_poly_pairs(final_token + kFinalT1Offset, 1, seed) &&
                        store_probe_poly_pairs(final_token + kFinalS0Offset, 2, seed) &&
                        store_probe_poly_pairs(final_token + kFinalS1Offset, 3, seed);
    if (!stored)
      write_header(final_token, kFinalTokenBytes, id, kBadToken, kFinalHeaderBytes);
  }
  clear_bytes(d, 32);
  clear_bytes(descriptor, 16);
}
}  // namespace

extern "C" void dr2d_kpke_keygen_terminal_probe(
    uint8_t d[32], uint8_t descriptor[16], uint8_t final_token[2112]) {
  produce(d, descriptor, final_token);
}
