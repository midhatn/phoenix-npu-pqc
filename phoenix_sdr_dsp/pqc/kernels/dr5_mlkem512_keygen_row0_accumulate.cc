// SPDX-License-Identifier: Apache-2.0
#include "dr5_mlkem512_keygen_internal.hpp"
#include <stdint.h>

extern "C" {

void dr5_mlkem512_keygen_row0_accumulate(
    const uint8_t * __restrict mat_in,       // 3152 bytes (MatrixToken)
    uint8_t * __restrict state_out           // 2128 bytes (RowStateToken)
) {
    // Copy secret prefix (header + rho + z + s0 + s1)
    for (uint32_t i = 0; i < mlkem512_dr5::kSecretE0Offset; ++i) {
        state_out[i] = mat_in[i];
    }
    
    // Copy e1[512] to second carry position
    for (uint32_t i = 0; i < 512; ++i) {
        state_out[mlkem512_dr5::kStateE1Offset + i] = mat_in[mlkem512_dr5::kSecretE1Offset + i];
    }
    
    auto *hdr = reinterpret_cast<uint32_t *>(state_out);
    if (hdr[2] != 0) return;
    
    const uint8_t *s0_raw = mat_in + mlkem512_dr5::kSecretS0Offset;
    const uint8_t *s1_raw = mat_in + mlkem512_dr5::kSecretS1Offset;
    const uint8_t *e0_raw = mat_in + mlkem512_dr5::kSecretE0Offset;
    const uint8_t *a0_raw = mat_in + mlkem512_dr5::kMatrixA0Offset;
    const uint8_t *a1_raw = mat_in + mlkem512_dr5::kMatrixA1Offset;
    
    uint8_t *t0_out = state_out + mlkem512_dr5::kStateT0Offset;
    
    DR5_DISABLE_UNROLL
    for (uint32_t i = 0; i < 64; ++i) {
        const uint32_t gamma = mlkem512_dr5::kZetas[64 + i];
        
        // Pair 0: (4i + 0, 4i + 1) with +gamma
        uint32_t a0_0 = mlkem512_dr5::load_le16(a0_raw + 2 * (4 * i + 0));
        uint32_t a0_1 = mlkem512_dr5::load_le16(a0_raw + 2 * (4 * i + 1));
        uint32_t s0_0 = mlkem512_dr5::load_le16(s0_raw + 2 * (4 * i + 0));
        uint32_t s0_1 = mlkem512_dr5::load_le16(s0_raw + 2 * (4 * i + 1));
        uint32_t prod0_0, prod0_1;
        mlkem512_dr5::basemul_pos(a0_0, a0_1, s0_0, s0_1, gamma, prod0_0, prod0_1);
        
        uint32_t a1_0 = mlkem512_dr5::load_le16(a1_raw + 2 * (4 * i + 0));
        uint32_t a1_1 = mlkem512_dr5::load_le16(a1_raw + 2 * (4 * i + 1));
        uint32_t s1_0 = mlkem512_dr5::load_le16(s1_raw + 2 * (4 * i + 0));
        uint32_t s1_1 = mlkem512_dr5::load_le16(s1_raw + 2 * (4 * i + 1));
        uint32_t prod1_0, prod1_1;
        mlkem512_dr5::basemul_pos(a1_0, a1_1, s1_0, s1_1, gamma, prod1_0, prod1_1);
        
        uint32_t e0_0 = mlkem512_dr5::load_le16(e0_raw + 2 * (4 * i + 0));
        uint32_t e0_1 = mlkem512_dr5::load_le16(e0_raw + 2 * (4 * i + 1));
        
        uint32_t t0 = prod0_0 + prod1_0 + e0_0;
        if (t0 >= mlkem512_dr5::kQ) t0 -= mlkem512_dr5::kQ;
        if (t0 >= mlkem512_dr5::kQ) t0 -= mlkem512_dr5::kQ;
        
        uint32_t t1 = prod0_1 + prod1_1 + e0_1;
        if (t1 >= mlkem512_dr5::kQ) t1 -= mlkem512_dr5::kQ;
        if (t1 >= mlkem512_dr5::kQ) t1 -= mlkem512_dr5::kQ;
        
        mlkem512_dr5::store_pair_word(t0_out, 2 * i + 0, t0, t1);
        
        // Pair 1: (4i + 2, 4i + 3) with -gamma (kQ - gamma)
        uint32_t a0_2 = mlkem512_dr5::load_le16(a0_raw + 2 * (4 * i + 2));
        uint32_t a0_3 = mlkem512_dr5::load_le16(a0_raw + 2 * (4 * i + 3));
        uint32_t s0_2 = mlkem512_dr5::load_le16(s0_raw + 2 * (4 * i + 2));
        uint32_t s0_3 = mlkem512_dr5::load_le16(s0_raw + 2 * (4 * i + 3));
        uint32_t prod0_2, prod0_3;
        mlkem512_dr5::basemul_pos(a0_2, a0_3, s0_2, s0_3, mlkem512_dr5::kQ - gamma, prod0_2, prod0_3);
        
        uint32_t a1_2 = mlkem512_dr5::load_le16(a1_raw + 2 * (4 * i + 2));
        uint32_t a1_3 = mlkem512_dr5::load_le16(a1_raw + 2 * (4 * i + 3));
        uint32_t s1_2 = mlkem512_dr5::load_le16(s1_raw + 2 * (4 * i + 2));
        uint32_t s1_3 = mlkem512_dr5::load_le16(s1_raw + 2 * (4 * i + 3));
        uint32_t prod1_2, prod1_3;
        mlkem512_dr5::basemul_pos(a1_2, a1_3, s1_2, s1_3, mlkem512_dr5::kQ - gamma, prod1_2, prod1_3);
        
        uint32_t e0_2 = mlkem512_dr5::load_le16(e0_raw + 2 * (4 * i + 2));
        uint32_t e0_3 = mlkem512_dr5::load_le16(e0_raw + 2 * (4 * i + 3));
        
        uint32_t t2 = prod0_2 + prod1_2 + e0_2;
        if (t2 >= mlkem512_dr5::kQ) t2 -= mlkem512_dr5::kQ;
        if (t2 >= mlkem512_dr5::kQ) t2 -= mlkem512_dr5::kQ;
        
        uint32_t t3 = prod0_3 + prod1_3 + e0_3;
        if (t3 >= mlkem512_dr5::kQ) t3 -= mlkem512_dr5::kQ;
        if (t3 >= mlkem512_dr5::kQ) t3 -= mlkem512_dr5::kQ;
        
        mlkem512_dr5::store_pair_word(t0_out, 2 * i + 1, t2, t3);
    }
}

} // extern "C"
