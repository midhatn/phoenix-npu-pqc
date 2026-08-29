// SPDX-License-Identifier: Apache-2.0
#include "dr12_mldsa44_sign_internal.hpp"

using namespace phoenix_sdr_dsp::pqc::dr11;
using namespace phoenix_sdr_dsp::pqc::dr12;

extern "C" void dr12_mldsa44_sign_w0_init(
    const uint8_t request[2656],
    const uint8_t descriptor[16],
    uint8_t out_token[2596]) {

  clear_bytes(out_token, 2596);

  const uint32_t request_id = load_le32(descriptor + 8);
  const uint8_t flags = descriptor[7];
  store_le32(out_token + 0, request_id);

  const uint8_t *sk = request;
  const uint8_t *rho = sk + 0;
  const uint8_t *K = sk + 32;
  const uint8_t *tr = sk + 64;
  const uint8_t *s_encoded = sk + 128;
  const uint8_t *t0_encoded = sk + 896;

  const uint8_t *m_or_mu = request + 2560;
  const uint8_t *rnd = request + 2624;

  // Copy rho (32 B) -> out_token[4..35]
  DR11_DISABLE_UNROLL
  for (uint32_t i = 0; i < 32; ++i) out_token[4 + i] = rho[i];

  // Derive mu (64 B) -> out_token[36..99]
  uint8_t *mu_dst = out_token + 36;
  if (flags & 1) {
    DR11_DISABLE_UNROLL
    for (uint32_t i = 0; i < 64; ++i) mu_dst[i] = m_or_mu[i];
  } else {
    alignas(8) uint8_t state[200];
    clear_bytes(state, sizeof(state));

    DR11_DISABLE_UNROLL
    for (uint32_t i = 0; i < 64; ++i) state[i] = tr[i];
    DR11_DISABLE_UNROLL
    for (uint32_t i = 0; i < 64; ++i) state[64 + i] = m_or_mu[i];
    state[128] ^= 0x1F;
    state[135] ^= 0x80;
    phoenix_sdr_dsp::pqc::dr1::keccak_f1600(state);

    DR11_DISABLE_UNROLL
    for (uint32_t i = 0; i < 64; ++i) mu_dst[i] = state[i];
    clear_bytes(state, sizeof(state));
  }

  // Derive rho_pp (64 B) -> out_token[100..163]
  uint8_t *rho_pp_dst = out_token + 100;
  {
    alignas(8) uint8_t state[200];
    clear_bytes(state, sizeof(state));

    DR11_DISABLE_UNROLL
    for (uint32_t i = 0; i < 32; ++i) state[i] = K[i];
    DR11_DISABLE_UNROLL
    for (uint32_t i = 0; i < 32; ++i) state[32 + i] = rnd[i];
    DR11_DISABLE_UNROLL
    for (uint32_t i = 0; i < 64; ++i) state[64 + i] = mu_dst[i];
    state[128] ^= 0x1F;
    state[135] ^= 0x80;
    phoenix_sdr_dsp::pqc::dr1::keccak_f1600(state);

    DR11_DISABLE_UNROLL
    for (uint32_t i = 0; i < 64; ++i) rho_pp_dst[i] = state[i];
    clear_bytes(state, sizeof(state));
  }

  // Copy s_encoded (768 B) -> out_token[164..931]
  DR11_DISABLE_UNROLL
  for (uint32_t i = 0; i < 768; ++i) out_token[164 + i] = s_encoded[i];

  // Copy t0_encoded (1664 B) -> out_token[932..2595]
  DR11_DISABLE_UNROLL
  for (uint32_t i = 0; i < 1664; ++i) out_token[932 + i] = t0_encoded[i];
}
