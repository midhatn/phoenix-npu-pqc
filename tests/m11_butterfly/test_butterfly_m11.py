# Purpose: Master Prompt Milestone 11: Vectorized Radix-2 NTT Butterfly on AIE2 Silicon.
# Target operating system: Windows 11 Pro 25H2.
# Target architecture: AMD Phoenix NPU1 / XDNA1 / AIE2.
# Arithmetic: Cooley-Tukey Radix-2 Butterfly mod q = 3329.

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
BARRETT_FACTOR = 20158
BARRETT_SHIFT = 26

def cpu_ct_butterfly(u, v, omega, q=MOD_Q):
    prod = (v.astype(np.int64) * omega.astype(np.int64))
    t = (prod * BARRETT_FACTOR) >> BARRETT_SHIFT
    v_w = prod - t * q
    v_w = np.where(v_w >= q, v_w - q, v_w)

    u_out = (u.astype(np.int32) + v_w) % q
    v_out = (u.astype(np.int32) - v_w + q) % q
    return u_out.astype(np.uint16), v_out.astype(np.uint16)

# Self-contained C++ kernel code embedded directly
KERNEL_CC_CODE = r"""
#include <stdint.h>

static constexpr int16_t MOD_Q = 3329;
static constexpr int32_t BARRETT_FACTOR = 20158;
static constexpr int32_t BARRETT_SHIFT = 26;

inline int16_t mod_add_scalar(int16_t a, int16_t b, int16_t q = MOD_Q) {
    int32_t res = static_cast<int32_t>(a) + static_cast<int32_t>(b);
    if (res >= q) res -= q;
    return static_cast<int16_t>(res);
}

inline int16_t mod_sub_scalar(int16_t a, int16_t b, int16_t q = MOD_Q) {
    int32_t res = static_cast<int32_t>(a) - static_cast<int32_t>(b);
    if (res < 0) res += q;
    return static_cast<int16_t>(res);
}

inline int16_t barrett_reduce_scalar(int32_t a, int16_t q = MOD_Q) {
    int32_t t = static_cast<int32_t>((static_cast<int64_t>(a) * BARRETT_FACTOR) >> BARRETT_SHIFT);
    int32_t res = a - t * q;
    if (res >= q) res -= q;
    return static_cast<int16_t>(res);
}

inline void ct_butterfly(int16_t u, int16_t v, int16_t omega, int16_t& u_out, int16_t& v_out, int16_t q = MOD_Q) {
    int32_t prod = static_cast<int32_t>(v) * static_cast<int32_t>(omega);
    int16_t v_w = barrett_reduce_scalar(prod, q);

    u_out = mod_add_scalar(u, v_w, q);
    v_out = mod_sub_scalar(u, v_w, q);
}

extern "C" {

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
        ct_butterfly(u, v, omega, u_out, v_out);

        uint32_t packed_out = (static_cast<uint16_t>(u_out)) | (static_cast<uint32_t>(static_cast<uint16_t>(v_out)) << 16);
        out_packed_res[i] = packed_out;
    }
}

}
"""

@iron.jit
def butterfly_pipeline(
    input_uv: In,
    input_twiddle: In,
    output_res: Out,
    *,
    N: CompileTime[int],
    kernel_source: CompileTime[str],
):
    in_ty = np.ndarray[(N,), np.dtype[np.uint32]]
    out_ty = np.ndarray[(N,), np.dtype[np.uint32]]

    of_in_uv = ObjectFifo(in_ty, name="in_uv")
    of_in_w = ObjectFifo(in_ty, name="in_w")
    of_out = ObjectFifo(out_ty, name="out")

    mod_func = ExternalFunction(
        "ntt_butterfly_kernel",
        source_file=kernel_source,
        arg_types=[in_ty, in_ty, out_ty],
        include_dirs=[cxx_header_path()],
    )

    def core_body(of_uv, of_w, of_out, mod_func):
        elem_uv = of_uv.acquire(1)
        elem_w = of_w.acquire(1)
        elem_out = of_out.acquire(1)
        mod_func(elem_uv, elem_w, elem_out)
        of_uv.release(1)
        of_w.release(1)
        of_out.release(1)

    worker = Worker(
        core_body,
        fn_args=[of_in_uv.cons(), of_in_w.cons(), of_out.prod(), mod_func],
    )

    def sequence(a_uv, a_w, c_out, uv_prod, w_prod, out_cons):
        uv_prod.fill(a_uv)
        w_prod.fill(a_w)
        out_cons.drain(c_out, wait=True)

    rt = Runtime(
        sequence,
        [in_ty, in_ty, out_ty, of_in_uv.prod(), of_in_w.prod(), of_out.cons()],
    )
    my_program = Program(iron.get_current_device(), rt, workers=[worker])
    return my_program.resolve_program()

def main():
    print("=== Phoenix SDR-DSP Master Prompt Milestone 11: Radix-2 NTT Butterfly Silicon Execution ===")

    N_BUTTERFLIES = 1024
    print(f"Workload: {N_BUTTERFLIES} parallel Cooley-Tukey Radix-2 Butterflies mod q={MOD_Q}")

    # Write self-contained kernel C++ file directly to disk
    kernel_src_path = Path(__file__).parent.resolve() / "butterfly_kernel.cc"
    with open(kernel_src_path, "w") as f:
        f.write(KERNEL_CC_CODE)

    np.random.seed(42)
    u_in = np.random.randint(0, MOD_Q, size=N_BUTTERFLIES, dtype=np.uint16)
    v_in = np.random.randint(0, MOD_Q, size=N_BUTTERFLIES, dtype=np.uint16)
    w_in = np.random.randint(0, MOD_Q, size=N_BUTTERFLIES, dtype=np.uint16)

    # Edge cases
    u_in[0] = 0;        v_in[0] = 0;        w_in[0] = 17      # root twiddle
    u_in[1] = MOD_Q-1;  v_in[1] = MOD_Q-1;  w_in[1] = 1       # trivial twiddle
    u_in[2] = 1832;     v_in[2] = 2718;     w_in[2] = 1664    # mid twiddle
    u_in[3] = 1;        v_in[3] = MOD_Q-1;  w_in[3] = MOD_Q-1

    ref_u, ref_v = cpu_ct_butterfly(u_in, v_in, w_in)

    # Pack into uint32
    uv_packed = (u_in.astype(np.uint32) | (v_in.astype(np.uint32) << 16))
    w_packed = w_in.astype(np.uint32)
    out_packed = np.zeros(N_BUTTERFLIES, dtype=np.uint32)

    print("Allocating XRTTensors on Phoenix NPU...")
    t_uv = XRTTensor(uv_packed)
    t_w = XRTTensor(w_packed)
    t_out = XRTTensor(out_packed)

    print("Compiling Radix-2 NTT Butterfly Kernel with Peano and dispatching to Phoenix NPU...")
    res = butterfly_pipeline(
        t_uv,
        t_w,
        t_out,
        N=N_BUTTERFLIES,
        kernel_source=str(kernel_src_path),
    )
    print(f"Kernel execution result: {res}")

    print("Execution complete. Unpacking results and verifying bit-exact accuracy...")
    actual_packed = t_out.numpy()
    actual_u = (actual_packed & 0xFFFF).astype(np.uint16)
    actual_v = ((actual_packed >> 16) & 0xFFFF).astype(np.uint16)

    print(f"Input U sample [0..4]:    {u_in[:5]}")
    print(f"Input V sample [0..4]:    {v_in[:5]}")
    print(f"Twiddle W sample [0..4]:  {w_in[:5]}")
    print(f"Ref U' sample [0..4]:     {ref_u[:5]}")
    print(f"Actual U' sample [0..4]:  {actual_u[:5]}")
    print(f"Ref V' sample [0..4]:     {ref_v[:5]}")
    print(f"Actual V' sample [0..4]:  {actual_v[:5]}")

    u_match = np.array_equal(actual_u, ref_u)
    v_match = np.array_equal(actual_v, ref_v)

    if u_match and v_match:
        print("\nPASS!")
        print(f"SUCCESS: Phoenix NPU executed Radix-2 NTT Butterflies with 100% BIT-EXACT accuracy mod {MOD_Q}!")
        print("PASS!")
    else:
        diff_u = np.abs(actual_u.astype(np.int32) - ref_u.astype(np.int32))
        diff_v = np.abs(actual_v.astype(np.int32) - ref_v.astype(np.int32))
        print(f"FAIL! U mismatches: {np.sum(diff_u != 0)}, V mismatches: {np.sum(diff_v != 0)}")
        import sys
        sys.exit(1)

if __name__ == "__main__":
    main()
