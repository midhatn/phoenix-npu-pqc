// SPDX-License-Identifier: Apache-2.0
#include "dr8_mlkem1024_internal.hpp"

using namespace phoenix_sdr_dsp::pqc::dr8_1024;

// Token from W4 to W5 (7760 B):
// [0..15]: Header
// [16..47]: K_bar_prime (32)
// [48..79]: K_bar (32)
// [80..111]: rho (32)
// [112..1679]: c (1568 B)
// [1680..2031]: u0 (352)
// [2032..2383]: u1 (352)
// [2384..2735]: u2 (352)
// [2736..4783]: y0..y3 (2048)
// [4784..7759]: e1_3, e2_mu, t0..t3 (512 * 6 = 3072)
// Total = 7760 B

extern "C" void dr8_mlkem1024_decaps_row2(
    const uint8_t in_token[8016],
    uint8_t out_token[7856]) {

  if (!word_aligned(in_token) || !word_aligned(out_token)) {
    clear_bytes(out_token, 7856);
    store_le32(out_token, 0);
    store_le32(out_token + 4, kBadToken);
    return;
  }

  const uint32_t request_id = load_le32(in_token);
  const uint32_t status = load_le32(in_token + 4);
  if (status != kOk) {
    clear_bytes(out_token, 7856);
    store_le32(out_token, request_id);
    store_le32(out_token + 4, status);
    return;
  }

  clear_bytes(out_token, 7856);
  store_le32(out_token, request_id);
  store_le32(out_token + 4, kOk);

  // Copy K_bar_prime, K_bar, rho, c, u0, u1 (2368 B)
  copy_words(out_token + 16, in_token + 16, 32 + 32 + 32 + 1568 + 352*2);

  // Copy y0..y3 (2048 B)
  copy_words(out_token + 2736, in_token + 2384, 2048);

  // Copy e1_3, e2_mu, t0..t3 (3072 B) from in_token + 4944 to out_token + 4784
  copy_words(out_token + 4784, in_token + 4944, 512 * 6);

  const uint8_t *rho = in_token + 80;
  const uint8_t *y0 = in_token + 2384;
  const uint8_t *y1 = in_token + 2896;
  const uint8_t *y2 = in_token + 3408;
  const uint8_t *y3 = in_token + 3920;
  const uint8_t *e1_2 = in_token + 4432;

  // A^T[2, 0..3] = A[0..3, 2]
  alignas(4) uint8_t a02[512], a12[512], a22[512], a32[512];
  const bool ok0 = sample_matrix_store(rho, 2, 0, a02);
  const bool ok1 = sample_matrix_store(rho, 2, 1, a12);
  const bool ok2 = sample_matrix_store(rho, 2, 2, a22);
  const bool ok3 = sample_matrix_store(rho, 2, 3, a32);

  if (!ok0 || !ok1 || !ok2 || !ok3) {
    store_le32(out_token + 4, kLimitExceeded);
  }

  uint32_t u2[kN];
  ntt_multiply_accumulate_4(a02, y0, a12, y1, a22, y2, a32, y3, u2);
  intt(u2);

  for (uint32_t i = 0; i < kN; ++i) {
    const uint32_t e_val = load_le16(e1_2 + 2 * i);
    const uint32_t sum = u2[i] + e_val;
    u2[i] = sum >= kQ ? sum - kQ : sum;
  }

  compress11_encode(u2, out_token + 2384);

  clear_bytes(a02, sizeof(a02));
  clear_bytes(a12, sizeof(a12));
  clear_bytes(a22, sizeof(a22));
  clear_bytes(a32, sizeof(a32));
  clear_bytes(reinterpret_cast<uint8_t *>(u2), sizeof(u2));
}
