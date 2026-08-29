// SPDX-License-Identifier: Apache-2.0
#include "dr12_mldsa44_sign_internal.hpp"

namespace {

__attribute__((noinline)) void keccak_sponge(
    uint32_t rate_bytes,
    const uint8_t *in, uint32_t in_len,
    uint8_t pad_byte,
    uint8_t *out, uint32_t out_len) {

  alignas(8) uint8_t state[200];
  phoenix_sdr_dsp::pqc::dr11::clear_bytes(state, 200);

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

  phoenix_sdr_dsp::pqc::dr11::clear_bytes(state, 200);
}

// SampleMask using unified sponge
__attribute__((noinline)) void sample_mask_sponge(
    const uint8_t rho_pp[64], uint16_t idx, int32_t y[256]) {
  uint8_t in_buf[66];
  DR11_DISABLE_UNROLL
  for (uint32_t i = 0; i < 64; ++i) in_buf[i] = rho_pp[i];
  in_buf[64] = static_cast<uint8_t>(idx & 0xFF);
  in_buf[65] = static_cast<uint8_t>((idx >> 8) & 0xFF);

  uint8_t stream[576];
  keccak_sponge(136, in_buf, 66, 0x1F, stream, 576);

  DR11_DISABLE_UNROLL
  for (uint32_t i = 0; i < 64; ++i) {
    const uint8_t *b = stream + i * 9;
    const uint32_t b0 = b[0], b1 = b[1], b2 = b[2], b3 = b[3], b4 = b[4], b5 = b[5], b6 = b[6], b7 = b[7], b8 = b[8];
    const uint32_t v0 = b0 | (b1 << 8) | ((b2 & 0x03) << 16);
    const uint32_t v1 = (b2 >> 2) | (b3 << 6) | ((b4 & 0x0F) << 14);
    const uint32_t v2 = (b4 >> 4) | (b5 << 4) | ((b6 & 0x3F) << 12);
    const uint32_t v3 = (b6 >> 6) | (b7 << 2) | (b8 << 10);

    y[i * 4 + 0] = phoenix_sdr_dsp::pqc::dr11::canonicalize(phoenix_sdr_dsp::pqc::dr12::kGamma1 - static_cast<int32_t>(v0));
    y[i * 4 + 1] = phoenix_sdr_dsp::pqc::dr11::canonicalize(phoenix_sdr_dsp::pqc::dr12::kGamma1 - static_cast<int32_t>(v1));
    y[i * 4 + 2] = phoenix_sdr_dsp::pqc::dr11::canonicalize(phoenix_sdr_dsp::pqc::dr12::kGamma1 - static_cast<int32_t>(v2));
    y[i * 4 + 3] = phoenix_sdr_dsp::pqc::dr11::canonicalize(phoenix_sdr_dsp::pqc::dr12::kGamma1 - static_cast<int32_t>(v3));
  }
}

// ExpandA using unified sponge
__attribute__((noinline)) void expand_a_sponge(
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
    if (val < phoenix_sdr_dsp::pqc::dr11::kQ) {
      out[accepted++] = static_cast<int32_t>(val);
    }
  }
}

// Challenge using unified sponge
__attribute__((noinline)) void challenge_sponge(
    const uint8_t mu[64], const uint8_t w1_bytes[768], uint8_t c_tilde[32]) {
  uint8_t hash_in[64 + 768];
  DR11_DISABLE_UNROLL
  for (uint32_t i = 0; i < 64; ++i) hash_in[i] = mu[i];
  DR11_DISABLE_UNROLL
  for (uint32_t i = 0; i < 768; ++i) hash_in[64 + i] = w1_bytes[i];

  keccak_sponge(136, hash_in, 64 + 768, 0x1F, c_tilde, 32);
}

// SampleInBall using unified sponge
__attribute__((noinline)) void sample_in_ball_sponge(
    const uint8_t c_tilde[32], int32_t c_poly[256]) {
  phoenix_sdr_dsp::pqc::dr11::clear_bytes(c_poly, 256 * sizeof(int32_t));

  uint8_t stream[272];
  keccak_sponge(136, c_tilde, 32, 0x1F, stream, 272);

  uint64_t signs = 0;
  DR11_DISABLE_UNROLL
  for (uint32_t i = 0; i < 8; ++i) {
    signs |= static_cast<uint64_t>(stream[i]) << (i * 8);
  }

  uint32_t pos = 8;
  for (uint32_t i = 256 - phoenix_sdr_dsp::pqc::dr12::kTau; i < 256; ++i) {
    uint32_t j;
    while (true) {
      if (pos >= 272) {
        pos = 8; // Wrap if needed
      }
      const uint32_t b = stream[pos++];
      if (b <= i) {
        j = b;
        break;
      }
    }
    c_poly[i] = c_poly[j];
    c_poly[j] = (signs & 1) ? (phoenix_sdr_dsp::pqc::dr11::kQ - 1) : 1;
    signs >>= 1;
  }
}

} // namespace

extern "C" void dr12_mldsa44_sign_w1_mask_a(
    const uint8_t in_token[2596],
    uint8_t out_token[10660]) {

  phoenix_sdr_dsp::pqc::dr11::clear_bytes(out_token, 10660);

  const uint32_t request_id = phoenix_sdr_dsp::pqc::dr11::load_le32(in_token + 0);
  const uint8_t *rho = in_token + 4;
  const uint8_t *mu = in_token + 36;
  const uint8_t *rho_pp = in_token + 100;
  const uint8_t *s_encoded = in_token + 164;
  const uint8_t *t0_encoded = in_token + 932;

  phoenix_sdr_dsp::pqc::dr11::store_le32(out_token + 0, request_id);
  DR11_DISABLE_UNROLL
  for (uint32_t i = 0; i < 768; ++i) out_token[36 + i] = s_encoded[i];
  DR11_DISABLE_UNROLL
  for (uint32_t i = 0; i < 1664; ++i) out_token[804 + i] = t0_encoded[i];

  int32_t *y_out = reinterpret_cast<int32_t *>(out_token + 2468);
  int32_t *w_out = reinterpret_cast<int32_t *>(out_token + 6564);

  int32_t poly[256];
  int32_t y_ntt[4][256];
  uint8_t w1_bytes[768];

  uint16_t kappa = 0;

  DR11_DISABLE_UNROLL
  for (uint32_t attempt = 0; attempt < 64; ++attempt) {
    // 1. Sample y, NTT
    for (uint16_t j = 0; j < 4; ++j) {
      sample_mask_sponge(rho_pp, kappa + j, y_out + j * 256);
      DR11_DISABLE_UNROLL
      for (uint32_t c = 0; c < 256; ++c) y_ntt[j][c] = y_out[j * 256 + c];
      phoenix_sdr_dsp::pqc::dr11::ntt_kernel(y_ntt[j]);
    }

    // 2. w = INTT(A * y_ntt), w1, w1_bytes
    int32_t w1_row[256];
    for (uint8_t row = 0; row < 4; ++row) {
      phoenix_sdr_dsp::pqc::dr11::clear_bytes(poly, sizeof(poly));
      for (uint8_t col = 0; col < 4; ++col) {
        int32_t a_entry[256];
        expand_a_sponge(rho, col, row, a_entry);
        int32_t prod[256];
        phoenix_sdr_dsp::pqc::dr11::basemul(prod, a_entry, y_ntt[col]);
        DR11_DISABLE_UNROLL
        for (uint32_t c = 0; c < 256; ++c) poly[c] += prod[c];
      }
      phoenix_sdr_dsp::pqc::dr11::invntt_kernel(poly);
      DR11_DISABLE_UNROLL
      for (uint32_t c = 0; c < 256; ++c) {
        w_out[row * 256 + c] = poly[c];
        int32_t dummy;
        phoenix_sdr_dsp::pqc::dr12::decompose(poly[c], w1_row[c], dummy);
      }
      phoenix_sdr_dsp::pqc::dr12::encode_w1_poly(w1_row, w1_bytes + row * 192);
    }

    // 3. c_tilde
    uint8_t c_tilde[32];
    challenge_sponge(mu, w1_bytes, c_tilde);

    // 4. c = SampleInBall -> NTT(c)
    int32_t c_ntt[256];
    sample_in_ball_sponge(c_tilde, c_ntt);
    phoenix_sdr_dsp::pqc::dr11::ntt_kernel(c_ntt);

    // 5. Check z = y + INTT(c*s1) norm
    bool reject = false;
    for (uint32_t j = 0; j < 4 && !reject; ++j) {
      phoenix_sdr_dsp::pqc::dr12::decode_sk_s_poly(s_encoded + j * 96, poly);
      phoenix_sdr_dsp::pqc::dr11::ntt_kernel(poly);
      phoenix_sdr_dsp::pqc::dr11::basemul(poly, c_ntt, poly);
      phoenix_sdr_dsp::pqc::dr11::invntt_kernel(poly);
      DR11_DISABLE_UNROLL
      for (uint32_t c = 0; c < 256; ++c)
        poly[c] = phoenix_sdr_dsp::pqc::dr11::canonicalize(y_out[j * 256 + c] + poly[c]);
      if (!phoenix_sdr_dsp::pqc::dr12::check_norm(poly, phoenix_sdr_dsp::pqc::dr12::kGamma1 - phoenix_sdr_dsp::pqc::dr12::kBeta)) reject = true;
    }
    if (reject) { kappa += 4; continue; }

    // 6. Check r0 = LowBits(w - INTT(c*s2)) norm
    for (uint32_t i = 0; i < 4 && !reject; ++i) {
      phoenix_sdr_dsp::pqc::dr12::decode_sk_s_poly(s_encoded + 384 + i * 96, poly);
      phoenix_sdr_dsp::pqc::dr11::ntt_kernel(poly);
      phoenix_sdr_dsp::pqc::dr11::basemul(poly, c_ntt, poly);
      phoenix_sdr_dsp::pqc::dr11::invntt_kernel(poly);
      DR11_DISABLE_UNROLL
      for (uint32_t c = 0; c < 256; ++c) {
        int32_t r1d, r0v;
        phoenix_sdr_dsp::pqc::dr12::decompose(phoenix_sdr_dsp::pqc::dr11::canonicalize(w_out[i * 256 + c] - poly[c]), r1d, r0v);
        poly[c] = r0v;
      }
      if (!phoenix_sdr_dsp::pqc::dr12::check_norm(poly, phoenix_sdr_dsp::pqc::dr12::kGamma2 - phoenix_sdr_dsp::pqc::dr12::kBeta)) reject = true;
    }
    if (reject) { kappa += 4; continue; }

    // 7. Check c*t0 norm
    for (uint32_t i = 0; i < 4 && !reject; ++i) {
      phoenix_sdr_dsp::pqc::dr12::decode_sk_t0_poly(t0_encoded + i * 416, poly);
      phoenix_sdr_dsp::pqc::dr11::ntt_kernel(poly);
      phoenix_sdr_dsp::pqc::dr11::basemul(poly, c_ntt, poly);
      phoenix_sdr_dsp::pqc::dr11::invntt_kernel(poly);
      if (!phoenix_sdr_dsp::pqc::dr12::check_norm(poly, phoenix_sdr_dsp::pqc::dr12::kGamma2)) reject = true;
    }
    if (reject) { kappa += 4; continue; }

    // Accepted! Store c_tilde
    DR11_DISABLE_UNROLL
    for (uint32_t i = 0; i < 32; ++i) out_token[4 + i] = c_tilde[i];
    phoenix_sdr_dsp::pqc::dr11::clear_bytes(y_ntt, sizeof(y_ntt));
    phoenix_sdr_dsp::pqc::dr11::clear_bytes(poly, sizeof(poly));
    phoenix_sdr_dsp::pqc::dr11::clear_bytes(c_ntt, sizeof(c_ntt));
    return;
  }
  phoenix_sdr_dsp::pqc::dr11::store_le32(out_token + 0, 0xFFFFFFFFu);
}
