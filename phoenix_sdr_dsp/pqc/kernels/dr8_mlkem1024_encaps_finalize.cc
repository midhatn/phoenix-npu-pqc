// SPDX-License-Identifier: Apache-2.0
#include "dr8_mlkem1024_internal.hpp"

using namespace phoenix_sdr_dsp::pqc::dr8_1024;

// Output Result (1632 B):
// [0..3]: Magic 0x4838524D (b"MR8H")
// [4..7]: request_id
// [8..11]: status
// [12..15]: c_bytes (1568)
// [16..19]: k_bytes (32)
// [20..23]: crc_c
// [24..27]: crc_k
// [28..31]: reserved
// [32..1599]: c (1568 B = 352*4 + 160)
// [1600..1631]: K (32 B)
// Total Result Bytes = 1632 B

extern "C" void dr8_mlkem1024_encaps_finalize(
    const uint8_t in_token[6064],
    uint8_t result[1632]) {

  if (!word_aligned(in_token) || !word_aligned(result)) {
    clear_bytes(result, 1632);
    store_le32(result, 0);
    store_le32(result + 4, kBadToken);
    return;
  }

  const uint32_t request_id = load_le32(in_token);
  const uint32_t status = load_le32(in_token + 4);

  if (status != kOk) {
    clear_bytes(result, 1632);
    store_le32(result + 0, 0x4838524Du);
    store_le32(result + 4, request_id);
    store_le32(result + 8, status);
    return;
  }

  const uint8_t *k_bar = in_token + 16;
  const uint8_t *y0 = in_token + 48;
  const uint8_t *y1 = in_token + 560;
  const uint8_t *y2 = in_token + 1072;
  const uint8_t *y3 = in_token + 1584;
  const uint8_t *u0 = in_token + 2096;
  const uint8_t *u1 = in_token + 2448;
  const uint8_t *u2 = in_token + 2800;
  const uint8_t *u3 = in_token + 3152;
  const uint8_t *e2_mu = in_token + 3504;
  const uint8_t *t0 = in_token + 4016;
  const uint8_t *t1 = in_token + 4528;
  const uint8_t *t2 = in_token + 5040;
  const uint8_t *t3 = in_token + 5552;

  uint8_t *c = result + 32;
  uint8_t *k_out = result + 1600;

  // Copy u0..u3 into c (1408 B)
  copy_words(c + 0, u0, 352);
  copy_words(c + 352, u1, 352);
  copy_words(c + 704, u2, 352);
  copy_words(c + 1056, u3, 352);

  // Compute v = INTT(t0*y0 + t1*y1 + t2*y2 + t3*y3) + e2_mu
  uint32_t v[kN];
  ntt_multiply_accumulate_4(t0, y0, t1, y1, t2, y2, t3, y3, v);
  intt(v);

  for (uint32_t i = 0; i < kN; ++i) {
    const uint32_t e_val = load_le16(e2_mu + 2 * i);
    const uint32_t sum = v[i] + e_val;
    v[i] = sum >= kQ ? sum - kQ : sum;
  }

  // Compress_5(v) into c + 1408 (160 B)
  compress5_encode(v, c + 1408);

  // Copy K_bar to K
  for (uint32_t i = 0; i < 32; ++i) {
    k_out[i] = k_bar[i];
  }

  // Pack header
  store_le32(result + 0, 0x4838524Du);
  store_le32(result + 4, request_id);
  store_le32(result + 8, kOk);
  store_le32(result + 12, 1568);
  store_le32(result + 16, 32);

  const uint32_t crc_c = compute_crc32(c, 1568);
  const uint32_t crc_k = compute_crc32(k_out, 32);
  store_le32(result + 20, crc_c);
  store_le32(result + 24, crc_k);
  store_le32(result + 28, 0);

  clear_bytes(reinterpret_cast<uint8_t *>(v), sizeof(v));
}
