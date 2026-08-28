// SPDX-License-Identifier: Apache-2.0
#include "dr7_mlkem512_decaps_internal.hpp"

using namespace phoenix_sdr_dsp::pqc::dr7;

extern "C" void dr7_mlkem512_decaps_row1_expand(
    const uint8_t u0_token[kU0TokenBytes],
    uint8_t col1_token[kCol1TokenBytes]) {

  if (!word_aligned(u0_token) || !word_aligned(col1_token)) {
    clear_bytes(col1_token, kCol1TokenBytes);
    store_le32(col1_token, 0);
    store_le32(col1_token + 4, kBadToken);
    return;
  }

  const uint32_t request_id = load_le32(u0_token);
  const uint32_t status = load_le32(u0_token + 4);

  if (status != kOk) {
    clear_bytes(col1_token, kCol1TokenBytes);
    store_le32(col1_token, request_id);
    store_le32(col1_token + 4, status);
    return;
  }

  copy_words(col1_token, u0_token, kU0TokenBytes);

  const uint8_t *rho = u0_token + kU0RhoOffset;

  const bool ok01 = sample_matrix_store(rho, 1, 0, col1_token + kA01Offset);
  const bool ok11 = sample_matrix_store(rho, 1, 1, col1_token + kA11Offset);

  if (!ok01 || !ok11) {
    store_le32(col1_token + 4, kLimitExceeded);
  }
}
