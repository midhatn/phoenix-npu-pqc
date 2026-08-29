// SPDX-License-Identifier: Apache-2.0
// DR14 ML-DSA-65 Sign Worker 2 (Encode, Seal & Hardware CRC32)
#include "dr14_mldsa65_internal.hpp"

using namespace phoenix_sdr_dsp::pqc::dr11;
using namespace phoenix_sdr_dsp::pqc::dr12;
using namespace phoenix_sdr_dsp::pqc::dr14;

extern "C" void dr14_mldsa65_sign_w2_fin(
    const uint8_t in_token[12836],
    uint8_t result[3336]) {

  clear_bytes(result, 3336);

  const uint32_t request_id = load_le32(in_token + 0);
  const uint8_t *c_tilde = in_token + 4;
  const int32_t *z_plain = reinterpret_cast<const int32_t *>(in_token + 36);
  const int32_t *h_plain = reinterpret_cast<const int32_t *>(in_token + 5156);

  uint8_t *sig = result + 20;

  // 1. Pack c_tilde (32 B)
  DR11_DISABLE_UNROLL
  for (uint32_t i = 0; i < 32; ++i) sig[0 + i] = c_tilde[i];

  // 2. Pack z (5 * 640 = 3200 B)
  for (uint32_t j = 0; j < 5; ++j) {
    encode_z_poly65(z_plain + j * 256, sig + 32 + j * 640);
  }

  // 3. Pack hints (77 B)
  int32_t h_arr[6][256];
  for (uint32_t i = 0; i < 6; ++i) {
    DR11_DISABLE_UNROLL
    for (uint32_t c = 0; c < 256; ++c) h_arr[i][c] = h_plain[i * 256 + c];
  }
  encode_hints65(h_arr, sig + 3232);

  // 4. Header + CRC32
  store_le32(result + 0, 0x4434524Du); // b"MR4D"
  store_le32(result + 4, request_id);
  store_le32(result + 8, 0);           // Status OK
  store_le32(result + 12, 3309);       // Signature length
  store_le32(result + 16, 0);          // Placeholder

  const uint32_t crc = compute_crc32(sig, 3309);
  store_le32(result + 16, crc);

  clear_bytes(h_arr, sizeof(h_arr));
}
