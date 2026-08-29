// SPDX-License-Identifier: Apache-2.0
// DR15 ML-DSA-87 KeyGen 4-Row Matrix Multiplication Template
#include "dr15_mldsa87_internal.hpp"

using namespace phoenix_sdr_dsp::pqc::dr11;
using namespace phoenix_sdr_dsp::pqc::dr12;
using namespace phoenix_sdr_dsp::pqc::dr13;
using namespace phoenix_sdr_dsp::pqc::dr14;
using namespace phoenix_sdr_dsp::pqc::dr15;

extern "C" void dr15_mldsa87_keygen_rows4567(
    const uint8_t in_token[11648],
    uint8_t out_token[14592]) {

  clear_bytes(out_token, 14592);

  constexpr uint8_t START_ROW = 4;

  // Copy header + rho + K + s1 + s2 + s1_hat
  DR11_DISABLE_UNROLL
  for (uint32_t i = 0; i < 8676; ++i) out_token[i] = in_token[i];

  // Copy previously computed t1 and t0
  constexpr uint32_t PREV_T1_BYTES = START_ROW * 320;
  constexpr uint32_t PREV_T0_BYTES = START_ROW * 416;

  DR11_DISABLE_UNROLL
  for (uint32_t i = 0; i < PREV_T1_BYTES; ++i) {
    out_token[8676 + i] = in_token[8676 + i];
  }
  DR11_DISABLE_UNROLL
  for (uint32_t i = 0; i < PREV_T0_BYTES; ++i) {
    out_token[11236 + i] = in_token[11236 + i];
  }

  const uint8_t *rho = in_token + 4;
  const uint8_t *s2_bytes = in_token + 740;
  const int32_t *s1_hat = reinterpret_cast<const int32_t *>(in_token + 1508);

  uint8_t *t1_out = out_token + 8676 + START_ROW * 320;
  uint8_t *t0_out = out_token + 11236 + START_ROW * 416;

  int32_t acc[256];
  int32_t a_entry[256];
  int32_t prod[256];
  int32_t s2_row[256];
  int32_t t1_poly[256];
  int32_t t0_poly[256];

  for (uint8_t r_offset = 0; r_offset < 4; ++r_offset) {
    const uint8_t row = START_ROW + r_offset;
    clear_bytes(acc, sizeof(acc));

    for (uint8_t col = 0; col < 7; ++col) {
      expand_a_sponge(rho, col, row, a_entry);
      basemul(prod, a_entry, s1_hat + col * 256);
      DR11_DISABLE_UNROLL
      for (uint32_t c = 0; c < 256; ++c) acc[c] += prod[c];
    }

    invntt_kernel(acc);

    decode_sk_s_poly(s2_bytes + row * 96, s2_row);

    DR11_DISABLE_UNROLL
    for (uint32_t c = 0; c < 256; ++c) {
      const int32_t t_coeff = canonicalize(acc[c] + s2_row[c]);
      power2round(t_coeff, t1_poly[c], t0_poly[c]);
    }

    encode_pk_t1_poly(t1_poly, t1_out + r_offset * 320);
    encode_sk_t0_poly(t0_poly, t0_out + r_offset * 416);
  }

  clear_bytes(acc, sizeof(acc));
  clear_bytes(a_entry, sizeof(a_entry));
  clear_bytes(prod, sizeof(prod));
  clear_bytes(s2_row, sizeof(s2_row));
  clear_bytes(t1_poly, sizeof(t1_poly));
  clear_bytes(t0_poly, sizeof(t0_poly));
}
