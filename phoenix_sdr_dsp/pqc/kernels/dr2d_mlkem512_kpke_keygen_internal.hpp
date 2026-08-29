// SPDX-License-Identifier: Apache-2.0
// Private DR2d token layouts and operation-local helpers.  No layout in this
// file is a public ABI: every record is carried only by an internal ObjectFIFO.
#pragma once

#include <cstdint>
#include <new>

#include "dr1_keccak_f1600.hpp"

#if defined(__clang__)
#define DR2D_DISABLE_UNROLL _Pragma("clang loop unroll(disable)")
#else
#define DR2D_DISABLE_UNROLL
#endif

namespace phoenix_sdr_dsp::pqc::dr2d {
constexpr uint32_t kN = 256, kQ = 3329, kRate128 = 168, kRate256 = 136;
constexpr uint32_t kRateG = 72, kBlockCap = 5, kPrfBytes = 192;
constexpr uint32_t kOk = 0, kLimitExceeded = 1, kBadDescriptor = 2, kBadToken = 3;
constexpr uint32_t kSeedHeaderBytes = 16, kSeedTokenBytes = 80;
constexpr uint32_t kSecretHeaderBytes = 16, kSecretTokenBytes = 2096;
constexpr uint32_t kStateHeaderBytes = 16, kStateTokenBytes = 2096;
constexpr uint32_t kMatrixHeaderBytes = 16, kMatrixTokenBytes = 3120;
constexpr uint32_t kFinalHeaderBytes = 32, kFinalTokenBytes = 2112;
constexpr uint32_t kRhoOffset = 16, kSigmaOffset = 48, kSecretPolyOffset = 48;
constexpr uint32_t kSecretS0Offset = 48, kSecretS1Offset = 560;
constexpr uint32_t kSecretE0Offset = 1072, kSecretE1Offset = 1584;
constexpr uint32_t kStateSecretOffset = 48, kStateS1Offset = 560;
constexpr uint32_t kStateT0Offset = 1072, kStateE1Offset = 1584;
constexpr uint32_t kMatrixSecretOffset = 48, kMatrixS1Offset = 560;
constexpr uint32_t kMatrixCarry0Offset = 1072, kMatrixCarry1Offset = 1584;
constexpr uint32_t kMatrixA0Offset = 2096, kMatrixA1Offset = 2608;
constexpr uint32_t kFinalRhoOffset = 32, kFinalS0Offset = 64;
constexpr uint32_t kFinalS1Offset = 576, kFinalT0Offset = 1088, kFinalT1Offset = 1600;

// Every DR2d token region that a normal-path coefficient store or bulk
// coefficient copy targets starts on a 32-bit boundary relative to its token
// base, so a single check of the token base statically justifies every
// full-word store below.  rho regions are excluded on purpose: rho is not
// coefficient storage and keeps its physically validated byte copies.
static_assert(kSigmaOffset % 4 == 0 && kSecretPolyOffset % 4 == 0,
              "DR2d shared polynomial offsets must be 32-bit aligned");
static_assert(kSecretS0Offset % 4 == 0 && kSecretS1Offset % 4 == 0 &&
                  kSecretE0Offset % 4 == 0 && kSecretE1Offset % 4 == 0,
              "DR2d secret-token polynomial offsets must be 32-bit aligned");
static_assert(kStateSecretOffset % 4 == 0 && kStateS1Offset % 4 == 0 &&
                  kStateT0Offset % 4 == 0 && kStateE1Offset % 4 == 0,
              "DR2d state-token polynomial offsets must be 32-bit aligned");
static_assert(kMatrixSecretOffset % 4 == 0 && kMatrixS1Offset % 4 == 0 &&
                  kMatrixCarry0Offset % 4 == 0 && kMatrixCarry1Offset % 4 == 0 &&
                  kMatrixA0Offset % 4 == 0 && kMatrixA1Offset % 4 == 0,
              "DR2d matrix-token polynomial offsets must be 32-bit aligned");
static_assert(kFinalRhoOffset % 4 == 0 && kFinalS0Offset % 4 == 0 &&
                  kFinalS1Offset % 4 == 0 && kFinalT0Offset % 4 == 0 &&
                  kFinalT1Offset % 4 == 0,
              "DR2d final-token polynomial offsets must be 32-bit aligned");
static_assert((2 * kN) % 4 == 0 && (4 * kN) % 4 == 0 && (8 * kN) % 4 == 0 &&
                  kN % 2 == 0,
              "DR2d coefficient copy spans must be whole 32-bit words");
#if defined(__BYTE_ORDER__) && defined(__ORDER_LITTLE_ENDIAN__)
static_assert(__BYTE_ORDER__ == __ORDER_LITTLE_ENDIAN__,
              "DR2d full-word coefficient stores assume a little-endian target");
#endif

// FIPS 203 kZetas in 7-bit bit-reversed order, frozen from physically
// validated DR2c.  No runtime bit reversal or modular exponentiation exists.
constexpr uint16_t kZetas[128] = {
    1u, 1729u, 2580u, 3289u, 2642u, 630u, 1897u, 848u,
    1062u, 1919u, 193u, 797u, 2786u, 3260u, 569u, 1746u,
    296u, 2447u, 1339u, 1476u, 3046u, 56u, 2240u, 1333u,
    1426u, 2094u, 535u, 2882u, 2393u, 2879u, 1974u, 821u,
    289u, 331u, 3253u, 1756u, 1197u, 2304u, 2277u, 2055u,
    650u, 1977u, 2513u, 632u, 2865u, 33u, 1320u, 1915u,
    2319u, 1435u, 807u, 452u, 1438u, 2868u, 1534u, 2402u,
    2647u, 2617u, 1481u, 648u, 2474u, 3110u, 1227u, 910u,
    17u, 2761u, 583u, 2649u, 1637u, 723u, 2288u, 1100u,
    1409u, 2662u, 3281u, 233u, 756u, 2156u, 3015u, 3050u,
    1703u, 1651u, 2789u, 1789u, 1847u, 952u, 1461u, 2687u,
    939u, 2308u, 2437u, 2388u, 733u, 2337u, 268u, 641u,
    1584u, 2298u, 2037u, 3220u, 375u, 2549u, 2090u, 1645u,
    1063u, 319u, 2773u, 757u, 2099u, 561u, 2466u, 2594u,
    2804u, 1092u, 403u, 1026u, 1143u, 2150u, 2775u, 886u,
    1722u, 1212u, 1874u, 1029u, 2110u, 2935u, 885u, 2154u,
};

static inline void clear_bytes(void *address, uint32_t bytes) {
  volatile uint8_t *out = static_cast<volatile uint8_t *>(address);
  DR2D_DISABLE_UNROLL
  for (uint32_t i = 0; i < bytes; ++i) out[i] = 0;
}
static inline uint16_t load_le16(const uint8_t *in) {
  return static_cast<uint16_t>(in[0]) | (static_cast<uint16_t>(in[1]) << 8);
}
static inline uint32_t load_le32(const uint8_t *in) {
  return static_cast<uint32_t>(in[0]) | (static_cast<uint32_t>(in[1]) << 8) |
         (static_cast<uint32_t>(in[2]) << 16) | (static_cast<uint32_t>(in[3]) << 24);
}
// ---------------------------------------------------------------------------
// Normal-path coefficient stores are full 32-bit words only.
//
// The installed Peano (llvm-aie 21.0.0, commit c9c5ecb7) is ancestral to
// upstream fix f1baf5a (PR #1221) and mis-schedules the high half of a
// sub-word store that lands in a zero-overhead-loop end bundle.  The failing
// DR2d diagnostic producer ELF carried high-byte `st.s8` in every coefficient
// ZOL loop-end bundle (0x8ac/0x8c0, 0x94a/0x960, 0x9e0/0xa00, 0xa70/0xa90);
// the full-word producer variant physically PASSED on Phoenix with the exact
// 1,588-byte terminal record and exit code 0.  Production therefore uses the
// same construct: one aligned 32-bit store per coefficient pair, and whole
// 32-bit words for bulk coefficient/carry copies.  The former 16-bit store
// helper is deleted outright, so no DR2d coefficient loop can regress to a
// sub-word store.
//
// Scope is deliberately limited to coefficient-bearing and polynomial-carry
// token regions.  Byte stores that are NOT coefficient storage are retained
// unchanged, because the diagnostic probe physically validated that shape and
// widening them would add unjustified code-generation scope: local Keccak/SHAKE
// absorption and domain padding, local PRF buffers, rho/sigma extraction and
// the 32-byte rho token copies, header fields via store_le32, volatile
// clear_bytes zeroization, and the entire unchanged serializer.
//
// C++17 lifetime/aliasing: each word begins a new uint32_t object's lifetime
// in the token's unsigned-char storage with placement new ([intro.object],
// [basic.life]) rather than writing through a cast pointer, so no object of
// the wrong type is ever accessed.  Consumers only ever read that object's
// representation through unsigned char (load_le16/load_le32/canonical_poly/
// the serializer) or overwrite it byte-wise via volatile clear_bytes; both
// directions are permitted.  Alignment is verified at run time and every
// failure is closed by the calling worker.
static inline bool word_aligned(const void *address) {
  constexpr uintptr_t kWordAlignmentMask = alignof(uint32_t) - 1u;
  return (reinterpret_cast<uintptr_t>(address) & kWordAlignmentMask) == 0;
}
static inline void store_pair_word(uint8_t *out, uint32_t pair, uint32_t a,
                                   uint32_t b) {
  const uint32_t word = (a & 0xffffu) | ((b & 0xffffu) << 16);
  ::new (static_cast<void *>(out + 4 * pair)) uint32_t(word);
}
static inline bool copy_words(uint8_t *destination, const uint8_t *source,
                              uint32_t bytes) {
  if ((bytes & 3u) != 0 || !word_aligned(destination) || !word_aligned(source))
    return false;
  const uint32_t words = bytes / 4u;
  DR2D_DISABLE_UNROLL
  for (uint32_t word = 0; word < words; ++word)
    ::new (static_cast<void *>(destination + 4 * word))
        uint32_t(load_le32(source + 4 * word));
  return true;
}
static inline void store_le32(uint8_t *out, uint32_t x) {
  out[0] = static_cast<uint8_t>(x); out[1] = static_cast<uint8_t>(x >> 8);
  out[2] = static_cast<uint8_t>(x >> 16); out[3] = static_cast<uint8_t>(x >> 24);
}
static inline bool valid_status(uint32_t status) { return status <= kBadToken; }
static inline bool valid_header(const uint8_t *token, uint32_t header_bytes) {
  if (!valid_status(load_le32(token + 4))) return false;
  DR2D_DISABLE_UNROLL
  for (uint32_t i = 8; i < header_bytes; ++i)
    if (token[i] != 0) return false;
  return true;
}
static inline void write_header(uint8_t *token, uint32_t token_bytes, uint32_t id,
                                uint32_t status, uint32_t header_bytes) {
  clear_bytes(token, token_bytes);
  store_le32(token, id); store_le32(token + 4, status);
  (void)header_bytes;  // Clear above fixes every reserved header byte to zero.
}
static inline bool valid_descriptor(const uint8_t d[16]) {
  return d[0] == 1 && d[1] == 0x24 && d[2] == 0x52 && d[3] == 0 &&
         d[4] == 2 && d[5] == 3 && d[6] == kBlockCap && d[7] == 0 &&
         d[12] == 0 && d[13] == 0 && d[14] == 0 && d[15] == 0;
}
static inline bool canonical_poly(const uint8_t *poly) {
  DR2D_DISABLE_UNROLL
  for (uint32_t i = 0; i < kN; ++i)
    if (load_le16(poly + 2 * i) >= kQ) return false;
  return true;
}
static inline uint32_t mod_mul(uint32_t a, uint32_t b) {
  const uint32_t Y = a * b;
  const uint32_t q = (static_cast<uint64_t>(Y) * 1290167u) >> 32;
  uint32_t r = Y - q * 3329u;
  if (r >= 3329u) r -= 3329u;
  if (r >= 3329u) r -= 3329u;
  return r;
}

static inline void derive_g(const uint8_t d[32], uint8_t rho[32], uint8_t sigma[32]) {
  alignas(8) uint8_t state[200];
  clear_bytes(state, sizeof(state));
  DR2D_DISABLE_UNROLL
  for (uint32_t i = 0; i < 32; ++i) state[i] ^= d[i];
  state[32] ^= 2; state[33] ^= 0x06; state[kRateG - 1] ^= 0x80;
  phoenix_sdr_dsp::pqc::dr1::keccak_f1600(state);
  DR2D_DISABLE_UNROLL
  for (uint32_t i = 0; i < 32; ++i) { rho[i] = state[i]; sigma[i] = state[32 + i]; }
  clear_bytes(state, sizeof(state));
}

// Expand one A[row,column] directly into packed 16-bit FIFO storage.  Rejection
// sampling accepts one coefficient at a time, so an even-index coefficient is
// buffered in a register and only the completed pair is committed, keeping the
// only store in this loop a full 32-bit word.
static inline bool sample_matrix_store(const uint8_t rho[32], uint8_t column,
                                       uint8_t row, uint8_t out[2 * kN]) {
  if (!word_aligned(out)) return false;
  alignas(8) uint8_t state[200];
  clear_bytes(state, sizeof(state));
  DR2D_DISABLE_UNROLL
  for (uint32_t i = 0; i < 32; ++i) state[i] ^= rho[i];
  state[32] ^= column; state[33] ^= row; state[34] ^= 0x1f; state[kRate128 - 1] ^= 0x80;
  phoenix_sdr_dsp::pqc::dr1::keccak_f1600(state);
  uint32_t accepted = 0, pending = 0;
  DR2D_DISABLE_UNROLL
  for (uint32_t block = 0; block < kBlockCap && accepted < kN; ++block) {
    if (block != 0) phoenix_sdr_dsp::pqc::dr1::keccak_f1600(state);
    DR2D_DISABLE_UNROLL
    for (uint32_t offset = 0; offset < kRate128 && accepted < kN; offset += 3) {
      const uint32_t d1 = state[offset] + 256u * (state[offset + 1] & 0x0fu);
      const uint32_t d2 = (state[offset + 1] >> 4) + 16u * state[offset + 2];
      if (d1 < kQ) {
        if ((accepted & 1u) == 0) pending = d1;
        else store_pair_word(out, accepted >> 1, pending, d1);
        ++accepted;
      }
      if (d2 < kQ && accepted < kN) {
        if ((accepted & 1u) == 0) pending = d2;
        else store_pair_word(out, accepted >> 1, pending, d2);
        ++accepted;
      }
    }
  }
  pending = 0;
  clear_bytes(state, sizeof(state));
  // kN is even, so a complete polynomial always committed its final pair; an
  // incomplete one is discarded by the caller's fail-closed header rewrite.
  return accepted == kN;
}

// Add MultiplyNTTs(a,b) to an existing NTT polynomial in place.  This avoids
// full product/accumulator arrays and keeps row accumulation stack bounded.
static inline bool add_product_ntt(const uint8_t a[2 * kN], const uint8_t b[2 * kN],
                                   uint8_t accumulator[2 * kN]) {
  if (!word_aligned(accumulator)) return false;
  DR2D_DISABLE_UNROLL
  for (uint32_t i = 0; i < 64; ++i) {
    const uint32_t o = 4 * i, g = kZetas[64 + i];
    const uint32_t a0 = load_le16(a + 2 * o), a1 = load_le16(a + 2 * (o + 1));
    const uint32_t a2 = load_le16(a + 2 * (o + 2)), a3 = load_le16(a + 2 * (o + 3));
    const uint32_t b0 = load_le16(b + 2 * o), b1 = load_le16(b + 2 * (o + 1));
    const uint32_t b2 = load_le16(b + 2 * (o + 2)), b3 = load_le16(b + 2 * (o + 3));
    const uint32_t p0 = (mod_mul(a0, b0) + mod_mul(g, mod_mul(a1, b1))) % kQ;
    const uint32_t p1 = (mod_mul(a0, b1) + mod_mul(a1, b0)) % kQ;
    const uint32_t p2 = (mod_mul(a2, b2) + mod_mul(kQ - g, mod_mul(a3, b3))) % kQ;
    const uint32_t p3 = (mod_mul(a2, b3) + mod_mul(a3, b2)) % kQ;
    const uint32_t values[4] = {p0, p1, p2, p3};
    uint32_t reduced[4] = {0, 0, 0, 0};
    DR2D_DISABLE_UNROLL
    for (uint32_t lane = 0; lane < 4; ++lane) {
      const uint32_t sum = load_le16(accumulator + 2 * (o + lane)) + values[lane];
      reduced[lane] = sum >= kQ ? sum - kQ : sum;
    }
    // Four consecutive lanes at byte offset 8*i are exactly two aligned words.
    store_pair_word(accumulator + 2 * o, 0, reduced[0], reduced[1]);
    store_pair_word(accumulator + 2 * o, 1, reduced[2], reduced[3]);
  }
  return true;
}
}  // namespace phoenix_sdr_dsp::pqc::dr2d
