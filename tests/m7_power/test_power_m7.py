# Purpose: Milestone 7 Power Detector / Energy Meter Silicon Validation on AMD Phoenix NPU.
# Target operating system: Windows 11 Pro 25H2.
# Target architecture: AMD Phoenix NPU1 / XDNA1 / AIE2.
# Input types: bfloat16 interleaved I/Q signal (4096 elements = 2048 I/Q pairs).
# Output types: bfloat16 power vector (2048 elements) verified against NumPy I^2 + Q^2.
# Scaling: direct bfloat16.
# Alignment assumptions: handled by IRON XRTTensor/BO runtime.
# State requirements: device 0 (NPU Phoenix).
# Error handling: Bit-accurate tolerance check against reference power detector.

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
def power_detector(
    input_iq: In,
    output_power: Out,
    *,
    N_IN: CompileTime[int],
    N_OUT: CompileTime[int],
    element_type: CompileTime[type]
):
    in_ty = np.ndarray[(N_IN,), np.dtype[element_type]]
    out_ty = np.ndarray[(N_OUT,), np.dtype[element_type]]

    of_in = ObjectFifo(in_ty, name="in_iq")
    of_out = ObjectFifo(out_ty, name="out_power")

    current_dir = Path(__file__).parent.resolve()
    include_sdr_dir = Path(r"C:\phoenix-sdr-dsp\include\sdr_dsp")

    pwr_func = ExternalFunction(
        "power_detector_kernel",
        source_file=str(current_dir / "power_kernel.cc"),
        arg_types=[in_ty, out_ty],
        include_dirs=[cxx_header_path(), str(include_sdr_dir)],
    )

    def core_body(of_in, of_out, pwr_func):
        elem_in = of_in.acquire(1)
        elem_out = of_out.acquire(1)
        pwr_func(elem_in, elem_out)
        of_in.release(1)
        of_out.release(1)

    worker = Worker(
        core_body, fn_args=[of_in.cons(), of_out.prod(), pwr_func]
    )

    rt = Runtime()
    with rt.sequence(in_ty, out_ty) as (a_in, c_out):
        rt.start(worker)
        rt.fill(of_in.prod(), a_in)
        rt.drain(of_out.cons(), c_out, wait=True)

    my_program = Program(iron.get_current_device(), rt)
    return my_program.resolve_program()


def main():
    print("=== Phoenix SDR-DSP Milestone 7: Power Detector Silicon Execution ===")
    in_size = 4096   # 2048 Complex pairs
    out_size = 2048  # 2048 Power samples
    element_type = bfloat16
    print(f"Target Device: {iron.get_current_device()}")
    print(f"Input: {in_size} elements ({in_size // 2} Complex I/Q pairs) -> Output: {out_size} Power elements")

    # Generate synthetic SDR baseband modulated signal with varying envelope
    num_complex = out_size
    t = np.linspace(0, 1, num_complex, endpoint=False)
    envelope = 1.0 + 0.5 * np.sin(2 * np.pi * 3 * t)
    sig_complex = envelope * np.exp(1j * 2 * np.pi * 10 * t)

    # Interleave I and Q into 4096-length array
    np_input_iq = np.zeros(in_size, dtype=np.float32)
    np_input_iq[0::2] = sig_complex.real
    np_input_iq[1::2] = sig_complex.imag
    np_in_bf16 = np_input_iq.astype(element_type)

    np_out_power = np.zeros(out_size, dtype=element_type)

    # Wrap in XRTTensor
    in_tensor = XRTTensor(np_in_bf16, dtype=element_type)
    out_tensor = XRTTensor(np_out_power, dtype=element_type)

    print("Compiling Power Detector with Peano and dispatching to Phoenix NPU...")
    res = power_detector(
        in_tensor,
        out_tensor,
        N_IN=in_size,
        N_OUT=out_size,
        element_type=element_type,
    )
    print(f"Kernel execution result: {res}")

    # Sync back from NPU to host memory
    out_tensor.to("cpu")

    print("Execution complete. Inspecting Power output buffer vs reference...")
    
    # Reference calculation: Power = I^2 + Q^2
    in_f = np_in_bf16.astype(np.float32)
    ref_power = np.zeros(out_size, dtype=np.float32)
    for i in range(out_size):
        i_s = in_f[2 * i]
        q_s = in_f[2 * i + 1]
        ref_power[i] = (i_s * i_s) + (q_s * q_s)

    ref_power_bf16 = ref_power.astype(element_type)
    out_np = out_tensor._data

    print(f"Input I/Q sample [0..4]:  {np_in_bf16[:4]}")
    print(f"Ref Power sample [0..4]:  {ref_power_bf16[:4]}")
    print(f"Actual Power sample [0..4]: {out_np[:4]}")

    max_err = float(np.max(np.abs(out_np.astype(np.float32) - ref_power_bf16.astype(np.float32))))
    print(f"Maximum absolute error: {max_err:.6f}")

    assert_pass(out_np, ref_power_bf16, fail_msg="Power detector output mismatch", atol=0.01)
    print("SUCCESS: Phoenix NPU executed Power Detector on physical silicon!")
    print("PASS!")


if __name__ == "__main__":
    main()
