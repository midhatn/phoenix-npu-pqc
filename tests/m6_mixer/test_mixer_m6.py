# Purpose: Milestone 6 Complex Mixer / NCO Silicon Validation on AMD Phoenix NPU (Ryzen AI 7940HS).
# Target operating system: Windows 11 Pro 25H2.
# Target architecture: AMD Phoenix NPU1 / XDNA1 / AIE2.
# Input types: bfloat16 interleaved I/Q signal (4096 elements = 2048 I/Q pairs) + NCO carrier vector.
# Output types: bfloat16 frequency-shifted I/Q output verified against NumPy complex multiplication.
# Scaling: direct bfloat16.
# Alignment assumptions: handled by IRON XRTTensor/BO runtime.
# State requirements: device 0 (NPU Phoenix).
# Error handling: Bit-accurate tolerance check against reference complex mixer.

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
from ml_dtypes import bfloat16


@iron.jit
def complex_mixer(
    input_iq: In,
    lo_carrier: In,
    output_iq: Out,
    *,
    N: CompileTime[int],
    element_type: CompileTime[type]
):
    in_ty = np.ndarray[(N,), np.dtype[element_type]]
    out_ty = np.ndarray[(N,), np.dtype[element_type]]

    of_in = ObjectFifo(in_ty, name="in_iq")
    of_lo = ObjectFifo(in_ty, name="lo")
    of_out = ObjectFifo(out_ty, name="out_iq")

    current_dir = Path(__file__).parent.resolve()
    include_sdr_dir = Path(r"C:\phoenix-sdr-dsp\include\sdr_dsp")

    mixer_func = ExternalFunction(
        "complex_mixer_kernel",
        source_file=str(current_dir / "mixer_kernel.cc"),
        arg_types=[in_ty, in_ty, out_ty],
        include_dirs=[cxx_header_path(), str(include_sdr_dir)],
    )

    def core_body(of_in, of_lo, of_out, mixer_func):
        elem_in = of_in.acquire(1)
        elem_lo = of_lo.acquire(1)
        elem_out = of_out.acquire(1)
        mixer_func(elem_in, elem_lo, elem_out)
        of_in.release(1)
        of_lo.release(1)
        of_out.release(1)

    worker = Worker(
        core_body, fn_args=[of_in.cons(), of_lo.cons(), of_out.prod(), mixer_func]
    )

    rt = Runtime()
    with rt.sequence(in_ty, in_ty, out_ty) as (a_in, a_lo, c_out):
        rt.start(worker)
        rt.fill(of_in.prod(), a_in)
        rt.fill(of_lo.prod(), a_lo)
        rt.drain(of_out.cons(), c_out, wait=True)

    my_program = Program(iron.get_current_device(), rt)
    return my_program.resolve_program()


def main():
    print("=== Phoenix SDR-DSP Milestone 6: Complex Mixer / NCO Silicon Execution ===")
    data_size = 4096  # 2048 Complex pairs
    element_type = bfloat16
    print(f"Target Device: {iron.get_current_device()}")
    print(f"Vector Length: {data_size} elements ({data_size // 2} Complex I/Q pairs) of {element_type.__name__}")

    # Generate synthetic SDR baseband signal (100 kHz tone modulated on I/Q)
    num_complex = data_size // 2
    t = np.linspace(0, 1, num_complex, endpoint=False)
    
    # Baseband signal: e^(j * 2*pi * f1 * t)
    f_bb = 5.0
    sig_complex = np.exp(1j * 2 * np.pi * f_bb * t)
    
    # NCO LO Carrier: e^(j * 2*pi * f_lo * t) to frequency-shift by +50 Hz
    f_lo = 50.0
    lo_complex = np.exp(1j * 2 * np.pi * f_lo * t)

    # Interleave I and Q into 4096-length arrays: [I0, Q0, I1, Q1, ...]
    np_input_iq = np.zeros(data_size, dtype=np.float32)
    np_input_iq[0::2] = sig_complex.real
    np_input_iq[1::2] = sig_complex.imag
    np_in_bf16 = np_input_iq.astype(element_type)

    np_lo_iq = np.zeros(data_size, dtype=np.float32)
    np_lo_iq[0::2] = lo_complex.real
    np_lo_iq[1::2] = lo_complex.imag
    np_lo_bf16 = np_lo_iq.astype(element_type)

    np_out_iq = np.zeros(data_size, dtype=element_type)

    # Wrap in XRTTensor
    in_tensor = XRTTensor(np_in_bf16, dtype=element_type)
    lo_tensor = XRTTensor(np_lo_bf16, dtype=element_type)
    out_tensor = XRTTensor(np_out_iq, dtype=element_type)

    print("Compiling Complex Mixer / NCO with Peano and dispatching to Phoenix NPU...")
    res = complex_mixer(in_tensor, lo_tensor, out_tensor, N=data_size, element_type=element_type)
    print(f"Kernel execution result: {res}")

    # Sync back from NPU to host memory
    out_tensor.to("cpu")

    print("Execution complete. Inspecting Mixed I/Q output buffer vs reference...")
    
    # Reference calculation matching exact bfloat16 input values:
    in_f = np_in_bf16.astype(np.float32)
    lo_f = np_lo_bf16.astype(np.float32)
    ref_out = np.zeros(data_size, dtype=np.float32)
    
    for i in range(0, data_size, 2):
        i_in = in_f[i]
        q_in = in_f[i + 1]
        c_lo = lo_f[i]
        s_lo = lo_f[i + 1]
        ref_out[i]     = (i_in * c_lo) - (q_in * s_lo)
        ref_out[i + 1] = (i_in * s_lo) + (q_in * c_lo)

    ref_out_bf16 = ref_out.astype(element_type)
    out_np = out_tensor._data

    print(f"Input I/Q sample [0..4]:    {np_in_bf16[:4]}")
    print(f"LO Carrier sample [0..4]:   {np_lo_bf16[:4]}")
    print(f"Ref Out sample [0..4]:      {ref_out_bf16[:4]}")
    print(f"Actual Out sample [0..4]:   {out_np[:4]}")

    max_err = float(np.max(np.abs(out_np.astype(np.float32) - ref_out_bf16.astype(np.float32))))
    print(f"Maximum absolute error: {max_err:.6f}")

    assert_pass(out_np, ref_out_bf16, fail_msg="Complex mixer output mismatch", atol=0.01)
    print("SUCCESS: Phoenix NPU executed Complex Mixer / NCO on physical silicon!")
    print("PASS!")


if __name__ == "__main__":
    main()
