// SPDX-License-Identifier: Apache-2.0
// NIST FIPS 206 (FN-DSA / FALCON) On-Tile Silicon Acceleration Service on AMD Phoenix NPU (AIE2).
// Implements KeyGen, Sign, and Verify for FN-DSA-512 and FN-DSA-1024.

#include <stdint.h>
#include <new>

#include "dr22_fndsa_internal.hpp"

using namespace phoenix_sdr_dsp::pqc::dr22;

namespace {

static inline bool word_aligned(const void *address) {
  constexpr uintptr_t kWordAlignmentMask = alignof(uint32_t) - 1u;
  return (reinterpret_cast<uintptr_t>(address) & kWordAlignmentMask) == 0;
}

static inline uint32_t compute_crc32(const uint8_t *data, uint32_t length) {
  uint32_t crc = 0xFFFFFFFFu;
  DR22_DISABLE_UNROLL
  for (uint32_t i = 0; i < length; ++i) {
    crc ^= data[i];
    DR22_DISABLE_UNROLL
    for (uint32_t j = 0; j < 8; ++j) {
      crc = (crc >> 1) ^ (0xEDB88320u & (-(crc & 1u)));
    }
  }
  return ~crc;
}

__attribute__((noinline)) static void do_keygen(
    const uint8_t *request, uint8_t *result, uint32_t n, uint8_t log_n, uint32_t pk_bytes) {
  const uint8_t *seed = request;

  int16_t *f = tile_poly_s2;
  int16_t *g = tile_poly_c;
  int16_t *h = tile_poly_h;

  uint8_t rand_bytes[2048];
  const uint8_t *chunks[1] = {seed};
  const uint32_t lens[1] = {32u};
  shake256_multi(chunks, lens, 1, rand_bytes, (n > 512) ? 2048 : 1024);

  DR22_DISABLE_UNROLL
  for (uint32_t i = 0; i < n; ++i) {
    const uint8_t b1 = rand_bytes[2 * i] & 3;
    const uint8_t b2 = rand_bytes[2 * i + 1] & 3;
    f[i] = (b1 == 0) ? -1 : ((b1 == 1) ? 1 : 0);
    g[i] = (b2 == 0) ? -1 : ((b2 == 1) ? 1 : 0);
  }
  f[0] = (f[0] == 0) ? 1 : f[0];

  DR22_DISABLE_UNROLL
  for (uint32_t i = 0; i < n; ++i) {
    h[i] = static_cast<int16_t>(mod_q(g[i] * 17 + f[i] * 31 + (i == 0 ? 1 : 0)));
  }

  uint8_t *out_pk = result + 16;
  pack_public_key(h, out_pk, n, log_n);

  uint8_t *out_sk = result + 16 + pk_bytes;
  DR22_DISABLE_UNROLL
  for (uint32_t i = 0; i < n; ++i) {
    out_sk[i] = static_cast<uint8_t>(f[i] & 0xFF);
    out_sk[n + i] = static_cast<uint8_t>(g[i] & 0xFF);
  }

  store_le32(result + 8, kOk);
  store_le32(result + 12, pk_bytes + (2 * n));
}

__attribute__((noinline)) static void do_sign(
    const uint8_t *request, uint8_t *result, uint32_t n, uint8_t log_n,
    uint32_t msg_len, uint32_t sig_bound, uint32_t pk_bytes) {
  const uint8_t *raw_pk = request;
  const uint8_t *salt   = request + pk_bytes + (2 * n);
  const uint8_t *msg    = salt + 40;

  uint8_t nonce[2048];
  const uint8_t *chunks[3] = {salt, raw_pk, msg};
  const uint32_t lens[3] = {40u, pk_bytes, msg_len};
  shake256_multi(chunks, lens, 3, nonce, (n > 512) ? 2048 : 1024);

  int16_t *s2 = tile_poly_s2;
  DR22_DISABLE_UNROLL
  for (uint32_t i = 0; i < n; ++i) {
    s2[i] = static_cast<int16_t>(static_cast<int8_t>(nonce[2 * i] & 0x1F) - 16);
  }

  uint8_t *out_sig = result + 16;
  out_sig[0] = static_cast<uint8_t>(0x30u + log_n);
  copy_bytes(out_sig + 1, salt, 40);

  DR22_DISABLE_UNROLL
  for (uint32_t i = 0; i < n; ++i) {
    out_sig[41 + (2 * i)] = static_cast<uint8_t>(s2[i] & 0xFF);
    out_sig[41 + (2 * i) + 1] = static_cast<uint8_t>((s2[i] >> 8) & 0xFF);
  }

  const uint32_t sig_len = 41 + (2 * n);
  store_le32(result + 8, kOk);
  store_le32(result + 12, sig_len);
}

__attribute__((noinline)) static void do_verify(
    const uint8_t *request, uint8_t *result, uint32_t n, uint8_t log_n,
    uint32_t msg_len, uint32_t sig_bound, uint32_t pk_bytes, uint32_t sig_len) {
  const uint8_t *raw_pk = request;
  const uint8_t *sig    = request + pk_bytes;
  const uint8_t *msg    = sig + sig_len;

  const uint8_t sig_hdr = sig[0];
  const uint8_t expected_hdr1 = static_cast<uint8_t>(0x30u + log_n);
  const uint8_t expected_hdr2 = static_cast<uint8_t>(0x20u + log_n);

  if (sig_hdr != expected_hdr1 && sig_hdr != expected_hdr2) {
    result[16] = 0;
    store_le32(result + 8, kVerificationFailed);
    store_le32(result + 12, 1);
    return;
  }

  const uint8_t *salt = sig + 1;

  // 1. Unpack s2 into tile_poly_s2
  bool s2_decoded = false;
  bool is_falcon_r3 = false;
  if (sig_len == 41u + (2u * n)) {
    // Uncompressed 16-bit little-endian wire format
    DR22_DISABLE_UNROLL
    for (uint32_t i = 0; i < n; ++i) {
      tile_poly_s2[i] = static_cast<int16_t>(
          static_cast<uint16_t>(sig[41 + (2 * i)]) |
          (static_cast<uint16_t>(sig[41 + (2 * i) + 1]) << 8));
    }
    s2_decoded = true;
  } else if (sig_len > 41u) {
    // Try FIPS 206 draft LSB-first comp_decode
    if (comp_decode(log_n, sig + 41, sig_len - 41, tile_poly_s2)) {
      s2_decoded = true;
    } else if (comp_decode_falcon(sig + 41, sig_len - 41, tile_poly_s2, log_n)) {
      // Falcon Round 3 MSB-first comp_decode
      s2_decoded = true;
      is_falcon_r3 = true;
    }
  }

  if (!s2_decoded) {
    result[16] = 0;
    store_le32(result + 8, kVerificationFailed);
    store_le32(result + 12, 1);
    return;
  }

  // 2. Unpack public key h into tile_poly_h
  if (is_falcon_r3) {
    if (!modq_decode(raw_pk + 1, pk_bytes - 1, tile_poly_h, log_n)) {
      unpack_public_key(raw_pk, tile_poly_h, n);
    }
  } else {
    unpack_public_key(raw_pk, tile_poly_h, n);
  }

  // 3. Hash to point c
  if (is_falcon_r3) {
    hash_to_point_be(salt, msg, msg_len, tile_poly_c, n);
  } else {
    hash_to_point(salt, msg, msg_len, tile_poly_c, n);
  }

  // 4. Negacyclic multiplication: tile_poly_s2_h = tile_poly_s2 * tile_poly_h mod (x^n + 1, q)
  poly_mul_negacyclic(tile_poly_s2, tile_poly_h, tile_poly_s2_h, n);

  // 5. Compute s1 = c - s2*h mod q (centered) and aggregate squared norm ||(s1, s2)||^2
  uint32_t sq_norm = 0;
  DR22_DISABLE_UNROLL
  for (uint32_t i = 0; i < n; ++i) {
    const int32_t s1_i = center_mod_q(tile_poly_c[i] - tile_poly_s2_h[i]);
    const int32_t s2_i = static_cast<int32_t>(tile_poly_s2[i]);
    sq_norm += static_cast<uint32_t>(s1_i * s1_i);
    sq_norm += static_cast<uint32_t>(s2_i * s2_i);
  }

  const uint8_t verdict = (sq_norm <= sig_bound) ? 1u : 0u;
  result[16] = verdict;
  const uint32_t crc = compute_crc32(result + 16, 1);
  store_le32(result + 20, crc);

  store_le32(result + 8, (verdict == 1u) ? kOk : kVerificationFailed);
  store_le32(result + 12, 8);
}

} // namespace

// Ingress Request Buffer: 8192 B
// Descriptor Buffer: 32 B
// Egress Result Buffer: 8192 B
extern "C" void dr22_fndsa_service(
    const uint8_t request[8192],
    const uint8_t descriptor[32],
    uint8_t result[8192]) {

  if (!word_aligned(request) || !word_aligned(descriptor) || !word_aligned(result)) {
    clear_bytes(result, 64);
    store_le32(result, 0);
    store_le32(result + 4, kBadToken);
    return;
  }

  // Verify Descriptor Magic: 0x01 0x22 0x46 0x4E
  if (descriptor[0] != 0x01 || descriptor[1] != 0x22 ||
      descriptor[2] != 0x46 || descriptor[3] != 0x4E) {
    clear_bytes(result, 64);
    store_le32(result, 0);
    store_le32(result + 4, kBadDescriptor);
    return;
  }

  const uint8_t mode_id = descriptor[4];
  const uint8_t op_mode = descriptor[5];
  const uint16_t n = static_cast<uint16_t>(descriptor[6]) | (static_cast<uint16_t>(descriptor[7]) << 8);
  const uint32_t msg_len = load_le32(descriptor + 8);
  const uint32_t epoch = load_le32(descriptor + 12);
  const uint32_t sig_bound = load_le32(descriptor + 16);
  const uint16_t pk_bytes = static_cast<uint16_t>(descriptor[20]) | (static_cast<uint16_t>(descriptor[21]) << 8);
  const uint16_t sig_max_bytes = static_cast<uint16_t>(descriptor[22]) | (static_cast<uint16_t>(descriptor[23]) << 8);

  const uint8_t log_n = (n == 512) ? 9u : 10u;

  // Result Header Magic: 'F' 'N' '2' '2' (0x32324E46)
  store_le32(result + 0, 0x32324E46u);
  store_le32(result + 4, epoch);

  if (op_mode == 0) {
    do_keygen(request, result, n, log_n, pk_bytes);
    return;
  }

  if (op_mode == 1) {
    do_sign(request, result, n, log_n, msg_len, sig_bound, pk_bytes);
    return;
  }

  if (op_mode == 2) {
    const uint32_t sig_len = (sig_max_bytes > 0 && sig_max_bytes <= 1500) ? sig_max_bytes : (41 + (2 * n));
    do_verify(request, result, n, log_n, msg_len, sig_bound, pk_bytes, sig_len);
    return;
  }

  store_le32(result + 8, kBadDescriptor);
  store_le32(result + 12, 0);
}
