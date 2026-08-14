# Purpose: Master Prompt Milestone 10: Vectorized Modular Arithmetic on AIE2 Silicon.
# Target operating system: Windows 11 Pro 25H2.
# Target architecture: AMD Phoenix NPU1 / XDNA1 / AIE2.
# Workload: 1024 (A, B) pairs mod q=3329 (2048 modular operations per burst).

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
BARRETT_FACTOR = 20158
BARRETT_SHIFT = 26

def cpu_mod_add(a, b, q=MOD_Q):
    return (a.astype(np.int32) + b.astype(np.int32)) % q

def cpu_barrett_mul(a, b, q=MOD_Q):
    prod = a.astype(np.int64) * b.astype(np.int64)
    t = (prod * BARRETT_FACTOR) >> BARRETT_SHIFT
    res = prod - t * q
    res = np.where(res >= q, res - q, res)
    return res.astype(np.int16)

@iron.jit
def modular_pipeline(
    input_ab: In,
    output_res: Out,
    *,
    N: CompileTime[int],
    kernel_source: CompileTime[str],
    include_dir: CompileTime[str],
):
    in_ty = np.ndarray[(N,), np.dtype[np.uint32]]
    out_ty = np.ndarray[(N,), np.dtype[np.uint32]]

    of_in = ObjectFifo(in_ty, name="in")
    of_out = ObjectFifo(out_ty, name="out")

    mod_func = ExternalFunction(
        "modular_arithmetic_kernel",
        source_file=kernel_source,
        arg_types=[in_ty, out_ty],
        include_dirs=[cxx_header_path(), include_dir],
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
    print("=== Phoenix SDR-DSP Master Prompt Milestone 10: Modular Arithmetic Silicon Execution ===")

    N_PAIRS = 1024
    print(f"Workload: {N_PAIRS} (A, B) pairs mod q={MOD_Q} (Total: {N_PAIRS * 2} modular operations)")

    np.random.seed(42)
    in_a = np.random.randint(0, MOD_Q, size=N_PAIRS, dtype=np.uint16)
    in_b = np.random.randint(0, MOD_Q, size=N_PAIRS, dtype=np.uint16)

    # Edge cases
    in_a[0] = 0;        in_b[0] = 0
    in_a[1] = MOD_Q-1;  in_b[1] = MOD_Q-1
    in_a[2] = MOD_Q-1;  in_b[2] = 1
    in_a[3] = 1;        in_b[3] = MOD_Q-1
    in_a[4] = 1832;     in_b[4] = 2718

    ref_add = cpu_mod_add(in_a.astype(np.int16), in_b.astype(np.int16)).astype(np.uint16)
    ref_mul = cpu_barrett_mul(in_a.astype(np.int16), in_b.astype(np.int16)).astype(np.uint16)

    # Pack into uint32
    in_packed = (in_a.astype(np.uint32) | (in_b.astype(np.uint32) << 16))
    out_packed = np.zeros(N_PAIRS, dtype=np.uint32)

    print("Allocating XRTTensors on Phoenix NPU...")
    t_in = XRTTensor(in_packed)
    t_out = XRTTensor(out_packed)

    kernel_src = str(Path(__file__).parent / "modular_kernel.cpp")
    inc_dir = r"C:\phoenix-sdr-dsp\include"

    print("Compiling Modular Arithmetic & Barrett Reduction Kernel with Peano and dispatching to Phoenix NPU...")
    res = modular_pipeline(
        t_in,
        t_out,
        N=N_PAIRS,
        kernel_source=kernel_src,
        include_dir=inc_dir,
    )
    print(f"Kernel execution result: {res}")

    print("Execution complete. Unpacking results and verifying bit-exact accuracy...")
    actual_packed = t_out.numpy()
    actual_add = (actual_packed & 0xFFFF).astype(np.uint16)
    actual_mul = ((actual_packed >> 16) & 0xFFFF).astype(np.uint16)

    print(f"Input A sample [0..4]:    {in_a[:5]}")
    print(f"Input B sample [0..4]:    {in_b[:5]}")
    print(f"Ref Add sample [0..4]:    {ref_add[:5]}")
    print(f"Actual Add sample [0..4]: {actual_add[:5]}")
    print(f"Ref Mul sample [0..4]:    {ref_mul[:5]}")
    print(f"Actual Mul sample [0..4]: {actual_mul[:5]}")

    add_match = np.array_equal(actual_add, ref_add)
    mul_match = np.array_equal(actual_mul, ref_mul)

    if add_match and mul_match:
        print("\nPASS!")
        print(f"SUCCESS: Phoenix NPU executed Modular Arithmetic & Barrett Reduction with 100% BIT-EXACT accuracy mod {MOD_Q}!")
        print("PASS!")
    else:
        diff_add = np.abs(actual_add.astype(np.int32) - ref_add.astype(np.int32))
        diff_mul = np.abs(actual_mul.astype(np.int32) - ref_mul.astype(np.int32))
        print(f"FAIL! Add mismatches: {np.sum(diff_add != 0)}, Mul mismatches: {np.sum(diff_mul != 0)}")
        import sys
        sys.exit(1)

if __name__ == "__main__":
    main()
