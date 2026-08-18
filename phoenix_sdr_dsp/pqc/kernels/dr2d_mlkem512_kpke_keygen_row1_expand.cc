// SPDX-License-Identifier: Apache-2.0
// DR2d worker 4: expand only A[1,0] and A[1,1] while carrying row-0 state.
#include "dr2d_mlkem512_kpke_keygen_internal.hpp"
namespace { using namespace phoenix_sdr_dsp::pqc::dr2d;
static void expand(uint8_t state[kStateTokenBytes], uint8_t matrix[kMatrixTokenBytes]) {
  const uint32_t id = load_le32(state), status = load_le32(state + 4);
  const bool valid = valid_header(state, kStateHeaderBytes) &&
      (status != kOk || (canonical_poly(state + kStateSecretOffset) &&
                         canonical_poly(state + kStateS1Offset) &&
                         canonical_poly(state + kStateT0Offset) &&
                         canonical_poly(state + kStateE1Offset)));
  if (!valid) write_header(matrix, kMatrixTokenBytes, id, kBadToken, kMatrixHeaderBytes);
  else if (status != kOk) write_header(matrix, kMatrixTokenBytes, id, status, kMatrixHeaderBytes);
  // Both token bases 32-bit aligned statically justifies every full-word store.
  else if (!word_aligned(matrix) || !word_aligned(state))
    write_header(matrix, kMatrixTokenBytes, id, kBadToken, kMatrixHeaderBytes);
  else {
    write_header(matrix, kMatrixTokenBytes, id, kOk, kMatrixHeaderBytes);
    // rho is not coefficient storage: its physically validated byte copy stays.
    DR2D_DISABLE_UNROLL for (uint32_t i = 0; i < 32; ++i)
      matrix[kRhoOffset + i] = state[kRhoOffset + i];
    const bool complete = copy_words(matrix + kMatrixSecretOffset, state + kStateSecretOffset, 8 * kN) &&
                          sample_matrix_store(matrix + kRhoOffset, 0, 1, matrix + kMatrixA0Offset) &&
                          sample_matrix_store(matrix + kRhoOffset, 1, 1, matrix + kMatrixA1Offset);
    if (!complete) write_header(matrix, kMatrixTokenBytes, id, kLimitExceeded, kMatrixHeaderBytes);
  }
  clear_bytes(state, kStateTokenBytes);
}
}  // namespace
extern "C" void dr2d_kpke_keygen_row1_expand(uint8_t state[2096], uint8_t matrix[3120]) { expand(state, matrix); }
