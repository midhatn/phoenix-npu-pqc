// SPDX-License-Identifier: Apache-2.0
// NIST FIPS 206 (FN-DSA / FALCON) Core Internal Subroutines for AMD Phoenix AIE2.
#pragma once

#include <stdint.h>
#include <new>

#include "dr1_keccak_f1600.hpp"

#if defined(__clang__)
#define DR22_DISABLE_UNROLL _Pragma("clang loop unroll(disable)")
#else
#define DR22_DISABLE_UNROLL
#endif

namespace phoenix_sdr_dsp::pqc::dr22 {

constexpr uint32_t kOk = 0u;
constexpr uint32_t kBadDescriptor = 2u;
constexpr uint32_t kBadToken = 3u;
constexpr uint32_t kLimitExceeded = 4u;
constexpr uint32_t kVerificationFailed = 5u;

constexpr int32_t Q_FNDSA = 12289;
constexpr int32_t Q_HALF = 6144;
constexpr uint32_t MAX_N = 1024;
constexpr int32_t B_INF = 840;

// Tile local SRAM scratch buffers (BSS section; zero stack overhead)
alignas(32) static int16_t tile_poly_h[MAX_N];
alignas(32) static int16_t tile_poly_c[MAX_N];
alignas(32) static int16_t tile_poly_s2[MAX_N];
alignas(32) static int16_t tile_poly_s2_h[MAX_N];

// Embedded twiddle tables and Radix-4 Stockham FFT engine (following parallel_fft64_kernel.cc and FFT_R4_AIE)
static const float tw_r[64] = {
     1.00000000f,  0.99518473f,  0.98078528f,  0.95694034f,
     0.92387953f,  0.88192126f,  0.83146961f,  0.77301045f,
     0.70710678f,  0.63439328f,  0.55557023f,  0.47139674f,
     0.38268343f,  0.29028468f,  0.19509032f,  0.09801714f,
     0.00000000f, -0.09801714f, -0.19509032f, -0.29028468f,
    -0.38268343f, -0.47139674f, -0.55557023f, -0.63439328f,
    -0.70710678f, -0.77301045f, -0.83146961f, -0.88192126f,
    -0.92387953f, -0.95694034f, -0.98078528f, -0.99518473f,
    -1.00000000f, -0.99518473f, -0.98078528f, -0.95694034f,
    -0.92387953f, -0.88192126f, -0.83146961f, -0.77301045f,
    -0.70710678f, -0.63439328f, -0.55557023f, -0.47139674f,
    -0.38268343f, -0.29028468f, -0.19509032f, -0.09801714f,
    -0.00000000f,  0.09801714f,  0.19509032f,  0.29028468f,
     0.38268343f,  0.47139674f,  0.55557023f,  0.63439328f,
     0.70710678f,  0.77301045f,  0.83146961f,  0.88192126f,
     0.92387953f,  0.95694034f,  0.98078528f,  0.99518473f
};

static const float tw_i[64] = {
     0.00000000f, -0.09801714f, -0.19509032f, -0.29028468f,
    -0.38268343f, -0.47139674f, -0.55557023f, -0.63439328f,
    -0.70710678f, -0.77301045f, -0.83146961f, -0.88192126f,
    -0.92387953f, -0.95694034f, -0.98078528f, -0.99518473f,
    -1.00000000f, -0.99518473f, -0.98078528f, -0.95694034f,
    -0.92387953f, -0.88192126f, -0.83146961f, -0.77301045f,
    -0.70710678f, -0.63439328f, -0.55557023f, -0.47139674f,
    -0.38268343f, -0.29028468f, -0.19509032f, -0.09801714f,
     0.00000000f,  0.09801714f,  0.19509032f,  0.29028468f,
     0.38268343f,  0.47139674f,  0.55557023f,  0.63439328f,
     0.70710678f,  0.77301045f,  0.83146961f,  0.88192126f,
     0.92387953f,  0.95694034f,  0.98078528f,  0.99518473f,
     1.00000000f,  0.99518473f,  0.98078528f,  0.95694034f,
     0.92387953f,  0.88192126f,  0.83146961f,  0.77301045f,
     0.70710678f,  0.63439328f,  0.55557023f,  0.47139674f,
     0.38268343f,  0.29028468f,  0.19509032f,  0.09801714f
};

static inline void radix4_butterfly(
    float ar, float ai, float br, float bi,
    float cr, float ci, float dr, float di,
    float &xr0, float &xi0, float &xr1, float &xi1,
    float &xr2, float &xi2, float &xr3, float &xi3) {
  const float t0r = ar + cr;
  const float t0i = ai + ci;
  const float t1r = ar - cr;
  const float t1i = ai - ci;
  const float t2r = br + dr;
  const float t2i = bi + di;
  const float t3r = br - dr;
  const float t3i = bi - di;

  xr0 = t0r + t2r;
  xi0 = t0i + t2i;
  xr2 = t0r - t2r;
  xi2 = t0i - t2i;
  xr1 = t1r + t3i;
  xi1 = t1i - t3r;
  xr3 = t1r - t3i;
  xi3 = t1i + t3r;
}

__attribute__((noinline)) static void clear_bytes(uint8_t *destination, uint32_t bytes) {
  DR22_DISABLE_UNROLL
  for (uint32_t index = 0; index < bytes; ++index) destination[index] = 0u;
}

static inline void copy_bytes(uint8_t *dest, const uint8_t *src, uint32_t bytes) {
  DR22_DISABLE_UNROLL
  for (uint32_t i = 0; i < bytes; ++i) dest[i] = src[i];
}

static inline uint32_t load_le32(const uint8_t *in) {
  return static_cast<uint32_t>(in[0]) | (static_cast<uint32_t>(in[1]) << 8) |
         (static_cast<uint32_t>(in[2]) << 16) | (static_cast<uint32_t>(in[3]) << 24);
}

static inline void store_le32(uint8_t *out, uint32_t val) {
  out[0] = static_cast<uint8_t>(val & 0xFFu);
  out[1] = static_cast<uint8_t>((val >> 8) & 0xFFu);
  out[2] = static_cast<uint8_t>((val >> 16) & 0xFFu);
  out[3] = static_cast<uint8_t>((val >> 24) & 0xFFu);
}

static inline int32_t mod_q(int32_t a) {
  int32_t r = a % Q_FNDSA;
  if (r < 0) r += Q_FNDSA;
  return r;
}

static inline int32_t center_mod_q(int32_t a) {
  int32_t r = mod_q(a);
  if (r > Q_HALF) r -= Q_FNDSA;
  return r;
}

// Multi-chunk SHAKE256 stream
__attribute__((noinline)) static void shake256_multi(
    const uint8_t *const chunks[],
    const uint32_t lens[],
    uint32_t num_chunks,
    uint8_t *out,
    uint32_t out_len) {
  alignas(8) uint8_t state[200];
  clear_bytes(state, 200);
  constexpr uint32_t kRate = 136u;
  uint32_t spos = 0;

  DR22_DISABLE_UNROLL
  for (uint32_t c = 0; c < num_chunks; ++c) {
    const uint8_t *data = chunks[c];
    const uint32_t clen = lens[c];
    DR22_DISABLE_UNROLL
    for (uint32_t i = 0; i < clen; ++i) {
      state[spos++] ^= data[i];
      if (spos == kRate) {
        phoenix_sdr_dsp::pqc::dr1::keccak_f1600(state);
        spos = 0;
      }
    }
  }

  state[spos] ^= 0x1Fu;
  state[kRate - 1u] ^= 0x80u;
  phoenix_sdr_dsp::pqc::dr1::keccak_f1600(state);

  uint32_t squeezed = 0;
  while (out_len > 0) {
    const uint32_t take = (out_len < kRate) ? out_len : kRate;
    DR22_DISABLE_UNROLL
    for (uint32_t i = 0; i < take; ++i) out[squeezed + i] = state[i];
    squeezed += take;
    out_len -= take;
    if (out_len > 0) {
      phoenix_sdr_dsp::pqc::dr1::keccak_f1600(state);
    }
  }
}

// Negacyclic polynomial multiplication: res = a * b mod (x^n + 1, q)
__attribute__((noinline)) static void poly_mul_negacyclic(
    const int16_t *a,
    const int16_t *b,
    int16_t *res,
    uint32_t n) {
  DR22_DISABLE_UNROLL
  for (uint32_t i = 0; i < n; ++i) {
    int32_t sum = 0;
    DR22_DISABLE_UNROLL
    for (uint32_t j = 0; j <= i; ++j) {
      sum = (sum + static_cast<int32_t>(a[j]) * static_cast<int32_t>(b[i - j])) % Q_FNDSA;
    }
    DR22_DISABLE_UNROLL
    for (uint32_t j = i + 1; j < n; ++j) {
      sum = (sum - static_cast<int32_t>(a[j]) * static_cast<int32_t>(b[n + i - j])) % Q_FNDSA;
    }
    res[i] = static_cast<int16_t>(mod_q(sum));
  }
}

// Unpack 14-bit coefficient public key: h in Z_q[x]/(x^n + 1)
__attribute__((noinline)) static void unpack_public_key(
    const uint8_t *raw_pk,
    int16_t *h_out,
    uint32_t n) {
  const uint8_t *in = raw_pk + 1;
  const uint32_t max_bytes = (n * 14 + 7) / 8;
  uint32_t in_bit_pos = 0;

  DR22_DISABLE_UNROLL
  for (uint32_t i = 0; i < n; ++i) {
    const uint32_t byte_idx = in_bit_pos >> 3;
    const uint32_t bit_offset = in_bit_pos & 7;
    const uint32_t b0 = static_cast<uint32_t>(in[byte_idx]);
    const uint32_t b1 = (byte_idx + 1 < max_bytes) ? static_cast<uint32_t>(in[byte_idx + 1]) : 0u;
    const uint32_t b2 = (byte_idx + 2 < max_bytes) ? static_cast<uint32_t>(in[byte_idx + 2]) : 0u;
    const uint32_t val = (b0 | (b1 << 8) | (b2 << 16)) >> bit_offset;
    h_out[i] = static_cast<int16_t>(val & 0x3FFFu);
    in_bit_pos += 14;
  }
}

// Pack 14-bit coefficient public key
__attribute__((noinline)) static void pack_public_key(
    const int16_t *h_in,
    uint8_t *raw_pk,
    uint32_t n,
    uint8_t log_n) {
  raw_pk[0] = static_cast<uint8_t>(0x00u + log_n);
  uint8_t *out = raw_pk + 1;
  const uint32_t out_bytes = (n * 14 + 7) / 8;
  clear_bytes(out, out_bytes);

  uint32_t out_bit_pos = 0;
  DR22_DISABLE_UNROLL
  for (uint32_t i = 0; i < n; ++i) {
    const uint32_t val = static_cast<uint32_t>(mod_q(h_in[i])) & 0x3FFFu;
    const uint32_t byte_idx = out_bit_pos >> 3;
    const uint32_t bit_offset = out_bit_pos & 7;
    out[byte_idx] |= static_cast<uint8_t>((val << bit_offset) & 0xFFu);
    if (byte_idx + 1 < out_bytes) {
      out[byte_idx + 1] |= static_cast<uint8_t>((val >> (8 - bit_offset)) & 0xFFu);
    }
    if (bit_offset > 2 && byte_idx + 2 < out_bytes) {
      out[byte_idx + 2] |= static_cast<uint8_t>((val >> (16 - bit_offset)) & 0xFFu);
    }
    out_bit_pos += 14;
  }
}

// Normative NIST FIPS 206 Algorithm 14 HashToPoint
// Squeezes SHAKE-256 over salt (40 bytes) || msg (msg_len bytes).
// Extracts 16-bit words w = b0 | (b1 << 8). If w < 61445, c[i] = w % 12289.
__attribute__((noinline)) static void hash_to_point(
    const uint8_t salt[40],
    const uint8_t *msg,
    uint32_t msg_len,
    int16_t *c_out,
    uint32_t n) {
  alignas(8) uint8_t state[200];
  clear_bytes(state, 200);
  constexpr uint32_t kRate = 136u;
  uint32_t spos = 0;

  // Absorb salt (40 bytes)
  DR22_DISABLE_UNROLL
  for (uint32_t i = 0; i < 40; ++i) {
    state[spos++] ^= salt[i];
    if (spos == kRate) {
      phoenix_sdr_dsp::pqc::dr1::keccak_f1600(state);
      spos = 0;
    }
  }

  // Absorb message
  DR22_DISABLE_UNROLL
  for (uint32_t i = 0; i < msg_len; ++i) {
    state[spos++] ^= msg[i];
    if (spos == kRate) {
      phoenix_sdr_dsp::pqc::dr1::keccak_f1600(state);
      spos = 0;
    }
  }

  // Pad for SHAKE256: 0x1F suffix, 0x80 on last rate byte
  state[spos] ^= 0x1Fu;
  state[kRate - 1u] ^= 0x80u;
  phoenix_sdr_dsp::pqc::dr1::keccak_f1600(state);

  // Rejection sampling into Z_q (q = 12289, 5 * q = 61445)
  uint32_t count = 0;
  uint32_t squeeze_idx = 0;
  while (count < n) {
    if (squeeze_idx + 2 > kRate) {
      phoenix_sdr_dsp::pqc::dr1::keccak_f1600(state);
      squeeze_idx = 0;
    }
    const uint32_t w = static_cast<uint32_t>(state[squeeze_idx]) |
                       (static_cast<uint32_t>(state[squeeze_idx + 1]) << 8);
    squeeze_idx += 2;
    if (w < 61445u) {
      c_out[count++] = static_cast<int16_t>(w % 12289u);
    }
  }
}

// Normative FIPS 206 signature decompressor (from pornin/c-fn-dsa codec.c)
__attribute__((noinline)) static bool comp_decode(
    uint32_t log_n,
    const uint8_t *d,
    uint32_t dlen,
    int16_t *s_out) {
  const uint32_t n = 1u << log_n;
  uint32_t acc = 0;
  uint32_t acc_len = 0;
  uint32_t j = 0;

  DR22_DISABLE_UNROLL
  for (uint32_t i = 0; i < n; ++i) {
    if (j >= dlen) return false;
    acc |= static_cast<uint32_t>(d[j++]) << acc_len;
    const uint32_t t = acc & 1u;
    uint32_t m = (acc >> 1) & 0x7Fu;
    acc >>= 8;

    if (acc == 0) {
      if (j >= dlen) return false;
      acc |= static_cast<uint32_t>(d[j++]) << acc_len;
      acc_len += 8;
      if (acc == 0) return false;
    }

    uint32_t tz = 0;
    uint32_t tmp_acc = acc;
    while ((tmp_acc & 1u) == 0) {
      tz++;
      tmp_acc >>= 1;
    }

    m += tz << 7;
    if (m > static_cast<uint32_t>(B_INF)) return false;
    acc >>= tz + 1;
    acc_len -= tz + 1;

    if (m == 0 && t != 0) return false;

    const int32_t val = (t != 0) ? -static_cast<int32_t>(m) : static_cast<int32_t>(m);
    s_out[i] = static_cast<int16_t>(val);
  }
  return true;
}

// Falcon Round 3 MSB-first compressed signature decompressor (NIST KAT .rsp / falcon-sign.info / BouncyCastle)
__attribute__((noinline)) static bool comp_decode_falcon(
    const uint8_t *srcin,
    uint32_t max_in_len,
    int16_t *s_out,
    uint32_t log_n) {
  const uint32_t n = 1u << log_n;
  uint32_t acc = 0;
  uint32_t acc_len = 0;
  uint32_t v = 0;

  DR22_DISABLE_UNROLL
  for (uint32_t u = 0; u < n; ++u) {
    if (v >= max_in_len) return false;
    acc = (acc << 8) | static_cast<uint32_t>(srcin[v++]);
    const uint32_t b = (acc >> acc_len) & 0xFFu;
    const uint32_t s_sign = b & 128u;
    uint32_t m = b & 127u;

    while (true) {
      if (acc_len == 0) {
        if (v >= max_in_len) return false;
        acc = (acc << 8) | static_cast<uint32_t>(srcin[v++]);
        acc_len = 8;
      }
      acc_len--;
      if (((acc >> acc_len) & 1u) != 0) {
        break;
      }
      m += 128u;
      if (m > 2047u) return false;
    }

    if (s_sign != 0 && m == 0) return false;
    s_out[u] = static_cast<int16_t>(s_sign != 0 ? -static_cast<int32_t>(m) : static_cast<int32_t>(m));
  }
  return true;
}

// Falcon Round 3 big-endian public key unpack (modq_decode)
__attribute__((noinline)) static bool modq_decode(
    const uint8_t *srcin,
    uint32_t max_in_len,
    int16_t *h_out,
    uint32_t log_n) {
  const uint32_t n = 1u << log_n;
  uint32_t acc = 0;
  uint32_t acc_len = 0;
  uint32_t buf = 0;
  uint32_t u = 0;

  DR22_DISABLE_UNROLL
  while (u < n) {
    if (buf >= max_in_len) return false;
    acc = (acc << 8) | static_cast<uint32_t>(srcin[buf++]);
    acc_len += 8;
    if (acc_len >= 14) {
      acc_len -= 14;
      const uint32_t w = (acc >> acc_len) & 0x3FFFu;
      if (w >= 12289u) return false;
      h_out[u++] = static_cast<int16_t>(w);
    }
  }
  return true;
}

// Falcon Round 3 big-endian word extraction HashToPoint
__attribute__((noinline)) static void hash_to_point_be(
    const uint8_t salt[40],
    const uint8_t *msg,
    uint32_t msg_len,
    int16_t *c_out,
    uint32_t n) {
  alignas(8) uint8_t state[200];
  clear_bytes(state, 200);
  constexpr uint32_t kRate = 136u;
  uint32_t spos = 0;

  DR22_DISABLE_UNROLL
  for (uint32_t i = 0; i < 40; ++i) {
    state[spos++] ^= salt[i];
    if (spos == kRate) {
      phoenix_sdr_dsp::pqc::dr1::keccak_f1600(state);
      spos = 0;
    }
  }

  DR22_DISABLE_UNROLL
  for (uint32_t i = 0; i < msg_len; ++i) {
    state[spos++] ^= msg[i];
    if (spos == kRate) {
      phoenix_sdr_dsp::pqc::dr1::keccak_f1600(state);
      spos = 0;
    }
  }

  state[spos] ^= 0x1Fu;
  state[kRate - 1u] ^= 0x80u;
  phoenix_sdr_dsp::pqc::dr1::keccak_f1600(state);

  uint32_t count = 0;
  uint32_t squeeze_idx = 0;
  while (count < n) {
    if (squeeze_idx + 2 > kRate) {
      phoenix_sdr_dsp::pqc::dr1::keccak_f1600(state);
      squeeze_idx = 0;
    }
    const uint32_t w = (static_cast<uint32_t>(state[squeeze_idx]) << 8) |
                        static_cast<uint32_t>(state[squeeze_idx + 1]);
    squeeze_idx += 2;
    if (w < 61445u) {
      c_out[count++] = static_cast<int16_t>(w % 12289u);
    }
  }
}

} // namespace phoenix_sdr_dsp::pqc::dr22
