// SPDX-License-Identifier: Apache-2.0
// DR14 ML-DSA-65 KeyGen Noise Worker
// Ingests 32-byte seed -> H(seed||k||ell) -> rho, rho_prime, K -> samples s1[5] and s2[6] with eta=4
#include "dr14_mldsa65_internal.hpp"

using namespace phoenix_sdr_dsp::pqc::dr11;
using namespace phoenix_sdr_dsp::pqc::dr14;

extern "C" void dr14_mldsa65_keygen_noise(
    const uint8_t seed_in[32],
    const uint8_t descriptor[16],
    uint8_t out_token[12800]) {

  clear_bytes(out_token, 12800);

  const uint32_t request_id = load_le32(descriptor + 8);
  store_le32(out_token + 0, request_id);

  // 1. Expand seed || k(6) || ell(5) via SHAKE256(128 bytes)
  uint8_t seed_buf[34];
  DR11_DISABLE_UNROLL
  for (uint32_t i = 0; i < 32; ++i) seed_buf[i] = seed_in[i];
  seed_buf[32] = 6;
  seed_buf[33] = 5;

  uint8_t seed_expanded[128];
  keccak_sponge(136, seed_buf, 34, 0x1F, seed_expanded, 128);

  const uint8_t *rho = seed_expanded + 0;        // 32 B
  const uint8_t *rho_prime = seed_expanded + 32;  // 64 B
  const uint8_t *K = seed_expanded + 96;          // 32 B

  // Store rho (32 B) -> [4..35]
  DR11_DISABLE_UNROLL
  for (uint32_t i = 0; i < 32; ++i) out_token[4 + i] = rho[i];

  // Store K (32 B) -> [36..67]
  DR11_DISABLE_UNROLL
  for (uint32_t i = 0; i < 32; ++i) out_token[36 + i] = K[i];

  // Token Layout:
  // [0..3]     request_id (4 B)
  // [4..35]    rho (32 B)
  // [36..67]   K (32 B)
  // [68..707]  s1_encoded: 5 * 128 = 640 B
  // [708..1475] s2_encoded: 6 * 128 = 768 B
  // [1476..6595] s1_hat: 5 * 256 * 4 = 5120 B
  // [6596..12739] s2_plain: 6 * 256 * 4 = 6144 B

  // 2. Sample s1[0..4] (5 polys)
  int32_t s_poly[256];
  for (uint16_t j = 0; j < 5; ++j) {
    sample_bounded_eta4(rho_prime, j, s_poly);
    encode_s_poly_eta4(s_poly, out_token + 68 + j * 128);

    // Compute NTT(s1[j])
    int32_t s_ntt[256];
    DR11_DISABLE_UNROLL
    for (uint32_t c = 0; c < 256; ++c) s_ntt[c] = s_poly[c];
    ntt_kernel(s_ntt);

    uint8_t *s1_hat_dst = out_token + 1476 + j * 1024;
    DR11_DISABLE_UNROLL
    for (uint32_t c = 0; c < 256; ++c) {
      store_le32(s1_hat_dst + c * 4, static_cast<uint32_t>(s_ntt[c]));
    }
  }

  // 3. Sample s2[0..5] (6 polys)
  for (uint16_t i = 0; i < 6; ++i) {
    sample_bounded_eta4(rho_prime, 5 + i, s_poly);
    encode_s_poly_eta4(s_poly, out_token + 708 + i * 128);

    uint8_t *s2_dst = out_token + 6596 + i * 1024;
    DR11_DISABLE_UNROLL
    for (uint32_t c = 0; c < 256; ++c) {
      store_le32(s2_dst + c * 4, static_cast<uint32_t>(s_poly[c]));
    }
  }

  clear_bytes(s_poly, sizeof(s_poly));
  clear_bytes(seed_buf, sizeof(seed_buf));
  clear_bytes(seed_expanded, sizeof(seed_expanded));
}
