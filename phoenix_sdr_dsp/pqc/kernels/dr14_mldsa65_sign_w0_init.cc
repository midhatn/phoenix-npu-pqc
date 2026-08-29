// SPDX-License-Identifier: Apache-2.0
// DR14 ML-DSA-65 Sign Worker 0 (Init & NTT Precomputation)
#include "dr14_mldsa65_internal.hpp"

using namespace phoenix_sdr_dsp::pqc::dr11;
using namespace phoenix_sdr_dsp::pqc::dr12;
using namespace phoenix_sdr_dsp::pqc::dr14;

extern "C" void dr14_mldsa65_sign_w0_init(
    const uint8_t req_in[4096],
    const uint8_t descriptor[16],
    uint8_t out_token[17572]) {

  clear_bytes(out_token, 17572);

  const uint32_t request_id = load_le32(descriptor + 8);
  const uint8_t ext_mu_flag = descriptor[7];

  store_le32(out_token + 0, request_id);

  const uint8_t *sk = req_in;
  const uint8_t *msg_or_mu = req_in + 4032;

  const uint8_t *rho = sk + 0;
  const uint8_t *K = sk + 32;
  const uint8_t *tr = sk + 64;
  const uint8_t *s1_bytes = sk + 128;  // 5 * 128 = 640 B
  const uint8_t *s2_bytes = sk + 768;  // 6 * 128 = 768 B
  const uint8_t *t0_bytes = sk + 1536; // 6 * 416 = 2496 B

  // 1. Derive mu (64 B)
  uint8_t mu[64];
  if (ext_mu_flag == 1) {
    DR11_DISABLE_UNROLL
    for (uint32_t i = 0; i < 64; ++i) mu[i] = msg_or_mu[i];
  } else {
    uint8_t tr_msg[128];
    DR11_DISABLE_UNROLL
    for (uint32_t i = 0; i < 64; ++i) tr_msg[i] = tr[i];
    DR11_DISABLE_UNROLL
    for (uint32_t i = 0; i < 64; ++i) tr_msg[64 + i] = msg_or_mu[i];
    keccak_sponge(136, tr_msg, 128, 0x1F, mu, 64);
  }

  // 2. Derive rho_pp (64 B) = SHAKE256(K || rnd(0) || mu, 64)
  uint8_t rho_pp[64];
  uint8_t k_rnd_mu[128];
  DR11_DISABLE_UNROLL
  for (uint32_t i = 0; i < 32; ++i) k_rnd_mu[i] = K[i];
  clear_bytes(k_rnd_mu + 32, 32);
  DR11_DISABLE_UNROLL
  for (uint32_t i = 0; i < 64; ++i) k_rnd_mu[64 + i] = mu[i];
  keccak_sponge(136, k_rnd_mu, 128, 0x1F, rho_pp, 64);

  // Layout:
  // [0..3]:     request_id (4 B)
  // [4..35]:    rho (32 B)
  // [36..99]:   mu (64 B)
  // [100..163]: rho_pp (64 B)
  // [164..5283]: s1_hat (5 * 1024 = 5120 B)
  // [5284..11427]: s2_hat (6 * 1024 = 6144 B)
  // [11428..17571]: t0_hat (6 * 1024 = 6144 B)

  DR11_DISABLE_UNROLL
  for (uint32_t i = 0; i < 32; ++i) out_token[4 + i] = rho[i];
  DR11_DISABLE_UNROLL
  for (uint32_t i = 0; i < 64; ++i) out_token[36 + i] = mu[i];
  DR11_DISABLE_UNROLL
  for (uint32_t i = 0; i < 64; ++i) out_token[100 + i] = rho_pp[i];

  int32_t poly[256];

  // Precompute s1_hat[0..4]
  int32_t *s1_hat_dst = reinterpret_cast<int32_t *>(out_token + 164);
  for (uint32_t j = 0; j < 5; ++j) {
    decode_s_poly_eta4(s1_bytes + j * 128, poly);
    ntt_kernel(poly);
    DR11_DISABLE_UNROLL
    for (uint32_t c = 0; c < 256; ++c) s1_hat_dst[j * 256 + c] = poly[c];
  }

  // Precompute s2_hat[0..5]
  int32_t *s2_hat_dst = reinterpret_cast<int32_t *>(out_token + 5284);
  for (uint32_t i = 0; i < 6; ++i) {
    decode_s_poly_eta4(s2_bytes + i * 128, poly);
    ntt_kernel(poly);
    DR11_DISABLE_UNROLL
    for (uint32_t c = 0; c < 256; ++c) s2_hat_dst[i * 256 + c] = poly[c];
  }

  // Precompute t0_hat[0..5]
  int32_t *t0_hat_dst = reinterpret_cast<int32_t *>(out_token + 11428);
  for (uint32_t i = 0; i < 6; ++i) {
    decode_sk_t0_poly(t0_bytes + i * 416, poly);
    ntt_kernel(poly);
    DR11_DISABLE_UNROLL
    for (uint32_t c = 0; c < 256; ++c) t0_hat_dst[i * 256 + c] = poly[c];
  }

  clear_bytes(poly, sizeof(poly));
  clear_bytes(mu, sizeof(mu));
  clear_bytes(rho_pp, sizeof(rho_pp));
  clear_bytes(k_rnd_mu, sizeof(k_rnd_mu));
}
