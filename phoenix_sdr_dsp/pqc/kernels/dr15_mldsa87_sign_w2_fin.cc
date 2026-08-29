// SPDX-License-Identifier: Apache-2.0
// DR15 ML-DSA-87 Sign Worker 2: SampleInBall, z Evaluation & Sealed Result
#include "dr15_mldsa87_internal.hpp"

using namespace phoenix_sdr_dsp::pqc::dr11;
using namespace phoenix_sdr_dsp::pqc::dr12;
using namespace phoenix_sdr_dsp::pqc::dr13;
using namespace phoenix_sdr_dsp::pqc::dr14;
using namespace phoenix_sdr_dsp::pqc::dr15;

extern "C" void dr15_mldsa87_sign_w2_fin(
    const uint8_t in_token[14500],
    uint8_t result[4656]) {

  clear_bytes(result, 4656);

  const uint32_t request_id = load_le32(in_token + 0);
  const uint8_t *c_tilde = in_token + 4;
  const int32_t *y_polys = reinterpret_cast<const int32_t *>(in_token + 36);
  const int32_t *s1_hat = reinterpret_cast<const int32_t *>(in_token + 7204);

  // 1. Copy c_tilde (32 B) -> result[20..51]
  uint8_t *sig = result + 20;
  DR11_DISABLE_UNROLL
  for (uint32_t i = 0; i < 32; ++i) sig[i] = c_tilde[i];

  // 2. c = SampleInBall87(c_tilde) -> NTT(c)
  int32_t c_ntt[256];
  int32_t poly[256];
  sample_in_ball87(c_tilde, c_ntt);
  ntt_kernel(c_ntt);

  // 3. Compute and encode z = y + INTT(c * s1) (7 polys * 640 B = 4480 B) -> sig[32..4511]
  for (uint32_t j = 0; j < 7; ++j) {
    basemul(poly, c_ntt, s1_hat + j * 256);
    invntt_kernel(poly);

    uint8_t *dst = sig + 32 + j * 640;
    const int32_t *y_src = y_polys + j * 256;
    for (uint32_t i = 0; i < 128; ++i) {
      const int32_t z0 = canonicalize(y_src[2 * i + 0] + poly[2 * i + 0]);
      const int32_t z1 = canonicalize(y_src[2 * i + 1] + poly[2 * i + 1]);

      const uint32_t v0 = static_cast<uint32_t>(kGamma1_87 - (z0 <= kGamma1_87 ? z0 : z0 - kQ));
      const uint32_t v1 = static_cast<uint32_t>(kGamma1_87 - (z1 <= kGamma1_87 ? z1 : z1 - kQ));

      dst[i * 5 + 0] = static_cast<uint8_t>(v0 & 0xFF);
      dst[i * 5 + 1] = static_cast<uint8_t>((v0 >> 8) & 0xFF);
      dst[i * 5 + 2] = static_cast<uint8_t>((v0 >> 16) | ((v1 & 0x0F) << 4));
      dst[i * 5 + 3] = static_cast<uint8_t>((v1 >> 4) & 0xFF);
      dst[i * 5 + 4] = static_cast<uint8_t>((v1 >> 12) & 0xFF);
    }
  }

  // 4. Hints are initialized to zero (83 bytes)

  // 5. Sealed Response Header (20 B)
  store_le32(result + 0, 0x4434524Du); // b"MR4D"
  store_le32(result + 4, request_id);
  store_le32(result + 8, 0);           // Status OK
  store_le32(result + 12, 4627);       // Signature length
  store_le32(result + 16, 0);          // CRC placeholder

  const uint32_t crc = compute_crc32(result + 20, 4627);
  store_le32(result + 4648, crc);

  clear_bytes(c_ntt, sizeof(c_ntt));
  clear_bytes(poly, sizeof(poly));
}
