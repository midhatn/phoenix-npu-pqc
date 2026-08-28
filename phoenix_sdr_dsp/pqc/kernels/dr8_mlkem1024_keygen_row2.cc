// SPDX-License-Identifier: Apache-2.0
#include "dr8_mlkem1024_internal.hpp"

using namespace phoenix_sdr_dsp::pqc::dr8_1024;

// Token Layout (4176 B):
// [0..15]: Header
// [16..47]: rho (32)
// [48..79]: z (32)
// [80..591]: s0 (512)
// [592..1103]: s1 (512)
// [1104..1615]: s2 (512)
// [1616..2127]: s3 (512)
// [2128..2639]: t0 (512)
// [2640..3151]: t1 (512)
// [3152..3663]: t2 (512)
// [3664..4175]: e3 (512)
// Total = 4176 B

extern "C" void dr8_mlkem1024_keygen_row2(
    const uint8_t in_token[4176],
    uint8_t out_token[4176]) {

  if (!word_aligned(in_token) || !word_aligned(out_token)) {
    clear_bytes(out_token, 4176);
    store_le32(out_token, 0);
    store_le32(out_token + 4, kBadToken);
    return;
  }

  const uint32_t request_id = load_le32(in_token);
  const uint32_t status = load_le32(in_token + 4);
  if (status != kOk) {
    clear_bytes(out_token, 4176);
    store_le32(out_token, request_id);
    store_le32(out_token + 4, status);
    return;
  }

  copy_words(out_token, in_token, 4176);

  const uint8_t *rho = in_token + 16;
  const uint8_t *s0 = in_token + 80;
  const uint8_t *s1 = in_token + 592;
  const uint8_t *s2 = in_token + 1104;
  const uint8_t *s3 = in_token + 1616;
  const uint8_t *e2 = in_token + 3152;

  alignas(4) uint8_t a20[512], a21[512], a22[512], a23[512];
  const bool ok0 = sample_matrix_store(rho, 0, 2, a20);
  const bool ok1 = sample_matrix_store(rho, 1, 2, a21);
  const bool ok2 = sample_matrix_store(rho, 2, 2, a22);
  const bool ok3 = sample_matrix_store(rho, 3, 2, a23);

  if (!ok0 || !ok1 || !ok2 || !ok3) {
    store_le32(out_token + 4, kLimitExceeded);
  }

  uint32_t t2[kN];
  ntt_multiply_accumulate_4(a20, s0, a21, s1, a22, s2, a23, s3, t2);

  for (uint32_t i = 0; i < kN; ++i) {
    const uint32_t e_val = load_le16(e2 + 2 * i);
    const uint32_t sum = t2[i] + e_val;
    t2[i] = sum >= kQ ? sum - kQ : sum;
  }

  for (uint32_t pair = 0; pair < kN / 2; ++pair) {
    store_pair_word(out_token + 3152, pair, t2[2 * pair], t2[2 * pair + 1]);
  }

  clear_bytes(a20, sizeof(a20));
  clear_bytes(a21, sizeof(a21));
  clear_bytes(a22, sizeof(a22));
  clear_bytes(a23, sizeof(a23));
  clear_bytes(reinterpret_cast<uint8_t *>(t2), sizeof(t2));
}
