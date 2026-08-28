// SPDX-License-Identifier: Apache-2.0
/**
 * Milestone DR4 Worker 1: Inner Product, INTT, Subtraction, Compress1, Serialize
 * Computes s_hat^T * u_hat, INTT, v - w, Compress1, CRC32, and commits result.
 */
#include "dr4_mlkem512_kpke_decrypt_internal.hpp"
#include <stdint.h>

extern "C" {

void dr4_accumulate_serialize(
    const uint8_t * __restrict tok_in,       // 5136 bytes (DecompressToken)
    uint8_t * __restrict res_out             // 52 bytes (Result token)
) {
    const auto *in_tok = reinterpret_cast<const mlkem512_dr4::DecompressToken *>(tok_in);
    
    auto *res_hdr = reinterpret_cast<uint32_t *>(res_out);
    uint8_t *msg_out = res_out + 20;
    
    res_hdr[0] = mlkem512_dr4::kResultMagic;
    res_hdr[1] = in_tok->request_id;
    res_hdr[2] = in_tok->status;
    res_hdr[3] = mlkem512_dr4::kN / 8; // 32 bytes
    res_hdr[4] = 0;
    
    if (in_tok->magic != mlkem512_dr4::kDecompressTokenMagic || in_tok->status != 0) {
        res_hdr[2] = in_tok->status != 0 ? in_tok->status : 3; // STATUS_BAD_TOKEN
        return;
    }
    
    // 1. Pointwise multiplication and accumulation in NTT domain (FIPS 203 MultiplyNTTs)
    uint32_t w_hat[mlkem512_dr4::kN];
    
    DR4_DISABLE_UNROLL
    for (uint32_t i = 0; i < 64; ++i) {
        const uint32_t gamma = mlkem512_dr4::kZetas[64 + i];
        
        // Pair 0: (4i + 0, 4i + 1) with +gamma
        uint32_t prod0_0, prod0_1;
        mlkem512_dr4::basemul(
            in_tok->s_hat0[4 * i + 0], in_tok->s_hat0[4 * i + 1],
            in_tok->u_hat0[4 * i + 0], in_tok->u_hat0[4 * i + 1],
            gamma, prod0_0, prod0_1
        );
        
        uint32_t prod1_0, prod1_1;
        mlkem512_dr4::basemul(
            in_tok->s_hat1[4 * i + 0], in_tok->s_hat1[4 * i + 1],
            in_tok->u_hat1[4 * i + 0], in_tok->u_hat1[4 * i + 1],
            gamma, prod1_0, prod1_1
        );
        
        const uint32_t s0 = prod0_0 + prod1_0;
        w_hat[4 * i + 0] = s0 >= mlkem512_dr4::kQ ? s0 - mlkem512_dr4::kQ : s0;
        
        const uint32_t s1 = prod0_1 + prod1_1;
        w_hat[4 * i + 1] = s1 >= mlkem512_dr4::kQ ? s1 - mlkem512_dr4::kQ : s1;
        
        // Pair 1: (4i + 2, 4i + 3) with -gamma (kQ - gamma)
        uint32_t prod0_2, prod0_3;
        mlkem512_dr4::basemul(
            in_tok->s_hat0[4 * i + 2], in_tok->s_hat0[4 * i + 3],
            in_tok->u_hat0[4 * i + 2], in_tok->u_hat0[4 * i + 3],
            mlkem512_dr4::kQ - gamma, prod0_2, prod0_3
        );
        
        uint32_t prod1_2, prod1_3;
        mlkem512_dr4::basemul(
            in_tok->s_hat1[4 * i + 2], in_tok->s_hat1[4 * i + 3],
            in_tok->u_hat1[4 * i + 2], in_tok->u_hat1[4 * i + 3],
            mlkem512_dr4::kQ - gamma, prod1_2, prod1_3
        );
        
        const uint32_t s2 = prod0_2 + prod1_2;
        w_hat[4 * i + 2] = s2 >= mlkem512_dr4::kQ ? s2 - mlkem512_dr4::kQ : s2;
        
        const uint32_t s3 = prod0_3 + prod1_3;
        w_hat[4 * i + 3] = s3 >= mlkem512_dr4::kQ ? s3 - mlkem512_dr4::kQ : s3;
    }
    
    // 2. Inverse NTT
    mlkem512_dr4::inverse_ntt(w_hat);
    
    // 3. Subtract from v: w[i] = (v[i] - w_hat[i]) mod q
    uint32_t w_poly[mlkem512_dr4::kN];
    DR4_DISABLE_UNROLL
    for (uint32_t i = 0; i < mlkem512_dr4::kN; ++i) {
        const uint32_t vi = in_tok->v[i];
        const uint32_t wi = w_hat[i];
        w_poly[i] = vi >= wi ? vi - wi : vi + mlkem512_dr4::kQ - wi;
    }
    
    // 4. Compress_1 and pack into 32-byte plaintext
    mlkem512_dr4::compress_1bit_to_bytes(w_poly, msg_out);
    
    // 5. Compute CRC32 over plaintext message
    const uint32_t crc = mlkem512_dr4::compute_crc32(msg_out, 32);
    res_hdr[4] = crc;
}

} // extern "C"
