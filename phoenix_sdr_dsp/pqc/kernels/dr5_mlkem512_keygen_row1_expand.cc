// SPDX-License-Identifier: Apache-2.0
#include "dr5_mlkem512_keygen_internal.hpp"
#include <stdint.h>

namespace {

static bool sample_ntt(const uint8_t rho[32], uint8_t col, uint8_t row, uint8_t *out) {
    alignas(8) uint8_t state[200];
    mlkem512_dr5::clear_bytes(state, sizeof(state));
    for (uint32_t i = 0; i < 32; ++i) state[i] ^= rho[i];
    state[32] ^= col;
    state[33] ^= row;
    state[34] ^= 0x1F; // SHAKE128 domain separation
    state[167] ^= 0x80; // SHAKE128 rate = 168 bytes
    phoenix_sdr_dsp::pqc::dr1::keccak_f1600(state);
    
    uint32_t written = 0;
    uint32_t offset = 0;
    
    for (uint32_t block = 0; block < mlkem512_dr5::kBlockCap && written < mlkem512_dr5::kN; ++block) {
        if (block > 0) {
            phoenix_sdr_dsp::pqc::dr1::keccak_f1600(state);
            offset = 0;
        }
        while (offset + 3 <= mlkem512_dr5::kRate128 && written < mlkem512_dr5::kN) {
            const uint32_t b0 = state[offset + 0];
            const uint32_t b1 = state[offset + 1];
            const uint32_t b2 = state[offset + 2];
            offset += 3;
            
            const uint32_t d1 = b0 | ((b1 & 0x0Fu) << 8);
            const uint32_t d2 = (b1 >> 4) | (b2 << 4);
            
            if (d1 < mlkem512_dr5::kQ) {
                *reinterpret_cast<uint16_t *>(out + 2 * written) = static_cast<uint16_t>(d1);
                written++;
            }
            if (d2 < mlkem512_dr5::kQ && written < mlkem512_dr5::kN) {
                *reinterpret_cast<uint16_t *>(out + 2 * written) = static_cast<uint16_t>(d2);
                written++;
            }
        }
    }
    mlkem512_dr5::clear_bytes(state, sizeof(state));
    return written == mlkem512_dr5::kN;
}

} // namespace

extern "C" {

void dr5_mlkem512_keygen_row1_expand(
    const uint8_t * __restrict state_in,     // 2128 bytes (RowStateToken)
    uint8_t * __restrict mat_out             // 3152 bytes (MatrixToken)
) {
    for (uint32_t i = 0; i < mlkem512_dr5::kRowStateTokenBytes; ++i) {
        mat_out[i] = state_in[i];
    }
    
    auto *hdr = reinterpret_cast<uint32_t *>(mat_out);
    if (hdr[2] != 0) return;
    
    const uint8_t *rho = state_in + mlkem512_dr5::kRhoOffset;
    
    // Sample A[1, 0] and A[1, 1] (SHAKE128(rho || j || i) where row=1, col=0 and 1)
    if (!sample_ntt(rho, 0, 1, mat_out + mlkem512_dr5::kMatrixA0Offset) ||
        !sample_ntt(rho, 1, 1, mat_out + mlkem512_dr5::kMatrixA1Offset)) {
        hdr[2] = 1; // STATUS_LIMIT_EXCEEDED
    }
}

} // extern "C"
