// SPDX-License-Identifier: Apache-2.0
// DR14 ML-DSA-65 KeyGen Finalize Worker (Compact Layout)
#include "dr14_mldsa65_internal.hpp"

using namespace phoenix_sdr_dsp::pqc::dr11;
using namespace phoenix_sdr_dsp::pqc::dr14;

extern "C" void dr14_mldsa65_keygen_finalize(
    const uint8_t in_token[5892],
    uint8_t result[6008]) {

  clear_bytes(result, 6008);

  const uint32_t request_id = load_le32(in_token + 0);
  const uint8_t *rho = in_token + 4;         // 32 B
  const uint8_t *K = in_token + 36;          // 32 B
  const uint8_t *s1_encoded = in_token + 68; // 640 B
  const uint8_t *s2_encoded = in_token + 708;// 768 B

  uint8_t *pk = result + 20;
  uint8_t *sk = result + 20 + 1952;

  // 1. Pack pk: rho(32 B) || t1[0..5](1920 B) = 1952 B
  DR11_DISABLE_UNROLL
  for (uint32_t i = 0; i < 32; ++i) pk[i] = rho[i];

  // Each row i in [0..5]: t1 is at offset 1476 + i * 736 (320 B), t0 is at 1476 + i * 736 + 320 (416 B)
  for (uint32_t i = 0; i < 6; ++i) {
    const uint8_t *t1_src = in_token + 1476 + i * 736;
    DR11_DISABLE_UNROLL
    for (uint32_t c = 0; c < 320; ++c) pk[32 + i * 320 + c] = t1_src[c];
  }

  // 2. Compute tr = SHAKE256(pk, 64)
  uint8_t tr[64];
  keccak_sponge(136, pk, 1952, 0x1F, tr, 64);

  // 3. Pack sk: rho(32 B) || K(32 B) || tr(64 B) || s1(640 B) || s2(768 B) || t0[0..5](2496 B) = 4032 B
  DR11_DISABLE_UNROLL
  for (uint32_t i = 0; i < 32; ++i) sk[0 + i] = rho[i];
  DR11_DISABLE_UNROLL
  for (uint32_t i = 0; i < 32; ++i) sk[32 + i] = K[i];
  DR11_DISABLE_UNROLL
  for (uint32_t i = 0; i < 64; ++i) sk[64 + i] = tr[i];
  DR11_DISABLE_UNROLL
  for (uint32_t i = 0; i < 640; ++i) sk[128 + i] = s1_encoded[i];
  DR11_DISABLE_UNROLL
  for (uint32_t i = 0; i < 768; ++i) sk[768 + i] = s2_encoded[i];

  for (uint32_t i = 0; i < 6; ++i) {
    const uint8_t *t0_src = in_token + 1476 + i * 736 + 320;
    DR11_DISABLE_UNROLL
    for (uint32_t c = 0; c < 416; ++c) sk[1536 + i * 416 + c] = t0_src[c];
  }

  // 4. Sealed Record Header + CRC32
  store_le32(result + 0, 0x4434524Du); // b"MR4D"
  store_le32(result + 4, request_id);
  store_le32(result + 8, 0);           // Status OK
  store_le32(result + 12, 5984);       // 1952 + 4032
  store_le32(result + 16, 0);          // Placeholder

  const uint32_t crc = compute_crc32(result + 20, 5984);
  store_le32(result + 16, crc);

  clear_bytes(tr, sizeof(tr));
}
