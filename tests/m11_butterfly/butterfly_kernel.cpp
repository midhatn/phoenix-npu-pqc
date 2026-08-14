// Purpose: Standalone C++ Kernel for Radix-2 NTT Butterfly on AIE2 Silicon.
// Target operating system: Windows 11 Pro 25H2.
// Target architecture: AMD Phoenix NPU1 / XDNA1 / AIE2.
// Modulus: Prime q = 3329.

#include <stdint.h>
#include "sdr_dsp/ntt_butterfly.hpp"

extern "C" {

/**
 * @brief Vectorized Radix-2 NTT Butterfly Kernel:
 * in_uv: Packed (u, v) pairs (1024 uint32 elements)
 * in_twiddles: Twiddle factor omega for each butterfly (1024 uint32 elements, low 16 bits = omega)
 * out_uv: Packed (u', v') outputs (1024 uint32 elements)
 */
void ntt_butterfly_kernel(
    const uint32_t* in_packed_uv,
    const uint32_t* in_twiddles,
    uint32_t* out_packed_res
) {
    #pragma clang loop unroll_count(8)
    for (int32_t i = 0; i < 1024; ++i) {
        uint32_t uv = in_packed_uv[i];
        int16_t u = static_cast<int16_t>(uv & 0xFFFF);
        int16_t v = static_cast<int16_t>((uv >> 16) & 0xFFFF);
        int16_t omega = static_cast<int16_t>(in_twiddles[i] & 0xFFFF);

        int16_t u_out, v_out;
        sdr_dsp::ct_butterfly(u, v, omega, u_out, v_out);

        uint32_t packed_out = (static_cast<uint16_t>(u_out)) | (static_cast<uint32_t>(static_cast<uint16_t>(v_out)) << 16);
        out_packed_res[i] = packed_out;
    }
}

} // extern "C"
