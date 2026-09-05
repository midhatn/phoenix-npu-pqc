// SPDX-License-Identifier: Apache-2.0
/**
 * Milestone DR39: dudect Side-Channel Timing & TVLA Constant-Time Diagnostic
 * Micro-architecture and Welch's t-test statistical primitives for AMD Phoenix AIE2 (XDNA1).
 * Compliant with NIST SP 800-140F, ISO/IEC 17825:2016/2024, and Reparaz et al. (DATE 2017).
 */
#ifndef DR39_DUDECT_INTERNAL_HPP
#define DR39_DUDECT_INTERNAL_HPP

#include <stdint.h>
#include <stddef.h>

#define DR39_DISABLE_UNROLL _Pragma("clang loop unroll(disable)")

namespace dr39 {

// Architectural Constants & Magic
static const uint32_t MAGIC_HEADER = 0x54443901; // "\x019DT"
static const uint32_t MAGIC_RESULT = 0x39334454; // "TD39"

// Operation Modes
enum OpMode : uint32_t {
    MODE_BENCH_CONSTANT_TIME_SELECT       = 1,
    MODE_BENCH_VARIABLE_TIME_BRANCH       = 2,
    MODE_BENCH_MONTGOMERY_REDUCTION       = 3,
    MODE_BENCH_POLYNOMIAL_ADD_SUB         = 4,
    MODE_BENCH_VARIABLE_TIME_EARLY_EXIT   = 5,
    MODE_BENCH_FULL_SUITE                 = 6,
};

// Status Codes
enum StatusCode : uint32_t {
    STATUS_SUCCESS                        = 0,
    STATUS_ERR_INVALID_MAGIC              = 1,
    STATUS_ERR_INSUFFICIENT_LEN           = 2,
    STATUS_ERR_TIMING_LEAKAGE             = 3,
    STATUS_ERR_PARAM_OUT_OF_BOUNDS        = 4,
};

// Buffer Geometries (32-byte aligned for AIE2 ObjectFifo)
static const size_t DESC_TOTAL_BYTES   = 64;
static const size_t REQ_TOTAL_BYTES    = 4096;
static const size_t RESULT_TOTAL_BYTES = 2048;

// dudect Threshold scaled by 1000 (|t| > 4.5 -> 4500)
static const int32_t DUDECT_T_THRESHOLD_SCALED = 4500;

// 32-bit integer square root (integer arithmetic only)
static inline uint32_t isqrt32(uint32_t n) {
    if (n == 0) return 0;
    uint32_t x0 = n / 2;
    if (x0 == 0) return 1;
    uint32_t x1 = (x0 + n / x0) / 2;
    DR39_DISABLE_UNROLL
    while (x1 < x0) {
        x0 = x1;
        x1 = (x0 + n / x0) / 2;
    }
    return x0;
}

// 1. Constant-time conditional move / select (Multiplexer: (mask & a) ^ (~mask & b))
__attribute__((noinline))
static uint32_t ct_select32(uint32_t mask, uint32_t a, uint32_t b) {
    return (mask & a) ^ ((~mask) & b);
}

// 2. Variable-time branch (Intentionally leaky microarchitecture for dudect validation)
__attribute__((noinline))
static uint32_t vt_branch32(uint32_t secret_flag, uint32_t a, uint32_t b) {
    volatile uint32_t acc = a;
    if (secret_flag != 0) {
        // Taken branch executes multi-cycle delay loop
        DR39_DISABLE_UNROLL
        for (volatile int i = 0; i < 64; ++i) {
            acc += (b ^ (uint32_t)i);
        }
    }
    return acc;
}

// 3. Constant-time Montgomery reduction in Z_q (q = 3329 for ML-KEM)
// R = 2^16, q = 3329, q_inv = 62209 (-q^-1 mod 2^16 = 3327)
__attribute__((noinline))
static int16_t ct_montgomery_reduce(int32_t a) {
    const int32_t q = 3329;
    const int32_t q_inv = 3327; // -q^{-1} mod 2^16
    int16_t m = (int16_t)((int16_t)a * q_inv);
    int32_t t = a + (int32_t)m * q;
    int16_t res = (int16_t)(t >> 16);
    return res;
}

// 4. Constant-time vector polynomial addition
__attribute__((noinline))
static void ct_poly_add(const int16_t* a, const int16_t* b, int16_t* r) {
    const int16_t q = 3329;
    DR39_DISABLE_UNROLL
    for (int i = 0; i < 256; ++i) {
        int32_t sum = (int32_t)a[i] + (int32_t)b[i];
        int32_t d = sum - q;
        int32_t mask = d >> 31; // -1 if sum < q, 0 if sum >= q
        r[i] = (int16_t)((d & ~mask) | (sum & mask));
    }
}

// 5. Variable-time early-exit buffer comparison
__attribute__((noinline))
static int vt_memcmp_early_exit(const uint8_t* a, const uint8_t* b, size_t len) {
    DR39_DISABLE_UNROLL
    for (size_t i = 0; i < len; ++i) {
        if (a[i] != b[i]) {
            return (int)a[i] - (int)b[i]; // Early exit creates timing leak
        }
    }
    return 0;
}

struct TimingAccumulator {
    uint32_t count;
    int32_t mean_scaled; // mean * 1000
    int32_t m2_scaled;   // sum of squared differences * 1000
    uint32_t min_time;
    uint32_t max_time;
};

static inline void welford_init(TimingAccumulator* acc) {
    acc->count = 0;
    acc->mean_scaled = 0;
    acc->m2_scaled = 0;
    acc->min_time = 0xFFFFFFFF;
    acc->max_time = 0;
}

static inline void welford_update(TimingAccumulator* acc, uint32_t x) {
    acc->count++;
    if (x < acc->min_time) acc->min_time = x;
    if (x > acc->max_time) acc->max_time = x;

    int32_t x_scaled = (int32_t)x * 1000;
    int32_t delta = x_scaled - acc->mean_scaled;
    acc->mean_scaled += delta / (int32_t)acc->count;
    int32_t delta2 = x_scaled - acc->mean_scaled;
    acc->m2_scaled += (delta * delta2) / 1000;
}

static inline int32_t welford_variance(const TimingAccumulator* acc) {
    if (acc->count < 2) return 0;
    return acc->m2_scaled / (int32_t)(acc->count - 1);
}

} // namespace dr39

#endif // DR39_DUDECT_INTERNAL_HPP
