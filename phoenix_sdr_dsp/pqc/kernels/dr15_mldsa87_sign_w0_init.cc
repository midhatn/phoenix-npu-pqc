// SPDX-License-Identifier: Apache-2.0
// DR15 ML-DSA-87 Sign Worker 0: Streamlined Seed & s1 Expansion
#include "dr15_mldsa87_internal.hpp"

using namespace phoenix_sdr_dsp::pqc::dr11;
using namespace phoenix_sdr_dsp::pqc::dr12;
using namespace phoenix_sdr_dsp::pqc::dr13;
using namespace phoenix_sdr_dsp::pqc::dr14;
using namespace phoenix_sdr_dsp::pqc::dr15;

extern "C" void dr15_mldsa87_sign_w0_init(
    const uint8_t req_in[4960],
    const uint8_t descriptor[16],
    uint8_t out_token[8000]) {

  clear_bytes(out_token, 8000);

  const uint32_t request_id = load_le32(descriptor + 8);
  store_le32(out_token + 0, request_id);

  const uint8_t *rho = req_in + 0;
  const uint8_t *k_key = req_in + 32;
  const uint8_t *s1_bytes = req_in + 128;
  const uint8_t *mu_in = req_in + 4896;

  // Layout of out_token (8000 B):
  // [0..3]:     request_id (4 B)
  // [4..35]:    rho (32 B)
  // [36..99]:   mu (64 B)
  // [100..163]: rho_pp (64 B)
  // [164..7331]: s1_hat (7 polys * 1024 B = 7168 B)
  DR11_DISABLE_UNROLL
  for (uint32_t i = 0; i < 32; ++i) out_token[4 + i] = rho[i];
  DR11_DISABLE_UNROLL
  for (uint32_t i = 0; i < 64; ++i) out_token[36 + i] = mu_in[i];

  // Derive rho_pp = H(K || mu, 64)
  uint8_t k_mu[96];
  for (uint32_t i = 0; i < 32; ++i) k_mu[i] = k_key[i];
  for (uint32_t i = 0; i < 64; ++i) k_mu[32 + i] = mu_in[i];
  uint8_t rho_pp[64];
  keccak_sponge(136, k_mu, 96, 0x1F, rho_pp, 64);

  DR11_DISABLE_UNROLL
  for (uint32_t i = 0; i < 64; ++i) out_token[100 + i] = rho_pp[i];

  int32_t poly[256];
  int32_t *s1_hat = reinterpret_cast<int32_t *>(out_token + 164);
  for (uint32_t i = 0; i < 7; ++i) {
    decode_sk_s_poly(s1_bytes + i * 96, poly);
    DR11_DISABLE_UNROLL
    for (uint32_t c = 0; c < 256; ++c) poly[c] = canonicalize(poly[c]);
    ntt_kernel(poly);
    DR11_DISABLE_UNROLL
    for (uint32_t c = 0; c < 256; ++c) s1_hat[i * 256 + c] = poly[c];
  }

  clear_bytes(poly, sizeof(poly));
  clear_bytes(k_mu, sizeof(k_mu));
  clear_bytes(rho_pp, sizeof(rho_pp));
}
