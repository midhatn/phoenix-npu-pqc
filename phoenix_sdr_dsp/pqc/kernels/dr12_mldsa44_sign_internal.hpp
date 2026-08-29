// SPDX-License-Identifier: Apache-2.0
#ifndef PHOENIX_SDR_DSP_PQC_KERNELS_DR12_MLDSA44_SIGN_INTERNAL_HPP_
#define PHOENIX_SDR_DSP_PQC_KERNELS_DR12_MLDSA44_SIGN_INTERNAL_HPP_

#include "dr11_mldsa44_internal.hpp"

namespace phoenix_sdr_dsp::pqc::dr12 {

using namespace phoenix_sdr_dsp::pqc::dr11;

constexpr int32_t kGamma1 = 131072; // 2^17
constexpr int32_t kGamma2 = 95232;  // (q - 1) / 88
constexpr int32_t kBeta = 78;       // tau * eta = 39 * 2
constexpr int32_t kTau = 39;
constexpr int32_t kOmega = 80;
constexpr int32_t kAlpha = 190464;  // 2 * gamma2

// 1. SampleMask for y (FIPS 204 Alg 29)
// Squeezes 576 bytes from SHAKE256(rho_pp || le16(idx), 576)
// Each 18 bits is 1 coefficient: y = gamma1 - (v mod 2^18)
__attribute__((noinline)) static void sample_mask_poly(
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

  uint8_t stream[576];
  uint32_t stream_pos = 0;

  // Absorb / squeeze 576 bytes
  while (stream_pos + 136 <= 576) {
    DR11_DISABLE_UNROLL
    for (uint32_t i = 0; i < 136; ++i) stream[stream_pos + i] = state[i];
    phoenix_sdr_dsp::pqc::dr1::keccak_f1600(state);
    stream_pos += 136;
  }
  const uint32_t rem = 576 - stream_pos;
  DR11_DISABLE_UNROLL
  for (uint32_t i = 0; i < rem; ++i) stream[stream_pos + i] = state[i];
  clear_bytes(state, sizeof(state));

  // Parse 18-bit chunks into 256 coefficients
  // 9 bytes = 72 bits = 4 coefficients of 18 bits each
  DR11_DISABLE_UNROLL
  for (uint32_t i = 0; i < 64; ++i) {
    const uint8_t *b = stream + i * 9;
    const uint32_t b0 = b[0], b1 = b[1], b2 = b[2], b3 = b[3], b4 = b[4], b5 = b[5], b6 = b[6], b7 = b[7], b8 = b[8];
    const uint32_t v0 = b0 | (b1 << 8) | ((b2 & 0x03) << 16);
    const uint32_t v1 = (b2 >> 2) | (b3 << 6) | ((b4 & 0x0F) << 14);
    const uint32_t v2 = (b4 >> 4) | (b5 << 4) | ((b6 & 0x3F) << 12);
    const uint32_t v3 = (b6 >> 6) | (b7 << 2) | (b8 << 10);

    y[i * 4 + 0] = canonicalize(kGamma1 - static_cast<int32_t>(v0));
    y[i * 4 + 1] = canonicalize(kGamma1 - static_cast<int32_t>(v1));
    y[i * 4 + 2] = canonicalize(kGamma1 - static_cast<int32_t>(v2));
    y[i * 4 + 3] = canonicalize(kGamma1 - static_cast<int32_t>(v3));
  }
  clear_bytes(stream, sizeof(stream));
}

// 2. Decompose (HighBits & LowBits) with alpha = 2 * gamma2 = 190464
static void decompose(int32_t r, int32_t &r1, int32_t &r0) {
  int32_t rp = canonicalize(r);
  int32_t r0_cand = rp % kAlpha;
  if (r0_cand > (kAlpha >> 1)) {
    r0_cand -= kAlpha;
  }
  if (rp - r0_cand == kQ - 1) {
    r1 = 0;
    r0 = r0_cand - 1;
  } else {
    r1 = (rp - r0_cand) / kAlpha;
    r0 = r0_cand;
  }
}

// 3. MakeHint: 1 if HighBits(r + z) != HighBits(r), else 0
static int32_t make_hint(int32_t z, int32_t r) {
  int32_t r1, r0, r_plus_z_1, r_plus_z_0;
  decompose(r, r1, r0);
  decompose(r + z, r_plus_z_1, r_plus_z_0);
  return r1 != r_plus_z_1 ? 1 : 0;
}

// 4. SampleInBall (FIPS 204 Alg 28)
// 32-byte seed c_tilde -> c with tau=39 non-zero coeffs in {-1, 1}
__attribute__((noinline)) static void sample_in_ball(
    const uint8_t c_tilde[32],
    int32_t c_poly[256]) {

  clear_bytes(c_poly, 256 * sizeof(int32_t));

  alignas(8) uint8_t state[200];
  clear_bytes(state, sizeof(state));

  DR11_DISABLE_UNROLL
  for (uint32_t i = 0; i < 32; ++i) state[i] = c_tilde[i];
  state[32] ^= 0x1F;
  state[135] ^= 0x80;
  phoenix_sdr_dsp::pqc::dr1::keccak_f1600(state);

  // Squeeze 8 bytes for 64-bit sign mask (first 8 bytes of state)
  uint64_t signs = 0;
  DR11_DISABLE_UNROLL
  for (uint32_t i = 0; i < 8; ++i) {
    signs |= static_cast<uint64_t>(state[i]) << (i * 8);
  }

  // Squeeze bytes from offset 8
  uint32_t state_pos = 8;
  for (uint32_t i = 256 - kTau; i < 256; ++i) {
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

// 5. Check Infinity Norm: max |centred(x)| < bound
__attribute__((noinline)) static bool check_norm(const int32_t poly[256], int32_t bound) {
  DR11_DISABLE_UNROLL
  for (uint32_t i = 0; i < 256; ++i) {
    int32_t v = canonicalize(poly[i]);
    if (v > (kQ >> 1)) {
      v -= kQ;
    }
    if (v < 0) v = -v;
    if (v >= bound) return false;
  }
  return true;
}

// 6. Check LowBits Norm: max |r0| < bound
static bool check_lowbits_norm(const int32_t poly[256], int32_t bound) {
  DR11_DISABLE_UNROLL
  for (uint32_t i = 0; i < 256; ++i) {
    int32_t r1, r0;
    decompose(poly[i], r1, r0);
    if (r0 < 0) r0 = -r0;
    if (r0 >= bound) return false;
  }
  return true;
}

// 7. w1Encode: 192 bytes per polynomial (6 bits per coefficient)
static void encode_w1_poly(const int32_t w1[256], uint8_t out[192]) {
  DR11_DISABLE_UNROLL
  for (uint32_t i = 0; i < 64; ++i) {
    const uint32_t a0 = static_cast<uint32_t>(w1[i * 4 + 0]) & 0x3F;
    const uint32_t a1 = static_cast<uint32_t>(w1[i * 4 + 1]) & 0x3F;
    const uint32_t a2 = static_cast<uint32_t>(w1[i * 4 + 2]) & 0x3F;
    const uint32_t a3 = static_cast<uint32_t>(w1[i * 4 + 3]) & 0x3F;

    out[i * 3 + 0] = static_cast<uint8_t>(a0 | (a1 << 6));
    out[i * 3 + 1] = static_cast<uint8_t>((a1 >> 2) | (a2 << 4));
    out[i * 3 + 2] = static_cast<uint8_t>((a2 >> 4) | (a3 << 2));
  }
}

static inline int32_t to_signed_coeff(int32_t r) {
  int32_t c = canonicalize(r);
  if (c > (kQ >> 1)) c -= kQ;
  return c;
}

// 8. zEncode: 576 bytes per polynomial (18 bits per coefficient: z = gamma1 - c)
static void encode_z_poly(const int32_t z[256], uint8_t out[576]) {
  DR11_DISABLE_UNROLL
  for (uint32_t i = 0; i < 64; ++i) {
    const uint32_t v0 = static_cast<uint32_t>(kGamma1 - to_signed_coeff(z[i * 4 + 0])) & 0x3FFFF;
    const uint32_t v1 = static_cast<uint32_t>(kGamma1 - to_signed_coeff(z[i * 4 + 1])) & 0x3FFFF;
    const uint32_t v2 = static_cast<uint32_t>(kGamma1 - to_signed_coeff(z[i * 4 + 2])) & 0x3FFFF;
    const uint32_t v3 = static_cast<uint32_t>(kGamma1 - to_signed_coeff(z[i * 4 + 3])) & 0x3FFFF;

    out[i * 9 + 0] = static_cast<uint8_t>(v0);
    out[i * 9 + 1] = static_cast<uint8_t>(v0 >> 8);
    out[i * 9 + 2] = static_cast<uint8_t>((v0 >> 16) | (v1 << 2));
    out[i * 9 + 3] = static_cast<uint8_t>(v1 >> 6);
    out[i * 9 + 4] = static_cast<uint8_t>((v1 >> 14) | (v2 << 4));
    out[i * 9 + 5] = static_cast<uint8_t>(v2 >> 4);
    out[i * 9 + 6] = static_cast<uint8_t>((v2 >> 12) | (v3 << 6));
    out[i * 9 + 7] = static_cast<uint8_t>(v3 >> 2);
    out[i * 9 + 8] = static_cast<uint8_t>(v3 >> 10);
  }
}

// 9. hintEncode: 84 bytes for 4 polynomials (omega=80 non-zero indices + 4 column offsets)
static void encode_hints(const int32_t h[4][256], uint8_t out[84]) {
  clear_bytes(out, 84);
  uint32_t k = 0;
  for (uint32_t i = 0; i < 4; ++i) {
    for (uint32_t j = 0; j < 256; ++j) {
      if (h[i][j] != 0) {
        out[k++] = static_cast<uint8_t>(j);
      }
    }
    out[kOmega + i] = static_cast<uint8_t>(k);
  }
}

// 10. skDecode: decode s1, s2 (3-bit) and t0 (13-bit) from sk
__attribute__((noinline)) static void decode_sk_s_poly(const uint8_t in[96], int32_t s[256]) {
  DR11_DISABLE_UNROLL
  for (uint32_t i = 0; i < 32; ++i) {
    const uint32_t b0 = in[i * 3 + 0];
    const uint32_t b1 = in[i * 3 + 1];
    const uint32_t b2 = in[i * 3 + 2];
    const uint32_t v = b0 | (b1 << 8) | (b2 << 16);

    s[i * 8 + 0] = 2 - static_cast<int32_t>((v >> 0) & 0x07);
    s[i * 8 + 1] = 2 - static_cast<int32_t>((v >> 3) & 0x07);
    s[i * 8 + 2] = 2 - static_cast<int32_t>((v >> 6) & 0x07);
    s[i * 8 + 3] = 2 - static_cast<int32_t>((v >> 9) & 0x07);
    s[i * 8 + 4] = 2 - static_cast<int32_t>((v >> 12) & 0x07);
    s[i * 8 + 5] = 2 - static_cast<int32_t>((v >> 15) & 0x07);
    s[i * 8 + 6] = 2 - static_cast<int32_t>((v >> 18) & 0x07);
    s[i * 8 + 7] = 2 - static_cast<int32_t>((v >> 21) & 0x07);
  }
}

__attribute__((noinline)) static void decode_sk_t0_poly(const uint8_t in[416], int32_t t0[256]) {
  DR11_DISABLE_UNROLL
  for (uint32_t i = 0; i < 32; ++i) {
    const uint8_t *b = in + i * 13;
    const uint32_t b0 = b[0], b1 = b[1], b2 = b[2], b3 = b[3], b4 = b[4], b5 = b[5], b6 = b[6];
    const uint32_t b7 = b[7], b8 = b[8], b9 = b[9], b10 = b[10], b11 = b[11], b12 = b[12];

    const uint32_t v0 = b0 | (b1 << 8);
    const uint32_t v1 = (b1 >> 5) | (b2 << 3) | (b3 << 11);
    const uint32_t v2 = (b3 >> 2) | (b4 << 6);
    const uint32_t v3 = (b4 >> 7) | (b5 << 1) | (b6 << 9);
    const uint32_t v4 = (b6 >> 4) | (b7 << 4) | (b8 << 12);
    const uint32_t v5 = (b8 >> 1) | (b9 << 7);
    const uint32_t v6 = (b9 >> 6) | (b10 << 2) | (b11 << 10);
    const uint32_t v7 = (b11 >> 3) | (b12 << 5);

    t0[i * 8 + 0] = (1 << 12) - static_cast<int32_t>(v0 & 0x1FFF);
    t0[i * 8 + 1] = (1 << 12) - static_cast<int32_t>(v1 & 0x1FFF);
    t0[i * 8 + 2] = (1 << 12) - static_cast<int32_t>(v2 & 0x1FFF);
    t0[i * 8 + 3] = (1 << 12) - static_cast<int32_t>(v3 & 0x1FFF);
    t0[i * 8 + 4] = (1 << 12) - static_cast<int32_t>(v4 & 0x1FFF);
    t0[i * 8 + 5] = (1 << 12) - static_cast<int32_t>(v5 & 0x1FFF);
    t0[i * 8 + 6] = (1 << 12) - static_cast<int32_t>(v6 & 0x1FFF);
    t0[i * 8 + 7] = (1 << 12) - static_cast<int32_t>(v7 & 0x1FFF);
  }
}

} // namespace phoenix_sdr_dsp::pqc::dr12

#endif // PHOENIX_SDR_DSP_PQC_KERNELS_DR12_MLDSA44_SIGN_INTERNAL_HPP_
