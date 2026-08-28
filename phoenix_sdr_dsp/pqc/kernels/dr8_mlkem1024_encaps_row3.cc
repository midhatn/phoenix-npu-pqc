// SPDX-License-Identifier: Apache-2.0
#include "dr8_mlkem1024_internal.hpp"

using namespace phoenix_sdr_dsp::pqc::dr8_1024;

// Token from W4 to W5:
// [0..15]: Header
// [16..47]: K_bar (32)
// [48..2095]: y0..y3 (2048)
// [2096..2447]: u0 (352)
// [2448..2799]: u1 (352)
// [2800..3151]: u2 (352)
// [3152..3503]: u3 (352)
// [3504..6063]: e2_mu, t0..t3 (512 * 5 = 2560)
// Total = 6064 B

extern "C" void dr8_mlkem1024_encaps_row3(
    const uint8_t in_token[6256],
    uint8_t out_token[6064]) {

  if (!word_aligned(in_token) || !word_aligned(out_token)) {
    clear_bytes(out_token, 6064);
    store_le32(out_token, 0);
    store_le32(out_token + 4, kBadToken);
    return;
  }

  const uint32_t request_id = load_le32(in_token);
  const uint32_t status = load_le32(in_token + 4);
  if (status != kOk) {
    clear_bytes(out_token, 6064);
    store_le32(out_token, request_id);
    store_le32(out_token + 4, status);
    return;
  }

  clear_bytes(out_token, 6064);
  store_le32(out_token, request_id);
  store_le32(out_token + 4, kOk);

  // Copy K_bar
  for (uint32_t i = 0; i < 32; ++i) out_token[16 + i] = in_token[16 + i];

  // Copy y0..y3 (2048 B)
  copy_words(out_token + 48, in_token + 80, 2048);

  // Copy u0, u1, u2 (1056 B)
  copy_words(out_token + 2096, in_token + 2128, 352 * 3);

  // Copy e2_mu, t0..t3 (2560 B) from in_token + 3696 to out_token + 3504
  copy_words(out_token + 3504, in_token + 3696, 512 * 5);

  const uint8_t *rho = in_token + 48;
  const uint8_t *y0 = in_token + 80;
  const uint8_t *y1 = in_token + 592;
  const uint8_t *y2 = in_token + 1104;
  const uint8_t *y3 = in_token + 1616;
  const uint8_t *e1_3 = in_token + 3184;

  // A^T[3, 0..3] = A[0..3, 3]
  alignas(4) uint8_t a03[512], a13[512], a23[512], a33[512];
  const bool ok0 = sample_matrix_store(rho, 3, 0, a03);
  const bool ok1 = sample_matrix_store(rho, 3, 1, a13);
  const bool ok2 = sample_matrix_store(rho, 3, 2, a23);
  const bool ok3 = sample_matrix_store(rho, 3, 3, a33);

  if (!ok0 || !ok1 || !ok2 || !ok3) {
    store_le32(out_token + 4, kLimitExceeded);
  }

  uint32_t u3[kN];
  ntt_multiply_accumulate_4(a03, y0, a13, y1, a23, y2, a33, y3, u3);
  intt(u3);

  for (uint32_t i = 0; i < kN; ++i) {
    const uint32_t e_val = load_le16(e1_3 + 2 * i);
    const uint32_t sum = u3[i] + e_val;
    u3[i] = sum >= kQ ? sum - kQ : sum;
  }

  compress11_encode(u3, out_token + 3152);

  clear_bytes(a03, sizeof(a03));
  clear_bytes(a13, sizeof(a13));
  clear_bytes(a23, sizeof(a23));
  clear_bytes(a33, sizeof(a33));
  clear_bytes(reinterpret_cast<uint8_t *>(u3), sizeof(u3));
}
