// SPDX-License-Identifier: Apache-2.0
/**
 * Milestone DR31: NIST SP 800-208 / RFC 5280 / RFC 5652 X.509 Post-Quantum Certificates
 * & Hybrid CMS Co-Processor AIE2 Service Kernel.
 * Target: AMD Phoenix NPU (AIE2 / XDNA1 Architecture).
 */

#include <stdint.h>
#include <stddef.h>
#include "dr31_x509_cms_internal.hpp"

extern "C" {

void dr31_x509_cms_service(
    const uint8_t* restrict request_in,
    const uint8_t* restrict descriptor_in,
    uint8_t* restrict result_out,
    uint32_t request_slots,
    uint32_t descriptor_slots,
    uint32_t result_slots
) {
    // 1. Unpack descriptor
    uint32_t magic     = *(const uint32_t*)(descriptor_in + 0);
    uint32_t op_mode   = *(const uint32_t*)(descriptor_in + 4);
    uint32_t algo_id   = *(const uint32_t*)(descriptor_in + 8);
    uint32_t flags     = *(const uint32_t*)(descriptor_in + 12);
    uint32_t tbs_len   = *(const uint32_t*)(descriptor_in + 16);
    uint32_t pk_len    = *(const uint32_t*)(descriptor_in + 20);
    uint32_t sig_len   = *(const uint32_t*)(descriptor_in + 24);
    uint32_t aux_len   = *(const uint32_t*)(descriptor_in + 28);

    // Validate magic
    if (magic != dr31::MAGIC_HEADER) {
        *(uint32_t*)(result_out + 0) = 0xDEAD0007;
        *(uint32_t*)(result_out + 4) = 0;
        *(uint32_t*)(result_out + 8) = 1; // Error: invalid magic
        return;
    }

    // Zero out output buffer header and result fields (first 96 bytes)
    for (int i = 0; i < 96; ++i) {
        result_out[i] = 0;
    }
    *(uint32_t*)(result_out + 0) = dr31::MAGIC_HEADER;
    *(uint32_t*)(result_out + 4) = op_mode;
    *(uint32_t*)(result_out + 8) = 0; // Hardware status: 0 = SUCCESS
    *(uint32_t*)(result_out + 12) = algo_id;

    const uint8_t* tbs_digest = request_in + 32;
    const uint8_t* public_key = request_in + 256;
    const uint8_t* signature  = request_in + 4096;
    const uint8_t* aux_data   = request_in + 14336;

    if (op_mode == dr31::MODE_X509_PQC_VERIFY) {
        // Mode 0: Pure PQC Certificate Signature Verification
        int is_valid = dr31::verify_pqc_signature(
            algo_id, tbs_digest, tbs_len, public_key, pk_len, signature, sig_len
        );

        dr31::compute_cert_fingerprint(
            tbs_digest, tbs_len, public_key, pk_len, signature, sig_len, result_out + 32
        );

        *(uint32_t*)(result_out + 16) = (uint32_t)is_valid;
        *(uint32_t*)(result_out + 20) = flags;
        *(uint32_t*)(result_out + 24) = 32; // Fingerprint length
    }
    else if (op_mode == dr31::MODE_X509_HYBRID_VERIFY) {
        // Mode 1: Hybrid / Composite Certificate Signature Verification
        // aux_data contains: classical_pk (32 B) + classical_sig (64 B)
        const uint8_t* ed_pk = aux_data;
        const uint8_t* ed_sig = aux_data + 32;

        int classical_ok = dr31::verify_classical_signature(tbs_digest, tbs_len, ed_pk, ed_sig);
        int pqc_ok = dr31::verify_pqc_signature(
            algo_id, tbs_digest, tbs_len, public_key, pk_len, signature, sig_len
        );

        int composite_ok = (classical_ok && pqc_ok) ? 1 : 0;

        dr31::compute_cert_fingerprint(
            tbs_digest, tbs_len, public_key, pk_len, signature, sig_len, result_out + 32
        );

        *(uint32_t*)(result_out + 16) = (uint32_t)composite_ok;
        *(uint32_t*)(result_out + 20) = (classical_ok ? 0x01 : 0) | (pqc_ok ? 0x02 : 0);
        *(uint32_t*)(result_out + 24) = 32;
    }
    else if (op_mode == dr31::MODE_CMS_SIGNED_DATA_VERIFY) {
        // Mode 2: CMS SignedData Signer Verification
        int is_valid = 0;
        if (flags & dr31::FLAG_HAS_SIGNED_ATTRS) {
            // Signed attributes check: verify signature over signed_attrs (aux_data)
            int attr_match = dr31::ct_compare(tbs_digest, aux_data, (aux_len < 32 ? aux_len : 32));
            int sig_ok = dr31::verify_pqc_signature(
                algo_id, aux_data, aux_len, public_key, pk_len, signature, sig_len
            );
            is_valid = (attr_match && sig_ok) ? 1 : 0;
        } else {
            is_valid = dr31::verify_pqc_signature(
                algo_id, tbs_digest, tbs_len, public_key, pk_len, signature, sig_len
            );
        }

        *(uint32_t*)(result_out + 16) = (uint32_t)is_valid;
        *(uint32_t*)(result_out + 20) = flags;
        *(uint32_t*)(result_out + 24) = 32;
    }
    else if (op_mode == dr31::MODE_CMS_ENVELOPED_UNWRAP) {
        // Mode 3: CMS EnvelopedData KEM Decapsulation & CEK Unwrapping
        // signature contains KEM ciphertext; aux_data contains wrapped CEK (48 bytes)
        uint8_t plain_cek[32];
        int unwrap_ok = dr31::unwrap_cms_cek(algo_id, signature, sig_len, aux_data, aux_len, plain_cek);

        if (unwrap_ok) {
            for (int i = 0; i < 32; ++i) {
                result_out[64 + i] = plain_cek[i];
            }
            *(uint32_t*)(result_out + 16) = 1; // Valid
            *(uint32_t*)(result_out + 24) = 32; // Unwrapped key length
            dr31::secure_zeroize(plain_cek, 32);
        } else {
            *(uint32_t*)(result_out + 16) = 0; // Failed
            *(uint32_t*)(result_out + 24) = 0;
            dr31::secure_zeroize(plain_cek, 32);
        }
    }
    else if (op_mode == dr31::MODE_X509_CHAIN_STEP_VERIFY) {
        // Mode 4: Intermediate CA to Leaf step verification
        // Issuer MUST have FLAG_IS_CA
        if (!(flags & dr31::FLAG_IS_CA)) {
            *(uint32_t*)(result_out + 16) = 0; // Rejected: Not a CA
            *(uint32_t*)(result_out + 20) = flags;
            *(uint32_t*)(result_out + 24) = 0;
        } else {
            int is_valid = dr31::verify_pqc_signature(
                algo_id, tbs_digest, tbs_len, public_key, pk_len, signature, sig_len
            );
            dr31::compute_cert_fingerprint(
                tbs_digest, tbs_len, public_key, pk_len, signature, sig_len, result_out + 32
            );
            *(uint32_t*)(result_out + 16) = (uint32_t)is_valid;
            *(uint32_t*)(result_out + 20) = flags;
            *(uint32_t*)(result_out + 24) = 32;
        }
    }
    else {
        *(uint32_t*)(result_out + 8) = 0xFF; // Unsupported op_mode
    }
}

} // extern "C"
