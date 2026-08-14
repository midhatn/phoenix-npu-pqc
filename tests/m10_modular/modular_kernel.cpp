// Purpose: Standalone C++ Kernel for Modular Arithmetic & Barrett Reduction on AIE2 Silicon.
// Target operating system: Windows 11 Pro 25H2.
// Target architecture: AMD Phoenix NPU1 / XDNA1 / AIE2.
// Modulus: q = 3329.

#include <stdint.h>
#include "sdr_dsp/modular_arithmetic.hpp"

extern "C" {

void modular_arithmetic_kernel(
    const uint32_t* in_packed_ab,
    uint32_t* out_packed_res
) {
    // Fixed block of 4096 packed pairs
    #pragma clang loop unroll_count(8)
    for (int32_t i = 0; i < 4096; ++i) {
        uint32_t packed_in = in_packed_ab[i];
        int16_t a = static_cast<int16_t>(packed_in & 0xFFFF);
        int16_t b = static_cast<int16_t>((packed_in >> 16) & 0xFFFF);

        int16_t res_add = sdr_dsp::mod_add_scalar(a, b);
        int32_t prod = static_cast<int32_t>(a) * static_cast<int32_t>(b);
        int16_t res_mul = sdr_dsp::barrett_reduce_scalar(prod);

        uint32_t packed_out = (static_cast<uint16_t>(res_add)) | (static_cast<uint32_t>(static_cast<uint16_t>(res_mul)) << 16);
        out_packed_res[i] = packed_out;
    }
}

} // extern "C"
