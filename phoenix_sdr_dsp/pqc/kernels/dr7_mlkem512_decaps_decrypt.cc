// SPDX-License-Identifier: Apache-2.0
#include "dr7_mlkem512_decaps_internal.hpp"
#include <stdint.h>

using namespace phoenix_sdr_dsp::pqc::dr7;

extern "C" void dr7_mlkem512_decaps_decrypt(
    const uint8_t request[2400],            // dk[1632] || c[768]
    const uint8_t descriptor[16],
    uint8_t dec_token[kDerivationTokenBytes]) {

  if (!word_aligned(dec_token) || !word_aligned(request) || !word_aligned(descriptor)) {
    clear_bytes(dec_token, kDerivationTokenBytes);
    store_le32(dec_token, 0);
    store_le32(dec_token + 4, kBadToken);
    return;
  }

  const uint32_t request_id = load_le32(descriptor + 8);
  if (!valid_descriptor(descriptor)) {
    clear_bytes(dec_token, kDerivationTokenBytes);
    store_le32(dec_token, request_id);
    store_le32(dec_token + 4, kBadDescriptor);
    return;
  }

  clear_bytes(dec_token, kDerivationTokenBytes);
  store_le32(dec_token, request_id);
  store_le32(dec_token + 4, kOk);

  const uint8_t *dk_pke = request + 0;
  const uint8_t *ek = request + 768;
  const uint8_t *h_ek = request + 1568;
  const uint8_t *z = request + 1600;
  const uint8_t *c = request + 1632;

  // 1. K-PKE.Decrypt(dk_pke, c) -> m' (32 B) with scoped low-stack variables
  uint8_t m_prime[32];
  {
    alignas(4) uint8_t u0_raw[512];
    alignas(4) uint8_t u1_raw[512];

    {
      uint32_t u_tmp[kN];
      decode_decompress_d10(c + 0, u_tmp);
      ntt(u_tmp);
      for (uint32_t pair = 0; pair < kN / 2; ++pair) {
        store_pair_word(u0_raw, pair, u_tmp[2 * pair], u_tmp[2 * pair + 1]);
      }

      decode_decompress_d10(c + 320, u_tmp);
      ntt(u_tmp);
      for (uint32_t pair = 0; pair < kN / 2; ++pair) {
        store_pair_word(u1_raw, pair, u_tmp[2 * pair], u_tmp[2 * pair + 1]);
      }
      clear_bytes(reinterpret_cast<uint8_t *>(u_tmp), sizeof(u_tmp));
    }

    alignas(4) uint8_t s0_raw[512];
    alignas(4) uint8_t s1_raw[512];
    decode_d12(dk_pke + 0, s0_raw);
    decode_d12(dk_pke + 384, s1_raw);

    uint32_t w[kN];
    ntt_multiply_accumulate(s0_raw, u0_raw, s1_raw, u1_raw, w);
    intt(w);

    clear_bytes(s0_raw, sizeof(s0_raw));
    clear_bytes(s1_raw, sizeof(s1_raw));
    clear_bytes(u0_raw, sizeof(u0_raw));
    clear_bytes(u1_raw, sizeof(u1_raw));

    {
      uint32_t v_poly[kN];
      decode_decompress_d4(c + 640, v_poly);
      for (uint32_t i = 0; i < kN; ++i) {
        const uint32_t diff = v_poly[i] + kQ - w[i];
        w[i] = diff >= kQ ? diff - kQ : diff;
      }
      clear_bytes(reinterpret_cast<uint8_t *>(v_poly), sizeof(v_poly));
    }

    compress1(w, m_prime);
    clear_bytes(reinterpret_cast<uint8_t *>(w), sizeof(w));
  }

  // 2. Store outputs in dec_token (1968 B)
  // Store m' (32 B), H(ek) (32 B), z (32 B), rho (32 B)
  for (uint32_t i = 0; i < 32; ++i) {
    dec_token[kDerivMPrimeOffset + i] = m_prime[i]; // 16
    dec_token[kDerivHEkOffset + i] = h_ek[i];       // 48
    dec_token[kDerivZOffset + i] = z[i];             // 80
    dec_token[kDerivRhoOffset + i] = ek[768 + i];    // 112
  }

  // Copy c (768 B)
  for (uint32_t i = 0; i < 768; ++i) {
    dec_token[kDerivCOffset + i] = c[i];             // 144
  }

  // Decode t_hat[0] and t_hat[1] from ek
  decode_d12(ek + 0, dec_token + kDerivT0Offset);   // 912
  decode_d12(ek + 384, dec_token + kDerivT1Offset); // 1424

  clear_bytes(m_prime, sizeof(m_prime));
}
