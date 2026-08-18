// SPDX-License-Identifier: Apache-2.0
// DR2d worker 2: expand only A[0,0] and A[0,1].
#include "dr2d_mlkem512_kpke_keygen_internal.hpp"
namespace { using namespace phoenix_sdr_dsp::pqc::dr2d;
static void expand(uint8_t secret[kSecretTokenBytes], uint8_t matrix[kMatrixTokenBytes]) {
  const uint32_t id = load_le32(secret), status = load_le32(secret + 4);
  const bool valid = valid_header(secret, kSecretHeaderBytes) &&
                     (status != kOk || (canonical_poly(secret + kSecretS0Offset) &&
                                        canonical_poly(secret + kSecretS1Offset) &&
                                        canonical_poly(secret + kSecretE0Offset) &&
                                        canonical_poly(secret + kSecretE1Offset)));
  if (!valid) write_header(matrix, kMatrixTokenBytes, id, kBadToken, kMatrixHeaderBytes);
  else if (status != kOk) write_header(matrix, kMatrixTokenBytes, id, status, kMatrixHeaderBytes);
  // Both token bases 32-bit aligned statically justifies every full-word store.
  else if (!word_aligned(matrix) || !word_aligned(secret))
    write_header(matrix, kMatrixTokenBytes, id, kBadToken, kMatrixHeaderBytes);
  else {
    write_header(matrix, kMatrixTokenBytes, id, kOk, kMatrixHeaderBytes);
    // rho is not coefficient storage: its physically validated byte copy stays.
    DR2D_DISABLE_UNROLL for (uint32_t i = 0; i < 32; ++i)
      matrix[kRhoOffset + i] = secret[kRhoOffset + i];
    const bool complete = copy_words(matrix + kMatrixSecretOffset, secret + kSecretS0Offset, 8 * kN) &&
                          sample_matrix_store(matrix + kRhoOffset, 0, 0, matrix + kMatrixA0Offset) &&
                          sample_matrix_store(matrix + kRhoOffset, 1, 0, matrix + kMatrixA1Offset);
    if (!complete) write_header(matrix, kMatrixTokenBytes, id, kLimitExceeded, kMatrixHeaderBytes);
  }
  clear_bytes(secret, kSecretTokenBytes);
}
}  // namespace
extern "C" void dr2d_kpke_keygen_row0_expand(uint8_t secret[2096], uint8_t matrix[3120]) { expand(secret, matrix); }
