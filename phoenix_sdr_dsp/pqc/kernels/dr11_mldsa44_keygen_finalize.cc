// SPDX-License-Identifier: Apache-2.0
#include "dr11_mldsa44_internal.hpp"

using namespace phoenix_sdr_dsp::pqc::dr11;

extern "C" void dr11_mldsa44_keygen_finalize(
    const uint8_t in_token[3780],
    uint8_t result[3892]) {

  clear_bytes(result, 3892);

  const uint32_t request_id = load_le32(in_token + 0);
  const uint8_t *rho = in_token + 4;             // 4..35 (32 B)
  const uint8_t *K = in_token + 36;              // 36..67 (32 B)
  const uint8_t *s_encoded = in_token + 68;      // 68..835 (768 B)
  const uint8_t *t1_encoded = in_token + 836;    // 836..2115 (1280 B)
  const uint8_t *t0_encoded = in_token + 2116;   // 2116..3779 (1664 B)

  // 1. Assemble pk (1312 B) at result + 20
  uint8_t *pk_dst = result + 20;
  DR11_DISABLE_UNROLL
  for (uint32_t i = 0; i < 32; ++i) pk_dst[i] = rho[i];
  DR11_DISABLE_UNROLL
  for (uint32_t i = 0; i < 1280; ++i) pk_dst[32 + i] = t1_encoded[i];

  // 2. Compute tr = SHAKE256(pk, 64)
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

  uint8_t tr[64];
  DR11_DISABLE_UNROLL
  for (uint32_t i = 0; i < 64; ++i) tr[i] = state[i];
  clear_bytes(state, sizeof(state));

  // 3. Assemble sk (2560 B) at result + 20 + 1312 = result + 1332
  uint8_t *sk_dst = result + 1332;
  // rho (32 B)
  DR11_DISABLE_UNROLL
  for (uint32_t i = 0; i < 32; ++i) sk_dst[i] = rho[i];
  // K (32 B)
  DR11_DISABLE_UNROLL
  for (uint32_t i = 0; i < 32; ++i) sk_dst[32 + i] = K[i];
  // tr (64 B)
  DR11_DISABLE_UNROLL
  for (uint32_t i = 0; i < 64; ++i) sk_dst[64 + i] = tr[i];
  // s_encoded (768 B)
  DR11_DISABLE_UNROLL
  for (uint32_t i = 0; i < 768; ++i) sk_dst[128 + i] = s_encoded[i];
  // t0_encoded (1664 B)
  DR11_DISABLE_UNROLL
  for (uint32_t i = 0; i < 1664; ++i) sk_dst[896 + i] = t0_encoded[i];

  // 4. Pack Header & Hardware CRC32
  store_le32(result + 0, 0x4431524Du); // b"MR1D"
  store_le32(result + 4, request_id);
  store_le32(result + 8, 0);           // Status OK
  store_le32(result + 12, 1312 | (2560 << 16));

  const uint32_t crc = compute_crc32(result + 20, 1312 + 2560);
  store_le32(result + 16, crc);

  clear_bytes(tr, sizeof(tr));
}
