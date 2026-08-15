# Purpose: Milestone 5 FIR Filter Silicon Validation using XRTTensor initialization.
# Target operating system: Windows 11 Pro 25H2.
# Target architecture: AMD Phoenix NPU1 / XDNA1 / AIE2.
# Input types: bfloat16 signal vector (4096 elements).
# Output types: bfloat16 filtered vector verified against matching arithmetic reference.
# Scaling: direct bfloat16.
# Alignment assumptions: handled by IRON XRTTensor/BO runtime.
# State requirements: device 0 (NPU Phoenix).
# Error handling: Bit-accurate tolerance check against reference FIR.

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
from aie.utils.verify import assert_pass
from ml_dtypes import bfloat16


@iron.jit
def fir_filter(
    input_sig: In,
    output_sig: Out,
    *,
    N: CompileTime[int],
    element_type: CompileTime[type]
):
    in_ty = np.ndarray[(N,), np.dtype[element_type]]
    out_ty = np.ndarray[(N,), np.dtype[element_type]]

    of_in = ObjectFifo(in_ty, name="in")
    of_out = ObjectFifo(out_ty, name="out")

    current_dir = Path(__file__).parent.resolve()
    include_sdr_dir = Path(r"C:\phoenix-sdr-dsp\include\sdr_dsp")

    fir_func = ExternalFunction(
        "fir_filter_kernel",
        source_file=str(current_dir / "fir_kernel.cc"),
        arg_types=[in_ty, out_ty],
        include_dirs=[cxx_header_path(), str(include_sdr_dir)],
    )

    def core_body(of_in, of_out, fir_func):
        elem_in = of_in.acquire(1)
        elem_out = of_out.acquire(1)
        fir_func(elem_in, elem_out)
        of_in.release(1)
        of_out.release(1)

    worker = Worker(
        core_body, fn_args=[of_in.cons(), of_out.prod(), fir_func]
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
    print("=== Phoenix SDR-DSP Milestone 5: FIR Filter Silicon Execution ===")
    data_size = 4096
    element_type = bfloat16
    print(f"Target Device: {iron.get_current_device()}")
    print(f"Vector Length: {data_size} elements of {element_type.__name__}")

    # Generate synthetic SDR test signal
    np.random.seed(123)
    np_input = (np.random.uniform(0.1, 1.0, data_size)).astype(element_type)
    np_output = np.zeros(data_size, dtype=element_type)

    # Wrap in XRTTensor with correct bfloat16 dtype
    input_tensor = XRTTensor(np_input, dtype=element_type)
    output_tensor = XRTTensor(np_output, dtype=element_type)

    print("Compiling 8-Tap Vectorized AIE2 FIR with Peano and dispatching to Phoenix NPU...")
    res = fir_filter(input_tensor, output_tensor, N=data_size, element_type=element_type)
    print(f"Kernel execution result: {res}")

    # Sync back from NPU to host memory
    output_tensor.to("cpu")

    print("Execution complete. Inspecting FIR output buffer vs reference...")
    
    # Kernel coefficients
    coeffs_f = [0.05, 0.10, 0.20, 0.30, 0.30, 0.20, 0.10, 0.05]
    coeffs = np.array([float(bfloat16(c)) for c in coeffs_f], dtype=np.float32)

    # Reference calculation: out[i] = sum_{k=0..7} in[i + k] * coeffs[k]
    in_floats = np_input.astype(np.float32)
    sig_ext = np.pad(in_floats, (0, 8), mode='constant')
    
    ref_out = np.zeros(data_size, dtype=np.float32)
    for i in range(data_size):
        ref_out[i] = sum(sig_ext[i + k] * coeffs[k] for k in range(8))
    
    ref_out_bf16 = ref_out.astype(element_type)
    out_np = output_tensor._data

    print(f"Input sample [0..4]:    {np_input[:4]}")
    print(f"Ref Out sample [0..4]:  {ref_out_bf16[:4]}")
    print(f"Actual Out sample [0..4]: {out_np[:4]}")

    max_err = float(np.max(np.abs(out_np.astype(np.float32) - ref_out_bf16.astype(np.float32))))
    print(f"Maximum absolute error: {max_err:.6f}")

    assert_pass(out_np, ref_out_bf16, fail_msg="FIR filter output mismatch", atol=0.01)
    print("SUCCESS: Phoenix NPU executed 8-tap Vectorized FIR Filter on physical silicon!")
    print("PASS!")


if __name__ == "__main__":
    main()
