// SPDX-License-Identifier: Apache-2.0
#include "dr8_mlkem1024_internal.hpp"

using namespace phoenix_sdr_dsp::pqc::dr8_1024;

extern "C" void dr8_mlkem1024_decaps_decrypt(
    const uint8_t request[4736],           // dk[3168] || c[1568]
    const uint8_t descriptor[16],
    uint8_t dec_token[3760]) {

  if (!word_aligned(dec_token) || !word_aligned(request) || !word_aligned(descriptor)) {
    clear_bytes(dec_token, 3760);
    store_le32(dec_token, 0);
    store_le32(dec_token + 4, kBadToken);
    return;
  }

  const uint32_t request_id = load_le32(descriptor + 8);
  clear_bytes(dec_token, 3760);
  store_le32(dec_token, request_id);
  store_le32(dec_token + 4, kOk);

  const uint8_t *dk_pke = request + 0;      // 1536 B
  const uint8_t *ek = request + 1536;       // 1568 B
  const uint8_t *h_ek = request + 3104;     // 32 B
  const uint8_t *z = request + 3136;        // 32 B
  const uint8_t *c = request + 3168;        // 1568 B

  // 1. K-PKE.Decrypt(dk_pke, c) -> m' (32 B) with scoped low-stack variables
  uint8_t m_prime[32];
  {
    alignas(4) uint8_t u_raw[4][512];
    DR8_DISABLE_UNROLL
    for (uint32_t poly = 0; poly < 4; ++poly) {
      uint32_t u_tmp[kN];
      decode_decompress_d11(c + 352 * poly, u_tmp);
      ntt(u_tmp);
      for (uint32_t pair = 0; pair < kN / 2; ++pair) {
        store_pair_word(u_raw[poly], pair, u_tmp[2 * pair], u_tmp[2 * pair + 1]);
      }
      clear_bytes(reinterpret_cast<uint8_t *>(u_tmp), sizeof(u_tmp));
    }

    alignas(4) uint8_t s_raw[4][512];
    DR8_DISABLE_UNROLL
    for (uint32_t poly = 0; poly < 4; ++poly) {
      decode_d12(dk_pke + 384 * poly, s_raw[poly]);
    }

    uint32_t w[kN];
    ntt_multiply_accumulate_4(s_raw[0], u_raw[0], s_raw[1], u_raw[1],
                              s_raw[2], u_raw[2], s_raw[3], u_raw[3], w);
    intt(w);

    clear_bytes(reinterpret_cast<uint8_t *>(s_raw), sizeof(s_raw));
    clear_bytes(reinterpret_cast<uint8_t *>(u_raw), sizeof(u_raw));

    {
      uint32_t v_poly[kN];
      decode_decompress_d5(c + 1408, v_poly);
      for (uint32_t i = 0; i < kN; ++i) {
        const uint32_t diff = v_poly[i] + kQ - w[i];
        w[i] = diff >= kQ ? diff - kQ : diff;
      }
      clear_bytes(reinterpret_cast<uint8_t *>(v_poly), sizeof(v_poly));
    }

    compress1(w, m_prime);
    clear_bytes(reinterpret_cast<uint8_t *>(w), sizeof(w));
  }

  // 2. Store outputs in dec_token
  for (uint32_t i = 0; i < 32; ++i) {
    dec_token[16 + i] = m_prime[i];
    dec_token[48 + i] = h_ek[i];
    dec_token[80 + i] = z[i];
    dec_token[112 + i] = ek[1536 + i]; // rho
  }

  // Copy c (1568 B)
  for (uint32_t i = 0; i < 1568; ++i) {
    dec_token[144 + i] = c[i];
  }

  // Decode t0..t3 from ek into dec_token + 1712
  DR8_DISABLE_UNROLL
  for (uint32_t poly = 0; poly < 4; ++poly) {
    decode_d12(ek + 384 * poly, dec_token + 1712 + 512 * poly);
  }

  clear_bytes(m_prime, sizeof(m_prime));
}
