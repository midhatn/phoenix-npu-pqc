// SPDX-License-Identifier: Apache-2.0
#include "dr8_mlkem768_internal.hpp"

using namespace phoenix_sdr_dsp::pqc::dr8_768;

// Token from W3 to W4:
// [0..15]: Header
// [16..47]: K_bar_prime (32)
// [48..79]: K_bar (32)
// [80..111]: rho (32)
// [112..1199]: c (1088 B)
// [1200..1519]: u0 (320)
// [1520..1839]: u1 (320)
// [1840..2351]: y0 (512)
// [2352..2863]: y1 (512)
// [2864..3375]: y2 (512)
// [3376..3887]: e1_2 (512)
// [3888..4399]: e2_mu (512)
// [4400..4911]: t0 (512)
// [4912..5423]: t1 (512)
// [5424..5935]: t2 (512)
// Total = 5936 B

extern "C" void dr8_mlkem768_decaps_row1(
    const uint8_t in_token[6128],
    uint8_t out_token[5936]) {

  if (!word_aligned(in_token) || !word_aligned(out_token)) {
    clear_bytes(out_token, 5936);
    store_le32(out_token, 0);
    store_le32(out_token + 4, kBadToken);
    return;
  }

  const uint32_t request_id = load_le32(in_token);
  const uint32_t status = load_le32(in_token + 4);
  if (status != kOk) {
    clear_bytes(out_token, 5936);
    store_le32(out_token, request_id);
    store_le32(out_token + 4, status);
    return;
  }

  clear_bytes(out_token, 5936);
  store_le32(out_token, request_id);
  store_le32(out_token + 4, kOk);

  // Copy K_bar_prime, K_bar, rho, c, u0
  copy_words(out_token + 16, in_token + 16, 32 + 32 + 32 + 1088 + 320);

  // Copy y0, y1, y2
  copy_words(out_token + 1840, in_token + 1520, 512 * 3);

  // Copy e1_2, e2_mu, t0, t1, t2
  copy_words(out_token + 3376, in_token + 3568, 512 * 5);

  const uint8_t *rho = in_token + 80;
  const uint8_t *y0 = in_token + 1520;
  const uint8_t *y1 = in_token + 2032;
  const uint8_t *y2 = in_token + 2544;
  const uint8_t *e1_1 = in_token + 3056;

  // A^T[1, 0..2] = A[0..2, 1]
  alignas(4) uint8_t a01[512], a11[512], a21[512];
  const bool ok0 = sample_matrix_store(rho, 1, 0, a01);
  const bool ok1 = sample_matrix_store(rho, 1, 1, a11);
  const bool ok2 = sample_matrix_store(rho, 1, 2, a21);

  if (!ok0 || !ok1 || !ok2) {
    store_le32(out_token + 4, kLimitExceeded);
  }

  uint32_t u1[kN];
  ntt_multiply_accumulate_3(a01, y0, a11, y1, a21, y2, u1);
  intt(u1);

  for (uint32_t i = 0; i < kN; ++i) {
    const uint32_t e_val = load_le16(e1_1 + 2 * i);
    const uint32_t sum = u1[i] + e_val;
    u1[i] = sum >= kQ ? sum - kQ : sum;
  }

  compress10_encode(u1, out_token + 1520);

  clear_bytes(a01, sizeof(a01));
  clear_bytes(a11, sizeof(a11));
  clear_bytes(a21, sizeof(a21));
  clear_bytes(reinterpret_cast<uint8_t *>(u1), sizeof(u1));
}
