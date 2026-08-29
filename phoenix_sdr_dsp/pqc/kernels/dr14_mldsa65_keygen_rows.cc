// SPDX-License-Identifier: Apache-2.0
// DR14 ML-DSA-65 KeyGen Row Pair Worker (Zero-Copy Direct In-Token Access)
#include "dr14_mldsa65_internal.hpp"

using namespace phoenix_sdr_dsp::pqc::dr11;
using namespace phoenix_sdr_dsp::pqc::dr14;

__attribute__((noinline)) static void compute_keygen_row(
    uint8_t row_idx,
    const uint8_t rho[32],
    const int32_t *s1_hat,
    const int32_t *s2_plain,
    uint8_t t1_out[320],
    uint8_t t0_out[416]) {

  int32_t acc[256];
  clear_bytes(acc, sizeof(acc));

  int32_t a_entry[256];
  int32_t prod[256];

  for (uint8_t col = 0; col < 5; ++col) {
    expand_a_sponge(rho, col, row_idx, a_entry);
    basemul(prod, a_entry, s1_hat + col * 256);
    DR11_DISABLE_UNROLL
    for (uint32_t c = 0; c < 256; ++c) acc[c] += prod[c];
  }

  invntt_kernel(acc);

  int32_t t1_poly[256];
  int32_t t0_poly[256];
  DR11_DISABLE_UNROLL
  for (uint32_t c = 0; c < 256; ++c) {
    const int32_t t_val = canonicalize(acc[c] + s2_plain[c]);
    power2round(t_val, t1_poly[c], t0_poly[c]);
  }

  encode_pk_t1_poly(t1_poly, t1_out);
  encode_sk_t0_poly(t0_poly, t0_out);

  clear_bytes(acc, sizeof(acc));
  clear_bytes(a_entry, sizeof(a_entry));
  clear_bytes(prod, sizeof(prod));
  clear_bytes(t1_poly, sizeof(t1_poly));
  clear_bytes(t0_poly, sizeof(t0_poly));
}

extern "C" void dr14_mldsa65_keygen_row01(
    const uint8_t in_token[12800],
    uint8_t out_token[12160]) {

  clear_bytes(out_token, 12160);

  // Copy header, rho, K, s1_enc, s2_enc, s1_hat: [0..6595] (6596 B)
  DR11_DISABLE_UNROLL
  for (uint32_t i = 0; i < 6596; ++i) out_token[i] = in_token[i];

  // Copy s2_plain[2..5] (4 * 1024 = 4096 B): from in[8644..12739] -> out[6596..10691]
  const uint8_t *s2_src_25 = in_token + 6596 + 2048;
  DR11_DISABLE_UNROLL
  for (uint32_t i = 0; i < 4096; ++i) out_token[6596 + i] = s2_src_25[i];

  const uint8_t *rho = in_token + 4;
  const int32_t *s1_hat = reinterpret_cast<const int32_t *>(in_token + 1476);
  const int32_t *s2_plain_01 = reinterpret_cast<const int32_t *>(in_token + 6596);

  uint8_t *row_dst = out_token + 10692;

  // Row 0
  compute_keygen_row(0, rho, s1_hat, s2_plain_01 + 0 * 256, row_dst + 0, row_dst + 320);

  // Row 1
  compute_keygen_row(1, rho, s1_hat, s2_plain_01 + 1 * 256, row_dst + 736, row_dst + 1056);
}

extern "C" void dr14_mldsa65_keygen_row23(
    const uint8_t in_token[12160],
    uint8_t out_token[11588]) {

  clear_bytes(out_token, 11588);

  // Copy header, rho, K, s1_enc, s2_enc, s1_hat: [0..6595] (6596 B)
  DR11_DISABLE_UNROLL
  for (uint32_t i = 0; i < 6596; ++i) out_token[i] = in_token[i];

  // Copy s2_plain[4..5] (2 * 1024 = 2048 B): from in[8644..10691] -> out[6596..8643]
  const uint8_t *s2_src_45 = in_token + 6596 + 2048;
  DR11_DISABLE_UNROLL
  for (uint32_t i = 0; i < 2048; ++i) out_token[6596 + i] = s2_src_45[i];

  // Copy rows 0-1 results (1472 B): from in[10692..12163] -> out[8644..10115]
  const uint8_t *rows01_src = in_token + 10692;
  DR11_DISABLE_UNROLL
  for (uint32_t i = 0; i < 1472; ++i) out_token[8644 + i] = rows01_src[i];

  const uint8_t *rho = in_token + 4;
  const int32_t *s1_hat = reinterpret_cast<const int32_t *>(in_token + 1476);
  const int32_t *s2_plain_23 = reinterpret_cast<const int32_t *>(in_token + 6596);

  uint8_t *row_dst = out_token + 10116;

  // Row 2
  compute_keygen_row(2, rho, s1_hat, s2_plain_23 + 0 * 256, row_dst + 0, row_dst + 320);

  // Row 3
  compute_keygen_row(3, rho, s1_hat, s2_plain_23 + 1 * 256, row_dst + 736, row_dst + 1056);
}

extern "C" void dr14_mldsa65_keygen_row45(
    const uint8_t in_token[11588],
    uint8_t out_token[5892]) {

  clear_bytes(out_token, 5892);

  // Copy header, rho, K, s1_enc, s2_enc: [0..1475] (1476 B)
  DR11_DISABLE_UNROLL
  for (uint32_t i = 0; i < 1476; ++i) out_token[i] = in_token[i];

  // Copy rows 0-3 results (2944 B): from in[8644..11587] -> out[1476..4419]
  const uint8_t *rows03_src = in_token + 8644;
  DR11_DISABLE_UNROLL
  for (uint32_t i = 0; i < 2944; ++i) out_token[1476 + i] = rows03_src[i];

  const uint8_t *rho = in_token + 4;
  const int32_t *s1_hat = reinterpret_cast<const int32_t *>(in_token + 1476);
  const int32_t *s2_plain_45 = reinterpret_cast<const int32_t *>(in_token + 6596);

  uint8_t *row_dst = out_token + 4420;

  // Row 4
  compute_keygen_row(4, rho, s1_hat, s2_plain_45 + 0 * 256, row_dst + 0, row_dst + 320);

  // Row 5
  compute_keygen_row(5, rho, s1_hat, s2_plain_45 + 1 * 256, row_dst + 736, row_dst + 1056);
}
