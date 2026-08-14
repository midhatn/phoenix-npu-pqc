# Purpose: Master Prompt Milestone 13: 16-Point Vectorized NTT on AMD Phoenix NPU Silicon.
# Target operating system: Windows 11 Pro 25H2.
# Target architecture: AMD Phoenix NPU1 / XDNA1 / AIE2.
# Parameters: N = 16, Prime Modulus q = 3329, omega = 2699.

from pathlib import Path
import aie.iron as iron
import numpy as np
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
from aie.utils.verify import assert_pass

MOD_Q = 3329
N_TRANSFORM = 16
OMEGA_16 = 2699
NUM_FRAMES = 64
TOTAL_ELEMS = NUM_FRAMES * N_TRANSFORM  # 1024 int16 elements (512 packed uint32s)
TOTAL_PACKED = TOTAL_ELEMS // 2

# Embedded C++ Kernel with programmatic stage twiddles for 16-Point NTT
KERNEL_CC_CODE = r"""
#include <stdint.h>

namespace {

static constexpr int16_t MOD_Q = 3329;
static constexpr int32_t BARRETT_FACTOR = 20158;
static constexpr int32_t BARRETT_SHIFT = 26;

// Precomputed powers of omega = 2699 mod 3329:
// omega^0 = 1, omega^1 = 2699, omega^2 = 749, omega^3 = 848,
// omega^4 = 1729, omega^5 = 2642, omega^6 = 40, omega^7 = 1432
static const int16_t W[8] = {
    1, 2699, 749, 848, 1729, 2642, 40, 1432
};

// Bit-reversal permutation for N=16 (4 bits)
static const uint8_t BIT_REV_16[16] = {
    0, 8, 4, 12, 2, 10, 6, 14, 1, 9, 5, 13, 3, 11, 7, 15
};

inline int16_t mod_add_scalar(int16_t a, int16_t b) {
    int32_t res = static_cast<int32_t>(a) + static_cast<int32_t>(b);
    if (res >= MOD_Q) res -= MOD_Q;
    return static_cast<int16_t>(res);
}

inline int16_t mod_sub_scalar(int16_t a, int16_t b) {
    int32_t res = static_cast<int32_t>(a) - static_cast<int32_t>(b);
    if (res < 0) res += MOD_Q;
    return static_cast<int16_t>(res);
}

inline int16_t barrett_reduce_scalar(int32_t a) {
    int32_t t = static_cast<int32_t>((static_cast<int64_t>(a) * BARRETT_FACTOR) >> BARRETT_SHIFT);
    int32_t res = a - t * MOD_Q;
    if (res >= MOD_Q) res -= MOD_Q;
    return static_cast<int16_t>(res);
}

inline void ntt_16_frame(const int16_t* in_frame, int16_t* out_frame) {
    int16_t a[16];

    // 1. Bit-reversal reordering
    for (int i = 0; i < 16; ++i) {
        a[i] = in_frame[BIT_REV_16[i]];
    }

    // Stage 1 (m=2, half_m=1, twiddle: W[0]=1)
    for (int k = 0; k < 16; k += 2) {
        int16_t u = a[k];
        int16_t v = a[k + 1];
        a[k] = mod_add_scalar(u, v);
        a[k + 1] = mod_sub_scalar(u, v);
    }

    // Stage 2 (m=4, half_m=2, twiddles: W[0]=1, W[4]=1729)
    for (int k = 0; k < 16; k += 4) {
        // j = 0: w = 1
        int16_t u0 = a[k];
        int16_t v0 = a[k + 2];
        a[k] = mod_add_scalar(u0, v0);
        a[k + 2] = mod_sub_scalar(u0, v0);

        // j = 1: w = W[4] = 1729 (since (16/4)*1 = 4)
        int16_t u1 = a[k + 1];
        int16_t v1_w = barrett_reduce_scalar(static_cast<int32_t>(a[k + 3]) * 1729);
        a[k + 1] = mod_add_scalar(u1, v1_w);
        a[k + 3] = mod_sub_scalar(u1, v1_w);
    }

    // Stage 3 (m=8, half_m=4, twiddles: W[0]=1, W[2]=749, W[4]=1729, W[6]=40)
    for (int k = 0; k < 16; k += 8) {
        // j = 0: w = W[0] = 1
        int16_t u0 = a[k];
        int16_t v0 = a[k + 4];
        a[k] = mod_add_scalar(u0, v0);
        a[k + 4] = mod_sub_scalar(u0, v0);

        // j = 1: w = W[2] = 749
        int16_t u1 = a[k + 1];
        int16_t v1_w = barrett_reduce_scalar(static_cast<int32_t>(a[k + 5]) * 749);
        a[k + 1] = mod_add_scalar(u1, v1_w);
        a[k + 5] = mod_sub_scalar(u1, v1_w);

        // j = 2: w = W[4] = 1729
        int16_t u2 = a[k + 2];
        int16_t v2_w = barrett_reduce_scalar(static_cast<int32_t>(a[k + 6]) * 1729);
        a[k + 2] = mod_add_scalar(u2, v2_w);
        a[k + 6] = mod_sub_scalar(u2, v2_w);

        // j = 3: w = W[6] = 40
        int16_t u3 = a[k + 3];
        int16_t v3_w = barrett_reduce_scalar(static_cast<int32_t>(a[k + 7]) * 40);
        a[k + 3] = mod_add_scalar(u3, v3_w);
        a[k + 7] = mod_sub_scalar(u3, v3_w);
    }

    // Stage 4 (m=16, half_m=8, twiddles: W[0..7])
    for (int j = 0; j < 8; ++j) {
        int16_t u = a[j];
        int16_t w = W[j];
        int16_t v_w = (j == 0) ? a[j + 8] : barrett_reduce_scalar(static_cast<int32_t>(a[j + 8]) * w);
        out_frame[j] = mod_add_scalar(u, v_w);
        out_frame[j + 8] = mod_sub_scalar(u, v_w);
    }
}

} // anonymous namespace

extern "C" {

void ntt16_kernel(
    const uint32_t* in_packed,
    uint32_t* out_packed
) {
    const int16_t* in_ptr = reinterpret_cast<const int16_t*>(in_packed);
    int16_t* out_ptr = reinterpret_cast<int16_t*>(out_packed);

    // Process 64 parallel 16-point NTT frames (1024 total elements)
    #pragma clang loop unroll_count(4)
    for (int frame = 0; frame < 64; ++frame) {
        ntt_16_frame(in_ptr + frame * 16, out_ptr + frame * 16);
    }
}

}
"""

def cpu_direct_ntt16(x, omega=OMEGA_16, q=MOD_Q):
    X = np.zeros(16, dtype=np.int64)
    for k in range(16):
        s = 0
        for n in range(16):
            w = pow(int(omega), n * k, q)
            s = (s + int(x[n]) * w) % q
        X[k] = s
    return X.astype(np.uint16)

@iron.jit
def ntt16_pipeline(
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
        "ntt16_kernel",
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

    rt = Runtime()
    with rt.sequence(in_ty, out_ty) as (a_in, c_out):
        rt.start(worker)
        rt.fill(of_in.prod(), a_in)
        rt.drain(of_out.cons(), c_out, wait=True)

    my_program = Program(iron.get_current_device(), rt)
    return my_program.resolve_program()

def main():
    print("=== Phoenix SDR-DSP Master Prompt Milestone 13: 16-Point NTT Silicon Execution ===")
    print(f"Parameters: N = {N_TRANSFORM}, Modulus q = {MOD_Q}, Omega = {OMEGA_16}")
    print(f"Batch Workload: {NUM_FRAMES} frames of 16-point NTT ({TOTAL_ELEMS} elements)")

    kernel_src_path = Path(__file__).parent.resolve() / "ntt16_kernel.cc"
    with open(kernel_src_path, "w") as f:
        f.write(KERNEL_CC_CODE)

    # Generate 64 test frames
    np.random.seed(42)
    in_frames = np.random.randint(0, MOD_Q, size=(NUM_FRAMES, N_TRANSFORM), dtype=np.uint16)

    # Frame 0: Unit impulse
    in_frames[0] = 0
    in_frames[0, 0] = 1

    # Frame 1: Constant vector
    in_frames[1] = 42

    # Compute CPU reference
    ref_frames = np.zeros_like(in_frames)
    for i in range(NUM_FRAMES):
        ref_frames[i] = cpu_direct_ntt16(in_frames[i])

    # Pack into uint32
    in_flat = in_frames.flatten()
    in_packed = (in_flat[0::2].astype(np.uint32) | (in_flat[1::2].astype(np.uint32) << 16))
    out_packed = np.zeros(TOTAL_PACKED, dtype=np.uint32)

    print("Allocating XRTTensors on Phoenix NPU...")
    t_in = XRTTensor(in_packed)
    t_out = XRTTensor(out_packed)

    print("Compiling 16-Point NTT Kernel with Peano and dispatching to Phoenix NPU...")
    res = ntt16_pipeline(
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

    print(f"\nFrame 0 (Impulse Input) Sample Spectrum [0..3]:   {actual_frames[0, :4]} (Expected: [1 1 1 1])")
    print(f"Frame 1 (Constant 42) Spectrum Bin 0:             {actual_frames[1, 0]} (Expected: {(42*16)%MOD_Q})")
    print(f"Frame 1 Non-DC Bins [1..4]:                       {actual_frames[1, 1:5]} (Expected: [0 0 0 0])")
    print(f"Frame 2 (Random Vector) Ref Spectrum [0..3]:     {ref_frames[2, :4]}")
    print(f"Frame 2 Actual Spectrum [0..3]:                   {actual_frames[2, :4]}")

    is_bit_exact = np.array_equal(actual_frames, ref_frames)
    if is_bit_exact:
        print("\nPASS!")
        print(f"SUCCESS: Phoenix NPU executed 16-Point Vectorized NTT on Silicon with 100% BIT-EXACT accuracy across all {NUM_FRAMES} frames!")
        print("PASS!")
    else:
        diff = np.abs(actual_frames.astype(np.int32) - ref_frames.astype(np.int32))
        print(f"FAIL! Mismatches detected in {np.sum(diff != 0)} elements.")
        import sys
        sys.exit(1)

if __name__ == "__main__":
    main()
