// Purpose: Milestone 17 v2 -- 64-point Radix-2 Cooley-Tukey FFT (Decimation-in-Time).
// Target operating system: Windows 11 Pro 25H2.
// Target architecture: AMD Ryzen 9 7940HS Phoenix / XDNA1 / AIE-ML (AIE2).
// Input:   bfloat16 interleaved complex vector (128 elements = 64 I/Q pairs) in BIT-REVERSED order.
// Output:  bfloat16 interleaved complex spectrum (128 elements = 64 I/Q bins) in NATURAL order.
// Twiddle: bfloat16 interleaved complex table (64 elements = 32 W_N^k pairs, k in [0..31]).
// Algorithm: 6-stage decimation-in-time radix-2, cbfloat16 arithmetic.
//
// Status: DOES NOT COMPILE on mlir-aie 1.3.4 (Aug 2026). See BLOCKING_ISSUE.md.
// Reason: __AIE_API_COMPLEX_VECTOR_SUPPORT__ is undefined on this build, so the
// entire aie_api/detail/aie2/fft_dit_radix2.hpp file is #if'd out at line 10,
// and no radix-2 fft_dit<> specializations exist. This affects ALL data types
// (cint16, cint32, cbfloat16, cfloat) -- not just cbfloat16.
//
// This file is preserved as the reference kernel design. When mlir-aie is
// reinstalled with __AIE_API_COMPLEX_VECTOR_SUPPORT__=1 (Path B), this kernel
// should be exercised again.
//
// References:
//   [1] AMD AI Engine API User Guide 2024.2: aie::fft_dit_r2_stage.
//       download.amd.com/docnav/aiengine/xilinx2024_2/aiengine_api/aie_api/doc/group__group__fft.html
//   [2] AMD Vitis Tutorial: Single-Tile AI Engine API Design (Radix-2 DIT 32-pt FFT).
//       docs.amd.com/r/2025.1-English/Vitis-Tutorials-AI-Engine-Development/Single-Tile-AI-Engine-API-Design
//   [3] Cooley & Tukey (1965). Math. Comp. 19(90): 297-301.
//       garfield.library.upenn.edu/classics1993/A1993MJ84400001.pdf
//   [4] Header: aie_api/fft.hpp:278 (delegation target: detail::fft_dit_stage::run).
//   [5] Header: aie_api/detail/aie2/fft_dit_radix2.hpp:1069+ (cbfloat16 specializations).

#define NOCPP

#include <stdint.h>
#include <aie_api/aie.hpp>

extern "C" {

// Public C-ABI entrypoint invoked by the MLIR-AIE dispatcher.
//
// ABI: bfloat16* interleaved I/Q arrays (same convention as M11/M17 v1 kernels).
//   in_iq        = 128 bfloat16 = 64 cbfloat16 samples (bit-reversed order)
//   twiddles     = 64  bfloat16 = 32 cbfloat16 W_N^k for k in [0..31]
//   out_spectrum = 128 bfloat16 = 64 cbfloat16 bins (natural order)
//
// cbfloat16 is defined in aie_api/types.hpp as { bfloat16 real, imag; }.
// Reinterpret-casting bfloat16* -> cbfloat16* is legal (POD, identical layout).
void fft64_kernel(
    bfloat16 *__restrict in_iq,       // 128 bfloat16 = 64 cbfloat16 samples, bit-reversed
    bfloat16 *__restrict twiddles,    // 64  bfloat16 = 32 cbfloat16 W_N^k for k in [0..31]
    bfloat16 *__restrict out_spectrum // 128 bfloat16 = 64 cbfloat16 bins, natural order
) {
    event0();  // profiling marker: begin

    // Reinterpret host-supplied bfloat16* buffers as cbfloat16* -- identical layout.
    const cbfloat16 *__restrict in_c  = reinterpret_cast<const cbfloat16 *__restrict>(in_iq);
    const cbfloat16 *__restrict tw_c  = reinterpret_cast<const cbfloat16 *__restrict>(twiddles);
    cbfloat16       *__restrict out_c = reinterpret_cast<cbfloat16 *__restrict>(out_spectrum);

    // Two ping-pong scratch buffers in tile local memory (avoid in-place aliasing).
    // Each buffer: 64 x 4B = 256 B. Total scratch: 512 B, well under the 64 KB AIE-ML tile.
    alignas(32) cbfloat16 buf_a[64];
    alignas(32) cbfloat16 buf_b[64];

    // Copy input (already bit-reversed by the host) into buf_a.
    for (int i = 0; i < 64; ++i) buf_a[i] = in_c[i];

    constexpr bool inv = false;  // Forward FFT
    constexpr unsigned N = 64;

    // Six radix-2 DIT stages. Vectorization halves each stage: 32 -> 16 -> 8 -> 4 -> 2 -> 1.
    // Ping-pong between buf_a and buf_b; final stage writes directly to out_c.
    using aie::detail::fft_dit_stage;

    fft_dit_stage<2, 32, cbfloat16, cbfloat16, cbfloat16>::run(buf_a, tw_c, N, 0, 0, inv, buf_b);
    fft_dit_stage<2, 16, cbfloat16, cbfloat16, cbfloat16>::run(buf_b, tw_c, N, 0, 0, inv, buf_a);
    fft_dit_stage<2,  8, cbfloat16, cbfloat16, cbfloat16>::run(buf_a, tw_c, N, 0, 0, inv, buf_b);
    fft_dit_stage<2,  4, cbfloat16, cbfloat16, cbfloat16>::run(buf_b, tw_c, N, 0, 0, inv, buf_a);
    fft_dit_stage<2,  2, cbfloat16, cbfloat16, cbfloat16>::run(buf_a, tw_c, N, 0, 0, inv, buf_b);
    fft_dit_stage<2,  1, cbfloat16, cbfloat16, cbfloat16>::run(buf_b, tw_c, N, 0, 0, inv, out_c);

    event1();  // profiling marker: end
}

}  // extern "C"