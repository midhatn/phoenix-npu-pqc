// SPDX-License-Identifier: Apache-2.0
// DR14 ML-DSA-65 Verify Worker 1 (Matrix Multiply & UseHint)
#include "dr14_mldsa65_internal.hpp"

using namespace phoenix_sdr_dsp::pqc::dr11;
using namespace phoenix_sdr_dsp::pqc::dr12;
using namespace phoenix_sdr_dsp::pqc::dr13;
using namespace phoenix_sdr_dsp::pqc::dr14;

extern "C" void dr14_mldsa65_verify_w1_matrix(
    const uint8_t in_token[14000],
    uint8_t out_token[104]) {

  clear_bytes(out_token, 104);

  const uint32_t request_id = load_le32(in_token + 0);
  const uint8_t initial_fail = in_token[4];
  const uint8_t *rho = in_token + 5;
  const uint8_t *c_tilde = in_token + 37;
  const uint8_t *mu = in_token + 85;

  const int32_t *z_hat = reinterpret_cast<const int32_t *>(in_token + 156);
  const uint8_t *h_plain = in_token + 5276;
  const int32_t *t1_hat = reinterpret_cast<const int32_t *>(in_token + 6812);
  const int32_t *c_hat = reinterpret_cast<const int32_t *>(in_token + 12956);

  store_le32(out_token + 0, request_id);

  if (initial_fail != 0) {
    out_token[4] = 0; // Fail
    return;
  }

  uint8_t w1_prime_bytes[768];
  int32_t w_prime[256];
  int32_t a_entry[256];
  int32_t prod[256];
  int32_t ct1[256];

  for (uint8_t row = 0; row < 6; ++row) {
    clear_bytes(w_prime, sizeof(w_prime));

    // A[row] * z_hat
    for (uint8_t col = 0; col < 5; ++col) {
      expand_a_sponge(rho, col, row, a_entry);
      basemul(prod, a_entry, z_hat + col * 256);
      DR11_DISABLE_UNROLL
      for (uint32_t c = 0; c < 256; ++c) w_prime[c] += prod[c];
    }

    // c_hat * t1_hat[row]
    basemul(ct1, c_hat, t1_hat + row * 256);
    DR11_DISABLE_UNROLL
    for (uint32_t c = 0; c < 256; ++c) {
      w_prime[c] = canonicalize(w_prime[c] - ct1[c]);
    }

    invntt_kernel(w_prime);

    // UseHint65
    int32_t w1_poly[256];
    const uint8_t *h_row = h_plain + row * 256;
    DR11_DISABLE_UNROLL
    for (uint32_t c = 0; c < 256; ++c) {
      w1_poly[c] = use_hint65(h_row[c], w_prime[c]);
    }

    encode_w1_poly65(w1_poly, w1_prime_bytes + row * 128);
  }

  // Squeeze c_tilde_prime = SHAKE256(mu || w1_prime_bytes, 48)
  uint8_t mu_w1[832];
  DR11_DISABLE_UNROLL
  for (uint32_t c = 0; c < 64; ++c) mu_w1[c] = mu[c];
  DR11_DISABLE_UNROLL
  for (uint32_t c = 0; c < 768; ++c) mu_w1[64 + c] = w1_prime_bytes[c];

  uint8_t c_tilde_prime[48];
  keccak_sponge(136, mu_w1, 832, 0x1F, c_tilde_prime, 48);

  // Compare c_tilde == c_tilde_prime
  uint8_t valid = 1;
  for (uint32_t i = 0; i < 48; ++i) {
    if (c_tilde[i] != c_tilde_prime[i]) valid = 0;
  }

  out_token[4] = valid;
  DR11_DISABLE_UNROLL
  for (uint32_t i = 0; i < 48; ++i) out_token[8 + i] = c_tilde[i];
  DR11_DISABLE_UNROLL
  for (uint32_t i = 0; i < 48; ++i) out_token[56 + i] = c_tilde_prime[i];

  clear_bytes(w_prime, sizeof(w_prime));
  clear_bytes(a_entry, sizeof(a_entry));
  clear_bytes(prod, sizeof(prod));
  clear_bytes(ct1, sizeof(ct1));
}
