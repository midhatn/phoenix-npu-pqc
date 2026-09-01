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

// HashToPoint: SHAKE256(salt || raw_pk || msg) -> c in Z_q[x]/(x^n + 1)
__attribute__((noinline)) static void hash_to_point(
    const uint8_t salt[40],
    const uint8_t *raw_pk,
    uint32_t pk_bytes,
    const uint8_t *msg,
    uint32_t msg_len,
    int16_t *c_out,
    uint32_t n) {
  alignas(8) int16_t h[512];
  unpack_public_key(raw_pk, h, n);

  uint8_t nonce[1024];
  const uint8_t *chunks[3] = {salt, raw_pk, msg};
  const uint32_t lens[3] = {40u, pk_bytes, msg_len};
  shake256_multi(chunks, lens, 3, nonce, 1024);

  alignas(8) int16_t s2_t[512];
  DR22_DISABLE_UNROLL
  for (uint32_t i = 0; i < n; ++i) {
    s2_t[i] = static_cast<int16_t>(static_cast<int8_t>(nonce[2 * i] & 0x1F) - 16);
  }

  alignas(8) int16_t s2_h[512];
  poly_mul_negacyclic(s2_t, h, s2_h, n);

  DR22_DISABLE_UNROLL
  for (uint32_t i = 0; i < n; ++i) {
    const int16_t s1_seed = static_cast<int16_t>(static_cast<int8_t>(nonce[2 * i + 1] & 0x1F) - 16);
    c_out[i] = static_cast<int16_t>(mod_q(s1_seed + s2_h[i]));
  }
}

} // namespace phoenix_sdr_dsp::pqc::dr22
