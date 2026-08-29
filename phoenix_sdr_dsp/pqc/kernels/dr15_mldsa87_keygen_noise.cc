// SPDX-License-Identifier: Apache-2.0
// DR15 ML-DSA-87 KeyGen Worker 0 (Seed Expansion, Noise Sampling & NTT)
#include "dr15_mldsa87_internal.hpp"

using namespace phoenix_sdr_dsp::pqc::dr11;
using namespace phoenix_sdr_dsp::pqc::dr12;
using namespace phoenix_sdr_dsp::pqc::dr13;
using namespace phoenix_sdr_dsp::pqc::dr14;
using namespace phoenix_sdr_dsp::pqc::dr15;

extern "C" void dr15_mldsa87_keygen_noise(
    const uint8_t req_in[32],
    const uint8_t descriptor[16],
    uint8_t out_token[8704]) {

  clear_bytes(out_token, 8704);

  const uint32_t request_id = load_le32(descriptor + 8);
  store_le32(out_token + 0, request_id);

  // 1. Expand H(seed || 8 || 7) = SHAKE256(seed || 0x08 || 0x07, 128)
  alignas(8) uint8_t state[200];
  clear_bytes(state, sizeof(state));

  DR11_DISABLE_UNROLL
  for (uint32_t i = 0; i < 32; ++i) state[i] = req_in[i];
  state[32] = 8;
  state[33] = 7;
  state[34] ^= 0x1F;
  state[135] ^= 0x80;
  phoenix_sdr_dsp::pqc::dr1::keccak_f1600(state);

  // rho: 0..31 -> out_token[4..35]
  DR11_DISABLE_UNROLL
  for (uint32_t i = 0; i < 32; ++i) out_token[4 + i] = state[i];

  // K: 96..127 -> out_token[36..67]
  DR11_DISABLE_UNROLL
  for (uint32_t i = 0; i < 32; ++i) out_token[36 + i] = state[96 + i];

  // rho_prime: 32..95
  uint8_t rho_prime[64];
  DR11_DISABLE_UNROLL
  for (uint32_t i = 0; i < 64; ++i) rho_prime[i] = state[32 + i];
  clear_bytes(state, sizeof(state));

  int32_t poly[256];
  uint8_t *s1_bytes = out_token + 68;
  int32_t *s1_hat = reinterpret_cast<int32_t *>(out_token + 1508);

  for (uint16_t i = 0; i < 7; ++i) {
    sample_bounded_eta2(rho_prime, i, poly);
    encode_sk_s_poly(poly, s1_bytes + i * 96);
    DR11_DISABLE_UNROLL
    for (uint32_t c = 0; c < 256; ++c) {
      poly[c] = canonicalize(poly[c]);
    }
    ntt_kernel(poly);
    DR11_DISABLE_UNROLL
    for (uint32_t c = 0; c < 256; ++c) {
      s1_hat[i * 256 + c] = poly[c];
    }
  }

  uint8_t *s2_bytes = out_token + 740;
  for (uint16_t i = 0; i < 8; ++i) {
    sample_bounded_eta2(rho_prime, 7 + i, poly);
    encode_sk_s_poly(poly, s2_bytes + i * 96);
  }

  clear_bytes(poly, sizeof(poly));
  clear_bytes(rho_prime, sizeof(rho_prime));
}
