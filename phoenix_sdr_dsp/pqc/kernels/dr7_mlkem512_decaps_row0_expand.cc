// SPDX-License-Identifier: Apache-2.0
#include "dr7_mlkem512_decaps_internal.hpp"

using namespace phoenix_sdr_dsp::pqc::dr7;

extern "C" void dr7_mlkem512_decaps_row0_expand(
    const uint8_t noise_token[kNoiseTokenBytes],
    uint8_t col0_token[kCol0TokenBytes]) {

  if (!word_aligned(noise_token) || !word_aligned(col0_token)) {
    clear_bytes(col0_token, kCol0TokenBytes);
    store_le32(col0_token, 0);
    store_le32(col0_token + 4, kBadToken);
    return;
  }

  const uint32_t request_id = load_le32(noise_token);
  const uint32_t status = load_le32(noise_token + 4);

  if (status != kOk) {
    clear_bytes(col0_token, kCol0TokenBytes);
    store_le32(col0_token, request_id);
    store_le32(col0_token + 4, status);
    return;
  }

  copy_words(col0_token, noise_token, kNoiseTokenBytes);

  // 1. Expand A^T[0,0] and A^T[0,1]
  const uint8_t *rho = noise_token + kNoiseRhoOffset;
  const bool ok00 = sample_matrix_store(rho, 0, 0, col0_token + kA00Offset);
  const bool ok10 = sample_matrix_store(rho, 0, 1, col0_token + kA10Offset);

  if (!ok00 || !ok10) {
    store_le32(col0_token + 4, kLimitExceeded);
  }

  // 2. Compute K_bar = J(z || c) = SHAKE256(z || c, 32) (Rejection Key)
  const uint8_t *z = noise_token + kNoiseZOffset;
  const uint8_t *c = noise_token + kNoiseCOffset;
  uint8_t k_bar[32];
  shake256_800(z, c, k_bar);

  // Overwrite z offset (48) with computed K_bar
  for (uint32_t i = 0; i < 32; ++i) {
    col0_token[kNoiseZOffset + i] = k_bar[i];
  }
  clear_bytes(k_bar, sizeof(k_bar));
}
