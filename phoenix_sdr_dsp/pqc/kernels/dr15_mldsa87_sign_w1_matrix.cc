// SPDX-License-Identifier: Apache-2.0
// DR15 ML-DSA-87 Sign Worker 1: Matrix Streaming & Challenge Generation
#include "dr15_mldsa87_internal.hpp"

using namespace phoenix_sdr_dsp::pqc::dr11;
using namespace phoenix_sdr_dsp::pqc::dr12;
using namespace phoenix_sdr_dsp::pqc::dr13;
using namespace phoenix_sdr_dsp::pqc::dr14;
using namespace phoenix_sdr_dsp::pqc::dr15;

extern "C" void dr15_mldsa87_sign_w1_matrix(
    const uint8_t in_token[8000],
    uint8_t out_token[14500]) {

  clear_bytes(out_token, 14500);

  const uint32_t request_id = load_le32(in_token + 0);
  store_le32(out_token + 0, request_id);

  const uint8_t *rho = in_token + 4;
  const uint8_t *mu = in_token + 36;
  const uint8_t *rho_pp = in_token + 100;
  const int32_t *s1_hat = reinterpret_cast<const int32_t *>(in_token + 164);

  // Layout of out_token (14500 B):
  // [0..3]:      request_id (4 B)
  // [4..35]:     c_tilde (32 B)
  // [36..7203]:  y (7 polys * 1024 B = 7168 B)
  // [7204..14371]: s1_hat (7 polys * 1024 B = 7168 B)
  uint8_t *c_tilde_out = out_token + 4;
  int32_t *y_out = reinterpret_cast<int32_t *>(out_token + 36);
  int32_t *s1_hat_out = reinterpret_cast<int32_t *>(out_token + 7204);

  DR11_DISABLE_UNROLL
  for (uint32_t i = 0; i < 7168; ++i) {
    reinterpret_cast<uint8_t *>(s1_hat_out)[i] = reinterpret_cast<const uint8_t *>(s1_hat)[i];
  }

  int32_t y_poly[256];
  int32_t y_hat[256];
  int32_t w_plain[8 * 256];
  int32_t w_hat[256];
  int32_t a_entry[256];
  int32_t prod[256];
  uint8_t w1_bytes[1024];
  uint8_t c_tilde[32];
  int32_t poly[256];

  uint16_t kappa = 0;
  clear_bytes(w_plain, sizeof(w_plain));

  // 1. Expand y and Matrix multiply A * y
  for (uint8_t col = 0; col < 7; ++col) {
    sample_mask_poly_87(rho_pp, kappa + col, y_poly);
    DR11_DISABLE_UNROLL
    for (uint32_t c = 0; c < 256; ++c) {
      y_out[col * 256 + c] = y_poly[c];
      y_hat[c] = y_poly[c];
    }
    ntt_kernel(y_hat);

    for (uint8_t row = 0; row < 8; ++row) {
      expand_a_sponge(rho, col, row, a_entry);
      basemul(prod, a_entry, y_hat);
      DR11_DISABLE_UNROLL
      for (uint32_t c = 0; c < 256; ++c) {
        w_plain[row * 256 + c] = canonicalize(w_plain[row * 256 + c] + prod[c]);
      }
    }
  }

  // 2. INTT(w) & HighBits(w) -> w1
  for (uint8_t row = 0; row < 8; ++row) {
    DR11_DISABLE_UNROLL
    for (uint32_t c = 0; c < 256; ++c) w_hat[c] = w_plain[row * 256 + c];
    invntt_kernel(w_hat);
    DR11_DISABLE_UNROLL
    for (uint32_t c = 0; c < 256; ++c) {
      int32_t r1, r0;
      decompose65(w_hat[c], r1, r0);
      poly[c] = r1;
    }
    encode_w1_poly65(poly, w1_bytes + row * 128);
  }

  // 3. Challenge hash c_tilde = H(mu || w1, 32)
  uint8_t mu_w1[1088];
  for (uint32_t i = 0; i < 64; ++i) mu_w1[i] = mu[i];
  for (uint32_t i = 0; i < 1024; ++i) mu_w1[64 + i] = w1_bytes[i];
  keccak_sponge(136, mu_w1, 1088, 0x1F, c_tilde_out, 32);

  clear_bytes(y_poly, sizeof(y_poly));
  clear_bytes(y_hat, sizeof(y_hat));
  clear_bytes(w_plain, sizeof(w_plain));
  clear_bytes(w_hat, sizeof(w_hat));
  clear_bytes(a_entry, sizeof(a_entry));
  clear_bytes(prod, sizeof(prod));
  clear_bytes(w1_bytes, sizeof(w1_bytes));
  clear_bytes(c_tilde, sizeof(c_tilde));
  clear_bytes(poly, sizeof(poly));
}
