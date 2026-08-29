// SPDX-License-Identifier: Apache-2.0
// DR15: NIST FIPS 204 ML-DSA-87 Internal Definitions & Primitives
#ifndef PHOENIX_SDR_DSP_PQC_KERNELS_DR15_MLDSA87_INTERNAL_HPP_
#define PHOENIX_SDR_DSP_PQC_KERNELS_DR15_MLDSA87_INTERNAL_HPP_

#include "dr11_mldsa44_internal.hpp"
#include "dr12_mldsa44_sign_internal.hpp"
#include "dr13_mldsa44_verify_internal.hpp"
#include "dr14_mldsa65_internal.hpp"

namespace phoenix_sdr_dsp::pqc::dr15 {

using namespace phoenix_sdr_dsp::pqc::dr11;
using namespace phoenix_sdr_dsp::pqc::dr12;
using namespace phoenix_sdr_dsp::pqc::dr13;
using namespace phoenix_sdr_dsp::pqc::dr14;

// FIPS 204 ML-DSA-87 Parameters
constexpr uint8_t kK87 = 8;
constexpr uint8_t kL87 = 7;
constexpr int32_t kEta87 = 2;
constexpr int32_t kTau87 = 60;
constexpr int32_t kBeta87 = 120;
constexpr int32_t kGamma1_87 = 524288;  // 2^19
constexpr int32_t kGamma2_87 = 261888;  // (q - 1) / 32
constexpr int32_t kAlpha87 = 523776;   // 2 * gamma2
constexpr int32_t kOmega87 = 75;
constexpr int32_t kM87 = 16;           // (q - 1) / alpha = 16

// 1. Sample Mask Polynomial y for ML-DSA-87 (20 bits per coeff -> 640 bytes)
__attribute__((noinline)) static void sample_mask_poly_87(
    const uint8_t rho_pp[64],
    uint16_t idx,
    int32_t y[256]) {

  alignas(8) uint8_t state[200];
  clear_bytes(state, sizeof(state));

  DR11_DISABLE_UNROLL
  for (uint32_t i = 0; i < 64; ++i) state[i] = rho_pp[i];
  state[64] = static_cast<uint8_t>(idx & 0xFF);
  state[65] = static_cast<uint8_t>((idx >> 8) & 0xFF);
  state[66] ^= 0x1F;
  state[135] ^= 0x80;
  phoenix_sdr_dsp::pqc::dr1::keccak_f1600(state);

  uint8_t stream[640];
  uint32_t stream_pos = 0;

  while (stream_pos + 136 <= 640) {
    DR11_DISABLE_UNROLL
    for (uint32_t i = 0; i < 136; ++i) stream[stream_pos + i] = state[i];
    phoenix_sdr_dsp::pqc::dr1::keccak_f1600(state);
    stream_pos += 136;
  }
  const uint32_t rem = 640 - stream_pos;
  DR11_DISABLE_UNROLL
  for (uint32_t i = 0; i < rem; ++i) stream[stream_pos + i] = state[i];
  clear_bytes(state, sizeof(state));

  DR11_DISABLE_UNROLL
  for (uint32_t i = 0; i < 128; ++i) {
    const uint8_t *b = stream + i * 5;
    const uint32_t b0 = b[0], b1 = b[1], b2 = b[2], b3 = b[3], b4 = b[4];

    const uint32_t v0 = b0 | (b1 << 8) | ((b2 & 0x0F) << 16);
    const uint32_t v1 = (b2 >> 4) | (b3 << 4) | (b4 << 12);

    y[i * 2 + 0] = canonicalize(kGamma1_87 - static_cast<int32_t>(v0));
    y[i * 2 + 1] = canonicalize(kGamma1_87 - static_cast<int32_t>(v1));
  }
}

// 2. SampleInBall for ML-DSA-87 (tau = 60)
__attribute__((noinline)) static void sample_in_ball87(
    const uint8_t c_tilde[32], int32_t c_poly[256]) {

  clear_bytes(c_poly, 256 * sizeof(int32_t));

  alignas(8) uint8_t state[200];
  clear_bytes(state, sizeof(state));

  DR11_DISABLE_UNROLL
  for (uint32_t i = 0; i < 32; ++i) state[i] = c_tilde[i];
  state[32] ^= 0x1F;
  state[135] ^= 0x80;
  phoenix_sdr_dsp::pqc::dr1::keccak_f1600(state);

  uint64_t signs = 0;
  DR11_DISABLE_UNROLL
  for (uint32_t i = 0; i < 8; ++i) {
    signs |= static_cast<uint64_t>(state[i]) << (i * 8);
  }

  uint32_t state_pos = 8;
  for (uint32_t i = 256 - kTau87; i < 256; ++i) {
    uint32_t j;
    while (true) {
      if (state_pos >= 136) {
        phoenix_sdr_dsp::pqc::dr1::keccak_f1600(state);
        state_pos = 0;
      }
      const uint32_t b = state[state_pos++];
      if (b <= i) {
        j = b;
        break;
      }
    }
    c_poly[i] = c_poly[j];
    c_poly[j] = (signs & 1) ? (kQ - 1) : 1;
    signs >>= 1;
  }
  clear_bytes(state, sizeof(state));
}

// 3. encode_hints for ML-DSA-87 (omega = 75, k = 8 -> 83 bytes)
static inline void encode_hints87(
    const uint8_t h[8][256], uint8_t out[83]) {

  clear_bytes(out, 83);
  uint32_t pos = 0;

  for (uint32_t i = 0; i < 8; ++i) {
    for (uint32_t j = 0; j < 256; ++j) {
      if (h[i][j] != 0 && pos < 75) {
        out[pos++] = static_cast<uint8_t>(j);
      }
    }
    out[75 + i] = static_cast<uint8_t>(pos);
  }
}

// 4. decode_hints for ML-DSA-87 (83 bytes: 75 hints capacity + 8 endpoints)
__attribute__((noinline)) static bool decode_hints87_and_check(
    const uint8_t in[83], uint8_t h[8][256]) {

  clear_bytes(h, 8 * 256);

  uint32_t k = 0;
  for (uint32_t i = 0; i < 8; ++i) {
    const uint32_t end = in[75 + i];
    if (end < k || end > 75) return false;
    for (uint32_t j = k; j < end; ++j) {
      const uint32_t idx = in[j];
      h[i][idx] = 1;
    }
    k = end;
  }
  return in[75 + 7] <= 75;
}

} // namespace phoenix_sdr_dsp::pqc::dr15

#endif // PHOENIX_SDR_DSP_PQC_KERNELS_DR15_MLDSA87_INTERNAL_HPP_
