// SPDX-License-Identifier: Apache-2.0
#include "dr6_mlkem512_encaps_internal.hpp"

using namespace phoenix_sdr_dsp::pqc::dr6;

extern "C" void dr6_mlkem512_encaps_row0_expand(
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

  // 1. Pass through entire noise_token (3664 B)
  copy_words(col0_token, noise_token, kNoiseTokenBytes);

  const uint8_t *rho = noise_token + kRhoOffset;

  // 2. Expand A^T[0, 0] = SampleNTT(rho, 0, 0) and A^T[0, 1] = SampleNTT(rho, 0, 1)
  const bool ok00 = sample_matrix_store(rho, 0, 0, col0_token + kA00Offset);
  const bool ok10 = sample_matrix_store(rho, 0, 1, col0_token + kA10Offset);

  if (!ok00 || !ok10) {
    store_le32(col0_token + 4, kLimitExceeded);
  }
}
