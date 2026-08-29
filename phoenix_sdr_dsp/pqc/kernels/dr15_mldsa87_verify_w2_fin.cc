// SPDX-License-Identifier: Apache-2.0
// DR15 ML-DSA-87 Verify Worker 2: Sealed Response Envelope & CRC32
#include "dr15_mldsa87_internal.hpp"

using namespace phoenix_sdr_dsp::pqc::dr11;
using namespace phoenix_sdr_dsp::pqc::dr12;
using namespace phoenix_sdr_dsp::pqc::dr13;
using namespace phoenix_sdr_dsp::pqc::dr14;
using namespace phoenix_sdr_dsp::pqc::dr15;

extern "C" void dr15_mldsa87_verify_w2_fin(
    const uint8_t in_token[72],
    uint8_t result[64]) {

  clear_bytes(result, 64);

  const uint32_t request_id = load_le32(in_token + 0);
  const uint8_t valid = in_token[4];

  // Sealed Response Envelope (64 B):
  // [0..19]:   Header (20 B)
  // [20]:      Verdict (1 B: 1 = Valid, 0 = Invalid)
  // [21..59]:  Zero padding (39 B)
  // [60..63]:  CRC32 (4 B)
  store_le32(result + 0, 0x4434524Du); // b"MR4D"
  store_le32(result + 4, request_id);
  store_le32(result + 8, 0);           // Status OK
  store_le32(result + 12, 1);          // Payload length (1 B verdict)
  store_le32(result + 16, 0);          // CRC placeholder

  result[20] = valid;

  const uint32_t crc = compute_crc32(result + 20, 1);
  store_le32(result + 60, crc);
}
