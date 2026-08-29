// SPDX-License-Identifier: Apache-2.0
// DR13 Worker 1: ExpandA, Matrix Multiply, INTT, UseHint, SHAKE256 Verify, Hardware Sealing
#include "dr13_mldsa44_verify_internal.hpp"

using namespace phoenix_sdr_dsp::pqc::dr11;
using namespace phoenix_sdr_dsp::pqc::dr12;
using namespace phoenix_sdr_dsp::pqc::dr13;

extern "C" void dr13_mldsa44_verify_w1_matrix_w(
    const uint8_t in_token[10376],
    uint8_t result[28]) {

  clear_bytes(result, 28);

  const uint32_t request_id = load_le32(in_token + 0);
  const uint32_t fail_flag = load_le32(in_token + 4);
  const uint8_t *rho = in_token + 8;
  const uint8_t *mu = in_token + 40;
  const uint8_t *c_tilde = in_token + 104;
  const uint8_t *h_in = in_token + 136;
  const int32_t *z_hat = reinterpret_cast<const int32_t *>(in_token + 1160);
  const int32_t *t1_hat = reinterpret_cast<const int32_t *>(in_token + 5256);
  const int32_t *c_hat = reinterpret_cast<const int32_t *>(in_token + 9352);

  uint32_t valid = 0;

  if (fail_flag == 0) {
    uint8_t w1_bytes[768];
    int32_t acc[256];
    int32_t a_entry[256];
    int32_t prod[256];
    int32_t w1_row[256];

    for (uint8_t row = 0; row < 4; ++row) {
      clear_bytes(acc, sizeof(acc));
      // Accumulate A[row, col] * z_hat[col]
      for (uint8_t col = 0; col < 4; ++col) {
        expand_a_sponge(rho, col, row, a_entry);
        basemul(prod, a_entry, z_hat + col * 256);
        DR11_DISABLE_UNROLL
        for (uint32_t c = 0; c < 256; ++c) acc[c] += prod[c];
      }
      // Subtract c_hat * t1_hat[row]
      basemul(prod, c_hat, t1_hat + row * 256);
      DR11_DISABLE_UNROLL
      for (uint32_t c = 0; c < 256; ++c) acc[c] -= prod[c];

      // INTT -> w_approx
      invntt_kernel(acc);

      // Reconstruct w1_prime via UseHint
      const uint8_t *h_row = h_in + row * 256;
      DR11_DISABLE_UNROLL
      for (uint32_t c = 0; c < 256; ++c) {
        w1_row[c] = use_hint(h_row[c], acc[c]);
      }
      encode_w1_poly(w1_row, w1_bytes + row * 192);
    }

    // Challenge c' = SHAKE256(mu || w1_bytes, 32)
    uint8_t hash_in[64 + 768];
    DR11_DISABLE_UNROLL
    for (uint32_t i = 0; i < 64; ++i) hash_in[i] = mu[i];
    DR11_DISABLE_UNROLL
    for (uint32_t i = 0; i < 768; ++i) hash_in[64 + i] = w1_bytes[i];

    uint8_t c_prime[32];
    keccak_sponge(136, hash_in, 64 + 768, 0x1F, c_prime, 32);

    // Verify c_prime == c_tilde
    uint32_t diff = 0;
    DR11_DISABLE_UNROLL
    for (uint32_t i = 0; i < 32; ++i) {
      diff |= static_cast<uint32_t>(c_prime[i] ^ c_tilde[i]);
    }
    if (diff == 0) {
      valid = 1;
    }

    clear_bytes(w1_bytes, sizeof(w1_bytes));
    clear_bytes(acc, sizeof(acc));
    clear_bytes(a_entry, sizeof(a_entry));
    clear_bytes(prod, sizeof(prod));
    clear_bytes(w1_row, sizeof(w1_row));
  }

  // Format Sealed Record: Header (20 B) + Payload (4 B) + CRC32 (4 B)
  store_le32(result + 0, 0x4433524Du); // b"MR3D"
  store_le32(result + 4, request_id);
  store_le32(result + 8, valid ? 0 : 1); // 0 = valid, 1 = rejected
  store_le32(result + 12, 4);            // Payload len
  store_le32(result + 16, 0);            // Pre-CRC placeholder
  store_le32(result + 20, valid);

  const uint32_t crc = compute_crc32(result + 20, 4);
  store_le32(result + 16, crc);
}
