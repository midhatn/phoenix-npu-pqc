// SPDX-License-Identifier: Apache-2.0
// DR14 ML-DSA-65 Sign Worker 1 (Mask, Matrix, Fast Single-Pass Loop)
#include "dr14_mldsa65_internal.hpp"

using namespace phoenix_sdr_dsp::pqc::dr11;
using namespace phoenix_sdr_dsp::pqc::dr12;
using namespace phoenix_sdr_dsp::pqc::dr14;

extern "C" void dr14_mldsa65_sign_w1_loop(
    const uint8_t in_token[17572],
    uint8_t out_token[12836]) {

  clear_bytes(out_token, 12836);

  const uint32_t request_id = load_le32(in_token + 0);
  store_le32(out_token + 0, request_id);

  const uint8_t *rho = in_token + 4;
  const uint8_t *mu = in_token + 36;
  const uint8_t *rho_pp = in_token + 100;
  const int32_t *s1_hat = reinterpret_cast<const int32_t *>(in_token + 164);
  const int32_t *s2_hat = reinterpret_cast<const int32_t *>(in_token + 5284);
  const int32_t *t0_hat = reinterpret_cast<const int32_t *>(in_token + 11428);

  int32_t *z_out = reinterpret_cast<int32_t *>(out_token + 36);      // [36..5155] (5120 B)
  int32_t *h_out = reinterpret_cast<int32_t *>(out_token + 5156);    // [5156..6691] (1536 B)
  int32_t *w_plain = reinterpret_cast<int32_t *>(out_token + 6692);  // [6692..12835] (6144 B)

  uint16_t kappa = 0;
  int32_t y_ntt[5][256];
  int32_t c_ntt[256];
  int32_t poly[256];
  int32_t poly2[256];
  int32_t poly3[256];
  uint8_t c_tilde[32];
  uint8_t w1_bytes[768];
  uint8_t mu_w1[832];

  DR11_DISABLE_UNROLL
  for (uint32_t c = 0; c < 64; ++c) mu_w1[c] = mu[c];

  while (true) {
    // 1. Sample y[0..4] directly into z_out & NTT into y_ntt
    for (uint16_t j = 0; j < 5; ++j) {
      sample_mask_poly_65(rho_pp, kappa + j, z_out + j * 256);
      DR11_DISABLE_UNROLL
      for (uint32_t c = 0; c < 256; ++c) y_ntt[j][c] = z_out[j * 256 + c];
      ntt_kernel(y_ntt[j]);
    }
    kappa += 5;

    // 2. Matrix multiply w[0..5] = A * y_ntt & decompose to w1
    for (uint8_t row = 0; row < 6; ++row) {
      clear_bytes(poly, sizeof(poly));
      int32_t a_entry[256];
      int32_t prod[256];

      for (uint8_t col = 0; col < 5; ++col) {
        expand_a_sponge(rho, col, row, a_entry);
        basemul(prod, a_entry, y_ntt[col]);
        DR11_DISABLE_UNROLL
        for (uint32_t c = 0; c < 256; ++c) poly[c] += prod[c];
      }

      invntt_kernel(poly);
      DR11_DISABLE_UNROLL
      for (uint32_t c = 0; c < 256; ++c) {
        w_plain[row * 256 + c] = poly[c];
        int32_t r1, r0;
        decompose65(poly[c], r1, r0);
        poly[c] = r1;
      }
      encode_w1_poly65(poly, w1_bytes + row * 128);
    }

    // 3. c_tilde = SHAKE256(mu || w1_bytes, 32)
    DR11_DISABLE_UNROLL
    for (uint32_t c = 0; c < 768; ++c) mu_w1[64 + c] = w1_bytes[c];
    keccak_sponge(136, mu_w1, 832, 0x1F, c_tilde, 32);

    // 4. c = SampleInBall65 -> NTT(c)
    sample_in_ball65(c_tilde, c_ntt);
    ntt_kernel(c_ntt);

    // 5. Check z = y + INTT(c * s1) norm < gamma1 - beta (524092)
    bool reject = false;
    for (uint32_t j = 0; j < 5 && !reject; ++j) {
      basemul(poly, c_ntt, s1_hat + j * 256);
      invntt_kernel(poly);
      DR11_DISABLE_UNROLL
      for (uint32_t c = 0; c < 256; ++c) {
        z_out[j * 256 + c] = canonicalize(z_out[j * 256 + c] + poly[c]);
      }
      if (!check_norm(z_out + j * 256, kGamma1_65 - kBeta65)) reject = true;
    }
    if (reject) continue;

    // 6, 7, 8. Check r0 norm, ct0 norm, and hint count using cached w_plain
    uint32_t hint_count = 0;
    for (uint8_t row = 0; row < 6 && !reject; ++row) {
      // Compute cs2[row] in poly2
      basemul(poly2, c_ntt, s2_hat + row * 256);
      invntt_kernel(poly2);

      // Check r0 norm < gamma2 - beta (261692)
      DR11_DISABLE_UNROLL
      for (uint32_t c = 0; c < 256; ++c) {
        int32_t r1, r0;
        decompose65(canonicalize(w_plain[row * 256 + c] - poly2[c]), r1, r0);
        poly3[c] = r0;
      }
      if (!check_norm(poly3, kGamma2_65 - kBeta65)) {
        reject = true;
        break;
      }

      // Compute ct0[row] in poly3
      basemul(poly3, c_ntt, t0_hat + row * 256);
      invntt_kernel(poly3);

      // Check ct0 norm < gamma2 (261888)
      if (!check_norm(poly3, kGamma2_65)) {
        reject = true;
        break;
      }

      // Compute hints h[row]
      DR11_DISABLE_UNROLL
      for (uint32_t c = 0; c < 256; ++c) {
        const int32_t minus_ct0 = canonicalize(-poly3[c]);
        const int32_t r_plus_z = canonicalize(w_plain[row * 256 + c] - poly2[c] + poly3[c]);
        h_out[row * 256 + c] = make_hint65(minus_ct0, r_plus_z);
        if (h_out[row * 256 + c] != 0) {
          ++hint_count;
        }
      }
    }
    if (reject || hint_count > 55) continue;

    // Accepted! Store c_tilde
    DR11_DISABLE_UNROLL
    for (uint32_t i = 0; i < 32; ++i) out_token[4 + i] = c_tilde[i];

    break;
  }

  clear_bytes(poly, sizeof(poly));
  clear_bytes(poly2, sizeof(poly2));
  clear_bytes(poly3, sizeof(poly3));
  clear_bytes(y_ntt, sizeof(y_ntt));
  clear_bytes(c_ntt, sizeof(c_ntt));
}
