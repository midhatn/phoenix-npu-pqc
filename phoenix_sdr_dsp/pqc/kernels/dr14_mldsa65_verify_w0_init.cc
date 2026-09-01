// SPDX-License-Identifier: Apache-2.0
// DR14 ML-DSA-65 Verify Worker 0 (Init, NTT, Decode, Challenge - Clean Layout)
#include "dr14_mldsa65_internal.hpp"

using namespace phoenix_sdr_dsp::pqc::dr11;
using namespace phoenix_sdr_dsp::pqc::dr12;
using namespace phoenix_sdr_dsp::pqc::dr13;
using namespace phoenix_sdr_dsp::pqc::dr14;

extern "C" void dr14_mldsa65_verify_w0_init(
    const uint8_t req_in[5376],
    const uint8_t descriptor[16],
    uint8_t out_token[14000]) {

  clear_bytes(out_token, 14000);

  const uint32_t request_id = load_le32(descriptor + 8);
  const uint8_t ext_mu_flag = descriptor[7];
  store_le32(out_token + 0, request_id);

  // Request Layout:
  // [0..1951]:    pk (1952 B: rho 32 B + t1 1920 B)
  // [1952..2015]: msg_or_mu (64 B)
  // [2016..5324]: sig (3309 B: c_tilde 48 B + z 3200 B + h 61 B)

  const uint8_t *pk = req_in + 0;
  const uint8_t *msg_or_mu = req_in + 1952;
  const uint8_t *sig = req_in + 2016;

  const uint8_t *rho = pk + 0;
  const uint8_t *t1_bytes = pk + 32;

  const uint8_t *c_tilde = sig + 0;
  const uint8_t *z_bytes = sig + 48;
  const uint8_t *h_bytes = sig + 3248;

  uint8_t fail_flag = 0;

  // 1. Derive mu (64 B)
  uint8_t mu[64];
  if (ext_mu_flag == 1) {
    DR11_DISABLE_UNROLL
    for (uint32_t i = 0; i < 64; ++i) mu[i] = msg_or_mu[i];
  } else {
    uint8_t tr[64];
    keccak_sponge(136, pk, 1952, 0x1F, tr, 64);
    uint8_t tr_msg[128];
    DR11_DISABLE_UNROLL
    for (uint32_t i = 0; i < 64; ++i) tr_msg[i] = tr[i];
    DR11_DISABLE_UNROLL
    for (uint32_t i = 0; i < 64; ++i) tr_msg[64 + i] = msg_or_mu[i];
    keccak_sponge(136, tr_msg, 128, 0x1F, mu, 64);
  }

  // 2. Decode & check z norm < gamma1 - beta (524092) -> NTT(z)
  int32_t poly[256];
  int32_t *z_hat = reinterpret_cast<int32_t *>(out_token + 156); // [156..5275] (5120 B)

  for (uint32_t j = 0; j < 5; ++j) {
    if (!decode_z_poly65_and_check(z_bytes + j * 640, poly, kGamma1_65 - kBeta65)) {
      fail_flag = 1;
    }
    ntt_kernel(poly);
    DR11_DISABLE_UNROLL
    for (uint32_t c = 0; c < 256; ++c) z_hat[j * 256 + c] = poly[c];
  }

  // 3. Decode & check h (61 B -> 6 * 256 hints, max 55)
  uint8_t *h_plain = out_token + 5276; // [5276..6811] (1536 B)
  uint8_t h_decoded[6][256];
  if (!decode_hints65_and_check(h_bytes, h_decoded)) {
    fail_flag = 1;
  }
  for (uint32_t i = 0; i < 6; ++i) {
    DR11_DISABLE_UNROLL
    for (uint32_t c = 0; c < 256; ++c) h_plain[i * 256 + c] = h_decoded[i][c];
  }

  // 4. Decode t1 -> t1 * 2^d -> NTT(t1 * 2^d)
  int32_t *t1_hat = reinterpret_cast<int32_t *>(out_token + 6812); // [6812..12955] (6144 B)
  for (uint32_t i = 0; i < 6; ++i) {
    decode_t1_poly(t1_bytes + i * 320, poly);
    ntt_kernel(poly);
    DR11_DISABLE_UNROLL
    for (uint32_t c = 0; c < 256; ++c) t1_hat[i * 256 + c] = poly[c];
  }

  // 5. SampleInBall65(c_tilde) -> c -> NTT(c)
  int32_t *c_hat = reinterpret_cast<int32_t *>(out_token + 12956); // [12956..13979] (1024 B)
  sample_in_ball65(c_tilde, poly);
  ntt_kernel(poly);
  DR11_DISABLE_UNROLL
  for (uint32_t c = 0; c < 256; ++c) c_hat[c] = poly[c];

  out_token[4] = fail_flag;
  DR11_DISABLE_UNROLL
  for (uint32_t i = 0; i < 32; ++i) out_token[5 + i] = rho[i];
  DR11_DISABLE_UNROLL
  for (uint32_t i = 0; i < 48; ++i) out_token[37 + i] = c_tilde[i];
  DR11_DISABLE_UNROLL
  for (uint32_t i = 0; i < 64; ++i) out_token[85 + i] = mu[i];

  clear_bytes(poly, sizeof(poly));
}
