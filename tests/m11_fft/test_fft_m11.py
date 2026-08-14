# Purpose: Milestone 11 64-point FFT / Channelizer Silicon Validation on AMD Phoenix NPU.
# Target operating system: Windows 11 Pro 25H2.
# Target architecture: AMD Phoenix NPU1 / XDNA1 / AIE2.
# Input types: bfloat16 interleaved complex vector (128 elements = 64 I/Q pairs) + Twiddles table (128 elements).
# Output types: bfloat16 spectrum vector (128 elements = 64 complex bins) verified against NumPy FFT.

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
def fft_64point(
    input_iq: In,
    twiddles: In,
    output_spec: Out,
    *,
    N: CompileTime[int],
    element_type: CompileTime[type]
):
    in_ty = np.ndarray[(N,), np.dtype[element_type]]
    out_ty = np.ndarray[(N,), np.dtype[element_type]]

    of_in = ObjectFifo(in_ty, name="in_iq")
    of_tw = ObjectFifo(in_ty, name="twiddles")
    of_out = ObjectFifo(out_ty, name="out_spec")

    current_dir = Path(__file__).parent.resolve()
    include_sdr_dir = Path(r"C:\phoenix-sdr-dsp\include\sdr_dsp")

    fft_func = ExternalFunction(
        "fft64_kernel",
        source_file=str(current_dir / "fft64_kernel.cc"),
        arg_types=[in_ty, in_ty, out_ty],
        include_dirs=[cxx_header_path(), str(include_sdr_dir)],
    )

    def core_body(of_in, of_tw, of_out, fft_fn):
        elem_in = of_in.acquire(1)
        elem_tw = of_tw.acquire(1)
        elem_out = of_out.acquire(1)
        fft_fn(elem_in, elem_tw, elem_out)
        of_in.release(1)
        of_tw.release(1)
        of_out.release(1)

    worker = Worker(
        core_body, fn_args=[of_in.cons(), of_tw.cons(), of_out.prod(), fft_func]
    )

    rt = Runtime()
    with rt.sequence(in_ty, in_ty, out_ty) as (a_in, a_tw, c_out):
        rt.start(worker)
        rt.fill(of_in.prod(), a_in)
        rt.fill(of_tw.prod(), a_tw)
        rt.drain(of_out.cons(), c_out, wait=True)

    my_program = Program(iron.get_current_device(), rt)
    return my_program.resolve_program()


def main():
    print("=== Phoenix SDR-DSP Milestone 11: 64-Point FFT Silicon Execution ===")
    n_points = 64
    data_size = n_points * 2  # 128 elements (64 complex I/Q pairs)
    element_type = bfloat16
    print(f"Target Device: {iron.get_current_device()}")
    print(f"Transform Size: {n_points}-Point Complex FFT ({data_size} bfloat16 values)")

    # Generate synthetic multi-tone signal: 3 distinct frequency tones
    t = np.linspace(0, 1, n_points, endpoint=False)
    f1, f2, f3 = 4.0, 12.0, 20.0
    sig_complex = (
        1.0 * np.exp(1j * 2 * np.pi * f1 * t) +
        0.7 * np.exp(1j * 2 * np.pi * f2 * t) +
        0.5 * np.exp(1j * 2 * np.pi * f3 * t)
    )

    # Interleave I and Q into 128-element array
    np_input_iq = np.zeros(data_size, dtype=np.float32)
    np_input_iq[0::2] = sig_complex.real
    np_input_iq[1::2] = sig_complex.imag
    np_in_bf16 = np_input_iq.astype(element_type)

    # Precalculate DFT Twiddle table: W_N^k = e^(-j * 2*pi * k / N)
    twiddles_c = np.exp(-1j * 2 * np.pi * np.arange(n_points) / n_points)
    np_twiddles = np.zeros(data_size, dtype=np.float32)
    np_twiddles[0::2] = twiddles_c.real
    np_twiddles[1::2] = twiddles_c.imag
    np_tw_bf16 = np_twiddles.astype(element_type)

    np_out_spec = np.zeros(data_size, dtype=element_type)

    # Wrap in XRTTensor
    in_tensor = XRTTensor(np_in_bf16, dtype=element_type)
    tw_tensor = XRTTensor(np_tw_bf16, dtype=element_type)
    out_tensor = XRTTensor(np_out_spec, dtype=element_type)

    print("Compiling 64-Point FFT with Peano and dispatching to Phoenix NPU...")
    res = fft_64point(
        in_tensor,
        tw_tensor,
        out_tensor,
        N=data_size,
        element_type=element_type,
    )
    print(f"Kernel execution result: {res}")

    # Sync back from NPU to host memory
    out_tensor.to("cpu")

    print("\nExecution complete. Inspecting FFT Spectrum output buffer vs NumPy reference...")
    
    # Reference calculation using exact bfloat16 quantized inputs
    in_f = np_in_bf16.astype(np.float32)
    tw_f = np_tw_bf16.astype(np.float32)
    
    ref_spec_r = np.zeros(n_points, dtype=np.float32)
    ref_spec_i = np.zeros(n_points, dtype=np.float32)
    
    for k in range(n_points):
        sum_r = 0.0
        sum_i = 0.0
        for n in range(n_points):
            in_r = in_f[2 * n]
            in_i = in_f[2 * n + 1]
            tw_idx = (k * n) % n_points
            tw_r = tw_f[2 * tw_idx]
            tw_i = tw_f[2 * tw_idx + 1]
            sum_r += (in_r * tw_r) - (in_i * tw_i)
            sum_i += (in_r * tw_i) + (in_i * tw_r)
        ref_spec_r[k] = sum_r
        ref_spec_i[k] = sum_i

    ref_spec_iq = np.zeros(data_size, dtype=np.float32)
    ref_spec_iq[0::2] = ref_spec_r
    ref_spec_iq[1::2] = ref_spec_i
    ref_spec_bf16 = ref_spec_iq.astype(element_type)

    out_np = out_tensor._data

    print(f"Input I/Q Bin [0..2]:       {np_in_bf16[:4]}")
    print(f"Ref Spectrum Bin [0..2]:    {ref_spec_bf16[:4]}")
    print(f"Actual Spectrum Bin [0..2]: {out_np[:4]}")

    # Inspect Peak Tones detected (Bins 4, 12, 20)
    mag_out = np.sqrt(out_np[0::2].astype(np.float32)**2 + out_np[1::2].astype(np.float32)**2)
    top_bins = np.argsort(mag_out)[::-1][:3]
    print(f"Detected Peak Frequencies (Top 3 Bins): {top_bins} (Expected: [4, 12, 20])")

    max_err = float(np.max(np.abs(out_np.astype(np.float32) - ref_spec_bf16.astype(np.float32))))
    print(f"Maximum absolute error: {max_err:.6f}")

    assert_pass(out_np, ref_spec_bf16, fail_msg="FFT spectrum output mismatch", atol=0.1)
    print("SUCCESS: Phoenix NPU executed 64-Point Vectorized FFT on physical silicon!")
    print("PASS!")


if __name__ == "__main__":
    main()
