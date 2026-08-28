// SPDX-License-Identifier: Apache-2.0
#include "dr8_mlkem768_internal.hpp"

using namespace phoenix_sdr_dsp::pqc::dr8_768;

// Token from W4 to W5:
// [0..15]: Header
// [16..47]: K_bar_prime (32)
// [48..79]: K_bar (32)
// [80..1167]: c (1088 B)
// [1168..1487]: u0 (320)
// [1488..1807]: u1 (320)
// [1808..2127]: u2 (320)
// [2128..2639]: y0 (512)
// [2640..3151]: y1 (512)
// [3152..3663]: y2 (512)
// [3664..4175]: e2_mu (512)
// [4176..4687]: t0 (512)
// [4688..5199]: t1 (512)
// [5200..5711]: t2 (512)
// Total = 5712 B

extern "C" void dr8_mlkem768_decaps_row2(
    const uint8_t in_token[5936],
    uint8_t out_token[5712]) {

  if (!word_aligned(in_token) || !word_aligned(out_token)) {
    clear_bytes(out_token, 5712);
    store_le32(out_token, 0);
    store_le32(out_token + 4, kBadToken);
    return;
  }

  const uint32_t request_id = load_le32(in_token);
  const uint32_t status = load_le32(in_token + 4);
  if (status != kOk) {
    clear_bytes(out_token, 5712);
    store_le32(out_token, request_id);
    store_le32(out_token + 4, status);
    return;
  }

  clear_bytes(out_token, 5712);
  store_le32(out_token, request_id);
  store_le32(out_token + 4, kOk);

  // Copy K_bar_prime, K_bar, c, u0, u1
  copy_words(out_token + 16, in_token + 16, 32 + 32);
  copy_words(out_token + 80, in_token + 112, 1088 + 320 + 320);

  // Copy y0, y1, y2
  copy_words(out_token + 2128, in_token + 1840, 512 * 3);

  // Copy e2_mu, t0, t1, t2
  copy_words(out_token + 3664, in_token + 3888, 512 * 4);

  const uint8_t *rho = in_token + 80;
  const uint8_t *y0 = in_token + 1840;
  const uint8_t *y1 = in_token + 2352;
  const uint8_t *y2 = in_token + 2864;
  const uint8_t *e1_2 = in_token + 3376;

  // A^T[2, 0..2] = A[0..2, 2]
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

  compress10_encode(u2, out_token + 1808);

  clear_bytes(a02, sizeof(a02));
  clear_bytes(a12, sizeof(a12));
  clear_bytes(a22, sizeof(a22));
  clear_bytes(reinterpret_cast<uint8_t *>(u2), sizeof(u2));
}
