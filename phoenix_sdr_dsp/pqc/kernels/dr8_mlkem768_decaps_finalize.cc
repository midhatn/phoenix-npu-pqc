// SPDX-License-Identifier: Apache-2.0
#include "dr8_mlkem768_internal.hpp"

using namespace phoenix_sdr_dsp::pqc::dr8_768;

// Result Layout (52 B):
// [0..3]: Magic 0x4838524D (b"MR8H")
// [4..7]: request_id
// [8..11]: status
// [12..15]: key_len (32)
// [16..19]: crc32 of K
// [20..51]: K (32 B)

extern "C" void dr8_mlkem768_decaps_finalize(
    const uint8_t in_token[5712],
    uint8_t result[52]) {

  if (!word_aligned(in_token) || !word_aligned(result)) {
    clear_bytes(result, 52);
    store_le32(result, 0);
    store_le32(result + 4, kBadToken);
    return;
  }

  const uint32_t request_id = load_le32(in_token);
  const uint32_t status = load_le32(in_token + 4);

  if (status != kOk) {
    clear_bytes(result, 52);
    store_le32(result + 0, 0x4838524Du);
    store_le32(result + 4, request_id);
    store_le32(result + 8, status);
    return;
  }

  const uint8_t *k_bar_prime = in_token + 16;
  const uint8_t *k_bar = in_token + 48;
  const uint8_t *c_orig = in_token + 80;
  const uint8_t *u0_bytes = in_token + 1168;
  const uint8_t *u1_bytes = in_token + 1488;
  const uint8_t *u2_bytes = in_token + 1808;
  const uint8_t *y0 = in_token + 2128;
  const uint8_t *y1 = in_token + 2640;
  const uint8_t *y2 = in_token + 3152;
  const uint8_t *e2_mu = in_token + 3664;
  const uint8_t *t0 = in_token + 4176;
  const uint8_t *t1 = in_token + 4688;
  const uint8_t *t2 = in_token + 5200;

  // 1. Compute v'
  alignas(4) uint8_t v_bytes[128];
  {
    uint32_t v[kN];
    ntt_multiply_accumulate_3(t0, y0, t1, y1, t2, y2, v);
    intt(v);

    for (uint32_t i = 0; i < kN; ++i) {
      const uint32_t e_val = load_le16(e2_mu + 2 * i);
      const uint32_t sum = v[i] + e_val;
      v[i] = sum >= kQ ? sum - kQ : sum;
    }
    compress4_encode(v, v_bytes);
    clear_bytes(reinterpret_cast<uint8_t *>(v), sizeof(v));
  }

  // 2. Constant-time difference check between c and c'
  uint32_t diff = 0;
  for (uint32_t i = 0; i < 320; ++i) diff |= (c_orig[i] ^ u0_bytes[i]);
  for (uint32_t i = 0; i < 320; ++i) diff |= (c_orig[320 + i] ^ u1_bytes[i]);
  for (uint32_t i = 0; i < 320; ++i) diff |= (c_orig[640 + i] ^ u2_bytes[i]);
  for (uint32_t i = 0; i < 128; ++i) diff |= (c_orig[960 + i] ^ v_bytes[i]);

  // 3. Constant-time selection between K_bar_prime and K_bar
  const uint32_t diff_is_zero = (diff == 0) ? 0xFFu : 0u;

  uint8_t k_final[32];
  for (uint32_t i = 0; i < 32; ++i) {
    k_final[i] = static_cast<uint8_t>((k_bar_prime[i] & diff_is_zero) | (k_bar[i] & ~diff_is_zero));
  }

  // 4. Pack terminal sealed record (52 B)
  store_le32(result + 0, 0x4838524Du); // b"MR8H"
  store_le32(result + 4, request_id);
  store_le32(result + 8, kOk);
  store_le32(result + 12, 32);

  for (uint32_t i = 0; i < 32; ++i) {
    result[20 + i] = k_final[i];
  }

  const uint32_t crc = compute_crc32(k_final, 32);
  store_le32(result + 16, crc);

  clear_bytes(v_bytes, sizeof(v_bytes));
  clear_bytes(k_final, sizeof(k_final));
}
