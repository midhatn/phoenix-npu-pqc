// SPDX-License-Identifier: Apache-2.0
#include "dr8_mlkem768_internal.hpp"

using namespace phoenix_sdr_dsp::pqc::dr8_768;

// Token from W2 to W3:
// [0..15]: Header
// [16..47]: K_bar_prime (32)
// [48..79]: K_bar (32) [Computed here via SHAKE256(z || c)]
// [80..111]: rho (32)
// [112..1199]: c (1088 B)
// [1200..1519]: u0 (320 B compressed)
// [1520..2031]: y0 (512)
// [2032..2543]: y1 (512)
// [2544..3055]: y2 (512)
// [3056..3567]: e1_1 (512)
// [3568..4079]: e1_2 (512)
// [4080..4591]: e2_mu (512)
// [4592..5103]: t0 (512)
// [5104..5615]: t1 (512)
// [5616..6127]: t2 (512)
// Total = 6128 B

extern "C" void dr8_mlkem768_decaps_row0(
    const uint8_t in_token[6320],
    uint8_t out_token[6128]) {

  if (!word_aligned(in_token) || !word_aligned(out_token)) {
    clear_bytes(out_token, 6128);
    store_le32(out_token, 0);
    store_le32(out_token + 4, kBadToken);
    return;
  }

  const uint32_t request_id = load_le32(in_token);
  const uint32_t status = load_le32(in_token + 4);
  if (status != kOk) {
    clear_bytes(out_token, 6128);
    store_le32(out_token, request_id);
    store_le32(out_token + 4, status);
    return;
  }

  clear_bytes(out_token, 6128);
  store_le32(out_token, request_id);
  store_le32(out_token + 4, kOk);

  // Copy K_bar_prime, rho
  for (uint32_t i = 0; i < 32; ++i) {
    out_token[16 + i] = in_token[16 + i];
    out_token[80 + i] = in_token[80 + i];
  }

  // Copy c (1088 B)
  for (uint32_t i = 0; i < 1088; ++i) {
    out_token[112 + i] = in_token[112 + i];
  }

  // Compute K_bar = SHAKE256(z || c, 32)
  const uint8_t *z = in_token + 48;
  const uint8_t *c = in_token + 112;
  uint8_t k_bar[32];
  shake256_1120(z, c, k_bar);
  for (uint32_t i = 0; i < 32; ++i) {
    out_token[48 + i] = k_bar[i];
  }
  clear_bytes(k_bar, sizeof(k_bar));

  // Copy y0, y1, y2
  copy_words(out_token + 1520, in_token + 1200, 512 * 3);

  // Copy e1_1, e1_2, e2_mu, t0, t1, t2
  copy_words(out_token + 3056, in_token + 3248, 512 * 6);

  const uint8_t *rho = in_token + 80;
  const uint8_t *y0 = in_token + 1200;
  const uint8_t *y1 = in_token + 1712;
  const uint8_t *y2 = in_token + 2224;
  const uint8_t *e1_0 = in_token + 2736;

  // A^T[0, 0..2] = A[0..2, 0]
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

  compress10_encode(u0, out_token + 1200);

  clear_bytes(a00, sizeof(a00));
  clear_bytes(a10, sizeof(a10));
  clear_bytes(a20, sizeof(a20));
  clear_bytes(reinterpret_cast<uint8_t *>(u0), sizeof(u0));
}
