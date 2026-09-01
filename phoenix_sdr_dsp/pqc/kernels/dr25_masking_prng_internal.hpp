// SPDX-License-Identifier: Apache-2.0
/**
 * Milestone DR25: Higher-Order Masking & On-Chip Local PRNG Entropy Expansion
 * Micro-architecture and polynomial blinding primitives for AMD Phoenix AIE2 (XDNA1).
 */
#ifndef DR25_MASKING_PRNG_INTERNAL_HPP
#define DR25_MASKING_PRNG_INTERNAL_HPP

#include <stdint.h>
#include <stddef.h>
#include "dr1_keccak_f1600.hpp"

#define DR25_DISABLE_UNROLL _Pragma("clang loop unroll(disable)")

namespace dr25 {

// On-tile FIPS 202 SHAKE-128 PRNG stream generator (rate = 168 bytes)
__attribute__((noinline))
static void shake128_stream(
    const uint8_t* seed,
    size_t seed_len,
    uint8_t* out,
    size_t out_len
) {
    alignas(8) uint8_t state[200];
    DR25_DISABLE_UNROLL
    for (int i = 0; i < 200; ++i) state[i] = 0;

    const size_t rate = 168; // SHAKE-128 rate
    size_t spos = 0;

    DR25_DISABLE_UNROLL
    for (size_t i = 0; i < seed_len; ++i) {
        state[spos++] ^= seed[i];
        if (spos == rate) {
            phoenix_sdr_dsp::pqc::dr1::keccak_f1600(state);
            spos = 0;
        }
    }

    // FIPS 202 SHAKE-128 domain separator (0x1F) and padding
    state[spos] ^= 0x1Fu;
    state[rate - 1] ^= 0x80u;
    phoenix_sdr_dsp::pqc::dr1::keccak_f1600(state);

    size_t squeezed = 0;
    while (squeezed < out_len) {
        size_t take = (out_len - squeezed < rate) ? (out_len - squeezed) : rate;
        DR25_DISABLE_UNROLL
        for (size_t i = 0; i < take; ++i) {
            out[squeezed + i] = state[i];
        }
        squeezed += take;
        if (squeezed < out_len) {
            phoenix_sdr_dsp::pqc::dr1::keccak_f1600(state);
        }
    }
}

// Expands 32-byte seed into 256-coefficient polynomial mask modulo q
__attribute__((noinline))
static void expand_mask_poly(
    const uint8_t* seed,
    uint32_t domain_sep,
    uint16_t* out_poly,
    uint32_t num_coeffs,
    uint32_t q
) {
    uint8_t prng_input[36];
    DR25_DISABLE_UNROLL
    for (int i = 0; i < 32; ++i) prng_input[i] = seed[i];
    prng_input[32] = (uint8_t)(domain_sep & 0xFF);
    prng_input[33] = (uint8_t)((domain_sep >> 8) & 0xFF);
    prng_input[34] = (uint8_t)((domain_sep >> 16) & 0xFF);
    prng_input[35] = (uint8_t)((domain_sep >> 24) & 0xFF);

    // Squeeze 2 * num_coeffs bytes of raw keystream
    uint8_t raw_bytes[1024];
    size_t req_bytes = num_coeffs * 2;
    if (req_bytes > 1024) req_bytes = 1024;
    shake128_stream(prng_input, 36, raw_bytes, req_bytes);

    DR25_DISABLE_UNROLL
    for (uint32_t i = 0; i < num_coeffs; ++i) {
        uint32_t val = (uint32_t)raw_bytes[2 * i] | ((uint32_t)raw_bytes[2 * i + 1] << 8);
        out_poly[i] = (uint16_t)(val % q);
    }
}

// 1st-Order Polynomial Blinding (1 secret -> 2 shares)
__attribute__((noinline))
static void mask_1st_order(
    const uint16_t* s,
    const uint16_t* mask,
    uint16_t* s0,
    uint16_t* s1,
    uint32_t num_coeffs,
    uint32_t q
) {
    DR25_DISABLE_UNROLL
    for (uint32_t i = 0; i < num_coeffs; ++i) {
        uint32_t m = mask[i] % q;
        uint32_t orig = s[i] % q;
        s0[i] = (uint16_t)((orig + q - m) % q);
        s1[i] = (uint16_t)m;
    }
}

// 2nd-Order Polynomial Blinding (1 secret -> 3 shares)
__attribute__((noinline))
static void mask_2nd_order(
    const uint16_t* s,
    const uint16_t* mask1,
    const uint16_t* mask2,
    uint16_t* s0,
    uint16_t* s1,
    uint16_t* s2,
    uint32_t num_coeffs,
    uint32_t q
) {
    DR25_DISABLE_UNROLL
    for (uint32_t i = 0; i < num_coeffs; ++i) {
        uint32_t m1 = mask1[i] % q;
        uint32_t m2 = mask2[i] % q;
        uint32_t orig = s[i] % q;
        s0[i] = (uint16_t)((orig + 2 * q - m1 - m2) % q);
        s1[i] = (uint16_t)m1;
        s2[i] = (uint16_t)m2;
    }
}

// 1st-Order Polynomial Unmasking (2 shares -> 1 secret)
__attribute__((noinline))
static void unmask_1st_order(
    const uint16_t* s0,
    const uint16_t* s1,
    uint16_t* s,
    uint32_t num_coeffs,
    uint32_t q
) {
    DR25_DISABLE_UNROLL
    for (uint32_t i = 0; i < num_coeffs; ++i) {
        s[i] = (uint16_t)(((uint32_t)s0[i] + (uint32_t)s1[i]) % q);
    }
}

// 2nd-Order Polynomial Unmasking (3 shares -> 1 secret)
__attribute__((noinline))
static void unmask_2nd_order(
    const uint16_t* s0,
    const uint16_t* s1,
    const uint16_t* s2,
    uint16_t* s,
    uint32_t num_coeffs,
    uint32_t q
) {
    DR25_DISABLE_UNROLL
    for (uint32_t i = 0; i < num_coeffs; ++i) {
        s[i] = (uint16_t)(((uint32_t)s0[i] + (uint32_t)s1[i] + (uint32_t)s2[i]) % q);
    }
}

// Component-wise Masked Polynomial Addition (1st-Order)
__attribute__((noinline))
static void masked_add_1st_order(
    const uint16_t* a0, const uint16_t* a1,
    const uint16_t* b0, const uint16_t* b1,
    uint16_t* c0, uint16_t* c1,
    uint32_t num_coeffs,
    uint32_t q
) {
    DR25_DISABLE_UNROLL
    for (uint32_t i = 0; i < num_coeffs; ++i) {
        c0[i] = (uint16_t)(((uint32_t)a0[i] + (uint32_t)b0[i]) % q);
        c1[i] = (uint16_t)(((uint32_t)a1[i] + (uint32_t)b1[i]) % q);
    }
}

// Strong Non-Interfering (SNI) 1st-Order Share Refresh
__attribute__((noinline))
static void sni_refresh_1st_order(
    const uint16_t* in_s0,
    const uint16_t* in_s1,
    const uint16_t* refresh_r,
    uint16_t* out_s0,
    uint16_t* out_s1,
    uint32_t num_coeffs,
    uint32_t q
) {
    DR25_DISABLE_UNROLL
    for (uint32_t i = 0; i < num_coeffs; ++i) {
        uint32_t r = refresh_r[i] % q;
        out_s0[i] = (uint16_t)(((uint32_t)in_s0[i] + r) % q);
        out_s1[i] = (uint16_t)(((uint32_t)in_s1[i] + q - r) % q);
    }
}

// Strong Non-Interfering (SNI) 2nd-Order Share Refresh
__attribute__((noinline))
static void sni_refresh_2nd_order(
    const uint16_t* in_s0,
    const uint16_t* in_s1,
    const uint16_t* in_s2,
    const uint16_t* r01,
    const uint16_t* r02,
    const uint16_t* r12,
    uint16_t* out_s0,
    uint16_t* out_s1,
    uint16_t* out_s2,
    uint32_t num_coeffs,
    uint32_t q
) {
    DR25_DISABLE_UNROLL
    for (uint32_t i = 0; i < num_coeffs; ++i) {
        uint32_t mask01 = r01[i] % q;
        uint32_t mask02 = r02[i] % q;
        uint32_t mask12 = r12[i] % q;

        out_s0[i] = (uint16_t)(((uint32_t)in_s0[i] + mask01 + mask02) % q);
        out_s1[i] = (uint16_t)(((uint32_t)in_s1[i] + q - mask01 + mask12) % q);
        out_s2[i] = (uint16_t)(((uint32_t)in_s2[i] + 2 * q - mask02 - mask12) % q);
    }
}

} // namespace dr25

#endif // DR25_MASKING_PRNG_INTERNAL_HPP
