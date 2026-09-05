// SPDX-License-Identifier: Apache-2.0
/**
 * Milestone DR40: High-Throughput Hardware Benchmark & Profiling Battery
 * Internal AIE2 vector compute definitions, primitive workload implementations,
 * and polynomial/state operations.
 */

#ifndef PHOENIX_PQC_DR40_BENCHMARK_INTERNAL_HPP
#define PHOENIX_PQC_DR40_BENCHMARK_INTERNAL_HPP

#include <stdint.h>
#include <stddef.h>

#ifdef __AIE2__
#define DR40_INLINE inline __attribute__((always_inline))
#define DR40_DISABLE_UNROLL _Pragma("clang loop unroll(disable)")
#else
#define DR40_INLINE inline
#define DR40_DISABLE_UNROLL
#endif

namespace dr40 {

// Magic & Status
static const uint32_t MAGIC_HEADER              = 0x44523430; // 'DR40'
static const uint32_t STATUS_SUCCESS             = 0x00000000;
static const uint32_t STATUS_ERR_INVALID_MAGIC   = 0x80000001;
static const uint32_t STATUS_ERR_UNSUPPORTED_MODE= 0x80000002;
static const uint32_t STATUS_ERR_INVALID_BATCH   = 0x80000003;

// Modes
static const uint32_t MODE_BENCH_NTT_BUTTERFLY   = 0x00000001;
static const uint32_t MODE_BENCH_KECCAK_F1600    = 0x00000002;
static const uint32_t MODE_BENCH_VECTOR_MAC      = 0x00000003;
static const uint32_t MODE_BENCH_SAMPLE_NTT      = 0x00000004;

// Modulus constants
static const uint32_t MODULUS_Q   = 3329;
static const uint32_t MONTGOMERY_R = 3328;

// Montgomery reduction: (a * R^{-1}) mod q
DR40_INLINE uint32_t montgomery_reduce(uint32_t a) {
    uint32_t t = (a * 62209u) & 0xFFFFu;
    int32_t res = ((int32_t)a - (int32_t)(t * MODULUS_Q)) >> 16;
    if (res < 0) {
        res += MODULUS_Q;
    }
    return (uint32_t)(res % MODULUS_Q);
}

// Butterfly layer: 128 radix-2 butterflies on 256 coefficients
DR40_INLINE void ntt_butterfly_layer(uint16_t* poly, uint32_t twiddle) {
    DR40_DISABLE_UNROLL
    for (size_t i = 0; i < 128; ++i) {
        uint32_t u = poly[i];
        uint32_t v = poly[i + 128];
        uint32_t v_tw = (v * twiddle) % MODULUS_Q;
        poly[i] = (uint16_t)((u + v_tw) % MODULUS_Q);
        poly[i + 128] = (uint16_t)((u - v_tw + MODULUS_Q) % MODULUS_Q);
    }
}

// Vector multiply-accumulate on 256 coefficients: accum[i] += (poly_a[i] * poly_b[i]) mod q
DR40_INLINE void vector_mac_step(uint16_t* accum, const uint16_t* poly_a, const uint16_t* poly_b) {
    DR40_DISABLE_UNROLL
    for (size_t i = 0; i < 256; ++i) {
        uint32_t prod = ((uint32_t)poly_a[i] * (uint32_t)poly_b[i]) % MODULUS_Q;
        accum[i] = (uint16_t)(((uint32_t)accum[i] + prod) % MODULUS_Q);
    }
}

// Keccak-f[1600] single round on 25 64-bit lanes
static const uint64_t KECCAK_ROUND_CONSTANTS[24] = {
    0x0000000000000001ULL, 0x0000000000008082ULL, 0x800000000000808AULL, 0x8000000080008000ULL,
    0x000000000000808BULL, 0x0000000080000001ULL, 0x8000000080008081ULL, 0x8000000000008009ULL,
    0x000000000000008AULL, 0x0000000000000088ULL, 0x0000000080008009ULL, 0x000000008000000AULL,
    0x000000008000808BULL, 0x800000000000008BULL, 0x8000000000008089ULL, 0x8000000000008003ULL,
    0x8000000000008002ULL, 0x8000000000000080ULL, 0x000000000000800AULL, 0x800000008000000AULL,
    0x8000000080008081ULL, 0x8000000000008080ULL, 0x0000000080000001ULL, 0x8000000080008008ULL,
};

static const uint8_t KECCAK_ROTATION_OFFSETS[25] = {
    0,  1, 62, 28, 27,
    36, 44,  6, 55, 20,
     3, 10, 43, 25, 39,
    41, 45, 15, 21,  8,
    18,  2, 61, 56, 14,
};

DR40_INLINE uint64_t rotl64(uint64_t x, uint8_t r) {
    return (r == 0) ? x : ((x << r) | (x >> (64 - r)));
}

DR40_INLINE void keccak_round(uint64_t* state, size_t round_idx) {
    // Theta
    uint64_t c[5];
    for (size_t x = 0; x < 5; ++x) {
        c[x] = state[x] ^ state[x + 5] ^ state[x + 10] ^ state[x + 15] ^ state[x + 20];
    }
    uint64_t d[5];
    for (size_t x = 0; x < 5; ++x) {
        d[x] = c[(x + 4) % 5] ^ rotl64(c[(x + 1) % 5], 1);
    }
    uint64_t theta_state[25];
    for (size_t i = 0; i < 25; ++i) {
        theta_state[i] = state[i] ^ d[i % 5];
    }

    // Rho and Pi
    uint64_t b[25];
    for (size_t x = 0; x < 5; ++x) {
        for (size_t y = 0; y < 5; ++y) {
            size_t idx = x + 5 * y;
            uint8_t r = KECCAK_ROTATION_OFFSETS[idx];
            size_t new_idx = y + 5 * ((2 * x + 3 * y) % 5);
            b[new_idx] = rotl64(theta_state[idx], r);
        }
    }

    // Chi
    for (size_t x = 0; x < 5; ++x) {
        for (size_t y = 0; y < 5; ++y) {
            size_t idx = x + 5 * y;
            state[idx] = b[idx] ^ ((~b[((x + 1) % 5) + 5 * y]) & b[((x + 2) % 5) + 5 * y]);
        }
    }

    // Iota
    state[0] ^= KECCAK_ROUND_CONSTANTS[round_idx % 24];
}

// Bounded rejection sampling from uniform byte stream into 256 coefficients in [0, 3329)
DR40_INLINE size_t sample_ntt(const uint8_t* seed_bytes, size_t seed_len, uint16_t* coeffs) {
    size_t count = 0;
    size_t i = 0;
    while (count < 256 && (i + 2) < seed_len) {
        uint32_t b0 = seed_bytes[i];
        uint32_t b1 = seed_bytes[i + 1];
        uint32_t b2 = seed_bytes[i + 2];
        uint32_t d1 = b0 | ((b1 & 0x0Fu) << 8);
        uint32_t d2 = (b1 >> 4) | (b2 << 4);
        if (d1 < MODULUS_Q && count < 256) {
            coeffs[count++] = (uint16_t)d1;
        }
        if (d2 < MODULUS_Q && count < 256) {
            coeffs[count++] = (uint16_t)d2;
        }
        i += 3;
    }
    while (count < 256) {
        coeffs[count++] = 0;
    }
    return count;
}

} // namespace dr40

#endif // PHOENIX_PQC_DR40_BENCHMARK_INTERNAL_HPP
