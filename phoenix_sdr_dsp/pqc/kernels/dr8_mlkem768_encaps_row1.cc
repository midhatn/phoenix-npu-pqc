// SPDX-License-Identifier: Apache-2.0
#include "dr8_mlkem768_internal.hpp"

using namespace phoenix_sdr_dsp::pqc::dr8_768;

// Token from W2 to W3:
// [0..15]: Header
// [16..47]: K_bar (32)
// [48..79]: rho (32)
// [80..591]: y0 (512)
// [592..1103]: y1 (512)
// [1104..1615]: y2 (512)
// [1616..1935]: u0 (320)
// [1936..2255]: u1 (320)
// [2256..2767]: e1_2 (512)
// [2768..3279]: e2_mu (512)
// [3280..3791]: t0 (512)
// [3792..4303]: t1 (512)
// [4304..4815]: t2 (512)
// Total = 4816 B

extern "C" void dr8_mlkem768_encaps_row1(
    const uint8_t in_token[5008],
    uint8_t out_token[4816]) {

  if (!word_aligned(in_token) || !word_aligned(out_token)) {
    clear_bytes(out_token, 4816);
    store_le32(out_token, 0);
    store_le32(out_token + 4, kBadToken);
    return;
  }

  const uint32_t request_id = load_le32(in_token);
  const uint32_t status = load_le32(in_token + 4);
  if (status != kOk) {
    clear_bytes(out_token, 4816);
    store_le32(out_token, request_id);
    store_le32(out_token + 4, status);
    return;
  }

  clear_bytes(out_token, 4816);
  store_le32(out_token, request_id);
  store_le32(out_token + 4, kOk);

  // Copy K_bar, rho, y0, y1, y2, u0
  copy_words(out_token + 16, in_token + 16, 32 + 32 + 512*3 + 320);

  // Copy e1_2, e2_mu, t0, t1, t2
  copy_words(out_token + 2256, in_token + 2448, 512 * 5);

  const uint8_t *rho = in_token + 48;
  const uint8_t *y0 = in_token + 80;
  const uint8_t *y1 = in_token + 592;
  const uint8_t *y2 = in_token + 1104;
  const uint8_t *e1_1 = in_token + 1936;

  // A^T[1, 0..2] = A[0..2, 1] = SampleNTT(rho || row || col)
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

  compress10_encode(u1, out_token + 1936);

  clear_bytes(a01, sizeof(a01));
  clear_bytes(a11, sizeof(a11));
  clear_bytes(a21, sizeof(a21));
  clear_bytes(reinterpret_cast<uint8_t *>(u1), sizeof(u1));
}
