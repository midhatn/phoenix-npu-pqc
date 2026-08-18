// SPDX-License-Identifier: Apache-2.0
// DR2d worker 3: form t_hat[0], retaining e_hat[1] for the next row.
#include "dr2d_mlkem512_kpke_keygen_internal.hpp"
namespace { using namespace phoenix_sdr_dsp::pqc::dr2d;
static void accumulate(uint8_t matrix[kMatrixTokenBytes], uint8_t state[kStateTokenBytes]) {
  const uint32_t id = load_le32(matrix), status = load_le32(matrix + 4);
  const bool valid = valid_header(matrix, kMatrixHeaderBytes) &&
      (status != kOk || (canonical_poly(matrix + kMatrixSecretOffset) &&
                         canonical_poly(matrix + kMatrixS1Offset) &&
                         canonical_poly(matrix + kMatrixCarry0Offset) &&
                         canonical_poly(matrix + kMatrixCarry1Offset) &&
                         canonical_poly(matrix + kMatrixA0Offset) && canonical_poly(matrix + kMatrixA1Offset)));
  if (!valid) write_header(state, kStateTokenBytes, id, kBadToken, kStateHeaderBytes);
  else if (status != kOk) write_header(state, kStateTokenBytes, id, status, kStateHeaderBytes);
  // Both token bases 32-bit aligned statically justifies every full-word store.
  else if (!word_aligned(state) || !word_aligned(matrix))
    write_header(state, kStateTokenBytes, id, kBadToken, kStateHeaderBytes);
  else {
    write_header(state, kStateTokenBytes, id, kOk, kStateHeaderBytes);
    // rho is not coefficient storage: its physically validated byte copy stays.
    DR2D_DISABLE_UNROLL for (uint32_t i = 0; i < 32; ++i)
      state[kRhoOffset + i] = matrix[kRhoOffset + i];
    // Ordered short circuit: both carries are seeded before accumulation.
    const bool stored =
        copy_words(state + kStateSecretOffset, matrix + kMatrixSecretOffset, 4 * kN) &&
        copy_words(state + kStateT0Offset, matrix + kMatrixCarry0Offset, 2 * kN) &&
        copy_words(state + kStateE1Offset, matrix + kMatrixCarry1Offset, 2 * kN) &&
        add_product_ntt(matrix + kMatrixA0Offset, matrix + kMatrixSecretOffset, state + kStateT0Offset) &&
        add_product_ntt(matrix + kMatrixA1Offset, matrix + kMatrixS1Offset, state + kStateT0Offset);
    if (!stored) write_header(state, kStateTokenBytes, id, kBadToken, kStateHeaderBytes);
  }
  clear_bytes(matrix, kMatrixTokenBytes);
}
}  // namespace
extern "C" void dr2d_kpke_keygen_row0_accumulate(uint8_t matrix[3120], uint8_t state[2096]) { accumulate(matrix, state); }
