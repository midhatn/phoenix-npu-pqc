// SPDX-License-Identifier: Apache-2.0
// DR2d worker 5: form t_hat[1] and create the final serializer token.
#include "dr2d_mlkem512_kpke_keygen_internal.hpp"
namespace { using namespace phoenix_sdr_dsp::pqc::dr2d;
static void accumulate(uint8_t matrix[kMatrixTokenBytes], uint8_t final_token[kFinalTokenBytes]) {
  const uint32_t id = load_le32(matrix), status = load_le32(matrix + 4);
  const bool valid = valid_header(matrix, kMatrixHeaderBytes) &&
      (status != kOk || (canonical_poly(matrix + kMatrixSecretOffset) &&
                         canonical_poly(matrix + kMatrixS1Offset) &&
                         canonical_poly(matrix + kMatrixCarry0Offset) &&
                         canonical_poly(matrix + kMatrixCarry1Offset) &&
                         canonical_poly(matrix + kMatrixA0Offset) && canonical_poly(matrix + kMatrixA1Offset)));
  if (!valid) write_header(final_token, kFinalTokenBytes, id, kBadToken, kFinalHeaderBytes);
  else if (status != kOk) write_header(final_token, kFinalTokenBytes, id, status, kFinalHeaderBytes);
  // Both token bases 32-bit aligned statically justifies every full-word store.
  else if (!word_aligned(final_token) || !word_aligned(matrix))
    write_header(final_token, kFinalTokenBytes, id, kBadToken, kFinalHeaderBytes);
  else {
    write_header(final_token, kFinalTokenBytes, id, kOk, kFinalHeaderBytes);
    // rho is not coefficient storage: its physically validated byte copy stays.
    DR2D_DISABLE_UNROLL for (uint32_t i = 0; i < 32; ++i)
      final_token[kFinalRhoOffset + i] = matrix[kRhoOffset + i];
    // Ordered short circuit: both carries are seeded before accumulation.
    const bool stored =
        copy_words(final_token + kFinalS0Offset, matrix + kMatrixSecretOffset, 4 * kN) &&
        copy_words(final_token + kFinalT0Offset, matrix + kMatrixCarry0Offset, 2 * kN) &&
        copy_words(final_token + kFinalT1Offset, matrix + kMatrixCarry1Offset, 2 * kN) &&
        add_product_ntt(matrix + kMatrixA0Offset, matrix + kMatrixSecretOffset, final_token + kFinalT1Offset) &&
        add_product_ntt(matrix + kMatrixA1Offset, matrix + kMatrixS1Offset, final_token + kFinalT1Offset);
    if (!stored) write_header(final_token, kFinalTokenBytes, id, kBadToken, kFinalHeaderBytes);
  }
  clear_bytes(matrix, kMatrixTokenBytes);
}
}  // namespace
extern "C" void dr2d_kpke_keygen_row1_accumulate(uint8_t matrix[3120], uint8_t final_token[2112]) { accumulate(matrix, final_token); }
