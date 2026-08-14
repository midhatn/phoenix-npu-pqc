#ifndef MODULAR_ARITHMETIC_HPP
#define MODULAR_ARITHMETIC_HPP

#include <stdint.h>

namespace sdr_dsp {

static constexpr int16_t MOD_Q = 3329;
static constexpr int32_t BARRETT_FACTOR = 20158;
static constexpr int32_t BARRETT_SHIFT = 26;
static constexpr int16_t MONTGOMERY_QINV = -3327;
static constexpr int16_t MONTGOMERY_Q = 3329;

inline int16_t mod_add_scalar(int16_t a, int16_t b, int16_t q = MOD_Q) {
    int32_t res = static_cast<int32_t>(a) + static_cast<int32_t>(b);
    if (res >= q) res -= q;
    return static_cast<int16_t>(res);
}

inline int16_t mod_sub_scalar(int16_t a, int16_t b, int16_t q = MOD_Q) {
    int32_t res = static_cast<int32_t>(a) - static_cast<int32_t>(b);
    if (res < 0) res += q;
    return static_cast<int16_t>(res);
}

inline int16_t barrett_reduce_scalar(int32_t a, int16_t q = MOD_Q) {
    int32_t t = static_cast<int32_t>((static_cast<int64_t>(a) * BARRETT_FACTOR) >> BARRETT_SHIFT);
    int32_t res = a - t * q;
    if (res >= q) res -= q;
    return static_cast<int16_t>(res);
}

inline int16_t montgomery_reduce_scalar(int32_t a) {
    int16_t k = static_cast<int16_t>(a * MONTGOMERY_QINV);
    int32_t t = (a - static_cast<int32_t>(k) * MONTGOMERY_Q) >> 16;
    if (t < 0) t += MONTGOMERY_Q;
    return static_cast<int16_t>(t);
}

} // namespace sdr_dsp

#endif // MODULAR_ARITHMETIC_HPP
