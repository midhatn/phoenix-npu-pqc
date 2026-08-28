// SPDX-License-Identifier: Apache-2.0
#include "dr8_mlkem768_internal.hpp"

using namespace phoenix_sdr_dsp::pqc::dr8_768;

// Deriv Token Layout from W0 to W1:
// [0..15]: Header
// [16..47]: m_prime (32)
// [48..79]: H(ek) (32)
// [80..111]: z (32)
// [112..143]: rho (32)
// [144..1231]: c (1088 B)
// [1232..1743]: t0 (512)
// [1744..2255]: t1 (512)
// [2256..2767]: t2 (512)
// Total Deriv Token Bytes = 2768 B

extern "C" void dr8_mlkem768_decaps_decrypt(
    const uint8_t request[3488],           // dk[2400] || c[1088]
    const uint8_t descriptor[16],
    uint8_t dec_token[2768]) {

  if (!word_aligned(dec_token) || !word_aligned(request) || !word_aligned(descriptor)) {
    clear_bytes(dec_token, 2768);
    store_le32(dec_token, 0);
    store_le32(dec_token + 4, kBadToken);
    return;
  }

  const uint32_t request_id = load_le32(descriptor + 8);
  clear_bytes(dec_token, 2768);
  store_le32(dec_token, request_id);
  store_le32(dec_token + 4, kOk);

  const uint8_t *dk_pke = request + 0;      // 1152 B
  const uint8_t *ek = request + 1152;       // 1184 B
  const uint8_t *h_ek = request + 2336;     // 32 B
  const uint8_t *z = request + 2368;        // 32 B
  const uint8_t *c = request + 2400;        // 1088 B

  // 1. K-PKE.Decrypt(dk_pke, c) -> m' (32 B) with scoped low-stack variables
  uint8_t m_prime[32];
  {
    alignas(4) uint8_t u0_raw[512], u1_raw[512], u2_raw[512];

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

      decode_decompress_d10(c + 640, u_tmp);
      ntt(u_tmp);
      for (uint32_t pair = 0; pair < kN / 2; ++pair) {
        store_pair_word(u2_raw, pair, u_tmp[2 * pair], u_tmp[2 * pair + 1]);
      }
      clear_bytes(reinterpret_cast<uint8_t *>(u_tmp), sizeof(u_tmp));
    }

    alignas(4) uint8_t s0_raw[512], s1_raw[512], s2_raw[512];
    decode_d12(dk_pke + 0, s0_raw);
    decode_d12(dk_pke + 384, s1_raw);
    decode_d12(dk_pke + 768, s2_raw);

    uint32_t w[kN];
    ntt_multiply_accumulate_3(s0_raw, u0_raw, s1_raw, u1_raw, s2_raw, u2_raw, w);
    intt(w);

    clear_bytes(s0_raw, sizeof(s0_raw));
    clear_bytes(s1_raw, sizeof(s1_raw));
    clear_bytes(s2_raw, sizeof(s2_raw));
    clear_bytes(u0_raw, sizeof(u0_raw));
    clear_bytes(u1_raw, sizeof(u1_raw));
    clear_bytes(u2_raw, sizeof(u2_raw));

    {
      uint32_t v_poly[kN];
      decode_decompress_d4(c + 960, v_poly);
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
    dec_token[112 + i] = ek[1152 + i]; // rho
  }

  // Copy c (1088 B)
  for (uint32_t i = 0; i < 1088; ++i) {
    dec_token[144 + i] = c[i];
  }

  // Decode t0, t1, t2 from ek
  decode_d12(ek + 0, dec_token + 1232);
  decode_d12(ek + 384, dec_token + 1744);
  decode_d12(ek + 768, dec_token + 2256);

  clear_bytes(m_prime, sizeof(m_prime));
}
