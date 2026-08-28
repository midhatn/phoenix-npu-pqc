// SPDX-License-Identifier: Apache-2.0
#include "dr8_mlkem768_internal.hpp"

using namespace phoenix_sdr_dsp::pqc::dr8_768;

// Noise Token Layout from W1 to W2:
// [0..15]: Header
// [16..47]: K_bar_prime (32)
// [48..79]: z (32)
// [80..111]: rho (32)
// [112..1199]: c (1088 B)
// [1200..1711]: y0 (512)
// [1712..2223]: y1 (512)
// [2224..2735]: y2 (512)
// [2736..3247]: e1_0 (512)
// [3248..3759]: e1_1 (512)
// [3760..4271]: e1_2 (512)
// [4272..4783]: e2_mu (512)
// [4784..5295]: t0 (512)
// [5296..5807]: t1 (512)
// [5808..6319]: t2 (512)
// Total Noise Token Bytes = 6320 B

extern "C" void dr8_mlkem768_decaps_noise(
    const uint8_t dec_token[2768],
    uint8_t noise_token[6320]) {

  if (!word_aligned(dec_token) || !word_aligned(noise_token)) {
    clear_bytes(noise_token, 6320);
    store_le32(noise_token, 0);
    store_le32(noise_token + 4, kBadToken);
    return;
  }

  const uint32_t request_id = load_le32(dec_token);
  const uint32_t status = load_le32(dec_token + 4);
  if (status != kOk) {
    clear_bytes(noise_token, 6320);
    store_le32(noise_token, request_id);
    store_le32(noise_token + 4, status);
    return;
  }

  clear_bytes(noise_token, 6320);
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

  // Copy c (1088 B)
  for (uint32_t i = 0; i < 1088; ++i) {
    noise_token[112 + i] = c[i];
  }

  // 2. Sample y0, y1, y2
  sample_cbd2_ntt(r_prime, 0, noise_token + 1200);
  sample_cbd2_ntt(r_prime, 1, noise_token + 1712);
  sample_cbd2_ntt(r_prime, 2, noise_token + 2224);

  // 3. Sample e1_0, e1_1, e1_2
  sample_cbd2_store(r_prime, 3, noise_token + 2736);
  sample_cbd2_store(r_prime, 4, noise_token + 3248);
  sample_cbd2_store(r_prime, 5, noise_token + 3760);

  // 4. Sample e2 + mu(m')
  sample_cbd2_add_mu(r_prime, m_prime, noise_token + 4272);

  // 5. Forward t0, t1, t2
  copy_words(noise_token + 4784, dec_token + 1232, 512 * 3);

  clear_bytes(g_in, sizeof(g_in));
  clear_bytes(g_out, sizeof(g_out));
}
