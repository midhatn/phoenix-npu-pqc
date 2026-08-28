// SPDX-License-Identifier: Apache-2.0
#include "dr11_mldsa44_internal.hpp"

using namespace phoenix_sdr_dsp::pqc::dr11;

extern "C" void dr11_mldsa44_keygen_noise(
    const uint8_t request[32],
    const uint8_t descriptor[16],
    uint8_t out_token[9028]) {

  clear_bytes(out_token, 9028);

  const uint32_t request_id = load_le32(descriptor + 8);
  store_le32(out_token + 0, request_id);

  // 1. Expand H(xi || bytes([4, 4])) = SHAKE256(xi || 0x04 || 0x04, 128) -> rho[32], sigma[64], K[32]
  alignas(8) uint8_t state[200];
  clear_bytes(state, sizeof(state));

  DR11_DISABLE_UNROLL
  for (uint32_t i = 0; i < 32; ++i) state[i] = request[i];
  state[32] = 4;
  state[33] = 4;
  state[34] ^= 0x1F;
  state[135] ^= 0x80;
  phoenix_sdr_dsp::pqc::dr1::keccak_f1600(state);

  // rho: 0..31 -> out_token[4..35]
  DR11_DISABLE_UNROLL
  for (uint32_t i = 0; i < 32; ++i) out_token[4 + i] = state[i];

  // K: 96..127 -> out_token[36..67]
  DR11_DISABLE_UNROLL
  for (uint32_t i = 0; i < 32; ++i) out_token[36 + i] = state[96 + i];

  // sigma: 32..95
  uint8_t sigma[64];
  DR11_DISABLE_UNROLL
  for (uint32_t i = 0; i < 64; ++i) sigma[i] = state[32 + i];
  clear_bytes(state, sizeof(state));

  // 2. Sample s1[0..3], encode, NTT, and store directly into out_token + 836 (s1_ntt)
  int32_t poly[256];
  for (uint16_t j = 0; j < 4; ++j) {
    sample_bounded_eta2(sigma, j, poly);
    encode_sk_s_poly(poly, out_token + 68 + j * 96);
    ntt_kernel(poly);
    uint8_t *dst = out_token + 836 + j * 1024;
    DR11_DISABLE_UNROLL
    for (uint32_t c = 0; c < 256; ++c) {
      store_le32(dst + c * 4, static_cast<uint32_t>(poly[c]));
    }
  }

  // 3. Sample s2[0..3], encode, and store directly into out_token + 4932
  for (uint16_t i = 0; i < 4; ++i) {
    sample_bounded_eta2(sigma, 4 + i, poly);
    encode_sk_s_poly(poly, out_token + 68 + 384 + i * 96);
    uint8_t *dst = out_token + 4932 + i * 1024;
    DR11_DISABLE_UNROLL
    for (uint32_t c = 0; c < 256; ++c) {
      store_le32(dst + c * 4, static_cast<uint32_t>(poly[c]));
    }
  }

  clear_bytes(sigma, sizeof(sigma));
  clear_bytes(poly, sizeof(poly));
}
