// SPDX-License-Identifier: Apache-2.0
/**
 * Milestone DR28: NIST SP 800-208 / RFC 8554 LMS Stateless Verification AIE2 Kernel.
 * Target: AMD Phoenix NPU (AIE2 / XDNA1 Architecture).
 */

#include <stdint.h>
#include <stddef.h>
#include "dr28_lms_verifier_internal.hpp"

extern "C" {

void dr28_lms_verifier_service(
    const uint8_t* restrict request_in,
    const uint8_t* restrict descriptor_in,
    uint8_t* restrict result_out,
    uint32_t request_slots,
    uint32_t descriptor_slots,
    uint32_t result_slots
) {
    // 1. Unpack descriptor
    uint32_t magic = *(const uint32_t*)(descriptor_in + 0);
    uint32_t op_mode = *(const uint32_t*)(descriptor_in + 4);
    uint32_t msg_len = *(const uint32_t*)(descriptor_in + 8);
    uint32_t epoch = *(const uint32_t*)(descriptor_in + 12);
    uint32_t lms_type = *(const uint32_t*)(descriptor_in + 16);
    uint32_t lmots_type = *(const uint32_t*)(descriptor_in + 20);

    // Check magic
    if (magic != 0x01284C4D) {
        *(uint32_t*)(result_out + 0) = 0xDEAD0004;
        *(uint32_t*)(result_out + 4) = 0;
        *(uint32_t*)(result_out + 8) = 1; // Error invalid magic
        return;
    }

    // Zero out result header
    for (int i = 0; i < 16; ++i) result_out[i] = 0;
    *(uint32_t*)(result_out + 0) = 0x01284C4D;
    *(uint32_t*)(result_out + 4) = epoch;

    const uint32_t h = 5; // LMS_SHA256_M32_H5 depth

    if (op_mode == 0) {
        // MODE_VERIFY_LMS_SIGNATURE
        // Input: I(16) + T1_expected(32) + q(4) + C(32) + y_sigs(2144) + auth_path(160) + msg(msg_len)
        const uint8_t* I = request_in;
        const uint8_t* t1_expected = request_in + 16;
        uint32_t q = *(const uint32_t*)(request_in + 48);
        const uint8_t* C = request_in + 52;
        const uint8_t* y_sigs = request_in + 84;
        const uint8_t* auth_path = request_in + 84 + 2144;
        const uint8_t* msg = request_in + 84 + 2144 + 160;

        uint8_t leaf_kc[32];
        dr28::lm_ots_recover_leaf(I, q, C, y_sigs, msg, msg_len, leaf_kc);

        uint8_t calc_root[32];
        dr28::lms_traverse_path(I, q, leaf_kc, auth_path, h, calc_root);

        // Constant-time compare root with expected
        uint8_t diff = 0;
        for (int i = 0; i < 32; ++i) {
            diff |= (calc_root[i] ^ t1_expected[i]);
            result_out[16 + i] = calc_root[i]; // Echo calculated root
        }

        *(uint32_t*)(result_out + 8) = (diff == 0) ? 0 : 2; // 0: VALID, 2: INVALID
        *(uint32_t*)(result_out + 12) = 32;
    } else if (op_mode == 1) {
        // MODE_RECOVER_LMOTS_LEAF
        // Input: I(16) + q(4) + C(32) + y_sigs(2144) + msg(msg_len)
        const uint8_t* I = request_in;
        uint32_t q = *(const uint32_t*)(request_in + 16);
        const uint8_t* C = request_in + 20;
        const uint8_t* y_sigs = request_in + 52;
        const uint8_t* msg = request_in + 52 + 2144;

        uint8_t* leaf_kc = result_out + 16;
        dr28::lm_ots_recover_leaf(I, q, C, y_sigs, msg, msg_len, leaf_kc);

        *(uint32_t*)(result_out + 8) = 0;
        *(uint32_t*)(result_out + 12) = 32;
    } else if (op_mode == 2) {
        // MODE_MERKLE_PATH_TRAVERSE
        // Input: I(16) + q(4) + leaf_kc(32) + auth_path(160)
        const uint8_t* I = request_in;
        uint32_t q = *(const uint32_t*)(request_in + 16);
        const uint8_t* leaf_kc = request_in + 20;
        const uint8_t* auth_path = request_in + 52;

        uint8_t* out_root = result_out + 16;
        dr28::lms_traverse_path(I, q, leaf_kc, auth_path, h, out_root);

        *(uint32_t*)(result_out + 8) = 0;
        *(uint32_t*)(result_out + 12) = 32;
    } else {
        *(uint32_t*)(result_out + 8) = 0xFF; // Unsupported mode
    }
}

} // extern "C"
