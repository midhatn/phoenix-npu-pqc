// SPDX-License-Identifier: Apache-2.0
#include "dr8_mlkem768_internal.hpp"

using namespace phoenix_sdr_dsp::pqc::dr8_768;

// Noise Token Layout from W0 to W1:
// [0..15]: Header
// [16..47]: K_bar (32)
// [48..79]: rho (32)
// [80..591]: y0 (512)
// [592..1103]: y1 (512)
// [1104..1615]: y2 (512)
// [1616..2127]: e1_0 (512)
// [2128..2639]: e1_1 (512)
// [2640..3151]: e1_2 (512)
// [3152..3663]: e2_mu (512)
// [3664..4175]: t0 (512)
// [4176..4687]: t1 (512)
// [4688..5199]: t2 (512)
// Total Noise Token Bytes = 5200 B

extern "C" void dr8_mlkem768_encaps_noise(
    const uint8_t request[1216],           // ek[1184] || m[32]
    const uint8_t descriptor[16],
    uint8_t noise_token[5200]) {

  if (!word_aligned(noise_token) || !word_aligned(request) || !word_aligned(descriptor)) {
    clear_bytes(noise_token, 5200);
    store_le32(noise_token, 0);
    store_le32(noise_token + 4, kBadToken);
    return;
  }

  const uint32_t request_id = load_le32(descriptor + 8);
  clear_bytes(noise_token, 5200);
  store_le32(noise_token, request_id);
  store_le32(noise_token + 4, kOk);

  const uint8_t *ek = request + 0;
  const uint8_t *m = request + 1184;

  // 1. H(ek) = SHA3-256(ek) (32 B)
  uint8_t h_ek[32];
  sha3_256_ek768(ek, h_ek);

  // 2. G(m || H(ek)) = SHA3-512(m || H(ek)) -> (K_bar, r)
  uint8_t g_in[64];
  for (uint32_t i = 0; i < 32; ++i) {
    g_in[i] = m[i];
    g_in[32 + i] = h_ek[i];
  }
  uint8_t g_out[64];
  sha3_512_64(g_in, g_out);
  const uint8_t *k_bar = g_out + 0;
  const uint8_t *r = g_out + 32;

  // Copy K_bar and rho
  for (uint32_t i = 0; i < 32; ++i) {
    noise_token[16 + i] = k_bar[i];
    noise_token[48 + i] = ek[1152 + i]; // rho
  }

  // 3. Sample y0, y1, y2 (nonces 0, 1, 2)
  sample_cbd2_ntt(r, 0, noise_token + 80);
  sample_cbd2_ntt(r, 1, noise_token + 592);
  sample_cbd2_ntt(r, 2, noise_token + 1104);

  // 4. Sample e1_0, e1_1, e1_2 (nonces 3, 4, 5)
  sample_cbd2_store(r, 3, noise_token + 1616);
  sample_cbd2_store(r, 4, noise_token + 2128);
  sample_cbd2_store(r, 5, noise_token + 2640);

  // 5. Sample e2 + mu(m)
  sample_cbd2_add_mu(r, m, noise_token + 3152);

  // 6. Decode t0, t1, t2 from ek
  decode_d12(ek + 0, noise_token + 3664);
  decode_d12(ek + 384, noise_token + 4176);
  decode_d12(ek + 768, noise_token + 4688);

  clear_bytes(h_ek, sizeof(h_ek));
  clear_bytes(g_in, sizeof(g_in));
  clear_bytes(g_out, sizeof(g_out));
}
