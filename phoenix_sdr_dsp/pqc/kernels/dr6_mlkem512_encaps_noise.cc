// SPDX-License-Identifier: Apache-2.0
#include "dr6_mlkem512_encaps_internal.hpp"
#include <stdint.h>

using namespace phoenix_sdr_dsp::pqc::dr6;

extern "C" void dr6_mlkem512_encaps_noise(
    const uint8_t deriv_token[kDerivationTokenBytes],
    uint8_t noise_token[kNoiseTokenBytes]) {

  if (!word_aligned(deriv_token) || !word_aligned(noise_token)) {
    clear_bytes(noise_token, kNoiseTokenBytes);
    store_le32(noise_token, 0);
    store_le32(noise_token + 4, kBadToken);
    return;
  }

  const uint32_t request_id = load_le32(deriv_token);
  const uint32_t status = load_le32(deriv_token + 4);

  if (status != kOk) {
    clear_bytes(noise_token, kNoiseTokenBytes);
    store_le32(noise_token, request_id);
    store_le32(noise_token + 4, status);
    return;
  }

  clear_bytes(noise_token, kNoiseTokenBytes);
  store_le32(noise_token, request_id);
  store_le32(noise_token + 4, kOk);

  const uint8_t *k_bar = deriv_token + kDerivKBarOffset;
  const uint8_t *r = deriv_token + kDerivROffset;
  const uint8_t *rho = deriv_token + kDerivRhoOffset;
  const uint8_t *m = deriv_token + kDerivMOffset;

  // 1. Copy K_bar (32 B) and rho (32 B)
  for (uint32_t i = 0; i < 32; ++i) {
    noise_token[kKBarOffset + i] = k_bar[i];
    noise_token[kRhoOffset + i] = rho[i];
  }

  // 2. Forward t_hat[0] and t_hat[1] (2 * 512 = 1024 B)
  copy_words(noise_token + kT0Offset, deriv_token + kDerivT0Offset, 512);
  copy_words(noise_token + kT1Offset, deriv_token + kDerivT1Offset, 512);

  // 3. Sample r[0] and r[1] (CBD3 + NTT)
  sample_cbd3_ntt(r, 0, noise_token + kR0Offset);
  sample_cbd3_ntt(r, 1, noise_token + kR1Offset);

  // 4. Sample e1[0] and e1[1] (CBD2)
  sample_cbd2_store(r, 2, noise_token + kE1_0Offset);
  sample_cbd2_store(r, 3, noise_token + kE1_1Offset);

  // 5. Sample e2 + mu (CBD2 + Decompress1(m))
  sample_cbd2_add_mu(r, m, noise_token + kE2MuOffset);
}
