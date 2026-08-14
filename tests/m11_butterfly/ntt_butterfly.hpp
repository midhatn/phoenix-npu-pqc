// Purpose: Radix-2 NTT Butterfly Kernel for AMD Phoenix NPU1 / AIE2.
// Target operating system: Windows 11 Pro 25H2.
// Target architecture: AMD Phoenix NPU1 / XDNA1 / AIE2.
// Modulus: Prime q = 3329.

#ifndef NTT_BUTTERFLY_HPP
#define NTT_BUTTERFLY_HPP

#include <stdint.h>
#include "sdr_dsp/modular_arithmetic.hpp"

namespace sdr_dsp {

/**
 * @brief Cooley-Tukey (CT) Radix-2 Butterfly:
 * Inputs: u, v, twiddle factor omega
 * Outputs:
 *   u' = (u + v * omega) mod q
 *   v' = (u - v * omega) mod q
 */
inline void ct_butterfly(int16_t u, int16_t v, int16_t omega, int16_t& u_out, int16_t& v_out, int16_t q = MOD_Q) {
    int32_t prod = static_cast<int32_t>(v) * static_cast<int32_t>(omega);
    int16_t v_w = barrett_reduce_scalar(prod, q);

    u_out = mod_add_scalar(u, v_w, q);
    v_out = mod_sub_scalar(u, v_w, q);
}

/**
 * @brief Gentleman-Sande (GS) Radix-2 Butterfly (used in INTT / Decimation-in-Frequency):
 * Inputs: u, v, twiddle factor omega
 * Outputs:
 *   u' = (u + v) mod q
 *   v' = ((u - v) * omega) mod q
 */
inline void gs_butterfly(int16_t u, int16_t v, int16_t omega, int16_t& u_out, int16_t& v_out, int16_t q = MOD_Q) {
    u_out = mod_add_scalar(u, v, q);
    int16_t diff = mod_sub_scalar(u, v, q);
    int32_t prod = static_cast<int32_t>(diff) * static_cast<int32_t>(omega);
    v_out = barrett_reduce_scalar(prod, q);
}

} // namespace sdr_dsp

#endif // NTT_BUTTERFLY_HPP
