// SPDX-License-Identifier: Apache-2.0
// DR14 ML-DSA-65 Verify Worker 2 (Finalize & Sealed Verdict)
#include "dr14_mldsa65_internal.hpp"

using namespace phoenix_sdr_dsp::pqc::dr11;
using namespace phoenix_sdr_dsp::pqc::dr12;
using namespace phoenix_sdr_dsp::pqc::dr13;
using namespace phoenix_sdr_dsp::pqc::dr14;

extern "C" void dr14_mldsa65_verify_w2_fin(
    const uint8_t in_token[72],
    uint8_t result[64]) {

  clear_bytes(result, 64);

  const uint32_t request_id = load_le32(in_token + 0);
  const uint8_t valid_flag = in_token[4];

  // Header
  store_le32(result + 0, 0x4434524Du); // b"MR4D"
  store_le32(result + 4, request_id);
  store_le32(result + 8, valid_flag ? 0 : 1); // Status 0 = Valid, 1 = Invalid
  store_le32(result + 12, 1);                 // 1 byte verdict
  store_le32(result + 16, 0);                 // CRC placeholder

  result[20] = valid_flag;

  const uint32_t crc = compute_crc32(result + 20, 1);
  store_le32(result + 16, crc);
}
