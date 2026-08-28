// SPDX-License-Identifier: Apache-2.0
#include "dr3_mlkem512_kpke_encrypt_internal.hpp"

using namespace phoenix_sdr_dsp::pqc::dr3;

extern "C" void dr3_mlkem512_kpke_encrypt_col0_expand(
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

  // Copy noise token prefix (3632 B)
  copy_words(col0_token, noise_token, kNoiseTokenBytes);

  const uint8_t *rho = noise_token + kRhoOffset;

  // A^T[0, 0] = SampleNTT(rho, 0, 0)
  if (!sample_matrix_store(rho, 0, 0, col0_token + kA00Offset)) {
    store_le32(col0_token + 4, kLimitExceeded);
    return;
  }

  // A^T[0, 1] = SampleNTT(rho, 0, 1)
  if (!sample_matrix_store(rho, 0, 1, col0_token + kA10Offset)) {
    store_le32(col0_token + 4, kLimitExceeded);
    return;
  }
}
