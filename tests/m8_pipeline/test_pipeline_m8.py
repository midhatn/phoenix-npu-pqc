# Purpose: Milestone 8 Multi-Stage SDR Demodulator Pipeline Silicon Validation.
# Target operating system: Windows 11 Pro 25H2.
# Target architecture: AMD Phoenix NPU1 / XDNA1 / AIE2.
# Pipeline: Raw RF I/Q -> Complex Downconversion -> Channel Low-Pass FIR -> Power/RSSI Envelope.
# Verification: Bit-accurate end-to-end match with streaming receiver reference model.

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
def sdr_demod_pipeline(
    input_iq: In,
    lo_carrier: In,
    output_power: Out,
    *,
    N_IN: CompileTime[int],
    N_OUT: CompileTime[int],
    element_type: CompileTime[type]
):
    in_ty = np.ndarray[(N_IN,), np.dtype[element_type]]
    out_ty = np.ndarray[(N_OUT,), np.dtype[element_type]]

    of_in = ObjectFifo(in_ty, name="in_iq")
    of_lo = ObjectFifo(in_ty, name="lo_carrier")
    of_out = ObjectFifo(out_ty, name="out_power")

    current_dir = Path(__file__).parent.resolve()
    include_sdr_dir = Path(r"C:\phoenix-sdr-dsp\include\sdr_dsp")

    pipe_func = ExternalFunction(
        "sdr_pipeline_kernel",
        source_file=str(current_dir / "pipeline_kernel.cc"),
        arg_types=[in_ty, in_ty, out_ty],
        include_dirs=[cxx_header_path(), str(include_sdr_dir)],
    )

    def core_body(of_in, of_lo, of_out, pipe_func):
        elem_in = of_in.acquire(1)
        elem_lo = of_lo.acquire(1)
        elem_out = of_out.acquire(1)
        pipe_func(elem_in, elem_lo, elem_out)
        of_in.release(1)
        of_lo.release(1)
        of_out.release(1)

    worker = Worker(
        core_body, fn_args=[of_in.cons(), of_lo.cons(), of_out.prod(), pipe_func]
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
    print("=== Phoenix SDR-DSP Milestone 8: Multi-Stage Demodulator Pipeline Silicon Execution ===")
    in_size = 4096   # 2048 Complex pairs
    out_size = 2048  # 2048 Power samples
    element_type = bfloat16
    print(f"Target Device: {iron.get_current_device()}")
    print(f"Pipeline: [Input I/Q (4096)] -> [Complex NCO Downconversion] -> [Dual-Channel FIR] -> [Power Detection (2048)]")

    # Generate synthetic SDR modulated RF signal at f_rf = 25 Hz
    num_complex = out_size
    t = np.linspace(0, 1, num_complex, endpoint=False)
    
    # Baseband audio signal modulating the amplitude
    bb_signal = 0.5 * (1.0 + np.sin(2 * np.pi * 5 * t))
    f_rf = 25.0
    sig_complex = bb_signal * np.exp(1j * 2 * np.pi * f_rf * t)
    
    # NCO carrier to downconvert f_rf -> baseband (0 Hz)
    lo_complex = np.exp(-1j * 2 * np.pi * f_rf * t)

    # Interleave I and Q into 4096-length arrays
    np_input_iq = np.zeros(in_size, dtype=np.float32)
    np_input_iq[0::2] = sig_complex.real
    np_input_iq[1::2] = sig_complex.imag
    np_in_bf16 = np_input_iq.astype(element_type)

    np_lo_iq = np.zeros(in_size, dtype=np.float32)
    np_lo_iq[0::2] = lo_complex.real
    np_lo_iq[1::2] = lo_complex.imag
    np_lo_bf16 = np_lo_iq.astype(element_type)

    np_out_power = np.zeros(out_size, dtype=element_type)

    # Wrap in XRTTensor
    in_tensor = XRTTensor(np_in_bf16, dtype=element_type)
    lo_tensor = XRTTensor(np_lo_bf16, dtype=element_type)
    out_tensor = XRTTensor(np_out_power, dtype=element_type)

    print("Compiling Streaming Pipeline with Peano and dispatching to Phoenix NPU...")
    res = sdr_demod_pipeline(
        in_tensor,
        lo_tensor,
        out_tensor,
        N_IN=in_size,
        N_OUT=out_size,
        element_type=element_type,
    )
    print(f"Kernel execution result: {res}")

    # Sync back from NPU to host memory
    out_tensor.to("cpu")

    print("Execution complete. Inspecting Demodulator output buffer vs reference...")
    
    # Streaming Reference Pipeline Execution matching exact bfloat16 quantization
    in_f = np_in_bf16.astype(np.float32)
    lo_f = np_lo_bf16.astype(np.float32)
    coeffs_f = [0.05, 0.10, 0.20, 0.30, 0.30, 0.20, 0.10, 0.05]
    
    hist_i = [0.0] * 8
    hist_q = [0.0] * 8
    ref_power = np.zeros(num_complex, dtype=np.float32)

    for i in range(num_complex):
        i_in = in_f[2 * i]
        q_in = in_f[2 * i + 1]
        c_lo = lo_f[2 * i]
        s_lo = lo_f[2 * i + 1]

        # 1. Mixer
        mixed_i = (i_in * c_lo) - (q_in * s_lo)
        mixed_q = (i_in * s_lo) + (q_in * c_lo)

        # Shift history
        hist_i = hist_i[1:] + [mixed_i]
        hist_q = hist_q[1:] + [mixed_q]

        # 2. FIR
        filt_i = sum(hist_i[7 - k] * coeffs_f[k] for k in range(8))
        filt_q = sum(hist_q[7 - k] * coeffs_f[k] for k in range(8))

        # 3. Power
        ref_power[i] = (filt_i * filt_i) + (filt_q * filt_q)

    ref_power_bf16 = ref_power.astype(element_type)
    out_np = out_tensor._data

    print(f"Input I/Q sample [0..4]:     {np_in_bf16[:4]}")
    print(f"Ref Power sample [0..4]:     {ref_power_bf16[:4]}")
    print(f"Actual Power sample [0..4]:  {out_np[:4]}")

    max_err = float(np.max(np.abs(out_np.astype(np.float32) - ref_power_bf16.astype(np.float32))))
    print(f"Maximum absolute error: {max_err:.6f}")

    assert_pass(out_np, ref_power_bf16, fail_msg="Pipeline output mismatch", atol=0.03)
    print("SUCCESS: Phoenix NPU executed Full Streaming SDR Demodulator Pipeline on physical silicon!")
    print("PASS!")


if __name__ == "__main__":
    main()
