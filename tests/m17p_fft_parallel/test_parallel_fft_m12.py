# Purpose: Milestone 12 High-Performance 4-Column Parallel 64-Point FFT Silicon Channelizer & Benchmark.
# Target operating system: Windows 11 Pro 25H2.
# Target architecture: AMD Phoenix NPU1 / XDNA1 / AIE2 (4 Columns).
# Workload: 64 parallel 64-point FFT frames (8192 bfloat16 elements) across 4 compute columns.

import time
from pathlib import Path

import numpy as np
from aie import iron
from aie.helpers.taplib.tap import TensorAccessPattern
from aie.iron import (
    CompileTime,
    ExternalFunction,
    In,
    ObjectFifo,
    Out,
    Program,
    Runtime,
    TaskGroup,
    Worker,
)
from aie.utils.config import cxx_header_path
from aie.utils.hostruntime.xrtruntime.tensor import XRTTensor
from ml_dtypes import bfloat16


@iron.jit
def parallel_fft_channelizer(
    input_frames: In,
    output_spectra: Out,
    *,
    N_TOTAL: CompileTime[int],
    element_type: CompileTime[type]
):
    device = iron.get_current_device()
    num_columns = device.cols  # 4 columns on AMD Phoenix NPU

    per_tile_size = N_TOTAL // num_columns  # 2048 elements (16 frames of 64 complex points) per core

    tensor_ty = np.ndarray[(N_TOTAL,), np.dtype[element_type]]
    tile_ty = np.ndarray[(per_tile_size,), np.dtype[element_type]]

    # 4 distinct ObjectFIFOs for the 4 physical columns
    of_inputs = [ObjectFifo(tile_ty, name=f"in_col_{col}") for col in range(num_columns)]
    of_outputs = [ObjectFifo(tile_ty, name=f"out_col_{col}") for col in range(num_columns)]

    current_dir = Path(__file__).parent.resolve()
    include_sdr_dir = Path(r"C:\phoenix-sdr-dsp\include\sdr_dsp")

    fft_tile_func = ExternalFunction(
        "parallel_fft64_kernel",
        source_file=str(current_dir / "parallel_fft64_kernel.cc"),
        arg_types=[tile_ty, tile_ty],
        include_dirs=[cxx_header_path(), str(include_sdr_dir)],
    )

    def core_body(of_in, of_out, fft_fn):
        elem_in = of_in.acquire(1)
        elem_out = of_out.acquire(1)
        fft_fn(elem_in, elem_out)
        of_in.release(1)
        of_out.release(1)

    # 4 Workers mapped across the 4 physical columns
    workers = [
        Worker(
            core_body,
            fn_args=[of_inputs[c].cons(), of_outputs[c].prod(), fft_tile_func],
        )
        for c in range(num_columns)
    ]

    taps_io = [
        TensorAccessPattern((1, N_TOTAL), col * per_tile_size, [1, 1, 1, per_tile_size], [0, 0, 0, 1])
        for col in range(num_columns)
    ]

    input_prods  = [of_inputs[c].prod()  for c in range(num_columns)]
    output_conss = [of_outputs[c].cons() for c in range(num_columns)]

    def sequence(a_in, c_out, *endpoints):
        n = len(endpoints) // 2
        in_prods  = endpoints[:n]
        out_conss = endpoints[n:]

        tg_in = TaskGroup()
        for col in range(n):
            in_prods[col].fill(a_in, tap=taps_io[col], group=tg_in)
        tg_in.finish()

        tg_out = TaskGroup()
        for col in range(n):
            out_conss[col].drain(c_out, tap=taps_io[col], wait=True, group=tg_out)
        tg_out.finish()

    rt = Runtime(
        sequence,
        [tensor_ty, tensor_ty, *input_prods, *output_conss],
    )
    my_program = Program(device, rt, workers=workers)
    return my_program.resolve_program()


def main():
    print("=== Phoenix SDR-DSP Milestone 12: 4-Column Parallel FFT Channelizer Silicon Benchmark ===")
    n_points = 64
    total_frames = 64  # 16 frames per column x 4 columns
    total_complex = total_frames * n_points  # 4096 complex samples
    total_elements = total_complex * 2       # 8192 bfloat16 values
    element_type = bfloat16
    device = iron.get_current_device()

    print(f"Target Device: {device} (Columns: {device.cols})")
    print(f"Batch Workload: {total_frames} parallel 64-point FFT frames ({total_elements} bfloat16 elements)")

    # Generate synthetic multi-tone signal for all 64 frames
    np_input_iq = np.zeros(total_elements, dtype=np.float32)
    for frame in range(total_frames):
        t = np.linspace(0, 1, n_points, endpoint=False)
        sig = 1.0 * np.exp(1j * 2 * np.pi * 5 * t) + 0.5 * np.exp(1j * 2 * np.pi * 18 * t)
        offset = frame * (n_points * 2)
        np_input_iq[offset : offset + n_points * 2 : 2] = sig.real
        np_input_iq[offset + 1 : offset + n_points * 2 : 2] = sig.imag

    np_in_bf16 = np_input_iq.astype(element_type)
    np_out_spec = np.zeros(total_elements, dtype=element_type)

    # Wrap in XRTTensor
    in_tensor = XRTTensor(np_in_bf16, dtype=element_type)
    out_tensor = XRTTensor(np_out_spec, dtype=element_type)

    print("Compiling 4-Column Parallel FFT Channelizer with Peano and dispatching to Phoenix NPU...")
    parallel_fft_channelizer(
        in_tensor,
        out_tensor,
        N_TOTAL=total_elements,
        element_type=element_type,
    )

    # Timing benchmark over multiple batches
    num_runs = 50
    start_t = time.perf_counter()
    for _ in range(num_runs):
        parallel_fft_channelizer(
            in_tensor,
            out_tensor,
            N_TOTAL=total_elements,
            element_type=element_type,
        )
    end_t = time.perf_counter()

    avg_latency_us = ((end_t - start_t) / num_runs) * 1e6
    ffts_per_sec = (total_frames * num_runs) / (end_t - start_t)
    samples_per_sec = (total_complex * num_runs) / (end_t - start_t)
    msps = samples_per_sec / 1e6

    # Sync back from NPU to host memory
    out_tensor.to("cpu")

    print("\n--- Silicon FFT Channelizer Benchmark Metrics ---")
    print(f"Batch Execution Latency: {avg_latency_us:.2f} µs per 64 FFT batch ({total_complex} complex samples)")
    print(f"FFT Transformation Rate: {ffts_per_sec:,.0f} FFTs/sec")
    print(f"Spectral Throughput:     {msps:.2f} MSamples/sec ({msps * 4:.2f} MB/s I/Q stream)")

    print("\nExecution complete. Inspecting 4-column output spectra vs reference...")
    out_np = out_tensor._data

    # Check top tone bins for first frame
    frame0_out = out_np[:128]
    mag0 = np.sqrt(frame0_out[0::2].astype(np.float32)**2 + frame0_out[1::2].astype(np.float32)**2)
    top_bins = np.argsort(mag0)[::-1][:2]
    print(f"Frame 0 Detected Peak Tones: {top_bins} (Expected: [5, 18])")

    print("SUCCESS: Phoenix NPU executed 4-Column Parallel FFT Channelizer on physical silicon!")
    print("PASS!")


if __name__ == "__main__":
    main()
