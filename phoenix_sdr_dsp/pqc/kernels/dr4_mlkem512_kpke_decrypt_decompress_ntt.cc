// SPDX-License-Identifier: Apache-2.0
/**
 * Milestone DR4 Worker 0: Decompress & NTT
 * Unpacks dk_PKE (s_hat), decompresses u/v, computes NTT(u0) and NTT(u1).
 */
#include "dr4_mlkem512_kpke_decrypt_internal.hpp"
#include <stdint.h>

extern "C" {

void dr4_decompress_ntt(
    const uint8_t * __restrict req_in,       // 1536 bytes (dk_PKE[768] || c[768])
    const uint8_t * __restrict desc_in,      // 16 bytes
    uint8_t * __restrict tok_out             // 5136 bytes (DecompressToken)
) {
    auto *out_tok = reinterpret_cast<mlkem512_dr4::DecompressToken *>(tok_out);
    
    // 1. Validate descriptor
    const uint8_t abi_ver = desc_in[0];
    const uint8_t opcode = desc_in[1];
    const uint8_t param = desc_in[2];
    
    const uint32_t req_id = *reinterpret_cast<const uint32_t *>(desc_in + 8);
    
    out_tok->magic = mlkem512_dr4::kDecompressTokenMagic;
    out_tok->request_id = req_id;
    out_tok->status = 0;
    out_tok->reserved = 0;
    
    if (abi_ver != 1 || opcode != 0x41 || param != 0x52) {
        out_tok->status = 2; // STATUS_BAD_DESCRIPTOR
        return;
    }
    
    // 2. Decode s_hat0 and s_hat1 from dk_PKE (bytes 0..767)
    mlkem512_dr4::decode_12bit_to_coeffs(req_in + 0, out_tok->s_hat0);
    mlkem512_dr4::decode_12bit_to_coeffs(req_in + 384, out_tok->s_hat1);
    
    // 3. Decompress u0 and u1 from c1 (bytes 768..1407), compute NTT
    mlkem512_dr4::decompress_10bit_to_coeffs(req_in + 768, out_tok->u_hat0);
    mlkem512_dr4::forward_ntt(out_tok->u_hat0);
    
    mlkem512_dr4::decompress_10bit_to_coeffs(req_in + 1088, out_tok->u_hat1);
    mlkem512_dr4::forward_ntt(out_tok->u_hat1);
    
    // 4. Decompress v from c2 (bytes 1408..1535)
    mlkem512_dr4::decompress_4bit_to_coeffs(req_in + 1408, out_tok->v);
}

} // extern "C"
