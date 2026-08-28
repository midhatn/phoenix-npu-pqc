// SPDX-License-Identifier: Apache-2.0
#include "dr8_mlkem768_internal.hpp"

using namespace phoenix_sdr_dsp::pqc::dr8_768;

// Output Result:
// [0..3]: Magic 0x4838524D (b"MR8H")
// [4..7]: request_id
// [8..11]: status
// [12..15]: c_bytes (1088)
// [16..19]: k_bytes (32)
// [20..23]: crc_c
// [24..27]: crc_k
// [28..31]: reserved
// [32..1119]: c (1088 B = 320*3 + 128)
// [1120..1151]: K (32 B)
// Total Result Bytes = 1152 B

extern "C" void dr8_mlkem768_encaps_finalize(
    const uint8_t in_token[4592],
    uint8_t result[1152]) {

  if (!word_aligned(in_token) || !word_aligned(result)) {
    clear_bytes(result, 1152);
    store_le32(result, 0);
    store_le32(result + 4, kBadToken);
    return;
  }

  const uint32_t request_id = load_le32(in_token);
  const uint32_t status = load_le32(in_token + 4);

  if (status != kOk) {
    clear_bytes(result, 1152);
    store_le32(result + 0, 0x4838524Du);
    store_le32(result + 4, request_id);
    store_le32(result + 8, status);
    return;
  }

  const uint8_t *k_bar = in_token + 16;
  const uint8_t *y0 = in_token + 48;
  const uint8_t *y1 = in_token + 560;
  const uint8_t *y2 = in_token + 1072;
  const uint8_t *u0 = in_token + 1584;
  const uint8_t *u1 = in_token + 1904;
  const uint8_t *u2 = in_token + 2224;
  const uint8_t *e2_mu = in_token + 2544;
  const uint8_t *t0 = in_token + 3056;
  const uint8_t *t1 = in_token + 3568;
  const uint8_t *t2 = in_token + 4080;

  uint8_t *c = result + 32;
  uint8_t *k_out = result + 1120;

  // Copy u0, u1, u2 into c (960 B)
  copy_words(c + 0, u0, 320);
  copy_words(c + 320, u1, 320);
  copy_words(c + 640, u2, 320);

  // Compute v = INTT(t0*y0 + t1*y1 + t2*y2) + e2_mu
  uint32_t v[kN];
  ntt_multiply_accumulate_3(t0, y0, t1, y1, t2, y2, v);
  intt(v);

  for (uint32_t i = 0; i < kN; ++i) {
    const uint32_t e_val = load_le16(e2_mu + 2 * i);
    const uint32_t sum = v[i] + e_val;
    v[i] = sum >= kQ ? sum - kQ : sum;
  }

  // Compress_4(v) into c + 960 (128 B)
  compress4_encode(v, c + 960);

  // Copy K_bar to K
  for (uint32_t i = 0; i < 32; ++i) {
    k_out[i] = k_bar[i];
  }

  // Pack header
  store_le32(result + 0, 0x4838524Du);
  store_le32(result + 4, request_id);
  store_le32(result + 8, kOk);
  store_le32(result + 12, 1088);
  store_le32(result + 16, 32);

  const uint32_t crc_c = compute_crc32(c, 1088);
  const uint32_t crc_k = compute_crc32(k_out, 32);
  store_le32(result + 20, crc_c);
  store_le32(result + 24, crc_k);
  store_le32(result + 28, 0);

  clear_bytes(reinterpret_cast<uint8_t *>(v), sizeof(v));
}
