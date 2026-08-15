# Purpose: Milestone 17 v3 (radix-4 Stockham FFT) silicon validation on AMD Phoenix NPU.
# Target operating system: Windows 11 Pro 25H2.
# Target architecture: AMD Phoenix NPU / XDNA / AIE2P (npu2).
# Input:   64 complex f32 samples (interleaved [re, im, re, im, ...] = 128 float32 values)
# Twiddle: 512 bf16 Ozaki-split radix-4 twiddle table (see twiddles_r4_stockham.py)
# Output:  64 complex f32 spectrum bins verified against numpy.fft.fft
#
# Kernel: kernels/fft_stockham_f32.cc (from FFT_R4_AIE) via fft64_r4_wrapper.cc

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

from twiddles_r4_stockham import pack_twiddles_r4_stockham


N_POINTS = 64
INPUT_ELEMS = N_POINTS * 2
OUTPUT_ELEMS = N_POINTS * 2
TWIDDLE_ELEMS = N_POINTS * 8


@iron.jit
def fft64_stockham_r4(
    input_iq: In,
    twiddles: In,
    output_spec: Out,
    *,
    N_in: CompileTime[int],
    N_tw: CompileTime[int],
    N_out: CompileTime[int],
):
    in_ty = np.ndarray[(N_in,), np.dtype[np.float32]]
    tw_ty = np.ndarray[(N_tw,), np.dtype[bfloat16]]
    out_ty = np.ndarray[(N_out,), np.dtype[np.float32]]

    of_in = ObjectFifo(in_ty, name="in_iq")
    of_tw = ObjectFifo(tw_ty, name="twiddles")
    of_out = ObjectFifo(out_ty, name="out_spec")

    current_dir = Path(__file__).parent.resolve()
    wrapper_path = current_dir / "fft64_r4_wrapper.cc"
    include_sdr_dir = Path(r"C:\phoenix-sdr-dsp\include\sdr_dsp")

    fft_func = ExternalFunction(
        "fft_stockham_f32",
        source_file=str(wrapper_path),
        arg_types=[in_ty, tw_ty, out_ty],
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

    def sequence(a_in, a_tw, c_out, in_h, tw_h, out_h):
        in_h.fill(a_in)
        tw_h.fill(a_tw)
        out_h.drain(c_out, wait=True)

    rt = Runtime(
        sequence,
        [in_ty, tw_ty, out_ty, of_in.prod(), of_tw.prod(), of_out.cons()],
    )

    my_program = Program(iron.get_current_device(), rt, workers=[worker])
    return my_program.resolve_program()


def main():
    print("=== Phoenix SDR-DSP Milestone 17 v3: Radix-4 Stockham FFT ===")
    print(f"Target Device:  {iron.get_current_device()}")
    print(f"FFT Size:       {N_POINTS} points ({INPUT_ELEMS} f32 in/out, {TWIDDLE_ELEMS} bf16 twiddles)")

    # 3-tone test signal (same as M17 direct-DFT for comparability)
    t = np.linspace(0, 1, N_POINTS, endpoint=False)
    f1, f2, f3 = 4.0, 12.0, 20.0
    sig_complex = (
        1.0 * np.exp(1j * 2 * np.pi * f1 * t) +
        0.7 * np.exp(1j * 2 * np.pi * f2 * t) +
        0.5 * np.exp(1j * 2 * np.pi * f3 * t)
    )
    np_input_iq = np.zeros(INPUT_ELEMS, dtype=np.float32)
    np_input_iq[0::2] = sig_complex.real
    np_input_iq[1::2] = sig_complex.imag

    np_twiddles = pack_twiddles_r4_stockham(N_POINTS, over_provision=True)
    assert len(np_twiddles) == TWIDDLE_ELEMS
    print(f"Twiddle table:  {len(np_twiddles)} bfloat16 elements, dtype={np_twiddles.dtype}")

    np_out_spec = np.zeros(OUTPUT_ELEMS, dtype=np.float32)

    in_tensor = XRTTensor(np_input_iq, dtype=np.float32)
    tw_tensor = XRTTensor(np_twiddles, dtype=bfloat16)
    out_tensor = XRTTensor(np_out_spec, dtype=np.float32)

    print("Compiling radix-4 Stockham FFT with Peano and dispatching to Phoenix NPU...")
    res = fft64_stockham_r4(
        in_tensor,
        tw_tensor,
        out_tensor,
        N_in=INPUT_ELEMS,
        N_tw=TWIDDLE_ELEMS,
        N_out=OUTPUT_ELEMS,
    )
    print(f"Kernel execution result: {res}")

    out_tensor.to("cpu")

    print("\nExecution complete. Verifying FFT output against numpy.fft.fft ...")

    ref_complex = np.fft.fft(sig_complex).astype(np.complex64)
    ref_iq = np.zeros(OUTPUT_ELEMS, dtype=np.float32)
    ref_iq[0::2] = ref_complex.real
    ref_iq[1::2] = ref_complex.imag

    out_np = out_tensor._data
    in_np_after = in_tensor._data
    print("")
    print(f"Ref Spectrum Bin [0..2]:    {ref_iq[:6]}")
    print(f"Actual Spectrum Bin [0..2]: {out_np[:6]}")

    mag_out = np.sqrt(out_np[0::2] ** 2 + out_np[1::2] ** 2)
    mag_ref = np.sqrt(ref_iq[0::2] ** 2 + ref_iq[1::2] ** 2)
    top_bins_out = np.argsort(mag_out)[::-1][:3]
    top_bins_ref = np.argsort(mag_ref)[::-1][:3]
    print(f"Detected Peak Bins (actual): {sorted(top_bins_out.tolist())} "
          f"(reference: {sorted(top_bins_ref.tolist())}, expected: [4, 12, 20])")

    abs_err = np.abs(out_np - ref_iq)
    max_err = float(np.max(abs_err))
    rms_err = float(np.sqrt(np.mean(abs_err ** 2)))
    ref_pwr = np.mean(ref_iq ** 2)
    err_pwr = np.mean(abs_err ** 2)
    snr_db = 10 * np.log10(ref_pwr / err_pwr) if err_pwr > 0 else float("inf")

    print(f"Max abs error:  {max_err:.6f}")
    print(f"RMS abs error:  {rms_err:.6f}")
    print(f"SNR:            {snr_db:.2f} dB")

    assert sorted(top_bins_out.tolist()) == [4, 12, 20], \
        f"Peak detection failed: got {sorted(top_bins_out.tolist())}, expected [4, 12, 20]"

    peak_magnitude = float(np.max(mag_ref))
    atol = 0.1 * peak_magnitude

    assert_pass(out_np, ref_iq,
                fail_msg=f"FFT output mismatch (max_err={max_err:.4f})",
                atol=atol)
    print(f"SUCCESS: Phoenix NPU executed 64-point radix-4 Stockham FFT!")
    print("PASS!")


if __name__ == "__main__":
    main()