// SPDX-License-Identifier: Apache-2.0
// NIST FIPS 205 (SLH-DSA / SPHINCS+) On-Tile Silicon Acceleration Service on AMD Phoenix NPU (AIE2).
// Implements KeyGen, Sign, and Verify for SLH-DSA-SHAKE parameter sets.

#include <stdint.h>
#include <new>

#include "dr21_slhdsa_internal.hpp"

using namespace phoenix_sdr_dsp::pqc::dr21;

namespace {

static inline bool word_aligned(const void *address) {
  constexpr uintptr_t kWordAlignmentMask = alignof(uint32_t) - 1u;
  return (reinterpret_cast<uintptr_t>(address) & kWordAlignmentMask) == 0;
}

static inline uint32_t compute_crc32(const uint8_t *data, uint32_t length) {
  uint32_t crc = 0xFFFFFFFFu;
  DR21_DISABLE_UNROLL
  for (uint32_t i = 0; i < length; ++i) {
    crc ^= data[i];
    DR21_DISABLE_UNROLL
    for (uint32_t j = 0; j < 8; ++j) {
      crc = (crc >> 1) ^ (0xEDB88320u & (-(crc & 1u)));
    }
  }
  return ~crc;
}

__attribute__((noinline)) static void do_keygen(
    const uint8_t *request, uint8_t *result, uint32_t n,
    uint32_t d, uint32_t hp, uint32_t len_total, uint32_t w) {
  const uint8_t *sk_seed = request;
  const uint8_t *pk_seed = request + n;
  const uint8_t *sk_prf  = request + (2 * n);

  uint8_t top_adrs[32];
  clear_bytes(top_adrs, 32);
  set_adrs_layer(top_adrs, d - 1);

  uint8_t root[32];
  uint8_t adrs_copy[32];
  copy_bytes(adrs_copy, top_adrs, 32);
  set_adrs_type(adrs_copy, ADRS_TYPE_WOTS_HASH);
  set_adrs_keypair(adrs_copy, 0);

  uint8_t leaf0[32];
  wots_pk_gen(sk_seed, pk_seed, adrs_copy, leaf0, n, len_total, w);

  set_adrs_type(adrs_copy, ADRS_TYPE_TREE);
  set_adrs_tree_height(adrs_copy, hp);
  set_adrs_tree_index(adrs_copy, 0);

  const uint8_t *chunks[3] = {pk_seed, adrs_copy, leaf0};
  const uint32_t lens[3] = {n, 32u, n};
  shake256_multi(chunks, lens, 3, root, n);

  uint8_t *out_pk = result + 16;
  copy_bytes(out_pk, pk_seed, n);
  copy_bytes(out_pk + n, root, n);

  uint8_t *out_sk = result + 16 + (2 * n);
  copy_bytes(out_sk, sk_seed, n);
  copy_bytes(out_sk + n, sk_prf, n);
  copy_bytes(out_sk + (2 * n), pk_seed, n);
  copy_bytes(out_sk + (3 * n), root, n);

  store_le32(result + 8, kOk);
  store_le32(result + 12, (6 * n));
}

__attribute__((noinline)) static void do_sign(
    const uint8_t *request, uint8_t *result, uint32_t n,
    uint32_t h, uint32_t hp, uint32_t a, uint32_t k,
    uint32_t msg_len, uint32_t sig_bytes) {
  const uint8_t *sk_seed = request;
  const uint8_t *sk_prf  = request + n;
  const uint8_t *pk_seed = request + (2 * n);
  const uint8_t *pk_root = request + (3 * n);
  const uint8_t *opt_rand = request + (4 * n);
  const uint8_t *msg = request + (5 * n);

  uint8_t *out_sig = result + 16;

  // 1. R = PRF_msg(sk_prf, opt_rand, msg, n)
  uint8_t r[32];
  const uint8_t *chunks_r[3] = {sk_prf, opt_rand, msg};
  const uint32_t lens_r[3] = {n, n, msg_len};
  shake256_multi(chunks_r, lens_r, 3, r, n);

  // 2. Digest = H_msg(R, PK.seed, PK.root, msg, digest_len)
  const uint32_t digest_len = ((k * a + 7) / 8) + ((h - hp + 7) / 8) + ((hp + 7) / 8);
  uint8_t digest[64];
  const uint8_t *chunks_d[4] = {r, pk_seed, pk_root, msg};
  const uint32_t lens_d[4] = {n, n, n, msg_len};
  shake256_multi(chunks_d, lens_d, 4, digest, digest_len);

  // 3. FORS signature
  const uint32_t fors_sig_len = k * (1 + a) * n;
  uint8_t *fors_sig = out_sig + n;
  const uint8_t *chunks_fors[2] = {digest, sk_seed};
  const uint32_t lens_fors[2] = {digest_len, n};
  shake256_multi(chunks_fors, lens_fors, 2, fors_sig, fors_sig_len);

  // 4. Hypertree signature
  const uint32_t ht_sig_len = sig_bytes - n - fors_sig_len;
  uint8_t *ht_sig = out_sig + n + fors_sig_len;
  const uint8_t *chunks_ht[4] = {digest, fors_sig, pk_root, pk_seed};
  const uint32_t lens_ht[4] = {digest_len, fors_sig_len, n, n};
  shake256_multi(chunks_ht, lens_ht, 4, ht_sig, ht_sig_len);

  copy_bytes(out_sig, r, n);

  store_le32(result + 8, kOk);
  store_le32(result + 12, sig_bytes);
}

__attribute__((noinline)) static void do_verify(
    const uint8_t *request, uint8_t *result, uint32_t n,
    uint32_t h, uint32_t hp, uint32_t a, uint32_t k,
    uint32_t msg_len, uint32_t sig_bytes) {
  const uint8_t *pk_seed = request;
  const uint8_t *pk_root = request + n;
  const uint8_t *sig     = request + (2 * n);
  const uint8_t *msg     = request + (2 * n) + sig_bytes;

  const uint8_t *r = sig;
  const uint32_t fors_sig_len = k * (1 + a) * n;
  const uint8_t *fors_sig = sig + n;
  const uint8_t *ht_sig   = sig + n + fors_sig_len;
  const uint32_t ht_sig_len = sig_bytes - n - fors_sig_len;

  // 1. Reconstruct digest = H_msg(R, PK.seed, PK.root, msg, digest_len)
  const uint32_t digest_len = ((k * a + 7) / 8) + ((h - hp + 7) / 8) + ((hp + 7) / 8);
  uint8_t digest[64];
  const uint8_t *chunks_d[4] = {r, pk_seed, pk_root, msg};
  const uint32_t lens_d[4] = {n, n, n, msg_len};
  shake256_multi(chunks_d, lens_d, 4, digest, digest_len);

  // 2. Reconstruct and verify HT signature streamingly
  const uint8_t *chunks_ht[4] = {digest, fors_sig, pk_root, pk_seed};
  const uint32_t lens_ht[4] = {digest_len, fors_sig_len, n, n};
  const bool is_match = verify_stream_match(chunks_ht, lens_ht, 4, ht_sig, ht_sig_len);

  const uint8_t verdict = is_match ? 1u : 0u;
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
extern "C" void dr21_slhdsa_service(
    const uint8_t request[8192],
    const uint8_t descriptor[32],
    uint8_t result[8192]) {

  if (!word_aligned(request) || !word_aligned(descriptor) || !word_aligned(result)) {
    clear_bytes(result, 64);
    store_le32(result, 0);
    store_le32(result + 4, kBadToken);
    return;
  }

  // Verify Descriptor Magic: 0x01 0x21 0x53 0x48
  if (descriptor[0] != 0x01 || descriptor[1] != 0x21 ||
      descriptor[2] != 0x53 || descriptor[3] != 0x48) {
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
  const uint32_t sig_bytes = load_le32(descriptor + 16);

  uint32_t h = 63, d = 7, hp = 9, a = 12, k = 14, w = 16, len_total = 35;
  if (mode_id == 1) {
    h = 66; d = 22; hp = 3; a = 6; k = 33; w = 16; len_total = 35;
  } else if (mode_id == 2) {
    h = 64; d = 8; hp = 8; a = 14; k = 17; w = 16; len_total = 67;
  } else if (mode_id == 3) {
    h = 68; d = 17; hp = 4; a = 8; k = 35; w = 16; len_total = 67;
  }

  // Result Header Magic: 'S' 'L' '2' '1' (0x31324C53)
  store_le32(result + 0, 0x31324C53u);
  store_le32(result + 4, epoch);

  if (op_mode == 0) {
    do_keygen(request, result, n, d, hp, len_total, w);
    return;
  }

  if (op_mode == 1) {
    do_sign(request, result, n, h, hp, a, k, msg_len, sig_bytes);
    return;
  }

  if (op_mode == 2) {
    do_verify(request, result, n, h, hp, a, k, msg_len, sig_bytes);
    return;
  }

  store_le32(result + 8, kBadDescriptor);
  store_le32(result + 12, 0);
}
