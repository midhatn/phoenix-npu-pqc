// SPDX-License-Identifier: Apache-2.0
// DR15 ML-DSA-87 KeyGen Worker 3 (Finalize, TR hash & Sealed Result)
#include "dr15_mldsa87_internal.hpp"

using namespace phoenix_sdr_dsp::pqc::dr11;
using namespace phoenix_sdr_dsp::pqc::dr12;
using namespace phoenix_sdr_dsp::pqc::dr13;
using namespace phoenix_sdr_dsp::pqc::dr14;
using namespace phoenix_sdr_dsp::pqc::dr15;

extern "C" void dr15_mldsa87_keygen_finalize(
    const uint8_t in_token[14592],
    uint8_t result[7512]) {

  clear_bytes(result, 7512);

  const uint32_t request_id = load_le32(in_token + 0);
  const uint8_t *rho = in_token + 4;
  const uint8_t *k_key = in_token + 36;
  const uint8_t *s1_bytes = in_token + 68;    // 672 B (7 * 96)
  const uint8_t *s2_bytes = in_token + 740;   // 768 B (8 * 96)
  const uint8_t *t1_bytes = in_token + 8676;  // 2560 B (8 * 320)
  const uint8_t *t0_bytes = in_token + 11236; // 3328 B (8 * 416)

  // 1. Build pk (2592 B)
  uint8_t *pk = result + 20;
  DR11_DISABLE_UNROLL
  for (uint32_t i = 0; i < 32; ++i) pk[i] = rho[i];
  DR11_DISABLE_UNROLL
  for (uint32_t i = 0; i < 2560; ++i) pk[32 + i] = t1_bytes[i];

  // 2. Compute tr = H(pk, 64)
  uint8_t tr[64];
  keccak_sponge(136, pk, 2592, 0x1F, tr, 64);

  // 3. Build sk (4896 B)
  uint8_t *sk = result + 2612;
  DR11_DISABLE_UNROLL
  for (uint32_t i = 0; i < 32; ++i) sk[0 + i] = rho[i];
  DR11_DISABLE_UNROLL
  for (uint32_t i = 0; i < 32; ++i) sk[32 + i] = k_key[i];
  DR11_DISABLE_UNROLL
  for (uint32_t i = 0; i < 64; ++i) sk[64 + i] = tr[i];
  DR11_DISABLE_UNROLL
  for (uint32_t i = 0; i < 672; ++i) sk[128 + i] = s1_bytes[i];
  DR11_DISABLE_UNROLL
  for (uint32_t i = 0; i < 768; ++i) sk[800 + i] = s2_bytes[i];
  DR11_DISABLE_UNROLL
  for (uint32_t i = 0; i < 3328; ++i) sk[1568 + i] = t0_bytes[i];

  // 4. Sealed Header (20 B)
  store_le32(result + 0, 0x4434524Du); // b"MR4D"
  store_le32(result + 4, request_id);
  store_le32(result + 8, 0);           // Status OK
  store_le32(result + 12, 7488);       // Payload length (pk 2592 + sk 4896)
  store_le32(result + 16, 0);          // CRC placeholder

  const uint32_t crc = compute_crc32(result + 20, 7488);
  store_le32(result + 7508, crc);

  clear_bytes(tr, sizeof(tr));
}
