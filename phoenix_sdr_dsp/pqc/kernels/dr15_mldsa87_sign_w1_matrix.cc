// SPDX-License-Identifier: Apache-2.0
// DR15 ML-DSA-87 Sign Worker 1 (Complete Single-Pass Rejection Loop)
#include "dr15_mldsa87_internal.hpp"

using namespace phoenix_sdr_dsp::pqc::dr11;
using namespace phoenix_sdr_dsp::pqc::dr12;
using namespace phoenix_sdr_dsp::pqc::dr13;
using namespace phoenix_sdr_dsp::pqc::dr14;
using namespace phoenix_sdr_dsp::pqc::dr15;

__attribute__((noinline)) static void sample_y_vector(
    const uint8_t *rho_pp, uint16_t kappa, int32_t *z_out) {
  DR11_DISABLE_UNROLL
  for (uint16_t j = 0; j < 7; ++j) {
    sample_mask_poly_65(rho_pp, kappa + j, z_out + j * 256);
  }
}

__attribute__((noinline)) static void matmul_accumulate_col(
    const uint8_t *rho, uint8_t col, const int32_t poly[256], int32_t w_plain[8][256]) {
  int32_t a_entry[256];
  int32_t prod[256];
  DR11_DISABLE_UNROLL
  for (uint8_t row = 0; row < 8; ++row) {
    expand_a_sponge(rho, col, row, a_entry);
    basemul(prod, a_entry, poly);
    DR11_DISABLE_UNROLL
    for (uint32_t c = 0; c < 256; ++c) {
      w_plain[row][c] += prod[c];
    }
  }
}

__attribute__((noinline)) static void compute_w_from_y(
    const uint8_t *rho, const int32_t *z_out, int32_t w_plain[8][256]) {
  clear_mem(w_plain, sizeof(int32_t) * 8 * 256);
  int32_t poly[256];
  DR11_DISABLE_UNROLL
  for (uint8_t col = 0; col < 7; ++col) {
    DR11_DISABLE_UNROLL
    for (uint32_t c = 0; c < 256; ++c) poly[c] = z_out[col * 256 + c];
    ntt_kernel(poly);
    matmul_accumulate_col(rho, col, poly, w_plain);
  }
}

__attribute__((noinline)) static void decompose_and_encode_w(
    int32_t w_plain[8][256], uint8_t w1_bytes[1024]) {
  int32_t poly[256];
  DR11_DISABLE_UNROLL
  for (uint8_t row = 0; row < 8; ++row) {
    DR11_DISABLE_UNROLL
    for (uint32_t c = 0; c < 256; ++c) poly[c] = w_plain[row][c];
    invntt_kernel(poly);
    DR11_DISABLE_UNROLL
    for (uint32_t c = 0; c < 256; ++c) {
      w_plain[row][c] = poly[c];
      int32_t r1, r0;
      decompose65(poly[c], r1, r0);
      poly[c] = r1;
    }
    encode_w1_poly65(poly, w1_bytes + row * 128);
  }
}

__attribute__((noinline)) static void compute_challenge_ntt(
    const uint8_t *mu, const uint8_t *w1_bytes, uint8_t *c_tilde, int32_t c_ntt[256]) {
  uint8_t mu_w1[1088];
  DR11_DISABLE_UNROLL
  for (uint32_t c = 0; c < 64; ++c) mu_w1[c] = mu[c];
  DR11_DISABLE_UNROLL
  for (uint32_t c = 0; c < 1024; ++c) mu_w1[64 + c] = w1_bytes[c];
  keccak_sponge(136, mu_w1, 1088, 0x1F, c_tilde, 64);
  sample_in_ball87(c_tilde, c_ntt);
  ntt_kernel(c_ntt);
}

__attribute__((noinline)) static void compute_cs2_intt(
    const uint8_t *s2_bytes, uint32_t row, const int32_t c_ntt[256], int32_t out[256]) {
  int32_t poly[256];
  decode_sk_s_poly(s2_bytes + row * 96, poly);
  DR11_DISABLE_UNROLL
  for (uint32_t c = 0; c < 256; ++c) poly[c] = canonicalize(poly[c]);
  ntt_kernel(poly);
  basemul(out, c_ntt, poly);
  invntt_kernel(out);
}

__attribute__((noinline)) static void compute_ct0_intt(
    const uint8_t *t0_bytes, uint32_t row, const int32_t c_ntt[256], int32_t out[256]) {
  int32_t poly[256];
  decode_sk_t0_poly(t0_bytes + row * 416, poly);
  ntt_kernel(poly);
  basemul(out, c_ntt, poly);
  invntt_kernel(out);
}

__attribute__((noinline)) static bool check_z_norm(
    const int32_t *s1_hat, const int32_t c_ntt[256], int32_t *z_out) {
  int32_t poly[256];
  DR11_DISABLE_UNROLL
  for (uint32_t j = 0; j < 7; ++j) {
    basemul(poly, c_ntt, s1_hat + j * 256);
    invntt_kernel(poly);
    DR11_DISABLE_UNROLL
    for (uint32_t c = 0; c < 256; ++c) {
      z_out[j * 256 + c] = canonicalize(z_out[j * 256 + c] + poly[c]);
    }
    if (!check_norm(z_out + j * 256, kGamma1_87 - kBeta87)) return false;
  }
  return true;
}

__attribute__((noinline)) static bool check_and_compute_hints(
    const uint8_t *s2_bytes, const uint8_t *t0_bytes,
    const int32_t c_ntt[256], const int32_t w_plain[8][256],
    uint8_t *h_out) {
  uint32_t hint_count = 0;
  int32_t poly2[256];
  int32_t poly3[256];
  DR11_DISABLE_UNROLL
  for (uint8_t row = 0; row < 8; ++row) {
    compute_cs2_intt(s2_bytes, row, c_ntt, poly2);

    DR11_DISABLE_UNROLL
    for (uint32_t c = 0; c < 256; ++c) {
      int32_t r1, r0;
      decompose65(canonicalize(w_plain[row][c] - poly2[c]), r1, r0);
      poly3[c] = r0;
    }
    if (!check_norm(poly3, kGamma2_87 - kBeta87)) return false;

    compute_ct0_intt(t0_bytes, row, c_ntt, poly3);
    if (!check_norm(poly3, kGamma2_87)) return false;

    DR11_DISABLE_UNROLL
    for (uint32_t c = 0; c < 256; ++c) {
      const int32_t minus_ct0 = canonicalize(-poly3[c]);
      const int32_t r_plus_z = canonicalize(w_plain[row][c] - poly2[c] + poly3[c]);
      h_out[row * 256 + c] = static_cast<uint8_t>(make_hint65(minus_ct0, r_plus_z));
      if (h_out[row * 256 + c] != 0) {
        ++hint_count;
      }
    }
  }
  return hint_count <= kOmega87;
}

extern "C" void dr15_mldsa87_sign_w1_matrix(
    const uint8_t in_token[11500],
    uint8_t out_token[9300]) {

  clear_mem(out_token, 9300);

  const uint32_t request_id = load_le32(in_token + 0);
  store_le32(out_token + 0, request_id);

  const uint8_t *rho = in_token + 4;
  const uint8_t *mu = in_token + 36;
  const uint8_t *rho_pp = in_token + 100;
  const int32_t *s1_hat = reinterpret_cast<const int32_t *>(in_token + 164);
  const uint8_t *s2_bytes = in_token + 7332;
  const uint8_t *t0_bytes = in_token + 8100;

  int32_t *z_out = reinterpret_cast<int32_t *>(out_token + 68);     // [68..7235] (7168 B)
  uint8_t *h_out = out_token + 7236;                                // [7236..9283] (2048 B)

  uint16_t kappa = 0;
  int32_t w_plain[8][256];
  int32_t c_ntt[256];
  uint8_t c_tilde[64];
  uint8_t w1_bytes[1024];

  while (true) {
    // 1. Sample y[0..6] directly into z_out
    sample_y_vector(rho_pp, kappa, z_out);
    kappa += 7;

    // 2. Matrix multiply w[0..7] = A * y_ntt & decompose to w1
    compute_w_from_y(rho, z_out, w_plain);
    decompose_and_encode_w(w_plain, w1_bytes);

    // 3. Challenge c_tilde & NTT(c)
    compute_challenge_ntt(mu, w1_bytes, c_tilde, c_ntt);

    // 4. Check z = y + INTT(c * s1) norm < gamma1 - beta (524168)
    if (!check_z_norm(s1_hat, c_ntt, z_out)) continue;

    // 5, 6, 7. Check r0 norm, ct0 norm, and hint count
    if (!check_and_compute_hints(s2_bytes, t0_bytes, c_ntt, w_plain, h_out)) continue;

    // Accepted! Store c_tilde (64 B)
    DR11_DISABLE_UNROLL
    for (uint32_t i = 0; i < 64; ++i) out_token[4 + i] = c_tilde[i];

    break;
  }

  clear_mem(w_plain, sizeof(w_plain));
  clear_mem(c_ntt, sizeof(c_ntt));
}
