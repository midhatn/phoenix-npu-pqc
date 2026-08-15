# Purpose: 4-column streamed I/Q mixer throughput (MB/s, Msps) on Phoenix NPU.
# Target operating system: Windows 11 Pro 22H2+.
# Target architecture: AMD Phoenix / Hawk Point NPU1 / XDNA1 / AIE2 (all columns).
# Input types: bfloat16 interleaved I/Q + LO, many 1024-element frames per dispatch.
# Output types: mixed I/Q; first dispatch checked vs NumPy; timed window prints MB/s.
# Verification: First buffer matches complex multiply (atol=0.01). Not in the 16-suite.
#
# The one-tile M6 loop was host-bound (~2 ms IRON round-trip per 8 KB, ~3.85 MB/s,
# ~53% Task Manager). This version keeps all columns in a streaming acquire/release
# loop so one dispatch moves ~0.5 MiB of I/Q. Rates are still host-visible
# (IRON + shim DMA), not a theoretical AIE peak.

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
IRONENV_PYTHON = (
    REPO_ROOT / "third_party" / "mlir-aie" / "ironenv" / "Scripts" / "python.exe"
)

MEASURE_SECONDS = 5.0
TILE_N = 1024
FRAMES = 64
BF16_BYTES = 2
ATOL = 0.01
COMPILE_HINT_SECONDS = 1.5
CACHE_SUFFIXES = {".xclbin", ".bin", ".elf", ".pdi"}


def _cache_roots() -> list[Path]:
    home = Path.home()
    return [
        home / ".npu" / "cache",
        home / ".npu",
        home / "AppData" / "Local" / "npu",
    ]


def _cache_fingerprint() -> dict[str, tuple[int, int]]:
    found: dict[str, tuple[int, int]] = {}
    for root in _cache_roots():
        if not root.is_dir():
            continue
        for path in root.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in CACHE_SUFFIXES:
                continue
            try:
                st = path.stat()
            except OSError:
                continue
            found[str(path)] = (st.st_size, int(st.st_mtime_ns))
    return found


def first_dispatch_label(elapsed_s: float, before: dict, after: dict) -> str:
    wrote_cache = after != before
    if wrote_cache or elapsed_s >= COMPILE_HINT_SECONDS:
        return f"First dispatch (includes compile): {elapsed_s:.2f}s"
    return f"First dispatch (cached): {elapsed_s:.2f}s"


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
from aie.utils.hostruntime.xrtruntime.tensor import XRTTensor
from aie.utils.verify import assert_pass
from ml_dtypes import bfloat16


@iron.jit
def iq_stream_mixer(
    input_iq: In,
    lo_carrier: In,
    output_iq: Out,
    *,
    N: CompileTime[int],
    element_type: CompileTime[type],
):
    device = iron.get_current_device()
    num_columns = device.cols
    per_col = N // num_columns
    tile_ty = np.ndarray[(TILE_N,), np.dtype[element_type]]
    tensor_ty = np.ndarray[(N,), np.dtype[element_type]]

    of_inputs = [ObjectFifo(tile_ty, name=f"in_col_{c}") for c in range(num_columns)]
    of_los = [ObjectFifo(tile_ty, name=f"lo_col_{c}") for c in range(num_columns)]
    of_outputs = [ObjectFifo(tile_ty, name=f"out_col_{c}") for c in range(num_columns)]

    mix_fn = ExternalFunction(
        "iq_mix_tile",
        source_file=str(Path(__file__).parent.resolve() / "iq_mix_tile.cc"),
        arg_types=[tile_ty, tile_ty, tile_ty],
        include_dirs=[cxx_header_path()],
    )

    # One acquire/release. Worker(while_true=True) streams every 1024-element token.
    # Do not for-range the frames here: static ObjectFifo lowering unrolls that
    # loop into the 16 KB AIE2 program memory and aiecc fails with
    # _XAie_LoadProgMemSection overflow.
    def core_body(of_in, of_lo, of_out, fn):
        elem_in = of_in.acquire(1)
        elem_lo = of_lo.acquire(1)
        elem_out = of_out.acquire(1)
        fn(elem_in, elem_lo, elem_out)
        of_in.release(1)
        of_lo.release(1)
        of_out.release(1)

    workers = [
        Worker(
            core_body,
            fn_args=[
                of_inputs[c].cons(),
                of_los[c].cons(),
                of_outputs[c].prod(),
                mix_fn,
            ],
            while_true=True,
            dynamic_objfifo_lowering=True,
        )
        for c in range(num_columns)
    ]

    taps = [
        TensorAccessPattern((1, N), c * per_col, [1, 1, 1, per_col], [0, 0, 0, 1])
        for c in range(num_columns)
    ]
    input_prods = [of_inputs[c].prod() for c in range(num_columns)]
    lo_prods = [of_los[c].prod() for c in range(num_columns)]
    output_conss = [of_outputs[c].cons() for c in range(num_columns)]

    def sequence(a_in, a_lo, c_out, *endpoints):
        n = len(endpoints) // 3
        in_prods = endpoints[:n]
        lo_prods_ = endpoints[n : 2 * n]
        out_conss = endpoints[2 * n :]
        tg_in = TaskGroup()
        for col in range(n):
            in_prods[col].fill(a_in, tap=taps[col], group=tg_in)
            lo_prods_[col].fill(a_lo, tap=taps[col], group=tg_in)
        tg_in.finish()
        tg_out = TaskGroup()
        for col in range(n):
            out_conss[col].drain(c_out, tap=taps[col], wait=True, group=tg_out)
        tg_out.finish()

    rt = Runtime(
        sequence,
        [tensor_ty, tensor_ty, tensor_ty, *input_prods, *lo_prods, *output_conss],
    )
    return Program(device, rt, workers=workers).resolve_program()


def make_iq(n_elems: int):
    n_c = n_elems // 2
    t = np.linspace(0, 1, n_c, endpoint=False)
    sig = np.exp(1j * 2 * np.pi * 5.0 * t)
    lo = np.exp(1j * 2 * np.pi * 50.0 * t)
    np_in = np.zeros(n_elems, dtype=np.float32)
    np_in[0::2] = sig.real
    np_in[1::2] = sig.imag
    np_lo = np.zeros(n_elems, dtype=np.float32)
    np_lo[0::2] = lo.real
    np_lo[1::2] = lo.imag
    return np_in.astype(bfloat16), np_lo.astype(bfloat16)


def mixer_reference(in_bf16, lo_bf16):
    in_f = in_bf16.astype(np.float32)
    lo_f = lo_bf16.astype(np.float32)
    in_c = in_f[0::2] + 1j * in_f[1::2]
    lo_c = lo_f[0::2] + 1j * lo_f[1::2]
    out_c = in_c * lo_c
    ref = np.empty_like(in_f)
    ref[0::2] = out_c.real
    ref[1::2] = out_c.imag
    return ref.astype(bfloat16)


def main() -> None:
    device = iron.get_current_device()
    cols = int(device.cols)
    n_elems = TILE_N * FRAMES * cols
    bytes_iq = n_elems * BF16_BYTES
    print("=== Phoenix SDR-DSP I/Q throughput (4-column streamed mixer) ===")
    print(f"Target Device: {device} (columns: {cols})")
    print(
        f"Dispatch: {FRAMES} frames x {TILE_N} bf16 x {cols} cols  "
        f"= {n_elems} elements ({bytes_iq} bytes I/Q in, {bytes_iq} bytes I/Q out)"
    )
    print("Previous 1-column 8 KB loop was host-bound (~3.85 MB/s, ~53% NPU).")
    print("Task Manager: Ctrl+Shift+Esc → Performance → NPU")
    print()

    in_bf16, lo_bf16 = make_iq(n_elems)
    out_bf16 = np.zeros(n_elems, dtype=bfloat16)
    in_tensor = XRTTensor(in_bf16, dtype=bfloat16)
    lo_tensor = XRTTensor(lo_bf16, dtype=bfloat16)
    out_tensor = XRTTensor(out_bf16, dtype=bfloat16)

    print("Warmup dispatch (compile on cache miss)...")
    cache_before = _cache_fingerprint()
    t0 = time.perf_counter()
    iq_stream_mixer(in_tensor, lo_tensor, out_tensor, N=n_elems, element_type=bfloat16)
    warmup_s = time.perf_counter() - t0
    print(first_dispatch_label(warmup_s, cache_before, _cache_fingerprint()))
    out_tensor.to("cpu")
    ref = mixer_reference(in_bf16, lo_bf16)
    max_err = float(
        np.max(np.abs(out_tensor._data.astype(np.float32) - ref.astype(np.float32)))
    )
    print(f"First-buffer max abs error: {max_err:.6f}")
    assert_pass(
        out_tensor._data,
        ref,
        fail_msg="streamed I/Q mixer mismatch on first dispatch",
        atol=ATOL,
    )
    print("First dispatch matches complex-multiply reference.")
    print()
    print("Measuring...")

    t0 = time.perf_counter()
    dispatches = 0
    while (time.perf_counter() - t0) < MEASURE_SECONDS:
        iq_stream_mixer(
            in_tensor, lo_tensor, out_tensor, N=n_elems, element_type=bfloat16
        )
        dispatches += 1
    elapsed = time.perf_counter() - t0

    if dispatches < 1:
        print("FAIL: no timed dispatch completed.")
        sys.exit(1)

    bytes_in = dispatches * bytes_iq
    bytes_out = dispatches * bytes_iq
    complex_samples = dispatches * (n_elems // 2)
    print("----------------------------------------------------------------------")
    print(f" Dispatches:       {dispatches}")
    print(f" Elapsed:          {elapsed:.3f} s")
    print(f" IQ in:            {bytes_in / 1e6 / elapsed:8.2f} MB/s")
    print(f" IQ out:           {bytes_out / 1e6 / elapsed:8.2f} MB/s")
    print(f" IQ in+out:        {(bytes_in + bytes_out) / 1e6 / elapsed:8.2f} MB/s")
    print(f" Complex samples:  {complex_samples / elapsed / 1e6:8.3f} Msps")
    print("----------------------------------------------------------------------")
    print("SUCCESS: 4-column streamed I/Q mixer. Rates are host-visible (IRON + DMA).")
    print("PASS!")


if __name__ == "__main__":
    main()
