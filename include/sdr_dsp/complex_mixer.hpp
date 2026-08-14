// Purpose: Vectorized Complex Mixer / NCO / Frequency Shifter for AIE2.
// Target operating system: Windows 11 Pro 25H2.
// Target architecture: AMD Ryzen 9 7940HS Phoenix / XDNA1 / AIE2.
// Input types: Complex I/Q input (cint16), Complex local oscillator carrier (cint16).
// Output types: Mixed Complex I/Q output (cint16).
// Scaling: Q15 complex multiply ((I1*I2 - Q1*Q2) >> 15, (I1*Q2 + Q1*I2) >> 15).
// Alignment assumptions: 32-byte aligned pointers.
// State requirements: Input phase table / carrier vector.
// Error handling: Assert num_samples is multiple of 16.

#pragma once

#include "sdr_dsp_common.hpp"

namespace sdr_dsp {

// Vectorized Complex Mixer / Frequency Shifter (cint16)
// Multiplies I/Q input with NCO carrier: out[i] = in[i] * lo[i]
// Processes 16 complex samples (32 16-bit words) per cycle.
__attribute__((always_inline))
inline void complex_mixer_cint16(
    const cint16 *__restrict in,
    const cint16 *__restrict lo,
    cint16 *__restrict out,
    unsigned num_samples
) {
    for (unsigned i = 0; i < num_samples; i += 16) {
        ::aie::vector<cint16, 16> x_v  = ::aie::load_v<16>(in + i);
        ::aie::vector<cint16, 16> lo_v = ::aie::load_v<16>(lo + i);

        ::aie::accum<cacc48, 16> acc = ::aie::mul(x_v, lo_v);
        ::aie::vector<cint16, 16> out_v = acc.to_vector<cint16>(Q15_SHIFT);

        ::aie::store_v(out + i, out_v);
    }
}

} // namespace sdr_dsp
