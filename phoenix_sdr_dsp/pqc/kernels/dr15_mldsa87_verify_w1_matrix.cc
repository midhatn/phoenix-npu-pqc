// SPDX-License-Identifier: Apache-2.0
// DR15 ML-DSA-87 Verify Worker 1: Matrix Streaming, UseHint, Challenge Squeeze & Compare
#include "dr15_mldsa87_internal.hpp"

using namespace phoenix_sdr_dsp::pqc::dr11;
using namespace phoenix_sdr_dsp::pqc::dr12;
using namespace phoenix_sdr_dsp::pqc::dr13;
using namespace phoenix_sdr_dsp::pqc::dr14;
using namespace phoenix_sdr_dsp::pqc::dr15;

extern "C" void dr15_mldsa87_verify_w1_matrix(
    const uint8_t in_token[19000],
    uint8_t out_token[72]) {

  clear_bytes(out_token, 72);

  const uint32_t request_id = load_le32(in_token + 0);
  store_le32(out_token + 0, request_id);

  const uint8_t *rho = in_token + 4;
  const uint8_t *mu = in_token + 36;
  const uint8_t *c_tilde = in_token + 100;
  const int32_t *z_hat = reinterpret_cast<const int32_t *>(in_token + 132);
  const uint8_t *h_unpacked = in_token + 7300;
  const int32_t *t1_hat = reinterpret_cast<const int32_t *>(in_token + 9348);
  const int32_t *c_hat = reinterpret_cast<const int32_t *>(in_token + 17540);
  const bool prev_valid = (in_token[18564] != 0);

  int32_t acc[256];
  int32_t a_entry[256];
  int32_t prod[256];
  int32_t ct1[256];
  int32_t w1_row[256];
  uint8_t w1_bytes[1024];

  // 1. Matrix multiply A * z_hat - c_hat * t1_hat -> INTT -> UseHint -> w1
  for (uint8_t row = 0; row < 8; ++row) {
    clear_bytes(acc, sizeof(acc));

    for (uint8_t col = 0; col < 7; ++col) {
      expand_a_sponge(rho, col, row, a_entry);
      basemul(prod, a_entry, z_hat + col * 256);
      DR11_DISABLE_UNROLL
      for (uint32_t c = 0; c < 256; ++c) acc[c] += prod[c];
    }

    basemul(ct1, c_hat, t1_hat + row * 256);
    DR11_DISABLE_UNROLL
    for (uint32_t c = 0; c < 256; ++c) {
      acc[c] = canonicalize(acc[c] - ct1[c]);
    }

    invntt_kernel(acc);

    const uint8_t *h_row = h_unpacked + row * 256;
    DR11_DISABLE_UNROLL
    for (uint32_t c = 0; c < 256; ++c) {
      w1_row[c] = use_hint65(h_row[c], acc[c]);
    }

    encode_w1_poly65(w1_row, w1_bytes + row * 128);
  }

  // 2. Challenge hash c_tilde_prime = H(mu || w1, 32)
  uint8_t mu_w1[1088];
  for (uint32_t i = 0; i < 64; ++i) mu_w1[i] = mu[i];
  for (uint32_t i = 0; i < 1024; ++i) mu_w1[64 + i] = w1_bytes[i];

  uint8_t c_tilde_prime[32];
  keccak_sponge(136, mu_w1, 1088, 0x1F, c_tilde_prime, 32);

  // 3. Constant-time compare c_tilde_prime == c_tilde
  uint32_t diff = 0;
  DR11_DISABLE_UNROLL
  for (uint32_t i = 0; i < 32; ++i) {
    diff |= (c_tilde_prime[i] ^ c_tilde[i]);
  }

  const bool is_valid = prev_valid && (diff == 0);
  out_token[4] = is_valid ? 1 : 0;

  clear_bytes(acc, sizeof(acc));
  clear_bytes(a_entry, sizeof(a_entry));
  clear_bytes(prod, sizeof(prod));
  clear_bytes(ct1, sizeof(ct1));
  clear_bytes(w1_row, sizeof(w1_row));
  clear_bytes(w1_bytes, sizeof(w1_bytes));
  clear_bytes(c_tilde_prime, sizeof(c_tilde_prime));
}
