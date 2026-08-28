// SPDX-License-Identifier: Apache-2.0
#include "dr6_mlkem512_encaps_internal.hpp"
#include <stdint.h>

using namespace phoenix_sdr_dsp::pqc::dr6;

extern "C" void dr6_mlkem512_encaps_derive(
    const uint8_t request[832],             // ek[800] || m[32]
    const uint8_t descriptor[16],
    uint8_t deriv_token[kDerivationTokenBytes]) {

  if (!word_aligned(deriv_token) || !word_aligned(request) || !word_aligned(descriptor)) {
    clear_bytes(deriv_token, kDerivationTokenBytes);
    store_le32(deriv_token, 0);
    store_le32(deriv_token + 4, kBadToken);
    return;
  }

  const uint32_t request_id = load_le32(descriptor + 8);
  if (!valid_descriptor(descriptor)) {
    clear_bytes(deriv_token, kDerivationTokenBytes);
    store_le32(deriv_token, request_id);
    store_le32(deriv_token + 4, kBadDescriptor);
    return;
  }

  clear_bytes(deriv_token, kDerivationTokenBytes);
  store_le32(deriv_token, request_id);
  store_le32(deriv_token + 4, kOk);

  const uint8_t *ek = request + 0;
  const uint8_t *m = request + 800;

  // 1. H(ek) = SHA3-256(ek) (32 bytes)
  uint8_t h_ek[32];
  sha3_256_800(ek, h_ek);

  // 2. G(m || H(ek)) = SHA3-512(m || H(ek)) (64 bytes: K_bar[32] || r[32])
  uint8_t g_in[64];
  for (uint32_t i = 0; i < 32; ++i) {
    g_in[i] = m[i];
    g_in[32 + i] = h_ek[i];
  }
  uint8_t g_out[64];
  sha3_512_64(g_in, g_out);

  const uint8_t *k_bar = g_out + 0;
  const uint8_t *r = g_out + 32;

  // 3. Store K_bar (32 B) and r (32 B)
  for (uint32_t i = 0; i < 32; ++i) {
    deriv_token[kDerivKBarOffset + i] = k_bar[i];
    deriv_token[kDerivROffset + i] = r[i];
  }

  // 4. Store rho from ek[768..799] (32 B) and m (32 B)
  for (uint32_t i = 0; i < 32; ++i) {
    deriv_token[kDerivRhoOffset + i] = ek[768 + i];
    deriv_token[kDerivMOffset + i] = m[i];
  }

  // 5. Decode t_hat[0] and t_hat[1] from ek
  decode_d12(ek + 0, deriv_token + kDerivT0Offset);
  decode_d12(ek + 384, deriv_token + kDerivT1Offset);

  // Clear secrets
  clear_bytes(h_ek, sizeof(h_ek));
  clear_bytes(g_in, sizeof(g_in));
  clear_bytes(g_out, sizeof(g_out));
}
