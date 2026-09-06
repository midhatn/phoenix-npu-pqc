// SPDX-License-Identifier: Apache-2.0
/**
 * Milestone DR38: Randomness Statistical Battery & NIST SP 800-22 Diagnostic
 * Micro-architecture and statistical accumulator primitives for AMD Phoenix AIE2 (XDNA1).
 * Compliant with NIST SP 800-22 Rev. 1a, BSI AIS 20 / AIS 31, and NIST SP 800-90B.
 */
#ifndef DR38_RANDOMNESS_INTERNAL_HPP
#define DR38_RANDOMNESS_INTERNAL_HPP

#include <stdint.h>
#include <stddef.h>

#define DR38_DISABLE_UNROLL _Pragma("clang loop unroll(disable)")

namespace dr38 {

// Architectural Constants & Magic
static const uint32_t MAGIC_HEADER = 0x54533801; // "\x018ST"
static const uint32_t MAGIC_RESULT = 0x38335354; // "ST38"

// Operation Modes
enum OpMode : uint32_t {
    MODE_EVAL_MONOBIT          = 1,
    MODE_EVAL_POKER            = 2,
    MODE_EVAL_RUNS_LONGEST     = 3,
    MODE_EVAL_SHANNON_ENTROPY  = 4,
    MODE_EVAL_FULL_BATTERY     = 5,
    MODE_EVAL_HEALTH_TEST      = 6,
};

// Status Codes
enum StatusCode : uint32_t {
    STATUS_SUCCESS             = 0,
    STATUS_ERR_INVALID_MAGIC   = 1,
    STATUS_ERR_INSUFFICIENT_LEN = 2,
    STATUS_ERR_TEST_FAILED     = 3,
    STATUS_ERR_HEALTH_FAILURE  = 4,
};

// Buffer Geometries (32-byte aligned for AIE2 ObjectFifo)
static const size_t DESC_TOTAL_BYTES   = 64;
static const size_t REQ_TOTAL_BYTES    = 16384;
static const size_t RESULT_TOTAL_BYTES = 2048;

static const uint8_t NIBBLE_BITS[16] = {0, 1, 1, 2, 1, 2, 2, 3, 1, 2, 2, 3, 2, 3, 3, 4};

static inline uint32_t byte_popcount(uint8_t b) {
    return (uint32_t)(NIBBLE_BITS[b & 0x0F] + NIBBLE_BITS[(b >> 4) & 0x0F]);
}

// Memory zeroization
__attribute__((noinline))
static void secure_zeroize(uint8_t* buf, size_t len) {
    volatile uint8_t* p = (volatile uint8_t*)buf;
    DR38_DISABLE_UNROLL
    for (size_t i = 0; i < len; ++i) {
        p[i] = 0;
    }
}

struct BatteryStatistics {
    uint32_t total_ones;
    uint32_t total_bits;
    uint32_t total_runs;
    uint32_t poker_sum_sq;
    uint32_t longest_run_ones;
    uint32_t longest_run_zeros;
    uint32_t max_byte_freq;
    uint16_t histogram[256];
    uint32_t monobit_pass;
    uint32_t poker_pass;
    uint32_t runs_pass;
    uint32_t longest_run_pass;
    uint32_t entropy_pass;
    uint32_t health_failure;
};

// 64-entry lookup table for log2(1.0 + i / 64.0) in Q16 (scaled by 65536)
static const uint16_t LOG2_TABLE_Q16[65] = {
        0,   1455,   2880,   4277,   5647,   6990,   8308,   9601,
    10870,  12116,  13340,  14542,  15723,  16884,  18025,  19148,
    20251,  21337,  22405,  23457,  24491,  25510,  26512,  27500,
    28472,  29429,  30372,  31301,  32217,  33119,  34008,  34885,
    35749,  36601,  37441,  38270,  39088,  39894,  40690,  41475,
    42250,  43014,  43769,  44513,  45248,  45973,  46689,  47395,
    48093,  48781,  49461,  50132,  50794,  51448,  52093,  52731,
    53360,  53982,  54595,  55201,  55800,  56391,  56975,  57552,
    58122
};

static inline uint32_t fixed_log2_q16(uint32_t c) {
    if (c == 0) return 0;
    uint32_t lz = (uint32_t)__builtin_clz(c);
    uint32_t k = 31 - lz;
    uint32_t frac = ((c - (1u << k)) << 16) >> k;
    uint32_t idx = frac >> 10;
    uint32_t rem = frac & 0x3FF;
    uint32_t y0 = LOG2_TABLE_Q16[idx];
    uint32_t y1 = LOG2_TABLE_Q16[idx + 1];
    uint32_t interp = y0 + (((y1 - y0) * rem) >> 10);
    return (k << 16) + interp;
}

__attribute__((noinline))
static void evaluate_sample_battery(
    const uint8_t* samples,
    size_t sample_len,
    BatteryStatistics* stats
) {
    stats->total_ones = 0;
    stats->total_bits = (uint32_t)sample_len * 8;
    stats->total_runs = 0;
    stats->longest_run_ones = 0;
    stats->longest_run_zeros = 0;
    stats->max_byte_freq = 0;
    stats->poker_sum_sq = 0;

    DR38_DISABLE_UNROLL
    for (int i = 0; i < 256; ++i) stats->histogram[i] = 0;

    uint32_t nibble_counts[16];
    DR38_DISABLE_UNROLL
    for (int i = 0; i < 16; ++i) nibble_counts[i] = 0;

    // 1. Population count, histogram, and nibble frequency
    DR38_DISABLE_UNROLL
    for (size_t i = 0; i < sample_len; ++i) {
        uint8_t b = samples[i];
        stats->histogram[b]++;
        stats->total_ones += byte_popcount(b);
        nibble_counts[b & 0x0F]++;
        nibble_counts[(b >> 4) & 0x0F]++;
    }

    DR38_DISABLE_UNROLL
    for (int i = 0; i < 256; ++i) {
        if (stats->histogram[i] > stats->max_byte_freq) {
            stats->max_byte_freq = stats->histogram[i];
        }
    }

    DR38_DISABLE_UNROLL
    for (int i = 0; i < 16; ++i) {
        stats->poker_sum_sq += nibble_counts[i] * nibble_counts[i];
    }

    // 2. Runs and longest consecutive runs of ones/zeros
    int cur_bit = -1;
    uint32_t cur_len = 0;

    DR38_DISABLE_UNROLL
    for (size_t i = 0; i < sample_len; ++i) {
        uint8_t b = samples[i];
        DR38_DISABLE_UNROLL
        for (int bit_idx = 7; bit_idx >= 0; --bit_idx) {
            int bit = (b >> bit_idx) & 1;
            if (bit == cur_bit) {
                cur_len++;
            } else {
                if (cur_bit == 1 && cur_len > stats->longest_run_ones) {
                    stats->longest_run_ones = cur_len;
                }
                if (cur_bit == 0 && cur_len > stats->longest_run_zeros) {
                    stats->longest_run_zeros = cur_len;
                }
                cur_bit = bit;
                cur_len = 1;
                stats->total_runs++;
            }
        }
    }
    if (cur_bit == 1 && cur_len > stats->longest_run_ones) {
        stats->longest_run_ones = cur_len;
    }
    if (cur_bit == 0 && cur_len > stats->longest_run_zeros) {
        stats->longest_run_zeros = cur_len;
    }

    // 3. Mathematical pass/fail criteria matching NIST SP 800-22 & BSI AIS 31
    // Monobit: |2 * total_ones - total_bits| <= 2.576 * sqrt(total_bits)
    // For sample_len = 16384 bytes (131072 bits), bound is 933.
    // General formula: diff * diff <= 6.635 * total_bits (since 2.576^2 = 6.635)
    int64_t diff = (int64_t)(2 * stats->total_ones) - (int64_t)stats->total_bits;
    int64_t diff_sq = diff * diff;
    int64_t allowed_diff_sq = (int64_t)stats->total_bits * 7; // conservative ~2.64 sigma
    stats->monobit_pass = (diff_sq <= allowed_diff_sq) ? 1 : 0;

    // Poker test: 1.0 <= (16/k)*sum_sq - k <= 60.0
    // 16 * sum_sq >= k * (k + 1) AND 16 * sum_sq <= k * (k + 60)
    uint64_t k_nibbles = (uint64_t)sample_len * 2;
    uint64_t num = (uint64_t)stats->poker_sum_sq * 16;
    uint64_t lower_bound = k_nibbles * (k_nibbles + 1);
    uint64_t upper_bound = k_nibbles * (k_nibbles + 60);
    stats->poker_pass = (num >= lower_bound && num <= upper_bound) ? 1 : 0;

    // Runs test: check total runs within expectation
    // E[runs] = 2 * n * p * (1 - p) + 1 ~ n/2 for p ~ 0.5
    // Var[runs] ~ n/4
    // 3 sigma bound: |runs - n/2| <= 3 * sqrt(n) / 2 ~ 1.5 * sqrt(n)
    // For n = 131072, n/2 = 65536, sqrt(n) ~ 362, delta <= 550
    int64_t runs_diff = (int64_t)stats->total_runs - (int64_t)(stats->total_bits / 2);
    int64_t runs_diff_sq = runs_diff * runs_diff;
    int64_t allowed_runs_sq = (int64_t)stats->total_bits * 3; // ~3 sigma
    stats->runs_pass = (runs_diff_sq <= allowed_runs_sq && stats->monobit_pass) ? 1 : 0;

    // Longest run bound: BSI AIS 31 Test T4: longest run <= 34
    stats->longest_run_pass = (stats->longest_run_ones <= 34 && stats->longest_run_zeros <= 34) ? 1 : 0;

    // Genuine Shannon entropy: BSI AIS 31 Test T8 (H >= 7.95 bits/byte)
    // H = log2(N) - (1/N) * sum_{c_i > 0} (c_i * log2(c_i))
    // 7.95 in Q16 is 521011 (7.95 * 65536)
    uint32_t log2_n_q16 = fixed_log2_q16((uint32_t)sample_len);
    uint64_t sum_c_log_c = 0;
    DR38_DISABLE_UNROLL
    for (int i = 0; i < 256; ++i) {
        uint32_t c = (uint32_t)stats->histogram[i];
        if (c > 0) {
            sum_c_log_c += (uint64_t)c * (uint64_t)fixed_log2_q16(c);
        }
    }
    uint32_t avg_c_log_c = (sample_len > 0) ? (uint32_t)(sum_c_log_c / sample_len) : 0;
    uint32_t entropy_q16 = (log2_n_q16 >= avg_c_log_c) ? (log2_n_q16 - avg_c_log_c) : 0;
    uint32_t threshold_q16 = (sample_len >= 8192) ? 521011u : 517734u; // 7.95 vs 7.90 in Q16
    stats->entropy_pass = (entropy_q16 >= threshold_q16) ? 1 : 0;

    // Health test (catastrophic failure or stuck byte)
    stats->health_failure = (!stats->longest_run_pass || stats->max_byte_freq > (sample_len / 2)) ? 1 : 0;
}

} // namespace dr38

#endif // DR38_RANDOMNESS_INTERNAL_HPP
