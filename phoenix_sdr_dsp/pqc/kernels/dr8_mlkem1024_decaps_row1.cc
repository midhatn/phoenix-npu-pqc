// SPDX-License-Identifier: Apache-2.0
#include "dr8_mlkem1024_internal.hpp"

using namespace phoenix_sdr_dsp::pqc::dr8_1024;

// Token from W3 to W4 (7952 B):
// [0..15]: Header
// [16..47]: K_bar_prime (32)
// [48..79]: K_bar (32)
// [80..111]: rho (32)
// [112..1679]: c (1568 B)
// [1680..2031]: u0 (352)
// [2032..2383]: u1 (352)
// [2384..4431]: y0..y3 (2048)
// [4432..7951]: e1_2..e1_3, e2_mu, t0..t3 (512 * 7 = 3584)
// Total = 7952 B

extern "C" void dr8_mlkem1024_decaps_row1(
    const uint8_t in_token[8176],
    uint8_t out_token[8016]) {

  if (!word_aligned(in_token) || !word_aligned(out_token)) {
    clear_bytes(out_token, 8016);
    store_le32(out_token, 0);
    store_le32(out_token + 4, kBadToken);
    return;
  }

  const uint32_t request_id = load_le32(in_token);
  const uint32_t status = load_le32(in_token + 4);
  if (status != kOk) {
    clear_bytes(out_token, 8016);
    store_le32(out_token, request_id);
    store_le32(out_token + 4, status);
    return;
  }

  clear_bytes(out_token, 8016);
  store_le32(out_token, request_id);
  store_le32(out_token + 4, kOk);

  // Copy K_bar_prime, K_bar, rho, c, u0 (2016 B)
  copy_words(out_token + 16, in_token + 16, 32 + 32 + 32 + 1568 + 352);

  // Copy y0..y3 (2048 B)
  copy_words(out_token + 2384, in_token + 2032, 2048);

  // Copy e1_2..e1_3, e2_mu, t0..t3 (3584 B) from in_token + 4592 to out_token + 4432
  copy_words(out_token + 4432, in_token + 4592, 512 * 7);

  const uint8_t *rho = in_token + 80;
  const uint8_t *y0 = in_token + 2032;
  const uint8_t *y1 = in_token + 2544;
  const uint8_t *y2 = in_token + 3056;
  const uint8_t *y3 = in_token + 3568;
  const uint8_t *e1_1 = in_token + 4080;

  // A^T[1, 0..3] = A[0..3, 1]
  alignas(4) uint8_t a01[512], a11[512], a21[512], a31[512];
  const bool ok0 = sample_matrix_store(rho, 1, 0, a01);
  const bool ok1 = sample_matrix_store(rho, 1, 1, a11);
  const bool ok2 = sample_matrix_store(rho, 1, 2, a21);
  const bool ok3 = sample_matrix_store(rho, 1, 3, a31);

  if (!ok0 || !ok1 || !ok2 || !ok3) {
    store_le32(out_token + 4, kLimitExceeded);
  }

  uint32_t u1[kN];
  ntt_multiply_accumulate_4(a01, y0, a11, y1, a21, y2, a31, y3, u1);
  intt(u1);

  for (uint32_t i = 0; i < kN; ++i) {
    const uint32_t e_val = load_le16(e1_1 + 2 * i);
    const uint32_t sum = u1[i] + e_val;
    u1[i] = sum >= kQ ? sum - kQ : sum;
  }

  compress11_encode(u1, out_token + 2032);

  clear_bytes(a01, sizeof(a01));
  clear_bytes(a11, sizeof(a11));
  clear_bytes(a21, sizeof(a21));
  clear_bytes(a31, sizeof(a31));
  clear_bytes(reinterpret_cast<uint8_t *>(u1), sizeof(u1));
}
