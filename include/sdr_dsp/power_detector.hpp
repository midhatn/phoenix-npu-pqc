// Purpose: Vectorized Power Meter / Energy Detector for SDR applications.
// Target operating system: Windows 11 Pro 25H2.
// Target architecture: AMD Ryzen 9 7940HS Phoenix / XDNA1 / AIE2.
// Input types: Complex I/Q input (cint16).
// Output types: Real Power / Magnitude squared (int32 or int16).
// Scaling: I^2 + Q^2 with shift options.
// Alignment assumptions: 32-byte aligned pointers.
// State requirements: Stateless vector magnitude squaring.
// Error handling: Assert num_samples is multiple of 16.

#pragma once

#include "sdr_dsp_common.hpp"

namespace sdr_dsp {

// Vectorized Power Detector (cint16 -> int32 power)
// Computes out[i] = I[i]^2 + Q[i]^2 for energy detection and RSSI
__attribute__((always_inline))
inline void power_detector_cint16(
    const cint16 *__restrict in,
    int32_t *__restrict out_power,
    unsigned num_samples
) {
    for (unsigned i = 0; i < num_samples; i += 16) {
        ::aie::vector<cint16, 16> x_v = ::aie::load_v<16>(in + i);
        ::aie::accum<acc32, 16> p_acc = ::aie::abs_square(x_v);
        ::aie::vector<int32_t, 16> p_v = p_acc.to_vector<int32_t>(0);
        ::aie::store_v(out_power + i, p_v);
    }
}

} // namespace sdr_dsp
