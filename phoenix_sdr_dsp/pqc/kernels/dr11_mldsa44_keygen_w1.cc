// SPDX-License-Identifier: Apache-2.0
#include "dr11_mldsa44_internal.hpp"

using namespace phoenix_sdr_dsp::pqc::dr11;

extern "C" void dr11_mldsa44_keygen_w1(
    const uint8_t in_token[8452],
    uint8_t result[3892]) {

  clear_bytes(result, 3892);

  const uint32_t request_id = load_le32(in_token + 0);
  const uint8_t *rho = in_token + 4;             // 4..35 (32 B)
  const uint8_t *K = in_token + 36;              // 36..67 (32 B)
  const uint8_t *s_encoded = in_token + 68;      // 68..835 (768 B)
  const uint8_t *t1_01 = in_token + 836;         // 836..1475 (640 B)
  const uint8_t *t0_01 = in_token + 1476;        // 1476..2307 (832 B)

  // 1. Copy partial pk & sk headers to result
  uint8_t *pk_dst = result + 20;
  DR11_DISABLE_UNROLL
  for (uint32_t i = 0; i < 32; ++i) pk_dst[i] = rho[i];
  DR11_DISABLE_UNROLL
  for (uint32_t i = 0; i < 640; ++i) pk_dst[32 + i] = t1_01[i];

  uint8_t *sk_dst = result + 1332;
  DR11_DISABLE_UNROLL
  for (uint32_t i = 0; i < 32; ++i) sk_dst[i] = rho[i];
  DR11_DISABLE_UNROLL
  for (uint32_t i = 0; i < 32; ++i) sk_dst[32 + i] = K[i];
  DR11_DISABLE_UNROLL
  for (uint32_t i = 0; i < 768; ++i) sk_dst[128 + i] = s_encoded[i];
  DR11_DISABLE_UNROLL
  for (uint32_t i = 0; i < 832; ++i) sk_dst[896 + i] = t0_01[i];

  // 2. Compute Row 2 and Row 3 reusing small stack buffers
  int32_t s1_j[256];
  int32_t a_entry[256];
  int32_t s2_row[256];
  int32_t w_ntt[256];
  int32_t t1[256];
  int32_t t0[256];

  for (uint8_t row = 2; row < 4; ++row) {
    clear_bytes(w_ntt, sizeof(w_ntt));

    for (uint8_t j = 0; j < 4; ++j) {
      expand_a_matrix_entry(rho, j, row, a_entry);
      const uint8_t *s1_src = in_token + 2308 + j * 1024;
      DR11_DISABLE_UNROLL
      for (uint32_t c = 0; c < 256; ++c) {
        s1_j[c] = static_cast<int32_t>(load_le32(s1_src + c * 4));
      }
      basemul(a_entry, a_entry, s1_j);
      DR11_DISABLE_UNROLL
      for (uint32_t c = 0; c < 256; ++c) {
        w_ntt[c] += a_entry[c];
      }
    }

    invntt_kernel(w_ntt);

    const uint8_t *s2_src = in_token + 6404 + (row - 2) * 1024;
    DR11_DISABLE_UNROLL
    for (uint32_t c = 0; c < 256; ++c) {
      s2_row[c] = static_cast<int32_t>(load_le32(s2_src + c * 4));
    }

    for (uint32_t c = 0; c < 256; ++c) {
      int32_t t_coeff = canonicalize(w_ntt[c] + s2_row[c]);
      power2round(t_coeff, t1[c], t0[c]);
    }

    // Write t1_23 directly to pk_dst + 32 + 640 + (row-2)*320
    encode_pk_t1_poly(t1, pk_dst + 32 + 640 + (row - 2) * 320);
    // Write t0_23 directly to sk_dst + 896 + 832 + (row-2)*416
    encode_sk_t0_poly(t0, sk_dst + 896 + 832 + (row - 2) * 416);
  }

  // 3. Compute tr = SHAKE256(pk, 64)
  alignas(8) uint8_t state[200];
  clear_bytes(state, sizeof(state));

  uint32_t offset = 0;
  while (offset + 136 <= 1312) {
    DR11_DISABLE_UNROLL
    for (uint32_t i = 0; i < 136; ++i) state[i] ^= pk_dst[offset + i];
    phoenix_sdr_dsp::pqc::dr1::keccak_f1600(state);
    offset += 136;
  }
  const uint32_t rem = 1312 - offset;
  DR11_DISABLE_UNROLL
  for (uint32_t i = 0; i < rem; ++i) state[i] ^= pk_dst[offset + i];

  state[rem] ^= 0x1F;
  state[135] ^= 0x80;
  phoenix_sdr_dsp::pqc::dr1::keccak_f1600(state);

  // Write tr directly to sk_dst + 64
  DR11_DISABLE_UNROLL
  for (uint32_t i = 0; i < 64; ++i) sk_dst[64 + i] = state[i];
  clear_bytes(state, sizeof(state));

  // 4. Pack Header & Hardware CRC32
  store_le32(result + 0, 0x4431524Du); // b"MR1D"
  store_le32(result + 4, request_id);
  store_le32(result + 8, 0);           // Status OK
  store_le32(result + 12, 1312 | (2560 << 16));

  const uint32_t crc = compute_crc32(result + 20, 1312 + 2560);
  store_le32(result + 16, crc);

  clear_bytes(s1_j, sizeof(s1_j));
  clear_bytes(a_entry, sizeof(a_entry));
  clear_bytes(s2_row, sizeof(s2_row));
  clear_bytes(w_ntt, sizeof(w_ntt));
  clear_bytes(t1, sizeof(t1));
  clear_bytes(t0, sizeof(t0));
}
