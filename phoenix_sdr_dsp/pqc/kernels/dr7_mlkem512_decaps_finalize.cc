// SPDX-License-Identifier: Apache-2.0
#include "dr7_mlkem512_decaps_internal.hpp"

using namespace phoenix_sdr_dsp::pqc::dr7;

extern "C" void dr7_mlkem512_decaps_finalize(
    const uint8_t col1_token[kCol1TokenBytes],
    uint8_t result[kResultBytes]) {

  if (!word_aligned(col1_token) || !word_aligned(result)) {
    clear_bytes(result, kResultBytes);
    store_le32(result, 0);
    store_le32(result + 4, kBadToken);
    return;
  }

  const uint32_t request_id = load_le32(col1_token);
  const uint32_t status = load_le32(col1_token + 4);

  if (status != kOk) {
    clear_bytes(result, kResultBytes);
    store_le32(result + 0, 0x4737524Du);
    store_le32(result + 4, request_id);
    store_le32(result + 8, status);
    store_le32(result + 12, 0);
    store_le32(result + 16, 0);
    return;
  }

  // 1. Compute u'_1
  alignas(4) uint8_t u1_bytes[320];
  {
    const uint8_t *a01 = col1_token + kA01Offset;
    const uint8_t *a11 = col1_token + kA11Offset;
    const uint8_t *r0 = col1_token + kU0R0Offset;
    const uint8_t *r1 = col1_token + kU0R1Offset;

    uint32_t u1[kN];
    ntt_multiply_accumulate(a01, r0, a11, r1, u1);
    intt(u1);

    const uint8_t *e1_1 = col1_token + kU0E1_1Offset;
    for (uint32_t i = 0; i < kN; ++i) {
      const uint32_t e_val = load_le16(e1_1 + 2 * i);
      const uint32_t sum = u1[i] + e_val;
      u1[i] = sum >= kQ ? sum - kQ : sum;
    }
    compress10_encode(u1, u1_bytes);
    clear_bytes(reinterpret_cast<uint8_t *>(u1), sizeof(u1));
  }

  // 2. Compute v'
  alignas(4) uint8_t v_bytes[128];
  {
    const uint8_t *t0 = col1_token + kU0T0Offset;
    const uint8_t *t1 = col1_token + kU0T1Offset;
    const uint8_t *r0 = col1_token + kU0R0Offset;
    const uint8_t *r1 = col1_token + kU0R1Offset;

    uint32_t v[kN];
    ntt_multiply_accumulate(t0, r0, t1, r1, v);
    intt(v);

    const uint8_t *e2_mu = col1_token + kU0E2MuOffset;
    for (uint32_t i = 0; i < kN; ++i) {
      const uint32_t e_val = load_le16(e2_mu + 2 * i);
      const uint32_t sum = v[i] + e_val;
      v[i] = sum >= kQ ? sum - kQ : sum;
    }
    compress4_encode(v, v_bytes);
    clear_bytes(reinterpret_cast<uint8_t *>(v), sizeof(v));
  }

  // 3. Constant-time difference check between c and c'
  const uint8_t *u0_bytes = col1_token + kU0C1_0Offset;
  const uint8_t *c_orig = col1_token + kU0COffset;

  uint32_t diff = 0;
  for (uint32_t i = 0; i < 320; ++i) diff |= (c_orig[i] ^ u0_bytes[i]);
  for (uint32_t i = 0; i < 320; ++i) diff |= (c_orig[320 + i] ^ u1_bytes[i]);
  for (uint32_t i = 0; i < 128; ++i) diff |= (c_orig[640 + i] ^ v_bytes[i]);

  // 4. Constant-time selection between K_bar_prime and K_bar
  const uint8_t *k_bar_prime = col1_token + kU0KBarPrimeOffset;
  const uint8_t *k_bar = col1_token + kU0ZOffset; // Rejection key computed in W2
  const uint32_t diff_is_zero = (diff == 0) ? 0xFFu : 0u;

  uint8_t k_final[32];
  for (uint32_t i = 0; i < 32; ++i) {
    k_final[i] = static_cast<uint8_t>((k_bar_prime[i] & diff_is_zero) | (k_bar[i] & ~diff_is_zero));
  }

  // 5. Pack terminal result (52 B)
  clear_bytes(result, kResultBytes);
  store_le32(result + 0, 0x4737524Du); // b"MR7G"
  store_le32(result + 4, request_id);
  store_le32(result + 8, kOk);
  store_le32(result + 12, 32);

  for (uint32_t i = 0; i < 32; ++i) {
    result[kResultKeyOffset + i] = k_final[i];
  }

  const uint32_t crc = compute_crc32(k_final, 32);
  store_le32(result + 16, crc);

  // Clear secrets
  clear_bytes(u1_bytes, sizeof(u1_bytes));
  clear_bytes(v_bytes, sizeof(v_bytes));
  clear_bytes(k_final, sizeof(k_final));
}
