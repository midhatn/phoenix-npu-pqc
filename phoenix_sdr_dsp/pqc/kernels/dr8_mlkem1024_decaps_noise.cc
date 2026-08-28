// SPDX-License-Identifier: Apache-2.0
#include "dr8_mlkem1024_internal.hpp"

using namespace phoenix_sdr_dsp::pqc::dr8_1024;

// Noise Token Layout (8336 B):
// [0..15]: Header
// [16..47]: K_bar_prime (32)
// [48..79]: z (32)
// [80..111]: rho (32)
// [112..1679]: c (1568 B)
// [1680..3727]: y0..y3 (2048)
// [3728..5775]: e1_0..e1_3 (2048)
// [5776..6287]: e2_mu (512)
// [6288..8335]: t0..t3 (2048)
// Total = 8336 B

extern "C" void dr8_mlkem1024_decaps_noise(
    const uint8_t dec_token[3760],
    uint8_t noise_token[8336]) {

  if (!word_aligned(dec_token) || !word_aligned(noise_token)) {
    clear_bytes(noise_token, 8336);
    store_le32(noise_token, 0);
    store_le32(noise_token + 4, kBadToken);
    return;
  }

  const uint32_t request_id = load_le32(dec_token);
  const uint32_t status = load_le32(dec_token + 4);
  if (status != kOk) {
    clear_bytes(noise_token, 8336);
    store_le32(noise_token, request_id);
    store_le32(noise_token + 4, status);
    return;
  }

  clear_bytes(noise_token, 8336);
  store_le32(noise_token, request_id);
  store_le32(noise_token + 4, kOk);

  const uint8_t *m_prime = dec_token + 16;
  const uint8_t *h_ek = dec_token + 48;
  const uint8_t *z = dec_token + 80;
  const uint8_t *rho = dec_token + 112;
  const uint8_t *c = dec_token + 144;

  // 1. G(m' || H(ek)) -> (K_bar_prime, r_prime)
  uint8_t g_in[64];
  for (uint32_t i = 0; i < 32; ++i) {
    g_in[i] = m_prime[i];
    g_in[32 + i] = h_ek[i];
  }
  uint8_t g_out[64];
  sha3_512_64(g_in, g_out);
  const uint8_t *k_bar_prime = g_out + 0;
  const uint8_t *r_prime = g_out + 32;

  // Copy K_bar_prime, z, rho
  for (uint32_t i = 0; i < 32; ++i) {
    noise_token[16 + i] = k_bar_prime[i];
    noise_token[48 + i] = z[i];
    noise_token[80 + i] = rho[i];
  }

  // Copy c (1568 B)
  for (uint32_t i = 0; i < 1568; ++i) {
    noise_token[112 + i] = c[i];
  }

  // 2. Sample y0..y3 (nonces 0, 1, 2, 3)
  sample_cbd2_ntt(r_prime, 0, noise_token + 1680);
  sample_cbd2_ntt(r_prime, 1, noise_token + 2192);
  sample_cbd2_ntt(r_prime, 2, noise_token + 2704);
  sample_cbd2_ntt(r_prime, 3, noise_token + 3216);

  // 3. Sample e1_0..e1_3 (nonces 4, 5, 6, 7)
  sample_cbd2_store(r_prime, 4, noise_token + 3728);
  sample_cbd2_store(r_prime, 5, noise_token + 4240);
  sample_cbd2_store(r_prime, 6, noise_token + 4752);
  sample_cbd2_store(r_prime, 7, noise_token + 5264);

  // 4. Sample e2 + mu(m')
  sample_cbd2_add_mu(r_prime, m_prime, noise_token + 5776);

  // 5. Forward t0..t3
  copy_words(noise_token + 6288, dec_token + 1712, 512 * 4);

  clear_bytes(g_in, sizeof(g_in));
  clear_bytes(g_out, sizeof(g_out));
}
