# Purpose: Visible NPU heartbeat for Windows Task Manager (Performance → NPU).
# Target operating system: Windows 11 Pro 22H2+ (NPU graph is a Windows 11 feature).
# Target architecture: AMD Phoenix / Hawk Point NPU1 / XDNA1 / AIE2.
# Workload: 4-column spin kernel, duty-cycled to random 0-100% targets for 5 s.
# Verification: At least one successful NPU dispatch. Not a bit-accurate DSP test.
#
# Task Manager samples NPU load at about 1 Hz via Microsoft's Compute Driver
# Model (MCDM). This script cannot write an exact percent into that graph. It
# duty-cycles real AIE2 work vs idle so the graph moves between low and high.
# Open Task Manager → Performance → NPU before the spin starts.
# https://learn.microsoft.com/en-us/windows/ai/npu-devices/

from __future__ import annotations

import os
import random
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
IRONENV_PYTHON = (
    REPO_ROOT / "third_party" / "mlir-aie" / "ironenv" / "Scripts" / "python.exe"
)


def ensure_ironenv_interpreter() -> None:
    if sys.platform != "win32":
        return
    if not IRONENV_PYTHON.is_file():
        print("ironenv not found. Run this first:")
        print("  python install.py")
        sys.exit(2)
    wanted = IRONENV_PYTHON.resolve()
    current = Path(sys.executable).resolve()
    try:
        if current.samefile(wanted):
            return
    except OSError:
        if current == wanted:
            return
    os.execv(str(wanted), [str(wanted), *sys.argv])


ensure_ironenv_interpreter()

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
from ml_dtypes import bfloat16

SPIN_SECONDS = 5.0
WINDOW_S = 1.0
TILE_N = 1024


@iron.jit
def npu_spin(
    input_sig: In,
    output_sig: Out,
    *,
    N: CompileTime[int],
    element_type: CompileTime[type],
):
    num_columns = iron.get_current_device().cols
    per_tile = N // num_columns
    tensor_ty = np.ndarray[(N,), np.dtype[element_type]]
    tile_ty = np.ndarray[(per_tile,), np.dtype[element_type]]

    of_inputs = [
        ObjectFifo(tile_ty, name=f"in_col_{col}") for col in range(num_columns)
    ]
    of_outputs = [
        ObjectFifo(tile_ty, name=f"out_col_{col}") for col in range(num_columns)
    ]

    spin_fn = ExternalFunction(
        "spin_tile",
        source_file=str(Path(__file__).parent.resolve() / "spin_tile_kernel.cc"),
        arg_types=[tile_ty, tile_ty],
        include_dirs=[cxx_header_path()],
    )

    def core_body(of_in, of_out, fn):
        elem_in = of_in.acquire(1)
        elem_out = of_out.acquire(1)
        fn(elem_in, elem_out)
        of_in.release(1)
        of_out.release(1)

    workers = [
        Worker(core_body, fn_args=[of_inputs[c].cons(), of_outputs[c].prod(), spin_fn])
        for c in range(num_columns)
    ]

    taps = [
        TensorAccessPattern(
            (1, N),
            col * per_tile,
            [1, 1, 1, per_tile],
            [0, 0, 0, 1],
        )
        for col in range(num_columns)
    ]
    input_prods = [of_inputs[c].prod() for c in range(num_columns)]
    output_conss = [of_outputs[c].cons() for c in range(num_columns)]

    def sequence(a_in, c_out, *endpoints):
        n = len(endpoints) // 2
        in_prods = endpoints[:n]
        out_conss = endpoints[n:]
        tg_in = TaskGroup()
        for col in range(n):
            in_prods[col].fill(a_in, tap=taps[col], group=tg_in)
        tg_in.finish()
        tg_out = TaskGroup()
        for col in range(n):
            out_conss[col].drain(c_out, tap=taps[col], wait=True, group=tg_out)
        tg_out.finish()

    rt = Runtime(sequence, [tensor_ty, tensor_ty, *input_prods, *output_conss])
    return Program(iron.get_current_device(), rt, workers=workers).resolve_program()


def _targets(windows: int) -> list[int]:
    """Random 0-100 per window, with at least one high window so the graph moves."""
    values = [random.randint(0, 100) for _ in range(windows)]
    if max(values) < 50:
        values[0] = 100
    return values


def main() -> None:
    print("=== Phoenix SDR-DSP NPU visibility heartbeat ===")
    device = iron.get_current_device()
    cols = int(device.cols)
    data_size = TILE_N * cols
    print(f"Target Device: {device} (columns: {cols})")
    print(
        f"Workload: {data_size} bfloat16 across {cols} tiles, duty-cycled {SPIN_SECONDS:.0f}s"
    )
    print()
    print("Open Task Manager now:")
    print("  Ctrl+Shift+Esc  →  Performance  →  NPU")
    print("https://learn.microsoft.com/en-us/windows/ai/npu-devices/")
    print()

    input_sig = iron.arange(data_size, dtype=bfloat16, device="npu")
    output_sig = iron.zeros_like(input_sig)

    print("Compiling 4-column spin kernel with Peano (once)...")
    t0 = time.perf_counter()
    npu_spin(
        input_sig,
        output_sig,
        N=data_size,
        element_type=bfloat16,
    )
    print(f"First dispatch (includes compile): {time.perf_counter() - t0:.2f}s")
    print()
    print("Spin starts. Watch the NPU graph.")
    print("----------------------------------------------------------------------")

    windows = int(SPIN_SECONDS / WINDOW_S)
    targets = _targets(windows)
    dispatches = 0
    spin_t0 = time.perf_counter()

    for i, target in enumerate(targets, start=1):
        window_end = spin_t0 + i * WINDOW_S
        busy_s = WINDOW_S * (target / 100.0)
        busy_end = min(spin_t0 + (i - 1) * WINDOW_S + busy_s, window_end)
        launched = 0
        while time.perf_counter() < busy_end:
            npu_spin(
                input_sig,
                output_sig,
                N=data_size,
                element_type=bfloat16,
            )
            launched += 1
            dispatches += 1
        remain = window_end - time.perf_counter()
        if remain > 0:
            time.sleep(remain)
        print(
            f" [{i}/{windows}] target {target:3d}%   "
            f"dispatches {launched:4d}   elapsed {time.perf_counter() - spin_t0:4.2f}s"
        )

    elapsed = time.perf_counter() - spin_t0
    sample = output_sig.numpy()[:4]
    print("----------------------------------------------------------------------")
    print(f" Windows: {windows} | dispatches: {dispatches} | spin wall: {elapsed:.2f}s")
    print(f" Output sample [0..4]: {sample}")

    if dispatches < 1:
        print("FAIL: no NPU dispatch ran (every target was 0%). Re-run.")
        sys.exit(1)
    print(
        "SUCCESS: NPU executed on physical silicon. Task Manager NPU should have moved."
    )
    print("PASS!")


if __name__ == "__main__":
    main()
