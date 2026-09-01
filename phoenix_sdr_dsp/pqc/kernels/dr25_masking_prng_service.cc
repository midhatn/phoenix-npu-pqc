// SPDX-License-Identifier: Apache-2.0
/**
 * Milestone DR25: Higher-Order Masking & Local PRNG Entropy Expansion AIE2 Kernel.
 * Target: AMD Phoenix NPU (AIE2 / XDNA1 Architecture).
 */

#include <stdint.h>
#include <stddef.h>
#include "dr25_masking_prng_internal.hpp"

extern "C" {

void dr25_masking_prng_service(
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
    uint32_t modulus = *(const uint32_t*)(descriptor_in + 8);
    uint32_t num_coeffs = *(const uint32_t*)(descriptor_in + 12);
    uint32_t epoch = *(const uint32_t*)(descriptor_in + 16);

    if (num_coeffs == 0 || num_coeffs > 256) num_coeffs = 256;
    if (modulus == 0) modulus = 3329;

    // Check magic
    if (magic != 0x01254D53) {
        *(uint32_t*)(result_out + 0) = 0xDEAD0002;
        *(uint32_t*)(result_out + 4) = 0;
        *(uint32_t*)(result_out + 8) = 1; // Error invalid magic
        return;
    }

    // Zero out result header
    for (int i = 0; i < 16; ++i) result_out[i] = 0;
    *(uint32_t*)(result_out + 0) = 0x01254D53;
    *(uint32_t*)(result_out + 4) = epoch;

    uint32_t poly_bytes = num_coeffs * 2;

    if (op_mode == 0) {
        // MODE_PRNG_EXPAND
        // Input: seed(32 B) + domain_sep(4 B)
        const uint8_t* seed = request_in;
        uint32_t domain_sep = *(const uint32_t*)(request_in + 32);
        uint16_t* out_poly = (uint16_t*)(result_out + 16);

        dr25::expand_mask_poly(seed, domain_sep, out_poly, num_coeffs, modulus);
        *(uint32_t*)(result_out + 8) = 0; // Success
        *(uint32_t*)(result_out + 12) = poly_bytes;
    } else if (op_mode == 1) {
        // MODE_MASK_1ST_ORDER
        // Input: s(poly_bytes) + mask(poly_bytes)
        const uint16_t* s = (const uint16_t*)request_in;
        const uint16_t* mask = (const uint16_t*)(request_in + poly_bytes);
        uint16_t* s0 = (uint16_t*)(result_out + 16);
        uint16_t* s1 = (uint16_t*)(result_out + 16 + poly_bytes);

        dr25::mask_1st_order(s, mask, s0, s1, num_coeffs, modulus);
        *(uint32_t*)(result_out + 8) = 0;
        *(uint32_t*)(result_out + 12) = 2 * poly_bytes;
    } else if (op_mode == 2) {
        // MODE_MASK_2ND_ORDER
        // Input: s(poly_bytes) + mask1(poly_bytes) + mask2(poly_bytes)
        const uint16_t* s = (const uint16_t*)request_in;
        const uint16_t* mask1 = (const uint16_t*)(request_in + poly_bytes);
        const uint16_t* mask2 = (const uint16_t*)(request_in + 2 * poly_bytes);
        uint16_t* s0 = (uint16_t*)(result_out + 16);
        uint16_t* s1 = (uint16_t*)(result_out + 16 + poly_bytes);
        uint16_t* s2 = (uint16_t*)(result_out + 16 + 2 * poly_bytes);

        dr25::mask_2nd_order(s, mask1, mask2, s0, s1, s2, num_coeffs, modulus);
        *(uint32_t*)(result_out + 8) = 0;
        *(uint32_t*)(result_out + 12) = 3 * poly_bytes;
    } else if (op_mode == 3) {
        // MODE_UNMASK_1ST_ORDER
        // Input: s0(poly_bytes) + s1(poly_bytes)
        const uint16_t* s0 = (const uint16_t*)request_in;
        const uint16_t* s1 = (const uint16_t*)(request_in + poly_bytes);
        uint16_t* s = (uint16_t*)(result_out + 16);

        dr25::unmask_1st_order(s0, s1, s, num_coeffs, modulus);
        *(uint32_t*)(result_out + 8) = 0;
        *(uint32_t*)(result_out + 12) = poly_bytes;
    } else if (op_mode == 4) {
        // MODE_UNMASK_2ND_ORDER
        // Input: s0(poly_bytes) + s1(poly_bytes) + s2(poly_bytes)
        const uint16_t* s0 = (const uint16_t*)request_in;
        const uint16_t* s1 = (const uint16_t*)(request_in + poly_bytes);
        const uint16_t* s2 = (const uint16_t*)(request_in + 2 * poly_bytes);
        uint16_t* s = (uint16_t*)(result_out + 16);

        dr25::unmask_2nd_order(s0, s1, s2, s, num_coeffs, modulus);
        *(uint32_t*)(result_out + 8) = 0;
        *(uint32_t*)(result_out + 12) = poly_bytes;
    } else if (op_mode == 5) {
        // MODE_MASKED_ADD_1ST
        // Input: a0, a1, b0, b1
        const uint16_t* a0 = (const uint16_t*)request_in;
        const uint16_t* a1 = (const uint16_t*)(request_in + poly_bytes);
        const uint16_t* b0 = (const uint16_t*)(request_in + 2 * poly_bytes);
        const uint16_t* b1 = (const uint16_t*)(request_in + 3 * poly_bytes);
        uint16_t* c0 = (uint16_t*)(result_out + 16);
        uint16_t* c1 = (uint16_t*)(result_out + 16 + poly_bytes);

        dr25::masked_add_1st_order(a0, a1, b0, b1, c0, c1, num_coeffs, modulus);
        *(uint32_t*)(result_out + 8) = 0;
        *(uint32_t*)(result_out + 12) = 2 * poly_bytes;
    } else if (op_mode == 7) {
        // MODE_SNI_REFRESH_1ST
        // Input: in_s0, in_s1, r
        const uint16_t* in_s0 = (const uint16_t*)request_in;
        const uint16_t* in_s1 = (const uint16_t*)(request_in + poly_bytes);
        const uint16_t* r = (const uint16_t*)(request_in + 2 * poly_bytes);
        uint16_t* out_s0 = (uint16_t*)(result_out + 16);
        uint16_t* out_s1 = (uint16_t*)(result_out + 16 + poly_bytes);

        dr25::sni_refresh_1st_order(in_s0, in_s1, r, out_s0, out_s1, num_coeffs, modulus);
        *(uint32_t*)(result_out + 8) = 0;
        *(uint32_t*)(result_out + 12) = 2 * poly_bytes;
    } else if (op_mode == 8) {
        // MODE_SNI_REFRESH_2ND
        // Input: in_s0, in_s1, in_s2, r01, r02, r12
        const uint16_t* in_s0 = (const uint16_t*)request_in;
        const uint16_t* in_s1 = (const uint16_t*)(request_in + poly_bytes);
        const uint16_t* in_s2 = (const uint16_t*)(request_in + 2 * poly_bytes);
        const uint16_t* r01 = (const uint16_t*)(request_in + 3 * poly_bytes);
        const uint16_t* r02 = (const uint16_t*)(request_in + 4 * poly_bytes);
        const uint16_t* r12 = (const uint16_t*)(request_in + 5 * poly_bytes);
        uint16_t* out_s0 = (uint16_t*)(result_out + 16);
        uint16_t* out_s1 = (uint16_t*)(result_out + 16 + poly_bytes);
        uint16_t* out_s2 = (uint16_t*)(result_out + 16 + 2 * poly_bytes);

        dr25::sni_refresh_2nd_order(in_s0, in_s1, in_s2, r01, r02, r12, out_s0, out_s1, out_s2, num_coeffs, modulus);
        *(uint32_t*)(result_out + 8) = 0;
        *(uint32_t*)(result_out + 12) = 3 * poly_bytes;
    } else {
        *(uint32_t*)(result_out + 8) = 0xFF; // Unsupported mode
    }
}

} // extern "C"
