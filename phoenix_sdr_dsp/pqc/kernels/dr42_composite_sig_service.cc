// SPDX-License-Identifier: Apache-2.0
/**
 * Milestone DR42: ANSSI Composite & Dual-Signature Sovereign Standard Engine
 * AMD Phoenix NPU (AIE2 / XDNA1 Architecture) Service Kernel.
 * Dispatched on AIE2 vector / crypto compute tiles.
 */

#include <stdint.h>
#include <stddef.h>
#include "dr42_composite_sig_internal.hpp"

extern "C" {

void dr42_composite_sig_service(
    const uint8_t* restrict request_in,
    const uint8_t* restrict descriptor_in,
    uint8_t* restrict result_out,
    uint32_t request_slots,
    uint32_t descriptor_slots,
    uint32_t result_slots
) {
    // 1. Unpack 64-byte descriptor header
    uint32_t magic        = *(const uint32_t*)(descriptor_in + 0);
    uint32_t op_code      = *(const uint32_t*)(descriptor_in + 4);
    uint32_t sig_type     = *(const uint32_t*)(descriptor_in + 8);
    uint32_t flags        = *(const uint32_t*)(descriptor_in + 12);
    uint32_t msg_len      = *(const uint32_t*)(descriptor_in + 16);
    uint32_t context_len  = *(const uint32_t*)(descriptor_in + 20);
    uint32_t trad_pk_len  = *(const uint32_t*)(descriptor_in + 24);
    uint32_t trad_sig_len = *(const uint32_t*)(descriptor_in + 28);
    uint32_t pqc_pk_len   = *(const uint32_t*)(descriptor_in + 32);
    uint32_t pqc_sig_len  = *(const uint32_t*)(descriptor_in + 36);
    uint32_t seq_id       = *(const uint32_t*)(descriptor_in + 40);

    // Zero out full 2048-byte result buffer using 32-bit scalar writes
    uint32_t* res_u32 = (uint32_t*)result_out;
    DR42_DISABLE_UNROLL
    _Pragma("clang loop vectorize(disable)")
    for (size_t i = 0; i < 512; ++i) {
        res_u32[i] = 0;
    }

    // 2. Validate magic header
    if (magic != dr42::MAGIC_HEADER) {
        *(uint32_t*)(result_out + 0)  = dr42::STATUS_ERR_INVALID_MAGIC;
        *(uint32_t*)(result_out + 4)  = op_code;
        *(uint32_t*)(result_out + 8)  = sig_type;
        *(uint32_t*)(result_out + 12) = 0; // is_valid
        *(uint32_t*)(result_out + 16) = 0; // checksum
        *(uint32_t*)(result_out + 20) = 0; // flags
        return;
    }

    // 3. Validate composite signature type
    if (sig_type != dr42::COMPOSITE_TYPE_MLDSA44_ED25519 &&
        sig_type != dr42::COMPOSITE_TYPE_MLDSA65_ECDSA_P384 &&
        sig_type != dr42::COMPOSITE_TYPE_MLDSA87_ECDSA_P521) {
        *(uint32_t*)(result_out + 0)  = dr42::STATUS_ERR_UNSUPPORTED_TYPE;
        *(uint32_t*)(result_out + 4)  = op_code;
        *(uint32_t*)(result_out + 8)  = sig_type;
        *(uint32_t*)(result_out + 12) = 0;
        *(uint32_t*)(result_out + 16) = 0;
        *(uint32_t*)(result_out + 20) = 0;
        return;
    }

    // 4. Extract buffer component pointers
    const uint8_t* context  = request_in + dr42::OFFSET_CONTEXT;
    const uint8_t* oid      = request_in + dr42::OFFSET_OID;
    const uint8_t* message  = request_in + dr42::OFFSET_MESSAGE;
    const uint8_t* trad_pk  = request_in + dr42::OFFSET_TRAD_PK;
    const uint8_t* trad_sig = request_in + dr42::OFFSET_TRAD_SIG;
    const uint8_t* pqc_pk   = request_in + dr42::OFFSET_PQC_PK;
    const uint8_t* pqc_sig  = request_in + dr42::OFFSET_PQC_SIG;

    uint8_t bound_digest[32];
    dr42::compute_ietf_bound_digest(oid, context, context_len, message, msg_len, bound_digest);

    uint8_t fingerprint[32];
    dr42::compute_composite_fingerprint(sig_type, trad_pk, trad_pk_len, pqc_pk, pqc_pk_len, fingerprint);

    uint32_t status = dr42::STATUS_SUCCESS;
    uint32_t is_valid = 0;
    uint32_t out_flags = flags;
    uint32_t checksum = 0;

    // 5. Execute Composite Sovereign Operation
    if (op_code == dr42::OP_COMPOSITE_KEY_INGRESS) {
        if (trad_pk_len == 0 || pqc_pk_len == 0) {
            status = dr42::STATUS_ERR_MALFORMED_KEY;
            is_valid = 0;
        } else {
            // Check non-zero keys
            uint32_t t_acc = 0;
            DR42_DISABLE_UNROLL
            for (size_t i = 0; i < trad_pk_len && i < 32; ++i) t_acc |= trad_pk[i];
            uint32_t p_acc = 0;
            DR42_DISABLE_UNROLL
            for (size_t i = 0; i < pqc_pk_len && i < 32; ++i) p_acc |= pqc_pk[i];

            if (t_acc == 0 || p_acc == 0) {
                status = dr42::STATUS_ERR_MALFORMED_KEY;
                is_valid = 0;
            } else {
                status = dr42::STATUS_SUCCESS;
                is_valid = 1;
                dr42::copy32_bytes(result_out + 32, fingerprint);
                *(uint32_t*)(result_out + 64) = trad_pk_len;
                *(uint32_t*)(result_out + 68) = pqc_pk_len;
                uint8_t zero_d[32] = {0};
                checksum = dr42::compute_composite_checksum(
                    status, op_code, sig_type, is_valid, flags, zero_d, fingerprint
                );
            }
        }

    } else if (op_code == dr42::OP_COMPOSITE_DIGEST_BIND) {
        status = dr42::STATUS_SUCCESS;
        is_valid = 1;
        dr42::copy32_bytes(result_out + 32, bound_digest);
        dr42::copy32_bytes(result_out + 64, fingerprint);
        checksum = dr42::compute_composite_checksum(
            status, op_code, sig_type, is_valid, flags, bound_digest, fingerprint
        );

    } else if (op_code == dr42::OP_COMPOSITE_VERIFY) {
        int trad_ok = dr42::verify_classical_signature(
            sig_type, bound_digest, trad_pk, trad_pk_len, trad_sig, trad_sig_len
        );
        int pqc_ok = dr42::verify_pqc_signature(
            sig_type, bound_digest, pqc_pk, pqc_pk_len, pqc_sig, pqc_sig_len
        );

        out_flags = (trad_ok ? 1 : 0) | (pqc_ok ? 2 : 0);

        // ANSSI conjunctive rule: both must succeed
        if (trad_ok && pqc_ok) {
            status = dr42::STATUS_SUCCESS;
            is_valid = 1;
        } else if (!trad_ok && pqc_ok) {
            status = dr42::STATUS_ERR_TRAD_VERIFY_FAILED;
            is_valid = 0;
        } else if (trad_ok && !pqc_ok) {
            status = dr42::STATUS_ERR_PQC_VERIFY_FAILED;
            is_valid = 0;
        } else {
            status = dr42::STATUS_ERR_COMPOSITE_VERIFY_FAILED;
            is_valid = 0;
        }

        dr42::copy32_bytes(result_out + 32, bound_digest);
        dr42::copy32_bytes(result_out + 64, fingerprint);
        *(uint32_t*)(result_out + 96) = out_flags;

        checksum = dr42::compute_composite_checksum(
            status, op_code, sig_type, is_valid, out_flags, bound_digest, fingerprint
        );

    } else if (op_code == dr42::OP_COMPOSITE_PACK_SIGNATURE) {
        if (trad_sig_len == 0 || pqc_sig_len == 0) {
            status = dr42::STATUS_ERR_MALFORMED_SIGNATURE;
            is_valid = 0;
        } else {
            uint32_t t_acc = 0;
            DR42_DISABLE_UNROLL
            for (size_t i = 0; i < trad_sig_len && i < 32; ++i) t_acc |= trad_sig[i];
            uint32_t p_acc = 0;
            DR42_DISABLE_UNROLL
            for (size_t i = 0; i < pqc_sig_len && i < 32; ++i) p_acc |= pqc_sig[i];

            if (t_acc == 0 || p_acc == 0) {
                status = dr42::STATUS_ERR_MALFORMED_SIGNATURE;
                is_valid = 0;
            } else {
                status = dr42::STATUS_SUCCESS;
                is_valid = 1;

                // Compute compound signature digest
                dr42::Sha256Ctx s_ctx;
                dr42::sha256_init(&s_ctx);
                uint8_t s_hdr[12];
                *(uint32_t*)(s_hdr + 0) = sig_type;
                *(uint32_t*)(s_hdr + 4) = trad_sig_len;
                *(uint32_t*)(s_hdr + 8) = pqc_sig_len;
                dr42::sha256_update(&s_ctx, s_hdr, 12);
                dr42::sha256_update(&s_ctx, trad_sig, trad_sig_len);
                dr42::sha256_update(&s_ctx, pqc_sig, pqc_sig_len);
                uint8_t sig_digest[32];
                dr42::sha256_final(&s_ctx, sig_digest);

                dr42::copy32_bytes(result_out + 32, sig_digest);
                *(uint32_t*)(result_out + 64) = trad_sig_len;
                *(uint32_t*)(result_out + 68) = pqc_sig_len;
                *(uint32_t*)(result_out + 72) = trad_sig_len + pqc_sig_len;

                checksum = dr42::compute_composite_checksum(
                    status, op_code, sig_type, is_valid, flags, sig_digest, fingerprint
                );
            }
        }

    } else if (op_code == dr42::OP_COMPOSITE_QUERY) {
        status = dr42::STATUS_SUCCESS;
        is_valid = 1;
        uint32_t category = (sig_type == dr42::COMPOSITE_TYPE_MLDSA44_ED25519) ? 2 :
                            ((sig_type == dr42::COMPOSITE_TYPE_MLDSA65_ECDSA_P384) ? 3 : 5);
        *(uint32_t*)(result_out + 32) = category;
        *(uint32_t*)(result_out + 36) = 0x00010002; // version 1.2
        *(uint32_t*)(result_out + 40) = 3;          // 3 suites
        uint8_t zero_d[32] = {0};
        checksum = dr42::compute_composite_checksum(
            status, op_code, sig_type, is_valid, flags, zero_d, zero_d
        );

    } else {
        status = dr42::STATUS_ERR_UNSUPPORTED_OP;
        is_valid = 0;
        checksum = 0;
    }

    // 6. Finalize result header (32 bytes)
    *(uint32_t*)(result_out + 0)  = status;
    *(uint32_t*)(result_out + 4)  = op_code;
    *(uint32_t*)(result_out + 8)  = sig_type;
    *(uint32_t*)(result_out + 12) = is_valid;
    *(uint32_t*)(result_out + 16) = checksum;
    *(uint32_t*)(result_out + 20) = out_flags;
}

} // extern "C"
