// SPDX-License-Identifier: Apache-2.0
// NIST FIPS 205 (SLH-DSA / SPHINCS+) Core Internal Subroutines for AMD Phoenix AIE2.
#pragma once

#include <stdint.h>
#include <new>

#include "dr1_keccak_f1600.hpp"

#if defined(__clang__)
#define DR21_DISABLE_UNROLL _Pragma("clang loop unroll(disable)")
#else
#define DR21_DISABLE_UNROLL
#endif

namespace phoenix_sdr_dsp::pqc::dr21 {

constexpr uint32_t kOk = 0u;
constexpr uint32_t kBadDescriptor = 2u;
constexpr uint32_t kBadToken = 3u;
constexpr uint32_t kLimitExceeded = 4u;
constexpr uint32_t kVerificationFailed = 5u;

constexpr uint32_t ADRS_TYPE_WOTS_HASH  = 0u;
constexpr uint32_t ADRS_TYPE_WOTS_PK    = 1u;
constexpr uint32_t ADRS_TYPE_TREE       = 2u;
constexpr uint32_t ADRS_TYPE_FORS_TREE  = 3u;
constexpr uint32_t ADRS_TYPE_FORS_ROOTS = 4u;
constexpr uint32_t ADRS_TYPE_WOTS_PRF   = 5u;
constexpr uint32_t ADRS_TYPE_FORS_PRF   = 6u;

__attribute__((noinline)) static void clear_bytes(uint8_t *destination, uint32_t bytes) {
  DR21_DISABLE_UNROLL
  for (uint32_t index = 0; index < bytes; ++index) destination[index] = 0u;
}

static inline void copy_bytes(uint8_t *dest, const uint8_t *src, uint32_t bytes) {
  DR21_DISABLE_UNROLL
  for (uint32_t i = 0; i < bytes; ++i) dest[i] = src[i];
}

static inline uint32_t load_be32(const uint8_t *in) {
  return (static_cast<uint32_t>(in[0]) << 24) | (static_cast<uint32_t>(in[1]) << 16) |
         (static_cast<uint32_t>(in[2]) << 8) | static_cast<uint32_t>(in[3]);
}

static inline void store_be32(uint8_t *out, uint32_t val) {
  out[0] = static_cast<uint8_t>((val >> 24) & 0xFFu);
  out[1] = static_cast<uint8_t>((val >> 16) & 0xFFu);
  out[2] = static_cast<uint8_t>((val >> 8) & 0xFFu);
  out[3] = static_cast<uint8_t>(val & 0xFFu);
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

static inline void set_adrs_layer(uint8_t adrs[32], uint32_t layer) {
  store_be32(adrs, layer);
}

static inline void set_adrs_type(uint8_t adrs[32], uint32_t type) {
  store_be32(adrs + 16, type);
  store_be32(adrs + 20, 0);
  store_be32(adrs + 24, 0);
  store_be32(adrs + 28, 0);
}

static inline void set_adrs_keypair(uint8_t adrs[32], uint32_t kp) {
  store_be32(adrs + 20, kp);
}

static inline void set_adrs_chain(uint8_t adrs[32], uint32_t chain) {
  store_be32(adrs + 24, chain);
}

static inline void set_adrs_hash(uint8_t adrs[32], uint32_t hash_idx) {
  store_be32(adrs + 28, hash_idx);
}

static inline void set_adrs_tree_height(uint8_t adrs[32], uint32_t height) {
  store_be32(adrs + 24, height);
}

static inline void set_adrs_tree_index(uint8_t adrs[32], uint32_t index) {
  store_be32(adrs + 28, index);
}

// Unified multi-chunk SHAKE-256 implementation on AIE2
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

  DR21_DISABLE_UNROLL
  for (uint32_t c = 0; c < num_chunks; ++c) {
    const uint8_t *data = chunks[c];
    const uint32_t clen = lens[c];
    DR21_DISABLE_UNROLL
    for (uint32_t i = 0; i < clen; ++i) {
      state[spos++] ^= data[i];
      if (spos == kRate) {
        phoenix_sdr_dsp::pqc::dr1::keccak_f1600(state);
        spos = 0;
      }
    }
  }

  // Padding for SHAKE256: 0x1F suffix, 0x80 on last rate byte
  state[spos] ^= 0x1Fu;
  state[kRate - 1u] ^= 0x80u;
  phoenix_sdr_dsp::pqc::dr1::keccak_f1600(state);

  // Squeeze out_len bytes
  uint32_t squeezed = 0;
  while (out_len > 0) {
    const uint32_t take = (out_len < kRate) ? out_len : kRate;
    DR21_DISABLE_UNROLL
    for (uint32_t i = 0; i < take; ++i) out[squeezed + i] = state[i];
    squeezed += take;
    out_len -= take;
    if (out_len > 0) {
      phoenix_sdr_dsp::pqc::dr1::keccak_f1600(state);
    }
  }
}

// Compare squeezed output against an actual buffer streamingly (zero stack overhead)
__attribute__((noinline)) static bool verify_stream_match(
    const uint8_t *const chunks[],
    const uint32_t lens[],
    uint32_t num_chunks,
    const uint8_t *expected_stream,
    uint32_t stream_len) {
  alignas(8) uint8_t state[200];
  clear_bytes(state, 200);
  constexpr uint32_t kRate = 136u;
  uint32_t spos = 0;

  DR21_DISABLE_UNROLL
  for (uint32_t c = 0; c < num_chunks; ++c) {
    const uint8_t *data = chunks[c];
    const uint32_t clen = lens[c];
    DR21_DISABLE_UNROLL
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

  uint8_t diff = 0;
  uint32_t offset = 0;
  while (stream_len > 0) {
    const uint32_t take = (stream_len < kRate) ? stream_len : kRate;
    DR21_DISABLE_UNROLL
    for (uint32_t i = 0; i < take; ++i) {
      diff |= (state[i] ^ expected_stream[offset + i]);
    }
    offset += take;
    stream_len -= take;
    if (stream_len > 0) {
      phoenix_sdr_dsp::pqc::dr1::keccak_f1600(state);
    }
  }
  return (diff == 0);
}

// PRF: SHAKE256(PK.seed || ADRS || SK.seed, n)
__attribute__((noinline)) static void slh_prf(
    const uint8_t *pk_seed, const uint8_t *sk_seed,
    const uint8_t adrs[32], uint8_t *out, uint32_t n) {
  const uint8_t *const chunks[3] = {pk_seed, adrs, sk_seed};
  const uint32_t lens[3] = {n, 32u, n};
  shake256_multi(chunks, lens, 3, out, n);
}

// F: SHAKE256(PK.seed || ADRS || M1, n)
__attribute__((noinline)) static void slh_f(
    const uint8_t *pk_seed, const uint8_t adrs[32],
    const uint8_t *m, uint8_t *out, uint32_t n) {
  const uint8_t *const chunks[3] = {pk_seed, adrs, m};
  const uint32_t lens[3] = {n, 32u, n};
  shake256_multi(chunks, lens, 3, out, n);
}

// Chaining function: chain(X, i, s, PK.seed, ADRS)
__attribute__((noinline)) static void slh_chain(
    const uint8_t *x, uint32_t i, uint32_t s,
    const uint8_t *pk_seed, uint8_t adrs[32], uint8_t *out, uint32_t n) {
  uint8_t curr[32];
  copy_bytes(curr, x, n);

  DR21_DISABLE_UNROLL
  for (uint32_t j = i; j < i + s; ++j) {
    set_adrs_hash(adrs, j);
    uint8_t nxt[32];
    slh_f(pk_seed, adrs, curr, nxt, n);
    copy_bytes(curr, nxt, n);
  }
  copy_bytes(out, curr, n);
}

// WOTS+ PKGen streaming directly into T_l (eliminates 2KB stack allocation)
__attribute__((noinline)) static void wots_pk_gen(
    const uint8_t *sk_seed, const uint8_t *pk_seed,
    uint8_t adrs[32], uint8_t *pk_out, uint32_t n, uint32_t len_total, uint32_t w) {
  uint8_t adrs_copy[32];
  copy_bytes(adrs_copy, adrs, 32);

  alignas(8) uint8_t tl_state[200];
  clear_bytes(tl_state, 200);
  constexpr uint32_t kRate = 136u;
  uint32_t tl_pos = 0;

  // Absorb pk_seed and wots_pk_adrs into T_l state
  uint8_t wots_pk_adrs[32];
  copy_bytes(wots_pk_adrs, adrs, 32);
  set_adrs_type(wots_pk_adrs, ADRS_TYPE_WOTS_PK);
  set_adrs_keypair(wots_pk_adrs, load_be32(adrs + 20));

  DR21_DISABLE_UNROLL
  for (uint32_t i = 0; i < n; ++i) {
    tl_state[tl_pos++] ^= pk_seed[i];
    if (tl_pos == kRate) { phoenix_sdr_dsp::pqc::dr1::keccak_f1600(tl_state); tl_pos = 0; }
  }
  DR21_DISABLE_UNROLL
  for (uint32_t i = 0; i < 32; ++i) {
    tl_state[tl_pos++] ^= wots_pk_adrs[i];
    if (tl_pos == kRate) { phoenix_sdr_dsp::pqc::dr1::keccak_f1600(tl_state); tl_pos = 0; }
  }

  // Generate and absorb each WOTS+ chain end directly
  DR21_DISABLE_UNROLL
  for (uint32_t i = 0; i < len_total; ++i) {
    set_adrs_chain(adrs_copy, i);
    set_adrs_hash(adrs_copy, 0);
    set_adrs_type(adrs_copy, ADRS_TYPE_WOTS_PRF);
    uint8_t sk_i[32];
    slh_prf(pk_seed, sk_seed, adrs_copy, sk_i, n);

    set_adrs_type(adrs_copy, ADRS_TYPE_WOTS_HASH);
    uint8_t pk_i[32];
    slh_chain(sk_i, 0, w - 1, pk_seed, adrs_copy, pk_i, n);

    DR21_DISABLE_UNROLL
    for (uint32_t j = 0; j < n; ++j) {
      tl_state[tl_pos++] ^= pk_i[j];
      if (tl_pos == kRate) { phoenix_sdr_dsp::pqc::dr1::keccak_f1600(tl_state); tl_pos = 0; }
    }
  }

  // Pad and squeeze T_l
  tl_state[tl_pos] ^= 0x1Fu;
  tl_state[kRate - 1u] ^= 0x80u;
  phoenix_sdr_dsp::pqc::dr1::keccak_f1600(tl_state);

  DR21_DISABLE_UNROLL
  for (uint32_t i = 0; i < n; ++i) pk_out[i] = tl_state[i];
}

} // namespace phoenix_sdr_dsp::pqc::dr21
