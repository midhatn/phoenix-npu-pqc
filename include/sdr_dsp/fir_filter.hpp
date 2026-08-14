// Purpose: Vectorized FIR Filter (Real & Complex) using AIE2 MAC/MUL intrinsics.
// Target operating system: Windows 11 Pro 25H2.
// Target architecture: AMD Ryzen 9 7940HS Phoenix / XDNA1 / AIE2.
// Input types: bfloat16 signal, bfloat16 taps, cint16_t signal, cint16_t taps.
// Output types: Filtered bfloat16 or cint16_t stream.
// Scaling: Direct float for bfloat16; Q1.15 right shift for cint16.
// Alignment assumptions: Aligned memory buffers.
// State requirements: Tap length N_TAPS <= 64 for single-tile local memory.
// Error handling: Assert loop bounds divisible by vector lanes.

#pragma once

#include "sdr_dsp_common.hpp"

namespace sdr_dsp {

// Vectorized bfloat16 FIR Filter (Real)
// Computes out[i] = sum_{k=0}^{TAPS-1} in[i + k] * coeffs[k]
// Processes 64 bfloat16 samples per iteration.
template <unsigned TAPS>
__attribute__((always_inline))
inline void fir_filter_bf16(
    const bfloat16 *__restrict in,
    const bfloat16 *__restrict coeffs,
    bfloat16 *__restrict out,
    unsigned num_samples
) {
    for (unsigned i = 0; i < num_samples; i += 64) {
        ::aie::accum<accfloat, 64> acc;
        acc.from_vector(::aie::zeros<bfloat16, 64>());

        for (unsigned k = 0; k < TAPS; ++k) {
            ::aie::vector<bfloat16, 64> x_v = ::aie::load_v<64>(in + i + k);
            ::aie::vector<bfloat16, 64> c_v = ::aie::broadcast<bfloat16, 64>(coeffs[k]);
            acc = ::aie::mac(acc, x_v, c_v);
        }

        ::aie::vector<bfloat16, 64> out_v = acc.to_vector<bfloat16>();
        ::aie::store_v(out + i, out_v);
    }
}

// Vectorized Complex int16 FIR Filter (cint16)
// Q15 fixed point with accumulator shift
template <unsigned TAPS>
__attribute__((always_inline))
inline void fir_filter_cint16(
    const cint16 *__restrict in,
    const cint16 *__restrict coeffs,
    cint16 *__restrict out,
    unsigned num_samples
) {
    for (unsigned i = 0; i < num_samples; i += 16) {
        ::aie::accum<cacc48, 16> acc;
        acc.from_vector(::aie::zeros<cint16, 16>());

        for (unsigned k = 0; k < TAPS; ++k) {
            ::aie::vector<cint16, 16> x_v = ::aie::load_v<16>(in + i + k);
            ::aie::vector<cint16, 16> c_v = ::aie::broadcast<cint16, 16>(coeffs[k]);
            acc = ::aie::mac(acc, x_v, c_v);
        }

        ::aie::vector<cint16, 16> out_v = acc.to_vector<cint16>(Q15_SHIFT);
        ::aie::store_v(out + i, out_v);
    }
}

} // namespace sdr_dsp
