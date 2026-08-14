// Purpose: Common SDR DSP definitions, complex data types, and scaling constants for AMD AIE2 (Phoenix NPU).
// Target operating system: Windows 11 Pro 25H2 / Clang / Peano AIE2.
// Target architecture: AMD Ryzen 9 7940HS Phoenix / XDNA1 / AIE2.
// Input types: int16, int32, bfloat16, cint16, cbfloat16.
// Output types: Standardized DSP vector types compatible with <aie_api/aie.hpp>.
// Scaling: Q1.15 fixed-point (shift 15) for int16 SDR pipelines.
// Alignment assumptions: 32-byte / 64-byte aligned vector pointers.
// State requirements: Stateless DSP primitive operations.
// Error handling: Static assertions on alignment and vector dimensions.

#pragma once

#define NOCPP

#include <stdint.h>
#include <stddef.h>
#include <aie_api/aie.hpp>

namespace sdr_dsp {

// SDR Vector chunk sizes
constexpr unsigned VECTOR_LANES_INT16 = 32;
constexpr unsigned VECTOR_LANES_BF16  = 64;
constexpr unsigned VECTOR_LANES_CINT16 = 16;
constexpr unsigned VECTOR_LANES_CBF16  = 32;

// Fixed-point scaling shifts
constexpr int Q15_SHIFT = 15;
constexpr int Q31_SHIFT = 31;

// Complex 16-bit integer representation (I/Q interleaved: [I0, Q0, I1, Q1, ...])
struct cint16_t {
    int16_t real;
    int16_t imag;
};

// Complex 32-bit integer representation
struct cint32_t {
    int32_t real;
    int32_t imag;
};

// Complex bfloat16 representation
struct cbfloat16_t {
    bfloat16 real;
    bfloat16 imag;
};

} // namespace sdr_dsp
