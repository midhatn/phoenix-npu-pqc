// SPDX-License-Identifier: Apache-2.0
#include "dr8_mlkem768_internal.hpp"

using namespace phoenix_sdr_dsp::pqc::dr8_768;

// Layout of Token from W0 to W1:
// [0..15]: Header (req_id, status)
// [16..47]: rho (32)
// [48..79]: z (32)
// [80..591]: s0 (512)
// [592..1103]: s1 (512)
// [1104..1615]: s2 (512)
// [1616..2127]: e0 (512)
// [2128..2639]: e1 (512)
// [2640..3151]: e2 (512)
// Total = 3152 B

extern "C" void dr8_mlkem768_keygen_noise(
    const uint8_t request[64],
    const uint8_t descriptor[16],
    uint8_t noise_token[3152]) {

  if (!word_aligned(noise_token) || !word_aligned(request) || !word_aligned(descriptor)) {
    clear_bytes(noise_token, 3152);
    store_le32(noise_token, 0);
    store_le32(noise_token + 4, kBadToken);
    return;
  }

  const uint32_t request_id = load_le32(descriptor + 8);
  clear_bytes(noise_token, 3152);
  store_le32(noise_token, request_id);
  store_le32(noise_token + 4, kOk);

  const uint8_t *d = request + 0;
  const uint8_t *z = request + 32;

  // G(d || 3) -> (rho, sigma)
  uint8_t d_in[33];
  for (uint32_t i = 0; i < 32; ++i) d_in[i] = d[i];
  d_in[32] = 3; // k=3 for ML-KEM-768
  uint8_t g_out[64];
  sha3_512_33(d_in, g_out);

  const uint8_t *rho = g_out + 0;
  const uint8_t *sigma = g_out + 32;

  for (uint32_t i = 0; i < 32; ++i) {
    noise_token[16 + i] = rho[i];
    noise_token[48 + i] = z[i];
  }

  // Sample s0, s1, s2 (nonces 0, 1, 2)
  sample_cbd2_ntt(sigma, 0, noise_token + 80);
  sample_cbd2_ntt(sigma, 1, noise_token + 592);
  sample_cbd2_ntt(sigma, 2, noise_token + 1104);

  // Sample e0, e1, e2 (nonces 3, 4, 5)
  sample_cbd2_ntt(sigma, 3, noise_token + 1616);
  sample_cbd2_ntt(sigma, 4, noise_token + 2128);
  sample_cbd2_ntt(sigma, 5, noise_token + 2640);

  clear_bytes(d_in, sizeof(d_in));
  clear_bytes(g_out, sizeof(g_out));
}
