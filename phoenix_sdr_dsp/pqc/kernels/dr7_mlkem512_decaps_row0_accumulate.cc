// SPDX-License-Identifier: Apache-2.0
#include "dr7_mlkem512_decaps_internal.hpp"

using namespace phoenix_sdr_dsp::pqc::dr7;

extern "C" void dr7_mlkem512_decaps_row0_accumulate(
    const uint8_t col0_token[kCol0TokenBytes],
    uint8_t u0_token[kU0TokenBytes]) {

  if (!word_aligned(col0_token) || !word_aligned(u0_token)) {
    clear_bytes(u0_token, kU0TokenBytes);
    store_le32(u0_token, 0);
    store_le32(u0_token + 4, kBadToken);
    return;
  }

  const uint32_t request_id = load_le32(col0_token);
  const uint32_t status = load_le32(col0_token + 4);

  if (status != kOk) {
    clear_bytes(u0_token, kU0TokenBytes);
    store_le32(u0_token, request_id);
    store_le32(u0_token + 4, status);
    return;
  }

  clear_bytes(u0_token, kU0TokenBytes);
  store_le32(u0_token, request_id);
  store_le32(u0_token + 4, kOk);

  // Copy K_bar_prime, K_bar, rho
  for (uint32_t i = 0; i < 32; ++i) {
    u0_token[kU0KBarPrimeOffset + i] = col0_token[kNoiseKBarPrimeOffset + i]; // 16
    u0_token[kU0ZOffset + i] = col0_token[kNoiseZOffset + i];                 // 48 (K_bar)
    u0_token[kU0RhoOffset + i] = col0_token[kNoiseRhoOffset + i];             // 80
  }

  // Copy c (768 B)
  for (uint32_t i = 0; i < 768; ++i) {
    u0_token[kU0COffset + i] = col0_token[kNoiseCOffset + i];
  }

  // Forward r'[0], r'[1], e'1[1], e'2+mu, t_hat[0], t_hat[1]
  copy_words(u0_token + kU0R0Offset, col0_token + kNoiseR0Offset, 512);
  copy_words(u0_token + kU0R1Offset, col0_token + kNoiseR1Offset, 512);
  copy_words(u0_token + kU0E1_1Offset, col0_token + kNoiseE1_1Offset, 512);
  copy_words(u0_token + kU0E2MuOffset, col0_token + kNoiseE2MuOffset, 512);
  copy_words(u0_token + kU0T0Offset, col0_token + kNoiseT0Offset, 512);
  copy_words(u0_token + kU0T1Offset, col0_token + kNoiseT1Offset, 512);

  // Compute u'_0 = INTT(A^T[0,0] * r'_0 + A^T[0,1] * r'_1) + e'1_0
  const uint8_t *a00 = col0_token + kA00Offset;
  const uint8_t *a10 = col0_token + kA10Offset;
  const uint8_t *r0 = col0_token + kNoiseR0Offset;
  const uint8_t *r1 = col0_token + kNoiseR1Offset;

  uint32_t u0[kN];
  ntt_multiply_accumulate(a00, r0, a10, r1, u0);
  intt(u0);

  const uint8_t *e1_0 = col0_token + kNoiseE1_0Offset;
  for (uint32_t i = 0; i < kN; ++i) {
    const uint32_t e_val = load_le16(e1_0 + 2 * i);
    const uint32_t sum = u0[i] + e_val;
    u0[i] = sum >= kQ ? sum - kQ : sum;
  }

  compress10_encode(u0, u0_token + kU0C1_0Offset);
  clear_bytes(reinterpret_cast<uint8_t *>(u0), sizeof(u0));
}
