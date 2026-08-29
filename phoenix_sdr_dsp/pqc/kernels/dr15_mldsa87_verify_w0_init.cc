// SPDX-License-Identifier: Apache-2.0
// DR15 ML-DSA-87 Verify Worker 0: Unpack, Norm Checks, SampleInBall & NTT Precomputations
#include "dr15_mldsa87_internal.hpp"

using namespace phoenix_sdr_dsp::pqc::dr11;
using namespace phoenix_sdr_dsp::pqc::dr12;
using namespace phoenix_sdr_dsp::pqc::dr13;
using namespace phoenix_sdr_dsp::pqc::dr14;
using namespace phoenix_sdr_dsp::pqc::dr15;

extern "C" void dr15_mldsa87_verify_w0_init(
    const uint8_t req_in[7300],
    const uint8_t descriptor[16],
    uint8_t out_token[19000]) {

  clear_bytes(out_token, 19000);

  const uint32_t request_id = load_le32(descriptor + 8);
  store_le32(out_token + 0, request_id);

  const uint8_t *rho = req_in + 0;
  const uint8_t *t1_bytes = req_in + 32;
  const uint8_t *mu = req_in + 2592;
  const uint8_t *c_tilde = req_in + 2656;
  const uint8_t *z_bytes = req_in + 2688;
  const uint8_t *h_bytes = req_in + 7168;

  DR11_DISABLE_UNROLL
  for (uint32_t i = 0; i < 32; ++i) out_token[4 + i] = rho[i];
  DR11_DISABLE_UNROLL
  for (uint32_t i = 0; i < 64; ++i) out_token[36 + i] = mu[i];
  DR11_DISABLE_UNROLL
  for (uint32_t i = 0; i < 32; ++i) out_token[100 + i] = c_tilde[i];

  bool valid = true;

  // 1. Decode & norm-check z (7 polys -> out_token[132..7299])
  int32_t poly[256];
  int32_t *z_hat = reinterpret_cast<int32_t *>(out_token + 132);
  for (uint32_t j = 0; j < 7; ++j) {
    if (!decode_z_poly65_and_check(z_bytes + j * 640, poly, kGamma1_87 - kBeta87)) valid = false;
    DR11_DISABLE_UNROLL
    for (uint32_t c = 0; c < 256; ++c) poly[c] = canonicalize(poly[c]);
    ntt_kernel(poly);
    DR11_DISABLE_UNROLL
    for (uint32_t c = 0; c < 256; ++c) z_hat[j * 256 + c] = poly[c];
  }

  // 2. Decode hints (83 B -> out_token[7300..9347])
  uint8_t h[8][256];
  if (!decode_hints87_and_check(h_bytes, h)) valid = false;
  uint8_t *h_dst = out_token + 7300;
  for (uint32_t r = 0; r < 8; ++r) {
    for (uint32_t c = 0; c < 256; ++c) {
      h_dst[r * 256 + c] = h[r][c];
    }
  }

  // 3. Decode t1 * 2^d -> NTT(t1 * 2^d) (8 polys -> out_token[9348..17539])
  int32_t *t1_hat = reinterpret_cast<int32_t *>(out_token + 9348);
  for (uint32_t r = 0; r < 8; ++r) {
    decode_t1_poly(t1_bytes + r * 320, poly);
    ntt_kernel(poly);
    DR11_DISABLE_UNROLL
    for (uint32_t c = 0; c < 256; ++c) t1_hat[r * 256 + c] = poly[c];
  }

  // 4. SampleInBall87(c_tilde) -> NTT(c) -> out_token[17540..18563]
  int32_t *c_hat = reinterpret_cast<int32_t *>(out_token + 17540);
  sample_in_ball87(c_tilde, poly);
  ntt_kernel(poly);
  DR11_DISABLE_UNROLL
  for (uint32_t c = 0; c < 256; ++c) c_hat[c] = poly[c];

  out_token[18564] = valid ? 1 : 0;

  clear_bytes(poly, sizeof(poly));
}
