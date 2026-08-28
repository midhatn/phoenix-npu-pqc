// SPDX-License-Identifier: Apache-2.0
#include "dr8_mlkem768_internal.hpp"

using namespace phoenix_sdr_dsp::pqc::dr8_768;

// Token from W3 to W4:
// [0..15]: Header
// [16..47]: K_bar (32)
// [48..559]: y0 (512)
// [560..1071]: y1 (512)
// [1072..1583]: y2 (512)
// [1584..1903]: u0 (320)
// [1904..2223]: u1 (320)
// [2224..2543]: u2 (320)
// [2544..3055]: e2_mu (512)
// [3056..3567]: t0 (512)
// [3568..4079]: t1 (512)
// [4080..4591]: t2 (512)
// Total = 4592 B

extern "C" void dr8_mlkem768_encaps_row2(
    const uint8_t in_token[4816],
    uint8_t out_token[4592]) {

  if (!word_aligned(in_token) || !word_aligned(out_token)) {
    clear_bytes(out_token, 4592);
    store_le32(out_token, 0);
    store_le32(out_token + 4, kBadToken);
    return;
  }

  const uint32_t request_id = load_le32(in_token);
  const uint32_t status = load_le32(in_token + 4);
  if (status != kOk) {
    clear_bytes(out_token, 4592);
    store_le32(out_token, request_id);
    store_le32(out_token + 4, status);
    return;
  }

  clear_bytes(out_token, 4592);
  store_le32(out_token, request_id);
  store_le32(out_token + 4, kOk);

  // Copy K_bar
  for (uint32_t i = 0; i < 32; ++i) out_token[16 + i] = in_token[16 + i];

  // Copy y0, y1, y2
  copy_words(out_token + 48, in_token + 80, 512 * 3);

  // Copy u0, u1
  copy_words(out_token + 1584, in_token + 1616, 640);

  // Copy e2_mu, t0, t1, t2
  copy_words(out_token + 2544, in_token + 2768, 512 * 4);

  const uint8_t *rho = in_token + 48;
  const uint8_t *y0 = in_token + 80;
  const uint8_t *y1 = in_token + 592;
  const uint8_t *y2 = in_token + 1104;
  const uint8_t *e1_2 = in_token + 2256;

  // A^T[2, 0..2] = A[0..2, 2] = SampleNTT(rho || row || col)
  alignas(4) uint8_t a02[512], a12[512], a22[512];
  const bool ok0 = sample_matrix_store(rho, 2, 0, a02);
  const bool ok1 = sample_matrix_store(rho, 2, 1, a12);
  const bool ok2 = sample_matrix_store(rho, 2, 2, a22);

  if (!ok0 || !ok1 || !ok2) {
    store_le32(out_token + 4, kLimitExceeded);
  }

  uint32_t u2[kN];
  ntt_multiply_accumulate_3(a02, y0, a12, y1, a22, y2, u2);
  intt(u2);

  for (uint32_t i = 0; i < kN; ++i) {
    const uint32_t e_val = load_le16(e1_2 + 2 * i);
    const uint32_t sum = u2[i] + e_val;
    u2[i] = sum >= kQ ? sum - kQ : sum;
  }

  compress10_encode(u2, out_token + 2224);

  clear_bytes(a02, sizeof(a02));
  clear_bytes(a12, sizeof(a12));
  clear_bytes(a22, sizeof(a22));
  clear_bytes(reinterpret_cast<uint8_t *>(u2), sizeof(u2));
}
