// SPDX-License-Identifier: Apache-2.0
#include "dr3_mlkem512_kpke_encrypt_internal.hpp"

using namespace phoenix_sdr_dsp::pqc::dr3;

extern "C" void dr3_mlkem512_kpke_encrypt_noise(
    const uint8_t request[864],
    const uint8_t descriptor[16],
    uint8_t noise_token[kNoiseTokenBytes]) {

  if (!word_aligned(noise_token) || !word_aligned(request) || !word_aligned(descriptor)) {
    clear_bytes(noise_token, kNoiseTokenBytes);
    store_le32(noise_token, 0);
    store_le32(noise_token + 4, kBadToken);
    return;
  }

  const uint32_t request_id = load_le32(descriptor + 8);
  if (!valid_descriptor(descriptor)) {
    clear_bytes(noise_token, kNoiseTokenBytes);
    store_le32(noise_token, request_id);
    store_le32(noise_token + 4, kBadDescriptor);
    return;
  }

  clear_bytes(noise_token, kNoiseTokenBytes);
  store_le32(noise_token, request_id);
  store_le32(noise_token + 4, kOk);

  const uint8_t *ek_t0 = request;
  const uint8_t *ek_t1 = request + 384;
  const uint8_t *rho   = request + 768;
  const uint8_t *m     = request + 800;
  const uint8_t *r     = request + 832;

  // 1. Copy rho
  for (uint32_t i = 0; i < 32; ++i) {
    noise_token[kRhoOffset + i] = rho[i];
  }

  // 2. Decode t_hat[0] and t_hat[1]
  decode_d12(ek_t0, noise_token + kT0Offset);
  decode_d12(ek_t1, noise_token + kT1Offset);

  // 3. Sample r[0] and r[1] (CBD3 + NTT)
  sample_cbd3_ntt(r, 0, noise_token + kR0Offset);
  sample_cbd3_ntt(r, 1, noise_token + kR1Offset);

  // 4. Sample e1[0] and e1[1] (CBD2)
  sample_cbd2_store(r, 2, noise_token + kE1_0Offset);
  sample_cbd2_store(r, 3, noise_token + kE1_1Offset);

  // 5. Sample e2 + mu (CBD2 + Decompress1(m))
  sample_cbd2_add_mu(r, m, noise_token + kE2MuOffset);
}
