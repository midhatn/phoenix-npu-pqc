// SPDX-License-Identifier: Apache-2.0
#include "dr8_mlkem1024_internal.hpp"

using namespace phoenix_sdr_dsp::pqc::dr8_1024;

extern "C" void dr8_mlkem1024_decaps_row0(
    const uint8_t in_token[8336],
    uint8_t out_token[8176]) {

  if (!word_aligned(in_token) || !word_aligned(out_token)) {
    clear_bytes(out_token, 8176);
    store_le32(out_token, 0);
    store_le32(out_token + 4, kBadToken);
    return;
  }

  const uint32_t request_id = load_le32(in_token);
  const uint32_t status = load_le32(in_token + 4);
  if (status != kOk) {
    clear_bytes(out_token, 8176);
    store_le32(out_token, request_id);
    store_le32(out_token + 4, status);
    return;
  }

  clear_bytes(out_token, 8176);
  store_le32(out_token, request_id);
  store_le32(out_token + 4, kOk);

  // Copy K_bar_prime, rho
  for (uint32_t i = 0; i < 32; ++i) {
    out_token[16 + i] = in_token[16 + i];
    out_token[80 + i] = in_token[80 + i];
  }

  // Copy c (1568 B)
  for (uint32_t i = 0; i < 1568; ++i) {
    out_token[112 + i] = in_token[112 + i];
  }

  // Compute K_bar = SHAKE256(z || c, 32)
  const uint8_t *z = in_token + 48;
  const uint8_t *c = in_token + 112;
  uint8_t k_bar[32];
  shake256_1600(z, c, k_bar);
  for (uint32_t i = 0; i < 32; ++i) {
    out_token[48 + i] = k_bar[i];
  }
  clear_bytes(k_bar, sizeof(k_bar));

  // Copy y0..y3 (2048 B)
  copy_words(out_token + 2032, in_token + 1680, 2048);

  // Copy e1_1..e1_3, e2_mu, t0..t3 (4096 B) from in_token + 4240 to out_token + 4080
  copy_words(out_token + 4080, in_token + 4240, 512 * 8);

  const uint8_t *rho = in_token + 80;
  const uint8_t *y0 = in_token + 1680;
  const uint8_t *y1 = in_token + 2192;
  const uint8_t *y2 = in_token + 2704;
  const uint8_t *y3 = in_token + 3216;
  const uint8_t *e1_0 = in_token + 3728;

  // A^T[0, 0..3] = A[0..3, 0]
  alignas(4) uint8_t a[4][512];
  DR8_DISABLE_UNROLL
  for (uint32_t col = 0; col < 4; ++col) {
    const bool ok = sample_matrix_store(rho, 0, col, a[col]);
    if (!ok) store_le32(out_token + 4, kLimitExceeded);
  }

  uint32_t u0[kN];
  ntt_multiply_accumulate_4(a[0], y0, a[1], y1, a[2], y2, a[3], y3, u0);
  intt(u0);

  for (uint32_t i = 0; i < kN; ++i) {
    const uint32_t e_val = load_le16(e1_0 + 2 * i);
    const uint32_t sum = u0[i] + e_val;
    u0[i] = sum >= kQ ? sum - kQ : sum;
  }

  compress11_encode(u0, out_token + 1680);

  clear_bytes(reinterpret_cast<uint8_t *>(a), sizeof(a));
  clear_bytes(reinterpret_cast<uint8_t *>(u0), sizeof(u0));
}
