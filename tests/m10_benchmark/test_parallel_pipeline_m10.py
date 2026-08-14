# Purpose: Milestone 10 4-Column Parallel Multi-Stage SDR Demodulator Pipeline Silicon Execution & Benchmarking.
# Target operating system: Windows 11 Pro 25H2.
# Target architecture: AMD Phoenix NPU1 / XDNA1 / AIE2 (4 Columns).
# Workload: 4096 I/Q interleaved samples across 4 parallel compute cores with latency and throughput benchmarking.

import time
from pathlib import Path
import aie.iron as iron
import numpy as np
from aie.helpers.taplib.tap import TensorAccessPattern
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
def parallel_sdr_pipeline(
    input_iq: In,
    lo_carrier: In,
    output_power: Out,
    *,
    N_IN: CompileTime[int],
    N_OUT: CompileTime[int],
    element_type: CompileTime[type]
):
    device = iron.get_current_device()
    num_columns = device.cols  # 4 columns on AMD Phoenix NPU

    per_tile_in = N_IN // num_columns    # 1024 I/Q samples per core
    per_tile_out = N_OUT // num_columns  # 512 Power samples per core

    in_ty = np.ndarray[(N_IN,), np.dtype[element_type]]
    out_ty = np.ndarray[(N_OUT,), np.dtype[element_type]]

    tile_in_ty = np.ndarray[(per_tile_in,), np.dtype[element_type]]
    tile_out_ty = np.ndarray[(per_tile_out,), np.dtype[element_type]]

    # 4 distinct ObjectFIFOs per column
    of_inputs = [ObjectFifo(tile_in_ty, name=f"in_col_{col}") for col in range(num_columns)]
    of_los = [ObjectFifo(tile_in_ty, name=f"lo_col_{col}") for col in range(num_columns)]
    of_outputs = [ObjectFifo(tile_out_ty, name=f"out_col_{col}") for col in range(num_columns)]

    current_dir = Path(__file__).parent.resolve()
    include_sdr_dir = Path(r"C:\phoenix-sdr-dsp\include\sdr_dsp")

    pipe_tile_func = ExternalFunction(
        "parallel_pipeline_kernel",
        source_file=str(current_dir / "parallel_pipeline_kernel.cc"),
        arg_types=[tile_in_ty, tile_in_ty, tile_out_ty],
        include_dirs=[cxx_header_path(), str(include_sdr_dir)],
    )

    def core_body(of_in, of_lo, of_out, pipe_fn):
        elem_in = of_in.acquire(1)
        elem_lo = of_lo.acquire(1)
        elem_out = of_out.acquire(1)
        pipe_fn(elem_in, elem_lo, elem_out)
        of_in.release(1)
        of_lo.release(1)
        of_out.release(1)

    # 4 Workers mapped across the 4 physical columns
    workers = [
        Worker(
            core_body,
            fn_args=[of_inputs[c].cons(), of_los[c].cons(), of_outputs[c].prod(), pipe_tile_func],
        )
        for c in range(num_columns)
    ]

    # TensorAccessPatterns for slicing 4096 inputs and 2048 outputs
    taps_in = [
        TensorAccessPattern((1, N_IN), col * per_tile_in, [1, 1, 1, per_tile_in], [0, 0, 0, 1])
        for col in range(num_columns)
    ]
    taps_out = [
        TensorAccessPattern((1, N_OUT), col * per_tile_out, [1, 1, 1, per_tile_out], [0, 0, 0, 1])
        for col in range(num_columns)
    ]

    rt = Runtime()
    with rt.sequence(in_ty, in_ty, out_ty) as (a_in, a_lo, c_out):
        rt.start(*workers)

        # Non-blocking Parallel DMA Input Task Group
        tg_in = rt.task_group()
        for col in range(num_columns):
            rt.fill(of_inputs[col].prod(), a_in, taps_in[col], task_group=tg_in)
            rt.fill(of_los[col].prod(), a_lo, taps_in[col], task_group=tg_in)
        rt.finish_task_group(tg_in)

        # Parallel DMA Output Task Group
        tg_out = rt.task_group()
        for col in range(num_columns):
            rt.drain(of_outputs[col].cons(), c_out, taps_out[col], wait=True, task_group=tg_out)
        rt.finish_task_group(tg_out)

    my_program = Program(device, rt)
    return my_program.resolve_program()


def main():
    print("=== Phoenix SDR-DSP Milestone 10: 4-Column Parallel Demodulator Pipeline Silicon Execution ===")
    in_size = 4096   # 2048 Complex pairs
    out_size = 2048  # 2048 Power samples
    element_type = bfloat16
    device = iron.get_current_device()
    print(f"Target Device: {device} (Columns: {device.cols})")
    print(f"Parallel Workload: {in_size} I/Q samples across 4 AIE cores ({in_size // device.cols} samples/core)")

    # Generate synthetic SDR modulated RF signal
    num_complex = out_size
    t = np.linspace(0, 1, num_complex, endpoint=False)
    bb_signal = 0.5 * (1.0 + np.sin(2 * np.pi * 5 * t))
    f_rf = 25.0
    sig_complex = bb_signal * np.exp(1j * 2 * np.pi * f_rf * t)
    lo_complex = np.exp(-1j * 2 * np.pi * f_rf * t)

    np_input_iq = np.zeros(in_size, dtype=np.float32)
    np_input_iq[0::2] = sig_complex.real
    np_input_iq[1::2] = sig_complex.imag
    np_in_bf16 = np_input_iq.astype(element_type)

    np_lo_iq = np.zeros(in_size, dtype=np.float32)
    np_lo_iq[0::2] = lo_complex.real
    np_lo_iq[1::2] = lo_complex.imag
    np_lo_bf16 = np_lo_iq.astype(element_type)

    np_out_power = np.zeros(out_size, dtype=element_type)

    in_tensor = XRTTensor(np_in_bf16, dtype=element_type)
    lo_tensor = XRTTensor(np_lo_bf16, dtype=element_type)
    out_tensor = XRTTensor(np_out_power, dtype=element_type)

    print("Compiling 4-Column Parallel Pipeline with Peano and dispatching to Phoenix NPU...")
    res = parallel_sdr_pipeline(
        in_tensor,
        lo_tensor,
        out_tensor,
        N_IN=in_size,
        N_OUT=out_size,
        element_type=element_type,
    )

    # Warmup and timing benchmark
    num_runs = 50
    start_t = time.perf_counter()
    for _ in range(num_runs):
        parallel_sdr_pipeline(in_tensor, lo_tensor, out_tensor, N_IN=in_size, N_OUT=out_size, element_type=element_type)
    end_t = time.perf_counter()

    avg_latency_us = ((end_t - start_t) / num_runs) * 1e6
    samples_per_sec = (num_complex * num_runs) / (end_t - start_t)
    msps = samples_per_sec / 1e6

    # Sync back from NPU to host memory
    out_tensor.to("cpu")

    print(f"\n--- Silicon Benchmark Metrics ---")
    print(f"Average Execution Latency: {avg_latency_us:.2f} µs per 2048 I/Q burst")
    print(f"SDR Processing Throughput:  {msps:.2f} MSamples/sec ({msps * 2 * 2:.2f} MB/s I/Q stream)")

    print("\nExecution complete. Inspecting 4-column output buffer vs reference...")
    
    # Per-tile reference verification
    in_f = np_in_bf16.astype(np.float32)
    lo_f = np_lo_bf16.astype(np.float32)
    coeffs_f = [0.05, 0.10, 0.20, 0.30, 0.30, 0.20, 0.10, 0.05]
    
    ref_power = np.zeros(num_complex, dtype=np.float32)
    per_tile_c = num_complex // device.cols

    for col in range(device.cols):
        hist_i = [0.0] * 8
        hist_q = [0.0] * 8
        tile_in = in_f[col * (2 * per_tile_c) : (col + 1) * (2 * per_tile_c)]
        tile_lo = lo_f[col * (2 * per_tile_c) : (col + 1) * (2 * per_tile_c)]

        for i in range(per_tile_c):
            i_in = tile_in[2 * i]
            q_in = tile_in[2 * i + 1]
            c_lo = tile_lo[2 * i]
            s_lo = tile_lo[2 * i + 1]

            mixed_i = (i_in * c_lo) - (q_in * s_lo)
            mixed_q = (i_in * s_lo) + (q_in * c_lo)

            hist_i = hist_i[1:] + [mixed_i]
            hist_q = hist_q[1:] + [mixed_q]

            filt_i = sum(hist_i[7 - k] * coeffs_f[k] for k in range(8))
            filt_q = sum(hist_q[7 - k] * coeffs_f[k] for k in range(8))

            ref_power[col * per_tile_c + i] = (filt_i * filt_i) + (filt_q * filt_q)

    ref_power_bf16 = ref_power.astype(element_type)
    out_np = out_tensor._data

    print(f"Input I/Q sample [0..4]:     {np_in_bf16[:4]}")
    print(f"Ref Power sample [0..4]:     {ref_power_bf16[:4]}")
    print(f"Actual Power sample [0..4]:  {out_np[:4]}")

    max_err = float(np.max(np.abs(out_np.astype(np.float32) - ref_power_bf16.astype(np.float32))))
    print(f"Maximum absolute error: {max_err:.6f}")

    assert_pass(out_np, ref_power_bf16, fail_msg="4-Column Pipeline output mismatch", atol=0.03)
    print("SUCCESS: Phoenix NPU executed 4-Column Parallel Demodulator Pipeline on physical silicon!")
    print("PASS!")


if __name__ == "__main__":
    main()
