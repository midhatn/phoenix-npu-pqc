# Purpose: Master Prompt Milestone 14: 256-Point Vectorized NTT on AMD Phoenix NPU Silicon.
# Target operating system: Windows 11 Pro 25H2.
# Target architecture: AMD Phoenix NPU1 / XDNA1 / AIE2.
# Parameters: N = 256, Prime Modulus q = 3329, omega = 3061.

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
NUM_FRAMES = 4
TOTAL_ELEMS = NUM_FRAMES * N_TRANSFORM  # 1024 int16 elements (512 packed uint32s)
TOTAL_PACKED = TOTAL_ELEMS // 2

# Precompute twiddle table powers: W[i] = omega^i mod q for i in 0..127
TWIDDLES_256 = [pow(OMEGA_256, i, MOD_Q) for i in range(128)]

# Bit-reversal table for 8-bit indices (0..255)
BIT_REV_256 = [int(f"{i:08b}"[::-1], 2) for i in range(256)]

# Embedded C++ Kernel for 256-Point Cooley-Tukey NTT (Batched across 4 frames = 1024 elements)
KERNEL_CC_CODE = f"""
#include <stdint.h>

namespace {{

static constexpr int16_t MOD_Q = {MOD_Q};
static constexpr int32_t BARRETT_FACTOR = 20158;
static constexpr int32_t BARRETT_SHIFT = 26;

// Precomputed powers of omega = {OMEGA_256} mod 3329 (128 twiddles)
static const int16_t W[128] = {{
    {", ".join(map(str, TWIDDLES_256))}
}};

// Precomputed 8-bit bit-reversal permutation (256 elements)
static const uint8_t BIT_REV_256[256] = {{
    {", ".join(map(str, BIT_REV_256))}
}};

inline int16_t mod_add_scalar(int16_t a, int16_t b) {{
    int32_t res = static_cast<int32_t>(a) + static_cast<int32_t>(b);
    if (res >= MOD_Q) res -= MOD_Q;
    return static_cast<int16_t>(res);
}}

inline int16_t mod_sub_scalar(int16_t a, int16_t b) {{
    int32_t res = static_cast<int32_t>(a) - static_cast<int32_t>(b);
    if (res < 0) res += MOD_Q;
    return static_cast<int16_t>(res);
}}

inline int16_t barrett_reduce_scalar(int32_t a) {{
    int32_t t = static_cast<int32_t>((static_cast<int64_t>(a) * BARRETT_FACTOR) >> BARRETT_SHIFT);
    int32_t res = a - t * MOD_Q;
    if (res >= MOD_Q) res -= MOD_Q;
    return static_cast<int16_t>(res);
}}

inline void ntt_256_frame(const int16_t* in_frame, int16_t* out_frame) {{
    int16_t a[256];

    // 1. Bit-reversal permutation
    #pragma clang loop unroll_count(8)
    for (int i = 0; i < 256; ++i) {{
        a[i] = in_frame[BIT_REV_256[i]];
    }}

    // 2. Cooley-Tukey 8 Stages (2^1 to 2^8)
    // Stage 1 (m=2, half_m=1, step=128)
    for (int k = 0; k < 256; k += 2) {{
        int16_t u = a[k];
        int16_t v = a[k + 1];
        a[k] = mod_add_scalar(u, v);
        a[k + 1] = mod_sub_scalar(u, v);
    }}

    // Stages 2..8
    for (int stage = 2; stage <= 8; ++stage) {{
        int m = 1 << stage;
        int half_m = m >> 1;
        int step = 256 >> stage;

        for (int k = 0; k < 256; k += m) {{
            for (int j = 0; j < half_m; ++j) {{
                int16_t u = a[k + j];
                int16_t w = W[j * step];
                int16_t v_w = (j == 0) ? a[k + j + half_m] : barrett_reduce_scalar(static_cast<int32_t>(a[k + j + half_m]) * w);
                a[k + j] = mod_add_scalar(u, v_w);
                a[k + j + half_m] = mod_sub_scalar(u, v_w);
            }}
        }}
    }}

    // Copy to output
    #pragma clang loop unroll_count(8)
    for (int i = 0; i < 256; ++i) {{
        out_frame[i] = a[i];
    }}
}}

}} // anonymous namespace

extern "C" {{

void ntt256_kernel(
    const uint32_t* in_packed,
    uint32_t* out_packed
) {{
    const int16_t* in_ptr = reinterpret_cast<const int16_t*>(in_packed);
    int16_t* out_ptr = reinterpret_cast<int16_t*>(out_packed);

    // Process 4 parallel 256-point NTT frames (1024 total elements)
    for (int frame = 0; frame < 4; ++frame) {{
        ntt_256_frame(in_ptr + frame * 256, out_ptr + frame * 256);
    }}
}}

}}
"""

def cpu_direct_ntt256(x, omega=OMEGA_256, q=MOD_Q):
    X = np.zeros(256, dtype=np.int64)
    for k in range(256):
        s = 0
        for n in range(256):
            w = pow(int(omega), n * k, q)
            s = (s + int(x[n]) * w) % q
        X[k] = s
    return X.astype(np.uint16)

@iron.jit
def ntt256_pipeline(
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
        "ntt256_kernel",
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
    print("=== Phoenix SDR-DSP Master Prompt Milestone 14: 256-Point NTT Silicon Execution ===")
    print(f"Parameters: N = {N_TRANSFORM}, Modulus q = {MOD_Q}, Omega = {OMEGA_256}")
    print(f"Batch Workload: {NUM_FRAMES} frames of 256-point NTT ({TOTAL_ELEMS} elements)")

    kernel_src_path = Path(__file__).parent.resolve() / "ntt256_kernel.cc"
    with open(kernel_src_path, "w") as f:
        f.write(KERNEL_CC_CODE)

    # Generate 4 test frames
    np.random.seed(42)
    in_frames = np.random.randint(0, MOD_Q, size=(NUM_FRAMES, N_TRANSFORM), dtype=np.uint16)

    # Frame 0: Unit impulse [1, 0, 0, ..., 0] -> Expected spectrum: [1, 1, 1, ..., 1]
    in_frames[0] = 0
    in_frames[0, 0] = 1

    # Frame 1: Constant vector [42, 42, ..., 42] -> Expected spectrum: [ (42*256) mod q, 0, 0, ..., 0 ]
    in_frames[1] = 42

    # Compute CPU reference for all 4 frames
    ref_frames = np.zeros_like(in_frames)
    for i in range(NUM_FRAMES):
        ref_frames[i] = cpu_direct_ntt256(in_frames[i])

    # Pack into uint32 (2 int16 elements per uint32)
    in_flat = in_frames.flatten()
    in_packed = (in_flat[0::2].astype(np.uint32) | (in_flat[1::2].astype(np.uint32) << 16))
    out_packed = np.zeros(TOTAL_PACKED, dtype=np.uint32)

    print("Allocating XRTTensors on Phoenix NPU...")
    t_in = XRTTensor(in_packed)
    t_out = XRTTensor(out_packed)

    print("Compiling 256-Point NTT Kernel with Peano and dispatching to Phoenix NPU...")
    res = ntt256_pipeline(
        t_in,
        t_out,
        N=TOTAL_PACKED,
        kernel_source=str(kernel_src_path),
    )
    print(f"Kernel execution result: {res}")

    print("Execution complete. Unpacking spectra and verifying bit-exact accuracy...")
    actual_packed = t_out.numpy()
    actual_flat = np.zeros(TOTAL_ELEMS, dtype=np.uint16)
    actual_flat[0::2] = (actual_packed & 0xFFFF).astype(np.uint16)
    actual_flat[1::2] = ((actual_packed >> 16) & 0xFFFF).astype(np.uint16)
    actual_frames = actual_flat.reshape(NUM_FRAMES, N_TRANSFORM)

    print(f"\nFrame 0 (Impulse Input) Sample Spectrum [0..4]:   {actual_frames[0, :5]} (Expected: [1 1 1 1 1])")
    print(f"Frame 1 (Constant 42) Spectrum Bin 0:             {actual_frames[1, 0]} (Expected: {(42*256)%MOD_Q})")
    print(f"Frame 1 Non-DC Bins [1..4]:                       {actual_frames[1, 1:5]} (Expected: [0 0 0 0])")
    print(f"Frame 2 (Random Vector) Ref Spectrum [0..4]:     {ref_frames[2, :5]}")
    print(f"Frame 2 Actual Spectrum [0..4]:                   {actual_frames[2, :5]}")

    is_bit_exact = np.array_equal(actual_frames, ref_frames)
    if is_bit_exact:
        print("\nPASS!")
        print(f"SUCCESS: Phoenix NPU executed 256-Point Vectorized NTT on Silicon with 100% BIT-EXACT accuracy across all {NUM_FRAMES} frames!")
        print("PASS!")
    else:
        diff = np.abs(actual_frames.astype(np.int32) - ref_frames.astype(np.int32))
        print(f"FAIL! Mismatches detected in {np.sum(diff != 0)} elements.")
        import sys
        sys.exit(1)

if __name__ == "__main__":
    main()
