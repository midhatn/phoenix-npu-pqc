// SPDX-License-Identifier: Apache-2.0
#ifndef PHOENIX_SDR_DSP_PQC_KERNELS_DR14_MLDSA65_INTERNAL_HPP_
#define PHOENIX_SDR_DSP_PQC_KERNELS_DR14_MLDSA65_INTERNAL_HPP_

#include "dr11_mldsa44_internal.hpp"
#include "dr12_mldsa44_sign_internal.hpp"
#include "dr13_mldsa44_verify_internal.hpp"

namespace phoenix_sdr_dsp::pqc::dr14 {

using namespace phoenix_sdr_dsp::pqc::dr11;
using namespace phoenix_sdr_dsp::pqc::dr12;
using namespace phoenix_sdr_dsp::pqc::dr13;

constexpr int32_t kK65 = 6;
constexpr int32_t kL65 = 5;
constexpr int32_t kEta65 = 4;
constexpr int32_t kGamma1_65 = 524288; // 2^19
constexpr int32_t kGamma2_65 = 261888; // (q - 1) / 32
constexpr int32_t kBeta65 = 196;       // tau * eta = 49 * 4
constexpr int32_t kTau65 = 49;
constexpr int32_t kOmega65 = 55;
constexpr int32_t kAlpha65 = 523776;   // 2 * gamma2
constexpr int32_t kM65 = 16;           // (q - 1) / alpha = 16

// 1. SampleBoundedEta4 (FIPS 204 Alg 27)
__attribute__((noinline)) static void sample_bounded_eta4(
    const uint8_t sigma[64], uint16_t nonce, int32_t out[256]) {

  uint8_t in_buf[66];
  DR11_DISABLE_UNROLL
  for (uint32_t i = 0; i < 64; ++i) in_buf[i] = sigma[i];
  in_buf[64] = static_cast<uint8_t>(nonce & 0xFF);
  in_buf[65] = static_cast<uint8_t>((nonce >> 8) & 0xFF);

  uint8_t stream[272];
  keccak_sponge(136, in_buf, 66, 0x1F, stream, 272);

  uint32_t accepted = 0;
  uint32_t pos = 0;
  while (accepted < 256) {
    if (pos >= 272) pos = 0;
    const uint32_t b = stream[pos++];
    const uint32_t t0 = b & 0x0F;
    const uint32_t t1 = b >> 4;
    if (t0 < 9 && accepted < 256) {
      out[accepted++] = canonicalize(4 - static_cast<int32_t>(t0));
    }
    if (t1 < 9 && accepted < 256) {
      out[accepted++] = canonicalize(4 - static_cast<int32_t>(t1));
    }
  }
}

// 2. SampleMask for ML-DSA-65 (gamma1 = 2^19, 20 bits per coeff, 640 bytes total)
__attribute__((noinline)) static void sample_mask_poly_65(
    const uint8_t rho_pp[64], uint16_t idx, int32_t y[256]) {

  uint8_t in_buf[66];
  DR11_DISABLE_UNROLL
  for (uint32_t i = 0; i < 64; ++i) in_buf[i] = rho_pp[i];
  in_buf[64] = static_cast<uint8_t>(idx & 0xFF);
  in_buf[65] = static_cast<uint8_t>((idx >> 8) & 0xFF);

  uint8_t stream[640];
  keccak_sponge(136, in_buf, 66, 0x1F, stream, 640);

  // 5 bytes = 2 coefficients of 20 bits each
  DR11_DISABLE_UNROLL
  for (uint32_t i = 0; i < 128; ++i) {
    const uint8_t *b = stream + i * 5;
    const uint32_t b0 = b[0], b1 = b[1], b2 = b[2], b3 = b[3], b4 = b[4];

    const uint32_t v0 = b0 | (b1 << 8) | ((b2 & 0x0F) << 16);
    const uint32_t v1 = (b2 >> 4) | (b3 << 4) | (b4 << 12);

    y[i * 2 + 0] = canonicalize(kGamma1_65 - static_cast<int32_t>(v0));
    y[i * 2 + 1] = canonicalize(kGamma1_65 - static_cast<int32_t>(v1));
  }
}

// 3. Decompose for ML-DSA-65 (alpha = 523776)
static inline void decompose65(int32_t r, int32_t &r1, int32_t &r0) {
  int32_t rp = canonicalize(r);
  int32_t r0_cand = rp % kAlpha65;
  if (r0_cand > (kAlpha65 >> 1)) {
    r0_cand -= kAlpha65;
  }
  if (rp - r0_cand == kQ - 1) {
    r1 = 0;
    r0 = r0_cand - 1;
  } else {
    r1 = (rp - r0_cand) / kAlpha65;
    r0 = r0_cand;
  }
}

// 4. UseHint for ML-DSA-65
static inline int32_t use_hint65(uint8_t h, int32_t r) {
  int32_t r1, r0;
  decompose65(r, r1, r0);
  if (h == 0) return r1;
  if (r0 > 0) {
    return (r1 + 1 == kM65) ? 0 : (r1 + 1);
  }
  return (r1 == 0) ? (kM65 - 1) : (r1 - 1);
}

// 5. MakeHint for ML-DSA-65
static inline int32_t make_hint65(int32_t z, int32_t r) {
  int32_t r1, r0, r_plus_z_1, r_plus_z_0;
  decompose65(r, r1, r0);
  decompose65(r + z, r_plus_z_1, r_plus_z_0);
  return r1 != r_plus_z_1 ? 1 : 0;
}

// 6. w1Encode for ML-DSA-65: 4 bits per coeff (128 bytes per poly)
static inline void encode_w1_poly65(const int32_t w1[256], uint8_t out[128]) {
  DR11_DISABLE_UNROLL
  for (uint32_t i = 0; i < 128; ++i) {
    const uint32_t a0 = static_cast<uint32_t>(w1[i * 2 + 0]) & 0x0F;
    const uint32_t a1 = static_cast<uint32_t>(w1[i * 2 + 1]) & 0x0F;
    out[i] = static_cast<uint8_t>(a0 | (a1 << 4));
  }
}

// 7. zEncode for ML-DSA-65: 20 bits per coeff (640 bytes per poly)
static inline void encode_z_poly65(const int32_t z[256], uint8_t out[640]) {
  DR11_DISABLE_UNROLL
  for (uint32_t i = 0; i < 128; ++i) {
    const uint32_t v0 = static_cast<uint32_t>(kGamma1_65 - to_signed_coeff(z[i * 2 + 0])) & 0xFFFFF;
    const uint32_t v1 = static_cast<uint32_t>(kGamma1_65 - to_signed_coeff(z[i * 2 + 1])) & 0xFFFFF;

    out[i * 5 + 0] = static_cast<uint8_t>(v0);
    out[i * 5 + 1] = static_cast<uint8_t>(v0 >> 8);
    out[i * 5 + 2] = static_cast<uint8_t>((v0 >> 16) | (v1 << 4));
    out[i * 5 + 3] = static_cast<uint8_t>(v1 >> 4);
    out[i * 5 + 4] = static_cast<uint8_t>(v1 >> 12);
  }
}

// 8. zDecode for ML-DSA-65
__attribute__((noinline)) static bool decode_z_poly65_and_check(
    const uint8_t in[640], int32_t z[256], int32_t bound) {

  DR11_DISABLE_UNROLL
  for (uint32_t i = 0; i < 128; ++i) {
    const uint8_t *b = in + i * 5;
    const uint32_t b0 = b[0], b1 = b[1], b2 = b[2], b3 = b[3], b4 = b[4];

    const uint32_t v0 = b0 | (b1 << 8) | ((b2 & 0x0F) << 16);
    const uint32_t v1 = (b2 >> 4) | (b3 << 4) | (b4 << 12);

    const int32_t z0 = kGamma1_65 - static_cast<int32_t>(v0);
    const int32_t z1 = kGamma1_65 - static_cast<int32_t>(v1);

    const int32_t az0 = z0 < 0 ? -z0 : z0;
    const int32_t az1 = z1 < 0 ? -z1 : z1;

    if (az0 >= bound || az1 >= bound) return false;

    z[i * 2 + 0] = canonicalize(z0);
    z[i * 2 + 1] = canonicalize(z1);
  }
  return true;
}

// 9. SampleInBall for ML-DSA-65 (tau = 49, c_tilde = 48 bytes)
__attribute__((noinline)) static void sample_in_ball65(
    const uint8_t c_tilde[48], int32_t c_poly[256]) {

  clear_bytes(c_poly, 256 * sizeof(int32_t));

  alignas(8) uint8_t state[200];
  clear_bytes(state, sizeof(state));

  DR11_DISABLE_UNROLL
  for (uint32_t i = 0; i < 48; ++i) state[i] = c_tilde[i];
  state[48] ^= 0x1F;
  state[135] ^= 0x80;
  phoenix_sdr_dsp::pqc::dr1::keccak_f1600(state);

  uint64_t signs = 0;
  DR11_DISABLE_UNROLL
  for (uint32_t i = 0; i < 8; ++i) {
    signs |= static_cast<uint64_t>(state[i]) << (i * 8);
  }

  uint32_t state_pos = 8;
  for (uint32_t i = 256 - kTau65; i < 256; ++i) {
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

// 10. encode_s_poly for eta=4 (128 bytes per poly)
static inline void encode_s_poly_eta4(const int32_t s[256], uint8_t out[128]) {
  DR11_DISABLE_UNROLL
  for (uint32_t i = 0; i < 128; ++i) {
    const uint32_t a0 = static_cast<uint32_t>(4 - to_signed_coeff(s[i * 2 + 0])) & 0x0F;
    const uint32_t a1 = static_cast<uint32_t>(4 - to_signed_coeff(s[i * 2 + 1])) & 0x0F;
    out[i] = static_cast<uint8_t>(a0 | (a1 << 4));
  }
}

// 11. decode_s_poly for eta=4 (128 bytes -> 256 coeffs)
__attribute__((noinline)) static void decode_s_poly_eta4(const uint8_t in[128], int32_t s[256]) {
  DR11_DISABLE_UNROLL
  for (uint32_t i = 0; i < 128; ++i) {
    const uint32_t b = in[i];
    s[i * 2 + 0] = canonicalize(4 - static_cast<int32_t>(b & 0x0F));
    s[i * 2 + 1] = canonicalize(4 - static_cast<int32_t>(b >> 4));
  }
}

// 12. encode_hints for ML-DSA-65 (61 bytes: 55 hints capacity + 6 endpoints)
static inline void encode_hints65(const uint8_t h[6][256], uint8_t out[61]) {
  clear_bytes(out, 61);
  uint32_t pos = 0;
  for (uint32_t i = 0; i < 6; ++i) {
    for (uint32_t j = 0; j < 256; ++j) {
      if (h[i][j] != 0 && pos < 55) {
        out[pos++] = static_cast<uint8_t>(j);
      }
    }
    out[55 + i] = static_cast<uint8_t>(pos);
  }
}

// 13. decode_hints for ML-DSA-65 (61 bytes: 55 hints capacity + 6 endpoints)
__attribute__((noinline)) static bool decode_hints65_and_check(
    const uint8_t in[61], uint8_t h[6][256]) {

  clear_bytes(h, 6 * 256);

  uint32_t k = 0;
  for (uint32_t i = 0; i < 6; ++i) {
    const uint32_t end = in[55 + i];
    if (end < k || end > 55) return false;
    uint32_t prev = 0;
    for (uint32_t j = k; j < end; ++j) {
      const uint32_t idx = in[j];
      if (j > k && idx <= prev) {
        return false;
      }
      h[i][idx] = 1;
      prev = idx;
    }
    k = end;
  }
  for (uint32_t j = k; j < 55; ++j) {
    if (in[j] != 0) return false;
  }
  return in[55 + 5] <= 55;
}

} // namespace phoenix_sdr_dsp::pqc::dr14

#endif // PHOENIX_SDR_DSP_PQC_KERNELS_DR14_MLDSA65_INTERNAL_HPP_
