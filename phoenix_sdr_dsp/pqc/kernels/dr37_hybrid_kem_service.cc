// SPDX-License-Identifier: Apache-2.0
/**
 * Milestone DR37: Dual-Scheme Hybrid Classical / Quantum-Safe KEM Engine
 * AMD Phoenix NPU (AIE2 / XDNA1 Architecture) Service Kernel.
 * Dispatched on AIE2 vector / crypto compute tiles.
 */

#include <stdint.h>
#include <stddef.h>
#include "dr37_hybrid_kem_internal.hpp"

extern "C" {

void dr37_hybrid_kem_service(
    const uint8_t* restrict request_in,
    const uint8_t* restrict descriptor_in,
    uint8_t* restrict result_out,
    uint32_t request_slots,
    uint32_t descriptor_slots,
    uint32_t result_slots
) {
    // 1. Unpack 64-byte descriptor header
    uint32_t magic       = *(const uint32_t*)(descriptor_in + 0);
    uint32_t op_mode     = *(const uint32_t*)(descriptor_in + 4);
    uint32_t profile_id  = *(const uint32_t*)(descriptor_in + 8);
    uint32_t ss_c_len    = *(const uint32_t*)(descriptor_in + 12);
    uint32_t ss_pqc_len  = *(const uint32_t*)(descriptor_in + 16);
    uint32_t ct_c_len    = *(const uint32_t*)(descriptor_in + 20);
    uint32_t ct_pqc_len  = *(const uint32_t*)(descriptor_in + 24);
    uint32_t flags       = *(const uint32_t*)(descriptor_in + 28);
    uint32_t seq_id      = *(const uint32_t*)(descriptor_in + 32);

    // Zero out initial 256 bytes of result buffer
    DR37_DISABLE_UNROLL
    for (size_t i = 0; i < 256; ++i) {
        result_out[i] = 0;
    }

    // 2. Validate magic header
    if (magic != dr37::MAGIC_HEADER) {
        *(uint32_t*)(result_out + 0) = dr37::STATUS_ERR_INVALID_MAGIC;
        *(uint32_t*)(result_out + 4) = op_mode;
        *(uint32_t*)(result_out + 8) = 0; // Outcome: Failure
        *(uint32_t*)(result_out + 12) = 0;
        return;
    }

    // 3. Validate profile identifier
    if (profile_id != dr37::PROFILE_X25519_MLKEM768 &&
        profile_id != dr37::PROFILE_SECP384R1_MLKEM1024) {
        *(uint32_t*)(result_out + 0) = dr37::STATUS_ERR_INVALID_PROFILE;
        *(uint32_t*)(result_out + 4) = op_mode;
        *(uint32_t*)(result_out + 8) = 0; // Outcome: Failure
        *(uint32_t*)(result_out + 12) = 0;
        return;
    }

    // 4. Handle Zeroize mode
    if (op_mode == dr37::MODE_HYBRID_ZEROIZE) {
        *(uint32_t*)(result_out + 0) = dr37::STATUS_SUCCESS;
        *(uint32_t*)(result_out + 4) = op_mode;
        *(uint32_t*)(result_out + 8) = 1; // Outcome: Success
        *(uint32_t*)(result_out + 12) = 200; // Cycle estimate
        return;
    }

    // 5. Unpack request fields from 16KB request tensor
    const uint8_t* classical_ss = request_in + 0;
    const uint8_t* pqc_ss       = request_in + 32;
    const uint8_t* classical_ct = request_in + 64;
    const uint8_t* salt         = request_in + 96;
    const uint8_t* pqc_ct       = request_in + 128;

    // 6. Enforce anti-degenerate key policies
    int classical_is_zero = dr37::ct_is_all_zero(classical_ss, 32);
    int pqc_is_zero       = dr37::ct_is_all_zero(pqc_ss, 32);

    if (op_mode == dr37::MODE_HYBRID_ENCAPS_COMBINE ||
        op_mode == dr37::MODE_HYBRID_DECAPS_COMBINE ||
        op_mode == dr37::MODE_HYBRID_POLICY_ENFORCE) {
        if (classical_is_zero || pqc_is_zero) {
            *(uint32_t*)(result_out + 0) = dr37::STATUS_ERR_DEGENERATE_KEY;
            *(uint32_t*)(result_out + 4) = op_mode;
            *(uint32_t*)(result_out + 8) = 0; // Outcome: Failure
            *(uint32_t*)(result_out + 12) = 150;
            return;
        }
    }

    // Bound ct_pqc_len for memory safety
    size_t effective_ct_pqc_len = ct_pqc_len;
    if (effective_ct_pqc_len > 1568) {
        effective_ct_pqc_len = 1568;
    }

    // 7. Execute Normative ETSI TS 103 744 Combiner
    uint8_t* final_ss          = result_out + 16;
    uint8_t* enc_key           = result_out + 48;
    uint8_t* mac_key           = result_out + 80;
    uint8_t* derived_iv        = result_out + 112;
    uint8_t* transcript_digest = result_out + 128;

    dr37::combine_hybrid_keys(
        profile_id,
        classical_ss,
        pqc_ss,
        classical_ct,
        salt,
        pqc_ct,
        effective_ct_pqc_len,
        final_ss,
        enc_key,
        mac_key,
        derived_iv,
        transcript_digest
    );

    // 8. Set return status header
    uint32_t cycle_est = (profile_id == dr37::PROFILE_X25519_MLKEM768) ? 720 : 950;
    *(uint32_t*)(result_out + 0) = dr37::STATUS_SUCCESS;
    *(uint32_t*)(result_out + 4) = op_mode;
    *(uint32_t*)(result_out + 8) = 1; // Outcome: Success
    *(uint32_t*)(result_out + 12) = cycle_est;
}

} // extern "C"
