// SPDX-License-Identifier: Apache-2.0
#include "dr12_mldsa44_sign_internal.hpp"

using namespace phoenix_sdr_dsp::pqc::dr11;
using namespace phoenix_sdr_dsp::pqc::dr12;

extern "C" void dr12_mldsa44_sign_w2_challenge_cs(
    const uint8_t in_token[10660],
    uint8_t out_token[12328]) {

  clear_bytes(out_token, 12328);

  const uint32_t request_id = load_le32(in_token + 0);
  const uint8_t *c_tilde = in_token + 4; // 32 B
  const uint8_t *s_encoded = in_token + 36;   // 768 B
  const uint8_t *t0_encoded = in_token + 804; // 1664 B

  store_le32(out_token + 0, request_id);

  // Copy c_tilde (32 B) -> out_token[4..35]
  DR11_DISABLE_UNROLL
  for (uint32_t i = 0; i < 32; ++i) out_token[4 + i] = c_tilde[i];

  // 1. Sample c = SampleInBall(c_tilde) -> NTT(c)
  int32_t c_poly[256];
  int32_t c_hat[256];
  sample_in_ball(c_tilde, c_poly);
  DR11_DISABLE_UNROLL
  for (uint32_t c = 0; c < 256; ++c) c_hat[c] = c_poly[c];
  ntt_kernel(c_hat);

  // 2. Compute z = y + INTT(c_hat * NTT(s1)) -> out_token[36..4131]
  int32_t s_poly[256];
  for (uint32_t j = 0; j < 4; ++j) {
    int32_t y_j[256];
    const uint8_t *y_src = in_token + 2468 + j * 1024;
    DR11_DISABLE_UNROLL
    for (uint32_t c = 0; c < 256; ++c) {
      y_j[c] = static_cast<int32_t>(load_le32(y_src + c * 4));
    }

    decode_sk_s_poly(s_encoded + j * 96, s_poly);
    ntt_kernel(s_poly);

    int32_t c_s1[256];
    basemul(c_s1, c_hat, s_poly);
    invntt_kernel(c_s1);

    uint8_t *z_dst = out_token + 36 + j * 1024;
    DR11_DISABLE_UNROLL
    for (uint32_t c = 0; c < 256; ++c) {
      int32_t z_val = canonicalize(y_j[c] + c_s1[c]);
      store_le32(z_dst + c * 4, static_cast<uint32_t>(z_val));
    }
  }

  // 3. Compute w_minus_cs2 = w - INTT(c_hat * NTT(s2)) -> out_token[4132..8227]
  for (uint32_t i = 0; i < 4; ++i) {
    int32_t w_i[256];
    const uint8_t *w_src = in_token + 6564 + i * 1024;
    DR11_DISABLE_UNROLL
    for (uint32_t c = 0; c < 256; ++c) {
      w_i[c] = static_cast<int32_t>(load_le32(w_src + c * 4));
    }

    decode_sk_s_poly(s_encoded + 384 + i * 96, s_poly);
    ntt_kernel(s_poly);

    int32_t c_s2[256];
    basemul(c_s2, c_hat, s_poly);
    invntt_kernel(c_s2);

    uint8_t *w_dst = out_token + 4132 + i * 1024;
    DR11_DISABLE_UNROLL
    for (uint32_t c = 0; c < 256; ++c) {
      int32_t w_val = canonicalize(w_i[c] - c_s2[c]);
      store_le32(w_dst + c * 4, static_cast<uint32_t>(w_val));
    }
  }

  // 4. Compute c*t0 = INTT(c_hat * NTT(t0)) -> out_token[8228..12323]
  for (uint32_t i = 0; i < 4; ++i) {
    decode_sk_t0_poly(t0_encoded + i * 416, s_poly);
    ntt_kernel(s_poly);

    int32_t c_t0[256];
    basemul(c_t0, c_hat, s_poly);
    invntt_kernel(c_t0);

    uint8_t *ct0_dst = out_token + 8228 + i * 1024;
    DR11_DISABLE_UNROLL
    for (uint32_t c = 0; c < 256; ++c) {
      store_le32(ct0_dst + c * 4, static_cast<uint32_t>(c_t0[c]));
    }
  }

  clear_bytes(s_poly, sizeof(s_poly));
  clear_bytes(c_poly, sizeof(c_poly));
  clear_bytes(c_hat, sizeof(c_hat));
}
