// SPDX-License-Identifier: Apache-2.0
#ifndef PHOENIX_SDR_DSP_PQC_KERNELS_DR13_MLDSA44_VERIFY_INTERNAL_HPP_
#define PHOENIX_SDR_DSP_PQC_KERNELS_DR13_MLDSA44_VERIFY_INTERNAL_HPP_

#include "dr11_mldsa44_internal.hpp"
#include "dr12_mldsa44_sign_internal.hpp"

namespace phoenix_sdr_dsp::pqc::dr13 {

using namespace phoenix_sdr_dsp::pqc::dr11;
using namespace phoenix_sdr_dsp::pqc::dr12;

constexpr int32_t kAlpha = 190464; // 2 * gamma2
constexpr int32_t kM = 44;         // (q - 1) / alpha = 8380416 / 190464

// Unified Keccak Sponge for DR13
__attribute__((noinline)) static void keccak_sponge(
    uint32_t rate_bytes,
    const uint8_t *in, uint32_t in_len,
    uint8_t pad_byte,
    uint8_t *out, uint32_t out_len) {

  alignas(8) uint8_t state[200];
  clear_bytes(state, 200);

  uint32_t in_pos = 0;
  while (in_len - in_pos >= rate_bytes) {
    DR11_DISABLE_UNROLL
    for (uint32_t i = 0; i < rate_bytes; ++i) state[i] ^= in[in_pos + i];
    phoenix_sdr_dsp::pqc::dr1::keccak_f1600(state);
    in_pos += rate_bytes;
  }

  const uint32_t rem = in_len - in_pos;
  DR11_DISABLE_UNROLL
  for (uint32_t i = 0; i < rem; ++i) state[i] ^= in[in_pos + i];
  state[rem] ^= pad_byte;
  state[rate_bytes - 1] ^= 0x80;
  phoenix_sdr_dsp::pqc::dr1::keccak_f1600(state);

  uint32_t out_pos = 0;
  while (out_len - out_pos > rate_bytes) {
    DR11_DISABLE_UNROLL
    for (uint32_t i = 0; i < rate_bytes; ++i) out[out_pos + i] = state[i];
    phoenix_sdr_dsp::pqc::dr1::keccak_f1600(state);
    out_pos += rate_bytes;
  }
  const uint32_t rem_out = out_len - out_pos;
  DR11_DISABLE_UNROLL
  for (uint32_t i = 0; i < rem_out; ++i) out[out_pos + i] = state[i];

  clear_bytes(state, 200);
}

// 1. Decode z (18-bit signed) and check infinity norm
__attribute__((noinline)) static bool decode_z_poly_and_check(
    const uint8_t in[576], int32_t z[256], int32_t bound) {

  DR11_DISABLE_UNROLL
  for (uint32_t i = 0; i < 64; ++i) {
    const uint8_t *b = in + i * 9;
    const uint32_t b0 = b[0], b1 = b[1], b2 = b[2], b3 = b[3], b4 = b[4], b5 = b[5], b6 = b[6], b7 = b[7], b8 = b[8];
    const uint32_t v0 = b0 | (b1 << 8) | ((b2 & 0x03) << 16);
    const uint32_t v1 = (b2 >> 2) | (b3 << 6) | ((b4 & 0x0F) << 14);
    const uint32_t v2 = (b4 >> 4) | (b5 << 4) | ((b6 & 0x3F) << 12);
    const uint32_t v3 = (b6 >> 6) | (b7 << 2) | (b8 << 10);

    const int32_t z0 = kGamma1 - static_cast<int32_t>(v0);
    const int32_t z1 = kGamma1 - static_cast<int32_t>(v1);
    const int32_t z2 = kGamma1 - static_cast<int32_t>(v2);
    const int32_t z3 = kGamma1 - static_cast<int32_t>(v3);

    // Norm check on signed values in [-gamma1, gamma1]
    int32_t az0 = z0 < 0 ? -z0 : z0;
    int32_t az1 = z1 < 0 ? -z1 : z1;
    int32_t az2 = z2 < 0 ? -z2 : z2;
    int32_t az3 = z3 < 0 ? -z3 : z3;

    if (az0 >= bound || az1 >= bound || az2 >= bound || az3 >= bound) {
      return false;
    }

    z[i * 4 + 0] = canonicalize(z0);
    z[i * 4 + 1] = canonicalize(z1);
    z[i * 4 + 2] = canonicalize(z2);
    z[i * 4 + 3] = canonicalize(z3);
  }
  return true;
}

// 2. Decode hints (84 bytes) and check popcount <= 80
__attribute__((noinline)) static bool decode_hints_and_check(
    const uint8_t in[84], uint8_t h[4][256]) {

  clear_bytes(h, 4 * 256);

  uint32_t k = 0;
  for (uint32_t i = 0; i < 4; ++i) {
    const uint32_t end = in[kOmega + i];
    if (end < k || end > static_cast<uint32_t>(kOmega)) {
      return false;
    }
    uint32_t prev = 0;
    for (uint32_t j = k; j < end; ++j) {
      const uint32_t idx = in[j];
      if (j > k && idx <= prev) {
        return false; // Non-strictly increasing indices
      }
      h[i][idx] = 1;
      prev = idx;
    }
    k = end;
  }
  return in[kOmega + 3] <= static_cast<uint32_t>(kOmega);
}

// 3. Decode t1 (10-bit) and multiply by 2^13 = 8192
__attribute__((noinline)) static void decode_t1_poly(
    const uint8_t in[320], int32_t t1_scaled[256]) {

  DR11_DISABLE_UNROLL
  for (uint32_t i = 0; i < 64; ++i) {
    const uint8_t *b = in + i * 5;
    const uint32_t b0 = b[0], b1 = b[1], b2 = b[2], b3 = b[3], b4 = b[4];

    const uint32_t v0 = b0 | ((b1 & 0x03) << 8);
    const uint32_t v1 = (b1 >> 2) | ((b2 & 0x0F) << 6);
    const uint32_t v2 = (b2 >> 4) | ((b3 & 0x3F) << 4);
    const uint32_t v3 = (b3 >> 6) | (b4 << 2);

    // t1 * 2^13 mod q
    t1_scaled[i * 4 + 0] = canonicalize(static_cast<int32_t>(v0 << 13));
    t1_scaled[i * 4 + 1] = canonicalize(static_cast<int32_t>(v1 << 13));
    t1_scaled[i * 4 + 2] = canonicalize(static_cast<int32_t>(v2 << 13));
    t1_scaled[i * 4 + 3] = canonicalize(static_cast<int32_t>(v3 << 13));
  }
}

// 4. SampleInBall using unified sponge
__attribute__((noinline)) static void sample_in_ball_sponge(
    const uint8_t c_tilde[32], int32_t c_poly[256]) {

  clear_bytes(c_poly, 256 * sizeof(int32_t));

  uint8_t stream[272];
  keccak_sponge(136, c_tilde, 32, 0x1F, stream, 272);

  uint64_t signs = 0;
  DR11_DISABLE_UNROLL
  for (uint32_t i = 0; i < 8; ++i) {
    signs |= static_cast<uint64_t>(stream[i]) << (i * 8);
  }

  uint32_t pos = 8;
  for (uint32_t i = 256 - kTau; i < 256; ++i) {
    uint32_t j;
    while (true) {
      if (pos >= 272) pos = 8;
      const uint32_t b = stream[pos++];
      if (b <= i) {
        j = b;
        break;
      }
    }
    c_poly[i] = c_poly[j];
    c_poly[j] = (signs & 1) ? (kQ - 1) : 1;
    signs >>= 1;
  }
}

// 5. ExpandA entry using unified sponge
__attribute__((noinline)) static void expand_a_sponge(
    const uint8_t rho[32], uint8_t col, uint8_t row, int32_t out[256]) {

  uint8_t in_buf[34];
  DR11_DISABLE_UNROLL
  for (uint32_t i = 0; i < 32; ++i) in_buf[i] = rho[i];
  in_buf[32] = col;
  in_buf[33] = row;

  uint8_t stream[840];
  keccak_sponge(168, in_buf, 34, 0x1F, stream, 840);

  uint32_t accepted = 0;
  uint32_t pos = 0;
  while (accepted < 256 && pos + 3 <= 840) {
    const uint32_t b0 = stream[pos + 0];
    const uint32_t b1 = stream[pos + 1];
    const uint32_t b2 = stream[pos + 2];
    pos += 3;
    const uint32_t val = b0 | (b1 << 8) | ((b2 & 0x7F) << 16);
    if (val < kQ) {
      out[accepted++] = static_cast<int32_t>(val);
    }
  }
}

// 6. UseHint: FIPS 204 Alg 31
static inline int32_t use_hint(uint8_t h, int32_t r) {
  int32_t r1, r0;
  decompose(r, r1, r0);
  if (h == 0) return r1;
  if (r0 > 0) {
    return (r1 + 1 == kM) ? 0 : (r1 + 1);
  }
  return (r1 == 0) ? (kM - 1) : (r1 - 1);
}

} // namespace phoenix_sdr_dsp::pqc::dr13

#endif // PHOENIX_SDR_DSP_PQC_KERNELS_DR13_MLDSA44_VERIFY_INTERNAL_HPP_
