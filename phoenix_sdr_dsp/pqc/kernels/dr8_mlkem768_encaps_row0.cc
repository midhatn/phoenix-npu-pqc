// SPDX-License-Identifier: Apache-2.0
#include "dr8_mlkem768_internal.hpp"

using namespace phoenix_sdr_dsp::pqc::dr8_768;

// Token from W1 to W2:
// [0..15]: Header
// [16..47]: K_bar (32)
// [48..79]: rho (32)
// [80..591]: y0 (512)
// [592..1103]: y1 (512)
// [1104..1615]: y2 (512)
// [1616..1935]: u0 (320 B compressed)
// [1936..2447]: e1_1 (512)
// [2448..2959]: e1_2 (512)
// [2960..3471]: e2_mu (512)
// [3472..3983]: t0 (512)
// [3984..4495]: t1 (512)
// [4496..5007]: t2 (512)
// Total = 5008 B

extern "C" void dr8_mlkem768_encaps_row0(
    const uint8_t in_token[5200],
    uint8_t out_token[5008]) {

  if (!word_aligned(in_token) || !word_aligned(out_token)) {
    clear_bytes(out_token, 5008);
    store_le32(out_token, 0);
    store_le32(out_token + 4, kBadToken);
    return;
  }

  const uint32_t request_id = load_le32(in_token);
  const uint32_t status = load_le32(in_token + 4);
  if (status != kOk) {
    clear_bytes(out_token, 5008);
    store_le32(out_token, request_id);
    store_le32(out_token + 4, status);
    return;
  }

  clear_bytes(out_token, 5008);
  store_le32(out_token, request_id);
  store_le32(out_token + 4, kOk);

  // Copy K_bar, rho, y0, y1, y2
  copy_words(out_token + 16, in_token + 16, 32 + 32 + 512 + 512 + 512);

  // Copy e1_1, e1_2, e2_mu, t0, t1, t2
  copy_words(out_token + 1936, in_token + 2128, 512 * 6);

  const uint8_t *rho = in_token + 48;
  const uint8_t *y0 = in_token + 80;
  const uint8_t *y1 = in_token + 592;
  const uint8_t *y2 = in_token + 1104;
  const uint8_t *e1_0 = in_token + 1616;

  // A^T[0, 0..2] = A[0..2, 0] = SampleNTT(rho || row || col)
  alignas(4) uint8_t a00[512], a10[512], a20[512];
  const bool ok0 = sample_matrix_store(rho, 0, 0, a00);
  const bool ok1 = sample_matrix_store(rho, 0, 1, a10);
  const bool ok2 = sample_matrix_store(rho, 0, 2, a20);

  if (!ok0 || !ok1 || !ok2) {
    store_le32(out_token + 4, kLimitExceeded);
  }

  uint32_t u0[kN];
  ntt_multiply_accumulate_3(a00, y0, a10, y1, a20, y2, u0);
  intt(u0);

  for (uint32_t i = 0; i < kN; ++i) {
    const uint32_t e_val = load_le16(e1_0 + 2 * i);
    const uint32_t sum = u0[i] + e_val;
    u0[i] = sum >= kQ ? sum - kQ : sum;
  }

  compress10_encode(u0, out_token + 1616);

  clear_bytes(a00, sizeof(a00));
  clear_bytes(a10, sizeof(a10));
  clear_bytes(a20, sizeof(a20));
  clear_bytes(reinterpret_cast<uint8_t *>(u0), sizeof(u0));
}
