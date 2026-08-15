# Purpose: Master Prompt Milestone 15: NPU INTT and Polynomial Multiplication on Silicon.
# Target operating system: Windows 11 Pro 25H2.
# Target architecture: AMD Phoenix NPU1 / XDNA1 / AIE2.
# Parameters: N = 256, Prime Modulus q = 3329, omega = 3061, omega^-1 = 2298, N^-1 = 3316.

from pathlib import Path

import numpy as np
from aie import iron
from aie.iron import (
    CompileTime,
    ExternalFunction,
    In,
    ObjectFifo,
    Out,
    Program,
    Runtime,
    Worker,
)
from aie.utils.config import cxx_header_path
from aie.utils.hostruntime.xrtruntime.tensor import XRTTensor

MOD_Q = 3329
N_TRANSFORM = 256
OMEGA_256 = 3061
OMEGA_INV_256 = 2298
N_INV_256 = 3316

# Precompute forward twiddles: W[i] = omega^i mod q
TWIDDLES_FWD = [pow(OMEGA_256, i, MOD_Q) for i in range(128)]
# Precompute inverse twiddles: W_inv[i] = (omega^-1)^i mod q
TWIDDLES_INV = [pow(OMEGA_INV_256, i, MOD_Q) for i in range(128)]

# Precomputed 8-bit bit-reversal table
BIT_REV_256 = [int(f"{i:08b}"[::-1], 2) for i in range(256)]

# Embedded C++ Kernel for Cyclic Polynomial Multiplication:
# C(x) = INTT( NTT(A(x)) (*) NTT(B(x)) ) mod (x^256 - 1) mod 3329
# Input: Packed uint32 array of length 256 (low 16-bits = A[i], high 16-bits = B[i])
# Output: Packed uint32 array of length 256 (low 16-bits = C[i], high 16-bits = A_recovered[i] via Round-Trip INTT(NTT(A)))
KERNEL_CC_CODE = f"""
#include <stdint.h>

namespace {{

static constexpr int16_t MOD_Q = {MOD_Q};
static constexpr int32_t BARRETT_FACTOR = 20158;
static constexpr int32_t BARRETT_SHIFT = 26;
static constexpr int16_t N_INV = {N_INV_256};

static const int16_t W_FWD[128] = {{
    {", ".join(map(str, TWIDDLES_FWD))}
}};

static const int16_t W_INV[128] = {{
    {", ".join(map(str, TWIDDLES_INV))}
}};

static const uint8_t BIT_REV[256] = {{
    {", ".join(map(str, BIT_REV_256))}
}};

inline int16_t mod_add(int16_t a, int16_t b) {{
    int32_t res = static_cast<int32_t>(a) + static_cast<int32_t>(b);
    if (res >= MOD_Q) res -= MOD_Q;
    return static_cast<int16_t>(res);
}}

inline int16_t mod_sub(int16_t a, int16_t b) {{
    int32_t res = static_cast<int32_t>(a) - static_cast<int32_t>(b);
    if (res < 0) res += MOD_Q;
    return static_cast<int16_t>(res);
}}

inline int16_t barrett_reduce(int32_t a) {{
    int32_t t = static_cast<int32_t>((static_cast<int64_t>(a) * BARRETT_FACTOR) >> BARRETT_SHIFT);
    int32_t res = a - t * MOD_Q;
    if (res >= MOD_Q) res -= MOD_Q;
    return static_cast<int16_t>(res);
}}

inline void forward_ntt_256(const int16_t* in_poly, int16_t* out_spec) {{
    int16_t a[256];
    for (int i = 0; i < 256; ++i) {{
        a[i] = in_poly[BIT_REV[i]];
    }}

    // Stage 1 (m=2)
    for (int k = 0; k < 256; k += 2) {{
        int16_t u = a[k];
        int16_t v = a[k + 1];
        a[k] = mod_add(u, v);
        a[k + 1] = mod_sub(u, v);
    }}

    // Stages 2..8
    for (int stage = 2; stage <= 8; ++stage) {{
        int m = 1 << stage;
        int half_m = m >> 1;
        int step = 256 >> stage;

        for (int k = 0; k < 256; k += m) {{
            for (int j = 0; j < half_m; ++j) {{
                int16_t u = a[k + j];
                int16_t w = W_FWD[j * step];
                int16_t v_w = (j == 0) ? a[k + j + half_m] : barrett_reduce(static_cast<int32_t>(a[k + j + half_m]) * w);
                a[k + j] = mod_add(u, v_w);
                a[k + j + half_m] = mod_sub(u, v_w);
            }}
        }}
    }}

    for (int i = 0; i < 256; ++i) {{
        out_spec[i] = a[i];
    }}
}}

inline void inverse_ntt_256(const int16_t* in_spec, int16_t* out_poly) {{
    int16_t a[256];
    for (int i = 0; i < 256; ++i) {{
        a[i] = in_spec[BIT_REV[i]];
    }}

    // Stage 1 (m=2)
    for (int k = 0; k < 256; k += 2) {{
        int16_t u = a[k];
        int16_t v = a[k + 1];
        a[k] = mod_add(u, v);
        a[k + 1] = mod_sub(u, v);
    }}

    // Stages 2..8 with inverse twiddles
    for (int stage = 2; stage <= 8; ++stage) {{
        int m = 1 << stage;
        int half_m = m >> 1;
        int step = 256 >> stage;

        for (int k = 0; k < 256; k += m) {{
            for (int j = 0; j < half_m; ++j) {{
                int16_t u = a[k + j];
                int16_t w = W_INV[j * step];
                int16_t v_w = (j == 0) ? a[k + j + half_m] : barrett_reduce(static_cast<int32_t>(a[k + j + half_m]) * w);
                a[k + j] = mod_add(u, v_w);
                a[k + j + half_m] = mod_sub(u, v_w);
            }}
        }}
    }}

    // Multiply by N^-1 mod q
    for (int i = 0; i < 256; ++i) {{
        out_poly[i] = barrett_reduce(static_cast<int32_t>(a[i]) * N_INV);
    }}
}}

}} // anonymous namespace

extern "C" {{

void poly_mul_intt_kernel(
    const uint32_t* in_packed_ab,
    uint32_t* out_packed_res
) {{
    int16_t a[256];
    int16_t b[256];

    for (int i = 0; i < 256; ++i) {{
        uint32_t packed = in_packed_ab[i];
        a[i] = static_cast<int16_t>(packed & 0xFFFF);
        b[i] = static_cast<int16_t>((packed >> 16) & 0xFFFF);
    }}

    int16_t A_spec[256];
    int16_t B_spec[256];
    forward_ntt_256(a, A_spec);
    forward_ntt_256(b, B_spec);

    // Pointwise Spectral Multiplication
    int16_t C_spec[256];
    for (int i = 0; i < 256; ++i) {{
        C_spec[i] = barrett_reduce(static_cast<int32_t>(A_spec[i]) * static_cast<int32_t>(B_spec[i]));
    }}

    int16_t c_poly[256];
    int16_t a_recovered[256];
    inverse_ntt_256(C_spec, c_poly);
    inverse_ntt_256(A_spec, a_recovered);

    for (int i = 0; i < 256; ++i) {{
        uint32_t packed_out = (static_cast<uint16_t>(c_poly[i])) | (static_cast<uint32_t>(static_cast<uint16_t>(a_recovered[i])) << 16);
        out_packed_res[i] = packed_out;
    }}
}}

}}
"""

def cpu_cyclic_poly_mul(a, b, q=MOD_Q):
    N = len(a)
    c = np.zeros(N, dtype=np.int64)
    for i in range(N):
        for j in range(N):
            idx = (i + j) % N
            c[idx] = (c[idx] + int(a[i]) * int(b[j])) % q
    return c.astype(np.uint16)

@iron.jit
def polymul_pipeline(
    input_data: In,
    output_data: Out,
    *,
    N: CompileTime[int],
    kernel_source: CompileTime[str],
):
    in_ty = np.ndarray[(N,), np.dtype[np.uint32]]
    out_ty = np.ndarray[(N,), np.dtype[np.uint32]]

    of_in = ObjectFifo(in_ty, name="in")
    of_out = ObjectFifo(out_ty, name="out")

    mod_func = ExternalFunction(
        "poly_mul_intt_kernel",
        source_file=kernel_source,
        arg_types=[in_ty, out_ty],
        include_dirs=[cxx_header_path()],
    )

    def core_body(of_in, of_out, mod_func):
        elem_in = of_in.acquire(1)
        elem_out = of_out.acquire(1)
        mod_func(elem_in, elem_out)
        of_in.release(1)
        of_out.release(1)

    worker = Worker(
        core_body,
        fn_args=[of_in.cons(), of_out.prod(), mod_func],
    )

    def sequence(a_in, c_out, in_prod, out_cons):
        in_prod.fill(a_in)
        out_cons.drain(c_out, wait=True)

    rt = Runtime(
        sequence,
        [in_ty, out_ty, of_in.prod(), of_out.cons()],
    )
    my_program = Program(iron.get_current_device(), rt, workers=[worker])
    return my_program.resolve_program()

def main():
    print("=== Phoenix SDR-DSP Master Prompt Milestone 15: NPU INTT & Poly Multiplication Silicon Execution ===")
    print(f"Parameters: N = {N_TRANSFORM}, Modulus q = {MOD_Q}, Omega = {OMEGA_256}")

    kernel_src_path = Path(__file__).parent.resolve() / "polymul_kernel.cc"
    with open(kernel_src_path, "w") as f:
        f.write(KERNEL_CC_CODE)

    # Generate two random polynomials A(x) and B(x)
    np.random.seed(42)
    poly_a = np.random.randint(0, MOD_Q, size=N_TRANSFORM, dtype=np.uint16)
    poly_b = np.random.randint(0, MOD_Q, size=N_TRANSFORM, dtype=np.uint16)

    # Edge cases
    poly_a[0] = 1; poly_b[0] = 1 # constant terms
    poly_a[1] = 2; poly_b[1] = 3

    # Exact CPU references
    ref_c = cpu_cyclic_poly_mul(poly_a, poly_b, MOD_Q)

    # Pack into uint32: low 16-bits = A, high 16-bits = B
    in_packed = (poly_a.astype(np.uint32) | (poly_b.astype(np.uint32) << 16))
    out_packed = np.zeros(N_TRANSFORM, dtype=np.uint32)

    print("Allocating XRTTensors on Phoenix NPU...")
    t_in = XRTTensor(in_packed)
    t_out = XRTTensor(out_packed)

    print("Compiling NTT/INTT Polynomial Multiplication Kernel with Peano and dispatching to Phoenix NPU...")
    res = polymul_pipeline(
        t_in,
        t_out,
        N=N_TRANSFORM,
        kernel_source=str(kernel_src_path),
    )
    print(f"Kernel execution result: {res}")

    print("Execution complete. Unpacking polynomials and verifying bit-exact accuracy...")
    actual_packed = t_out.numpy()
    actual_c = (actual_packed & 0xFFFF).astype(np.uint16)
    actual_a_rec = ((actual_packed >> 16) & 0xFFFF).astype(np.uint16)

    print(f"\nPoly A sample [0..4]:             {poly_a[:5]}")
    print(f"Poly B sample [0..4]:             {poly_b[:5]}")
    print(f"Recovered A (Round-Trip INTT):    {actual_a_rec[:5]}")
    print(f"Ref Poly C = A * B mod (x^N-1):   {ref_c[:5]}")
    print(f"Actual Poly C on Silicon:         {actual_c[:5]}")

    rt_match = np.array_equal(actual_a_rec, poly_a)
    mul_match = np.array_equal(actual_c, ref_c)

    if rt_match and mul_match:
        print("\nPASS!")
        print("SUCCESS: Phoenix NPU executed Inverse NTT (INTT) and Cyclic Polynomial Multiplication with 100% BIT-EXACT accuracy on Silicon!")
        print("PASS!")
    else:
        diff_rt = np.abs(actual_a_rec.astype(np.int32) - poly_a.astype(np.int32))
        diff_mul = np.abs(actual_c.astype(np.int32) - ref_c.astype(np.int32))
        print(f"FAIL! Round-trip mismatches: {np.sum(diff_rt != 0)}, PolyMul mismatches: {np.sum(diff_mul != 0)}")
        import sys
        sys.exit(1)

if __name__ == "__main__":
    main()
