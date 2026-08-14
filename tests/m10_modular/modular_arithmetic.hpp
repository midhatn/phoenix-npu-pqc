// Purpose: Vectorized Modular Arithmetic & Reduction Kernels (Barrett & Montgomery) for AMD AIE2.
// Target operating system: Windows 11 Pro 25H2.
// Target architecture: AMD Phoenix NPU1 / XDNA1 / AIE2.
// Input types: int16_t vectors (modular integers mod q = 3329).
// Output types: int16_t vectors normalized in range [0, q-1].
// Scaling: Integer arithmetic; no fractional scaling.
// State requirements: Stateless vector arithmetic.
// Error handling: Saturated / modulo arithmetic within bounded ranges.

#ifndef MODULAR_ARITHMETIC_HPP
#define MODULAR_ARITHMETIC_HPP

#include <stdint.h>
#if defined(__AIE_ARCH__) || defined(__AIE2__)
#include <aie_api/aie.hpp>
#endif

namespace sdr_dsp {

// Constants for Prime Modulus q = 3329 (Kyber / SDR finite-field parameter)
static constexpr int16_t MOD_Q = 3329;

// Barrett Reduction Precomputed Factor:
// floor((1 << 26) / 3329) = floor(67108864 / 3329) = 20158
static constexpr int32_t BARRETT_FACTOR = 20158;
static constexpr int32_t BARRETT_SHIFT = 26;

// Montgomery Reduction Precomputed Factors (R = 2^16 = 65536):
// q_inv = -q^(-1) mod 2^16 = 62209 = -3327 (as int16)
// 3329 * 62209 = 207093761 = 3160 * 65536 + 1 => 3329 * 62209 = 1 mod 2^16
// q_prime = -3327
static constexpr int16_t MONTGOMERY_QINV = -3327; // 62209 in uint16
static constexpr int16_t MONTGOMERY_Q = 3329;

/**
 * @brief Scalar Modular Addition: (a + b) mod q
 */
inline int16_t mod_add_scalar(int16_t a, int16_t b, int16_t q = MOD_Q) {
    int32_t res = static_cast<int32_t>(a) + static_cast<int32_t>(b);
    if (res >= q) res -= q;
    return static_cast<int16_t>(res);
}

/**
 * @brief Scalar Modular Subtraction: (a - b) mod q
 */
inline int16_t mod_sub_scalar(int16_t a, int16_t b, int16_t q = MOD_Q) {
    int32_t res = static_cast<int32_t>(a) - static_cast<int32_t>(b);
    if (res < 0) res += q;
    return static_cast<int16_t>(res);
}

/**
 * @brief Scalar Barrett Reduction: a mod q for a in [0, q^2 - 1]
 */
inline int16_t barrett_reduce_scalar(int32_t a, int16_t q = MOD_Q) {
    // t = floor((a * BARRETT_FACTOR) / 2^26)
    int32_t t = static_cast<int32_t>((static_cast<int64_t>(a) * BARRETT_FACTOR) >> BARRETT_SHIFT);
    int32_t res = a - t * q;
    if (res >= q) res -= q;
    return static_cast<int16_t>(res);
}

/**
 * @brief Scalar Montgomery Reduction: (a * R^-1) mod q for a in [-q*2^15, q*2^15]
 */
inline int16_t montgomery_reduce_scalar(int32_t a) {
    // k = (a * MONTGOMERY_QINV) mod 2^16
    int16_t k = static_cast<int16_t>(a * MONTGOMERY_QINV);
    // t = (a - k * q) / 2^16
    int32_t t = (a - static_cast<int32_t>(k) * MONTGOMERY_Q) >> 16;
    if (t < 0) t += MONTGOMERY_Q;
    return static_cast<int16_t>(t);
}

} // namespace sdr_dsp

#endif // MODULAR_ARITHMETIC_HPP
