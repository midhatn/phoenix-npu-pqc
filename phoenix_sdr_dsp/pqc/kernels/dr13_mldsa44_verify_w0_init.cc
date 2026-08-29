// SPDX-License-Identifier: Apache-2.0
// DR13 Worker 0: Ingest pk, mu, sig -> Decode & norm check z, decode h, decode t1, NTT transforms
#include "dr13_mldsa44_verify_internal.hpp"

using namespace phoenix_sdr_dsp::pqc::dr11;
using namespace phoenix_sdr_dsp::pqc::dr12;
using namespace phoenix_sdr_dsp::pqc::dr13;

extern "C" void dr13_mldsa44_verify_w0_init(
    const uint8_t request[3796],
    const uint8_t descriptor[16],
    uint8_t out_token[10376]) {

  clear_bytes(out_token, 10376);

  const uint32_t request_id = load_le32(descriptor + 8);
  store_le32(out_token + 0, request_id);

  // Ingress payload layout:
  // [0..1311]    pk (rho: 32 B, t1: 1280 B)
  // [1312..1375] mu (64 B)
  // [1376..3795] sig (c_tilde: 32 B, z: 2304 B, h: 84 B)
  const uint8_t *rho = request + 0;
  const uint8_t *t1_bytes = request + 32;
  const uint8_t *mu = request + 1312;
  const uint8_t *c_tilde = request + 1376;
  const uint8_t *z_bytes = request + 1408;
  const uint8_t *h_bytes = request + 3712;

  // Copy rho (32 B) -> out_token[8..39]
  DR11_DISABLE_UNROLL
  for (uint32_t i = 0; i < 32; ++i) out_token[8 + i] = rho[i];

  // Copy mu (64 B) -> out_token[40..103]
  DR11_DISABLE_UNROLL
  for (uint32_t i = 0; i < 64; ++i) out_token[40 + i] = mu[i];

  // Copy c_tilde (32 B) -> out_token[104..135]
  DR11_DISABLE_UNROLL
  for (uint32_t i = 0; i < 32; ++i) out_token[104 + i] = c_tilde[i];

  uint32_t fail_flag = 0;

  // 1. Decode hints -> out_token[136..1159]
  uint8_t *h_out = out_token + 136;
  uint8_t h_arr[4][256];
  if (!decode_hints_and_check(h_bytes, h_arr)) {
    fail_flag = 2; // Hint format / count violation
  }
  DR11_DISABLE_UNROLL
  for (uint32_t i = 0; i < 4; ++i) {
    DR11_DISABLE_UNROLL
    for (uint32_t j = 0; j < 256; ++j) {
      h_out[i * 256 + j] = h_arr[i][j];
    }
  }

  // 2. Decode z, check norm (bound = gamma1 - beta = 130994), compute NTT(z) -> out_token[1160..5255]
  int32_t *z_hat_out = reinterpret_cast<int32_t *>(out_token + 1160);
  int32_t poly[256];
  for (uint32_t j = 0; j < 4; ++j) {
    if (!decode_z_poly_and_check(z_bytes + j * 576, poly, kGamma1 - kBeta)) {
      fail_flag = 1; // Norm violation
    }
    ntt_kernel(poly);
    DR11_DISABLE_UNROLL
    for (uint32_t c = 0; c < 256; ++c) {
      z_hat_out[j * 256 + c] = poly[c];
    }
  }

  // 3. Decode t1, multiply by 2^13, compute NTT(t1*2^13) -> out_token[5256..9351]
  int32_t *t1_hat_out = reinterpret_cast<int32_t *>(out_token + 5256);
  for (uint32_t i = 0; i < 4; ++i) {
    decode_t1_poly(t1_bytes + i * 320, poly);
    ntt_kernel(poly);
    DR11_DISABLE_UNROLL
    for (uint32_t c = 0; c < 256; ++c) {
      t1_hat_out[i * 256 + c] = poly[c];
    }
  }

  // 4. SampleInBall(c_tilde) -> c, compute NTT(c) -> out_token[9352..10375]
  int32_t *c_hat_out = reinterpret_cast<int32_t *>(out_token + 9352);
  sample_in_ball_sponge(c_tilde, poly);
  ntt_kernel(poly);
  DR11_DISABLE_UNROLL
  for (uint32_t c = 0; c < 256; ++c) {
    c_hat_out[c] = poly[c];
  }

  store_le32(out_token + 4, fail_flag);
  clear_bytes(poly, sizeof(poly));
  clear_bytes(h_arr, sizeof(h_arr));
}
