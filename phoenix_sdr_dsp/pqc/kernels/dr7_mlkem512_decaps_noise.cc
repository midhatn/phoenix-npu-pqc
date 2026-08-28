// SPDX-License-Identifier: Apache-2.0
#include "dr7_mlkem512_decaps_internal.hpp"
#include <stdint.h>

using namespace phoenix_sdr_dsp::pqc::dr7;

extern "C" void dr7_mlkem512_decaps_noise(
    const uint8_t dec_token[kDerivationTokenBytes],
    uint8_t noise_token[kNoiseTokenBytes]) {

  if (!word_aligned(dec_token) || !word_aligned(noise_token)) {
    clear_bytes(noise_token, kNoiseTokenBytes);
    store_le32(noise_token, 0);
    store_le32(noise_token + 4, kBadToken);
    return;
  }

  const uint32_t request_id = load_le32(dec_token);
  const uint32_t status = load_le32(dec_token + 4);

  if (status != kOk) {
    clear_bytes(noise_token, kNoiseTokenBytes);
    store_le32(noise_token, request_id);
    store_le32(noise_token + 4, status);
    return;
  }

  clear_bytes(noise_token, kNoiseTokenBytes);
  store_le32(noise_token, request_id);
  store_le32(noise_token + 4, kOk);

  const uint8_t *m_prime = dec_token + kDerivMPrimeOffset;
  const uint8_t *h_ek = dec_token + kDerivHEkOffset;
  const uint8_t *z = dec_token + kDerivZOffset;
  const uint8_t *rho = dec_token + kDerivRhoOffset;
  const uint8_t *c = dec_token + kDerivCOffset;

  // 1. G(m' || H(ek)) = SHA3-512(m' || H(ek)) -> (K_bar_prime, r_prime)
  uint8_t g_in[64];
  for (uint32_t i = 0; i < 32; ++i) {
    g_in[i] = m_prime[i];
    g_in[32 + i] = h_ek[i];
  }
  uint8_t g_out[64];
  sha3_512_64(g_in, g_out);
  const uint8_t *k_bar_prime = g_out + 0;
  const uint8_t *r_prime = g_out + 32;

  // 2. Store K_bar_prime, z, rho
  for (uint32_t i = 0; i < 32; ++i) {
    noise_token[kNoiseKBarPrimeOffset + i] = k_bar_prime[i];
    noise_token[kNoiseZOffset + i] = z[i];
    noise_token[kNoiseRhoOffset + i] = rho[i];
  }

  // 3. Copy c (768 B)
  for (uint32_t i = 0; i < 768; ++i) {
    noise_token[kNoiseCOffset + i] = c[i];
  }

  // 4. Forward t_hat[0] and t_hat[1]
  copy_words(noise_token + kNoiseT0Offset, dec_token + kDerivT0Offset, 512);
  copy_words(noise_token + kNoiseT1Offset, dec_token + kDerivT1Offset, 512);

  // 5. Sample r'[0] and r'[1] (CBD3 + NTT)
  sample_cbd3_ntt(r_prime, 0, noise_token + kNoiseR0Offset);
  sample_cbd3_ntt(r_prime, 1, noise_token + kNoiseR1Offset);

  // 6. Sample e'1[0] and e'1[1] (CBD2)
  sample_cbd2_store(r_prime, 2, noise_token + kNoiseE1_0Offset);
  sample_cbd2_store(r_prime, 3, noise_token + kNoiseE1_1Offset);

  // 7. Sample e'2 + mu (CBD2 + Decompress1(m'))
  sample_cbd2_add_mu(r_prime, m_prime, noise_token + kNoiseE2MuOffset);

  clear_bytes(g_in, sizeof(g_in));
  clear_bytes(g_out, sizeof(g_out));
}
