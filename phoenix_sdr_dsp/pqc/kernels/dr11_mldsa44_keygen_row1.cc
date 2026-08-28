// SPDX-License-Identifier: Apache-2.0
#include "dr11_mldsa44_internal.hpp"

using namespace phoenix_sdr_dsp::pqc::dr11;

extern "C" void dr11_mldsa44_keygen_row1(
    const uint8_t in_token[8740],
    uint8_t out_token[8452]) {

  // Copy header (req_id, rho, K, s_encoded: 836 B)
  DR11_DISABLE_UNROLL
  for (uint32_t i = 0; i < 836; ++i) out_token[i] = in_token[i];

  // Copy t1[0] (320 B) to offset 836
  DR11_DISABLE_UNROLL
  for (uint32_t i = 0; i < 320; ++i) out_token[836 + i] = in_token[836 + i];

  // Copy t0[0] (416 B) to offset 1476
  DR11_DISABLE_UNROLL
  for (uint32_t i = 0; i < 416; ++i) out_token[1476 + i] = in_token[1156 + i];

  // Copy s1_ntt (4096 B) to offset 2308
  DR11_DISABLE_UNROLL
  for (uint32_t i = 0; i < 4096; ++i) out_token[2308 + i] = in_token[1572 + i];

  // Copy s2[2..3] (2048 B) to offset 6404
  DR11_DISABLE_UNROLL
  for (uint32_t i = 0; i < 2048; ++i) out_token[6404 + i] = in_token[5668 + 1024 + i];

  const uint8_t *rho = in_token + 4;

  int32_t s1_j[256];
  int32_t a_entry[256];
  int32_t w_ntt[256];
  clear_bytes(w_ntt, sizeof(w_ntt));

  for (uint8_t j = 0; j < 4; ++j) {
    expand_a_matrix_entry(rho, j, 1, a_entry);
    const uint8_t *src = in_token + 1572 + j * 1024;
    DR11_DISABLE_UNROLL
    for (uint32_t c = 0; c < 256; ++c) {
      s1_j[c] = static_cast<int32_t>(load_le32(src + c * 4));
    }
    basemul(a_entry, a_entry, s1_j);
    DR11_DISABLE_UNROLL
    for (uint32_t c = 0; c < 256; ++c) {
      w_ntt[c] += a_entry[c];
    }
  }

  invntt_kernel(w_ntt);

  int32_t s2_1[256];
  const uint8_t *s2_src = in_token + 5668;
  DR11_DISABLE_UNROLL
  for (uint32_t c = 0; c < 256; ++c) {
    s2_1[c] = static_cast<int32_t>(load_le32(s2_src + c * 4));
  }

  int32_t t1[256];
  int32_t t0[256];
  for (uint32_t c = 0; c < 256; ++c) {
    int32_t t_coeff = canonicalize(w_ntt[c] + s2_1[c]);
    power2round(t_coeff, t1[c], t0[c]);
  }

  encode_pk_t1_poly(t1, out_token + 836 + 320);
  encode_sk_t0_poly(t0, out_token + 1476 + 416);

  clear_bytes(s1_j, sizeof(s1_j));
  clear_bytes(a_entry, sizeof(a_entry));
  clear_bytes(s2_1, sizeof(s2_1));
  clear_bytes(w_ntt, sizeof(w_ntt));
  clear_bytes(t1, sizeof(t1));
  clear_bytes(t0, sizeof(t0));
}
