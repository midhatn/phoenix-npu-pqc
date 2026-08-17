"""Native MLIR-AIE/IRON dispatcher for the M33a Dilithium NTT kernel.

This module is deliberately *not* a numerical fallback.  ``run_m33a`` either
executes ``dilithium_ntt_kernel.cc`` through XRT on an AIE2 device or raises a
clear exception.  Keeping the MLIR-AIE imports lazy makes the contract
inspectable on ordinary CI hosts without allowing CI to mistake Python
reference arithmetic for a silicon dispatch.
"""

# Sources consulted for this runner's ABI and topology:
# - MLIR-AIE v1.4.1 IRON documentation:
#   https://xilinx.github.io/mlir-aie/1.4.1/
# - This repository's validated control-buffer/ObjectFifo pattern:
#   tests/m32_mlkem/test_ntt_m32b.py (ntt_program and _dispatch).
# The NTT arithmetic itself remains in tests/m33_mldsa/dilithium_ntt_kernel.cc;
# this file only adapts scalar mode into an ObjectFifo control buffer.

from collections.abc import Sequence
from pathlib import Path
from typing import Any

import numpy as np

N = 256
CTRL_LEN = 1
PACKED_LEN = CTRL_LEN + N
VALID_MODES = frozenset({0, 1, 2, 3})
BACKEND_LABEL = "m33a:silicon"

_PROGRAM: Any | None = None


class NativeRunnerUnavailable(RuntimeError):
    """The MLIR-AIE runtime or physical dispatch path is unavailable."""


def _load_iron() -> tuple[Any, ...]:
    """Load MLIR-AIE only at dispatch time; never substitute a CPU result."""
    try:
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
    except Exception as exc:
        raise NativeRunnerUnavailable(
            "M33a requires MLIR-AIE/IRON and an XRT-visible Phoenix NPU; "
            "no reference fallback is available."
        ) from exc
    return (
        iron,
        CompileTime,
        ExternalFunction,
        In,
        ObjectFifo,
        Out,
        Program,
        Runtime,
        Worker,
        cxx_header_path,
        XRTTensor,
    )


def require_hardware_runtime() -> None:
    """Fail early if the native MLIR-AIE runtime is not installed."""
    _load_iron()


def _checked_poly(name: str, values: Sequence[int] | None) -> np.ndarray:
    # Primitive callers historically pass [] for the unused BASEMUL operand on
    # NTT/INTT/REDUCE. Treat that spelling exactly like None for in_b only.
    if values is None or (name == "in_b" and len(values) == 0):
        return np.zeros(N, dtype=np.int32)
    if len(values) != N:
        raise ValueError(f"{name} must contain exactly {N} int32 coefficients")
    out = np.empty(N, dtype=np.int32)
    for i, value in enumerate(values):
        integer = int(value)
        if not -(1 << 31) <= integer < (1 << 31):
            raise ValueError(f"{name}[{i}]={integer} is outside signed int32 range")
        out[i] = integer
    return out


def _program() -> Any:
    global _PROGRAM
    if _PROGRAM is not None:
        return _PROGRAM

    (
        iron,
        CompileTime,
        ExternalFunction,
        In,
        ObjectFifo,
        Out,
        Program,
        Runtime,
        Worker,
        cxx_header_path,
        _,
    ) = _load_iron()

    @iron.jit
    def m33a_program(
        in_a: In,
        in_packed: In,
        out_c: Out,
        *,
        n_poly_slots: CompileTime[int],
        n_packed_slots: CompileTime[int],
        element_type: CompileTime[type],
    ):
        poly_ty = np.ndarray[(n_poly_slots,), np.dtype[element_type]]
        packed_ty = np.ndarray[(n_packed_slots,), np.dtype[element_type]]
        of_a = ObjectFifo(poly_ty, name="m33a_in_a")
        of_packed = ObjectFifo(packed_ty, name="m33a_in_packed")
        of_out = ObjectFifo(poly_ty, name="m33a_out_c")

        kernel = ExternalFunction(
            "dilithium_ntt_packed",
            source_file=str(
                Path(__file__).resolve().parents[2]
                / "tests"
                / "m33_mldsa"
                / "dilithium_ntt_kernel.cc"
            ),
            arg_types=[poly_ty, packed_ty, poly_ty],
            include_dirs=[cxx_header_path()],
        )

        def core_body(of_a, of_packed, of_out, kernel):
            a = of_a.acquire(1)
            packed = of_packed.acquire(1)
            out = of_out.acquire(1)
            kernel(a, packed, out)
            of_a.release(1)
            of_packed.release(1)
            of_out.release(1)

        worker = Worker(
            core_body,
            fn_args=[
                of_a.cons(),
                of_packed.cons(),
                of_out.prod(),
                kernel,
            ],
            stack_size=0x4000,
        )

        def sequence(a_in, packed_in, c_out, a_prod, packed_prod, out_cons):
            a_prod.fill(a_in)
            packed_prod.fill(packed_in)
            out_cons.drain(c_out, wait=True)

        runtime = Runtime(
            sequence,
            [
                poly_ty,
                packed_ty,
                poly_ty,
                of_a.prod(),
                of_packed.prod(),
                of_out.cons(),
            ],
        )
        return Program(iron.get_current_device(), runtime, workers=[worker]).resolve_program()

    _PROGRAM = m33a_program
    return _PROGRAM


def run_m33a(
    mode: int,
    in_a: Sequence[int],
    in_b: Sequence[int] | None = None,
) -> list[int]:
    """Run one M33a operation on physical Phoenix AIE2 silicon.

    ``mode`` has the kernel's native meaning: 0=NTT, 1=INTT, 2=BASEMUL, and
    3=REDUCE.  Modes other than BASEMUL ignore ``in_b`` but still transfer a
    zero-filled 256-lane buffer to retain the fixed kernel ABI.
    """
    mode_i = int(mode)
    if mode_i not in VALID_MODES:
        raise ValueError(f"unsupported M33a mode {mode_i}; expected one of {sorted(VALID_MODES)}")
    a_np = _checked_poly("in_a", in_a)
    b_np = _checked_poly("in_b", in_b)
    packed_np = np.empty(PACKED_LEN, dtype=np.int32)
    packed_np[0] = mode_i
    packed_np[CTRL_LEN:] = b_np
    out_np = np.zeros(N, dtype=np.int32)

    *_, XRTTensor = _load_iron()
    a_t = XRTTensor(a_np, dtype=np.int32)
    packed_t = XRTTensor(packed_np, dtype=np.int32)
    out_t = XRTTensor(out_np, dtype=np.int32)
    try:
        _program()(
            a_t,
            packed_t,
            out_t,
            n_poly_slots=N,
            n_packed_slots=PACKED_LEN,
            element_type=np.int32,
        )
        out_t.to("cpu")
    except Exception as exc:
        raise NativeRunnerUnavailable(
            "M33a native MLIR-AIE dispatch failed; no reference fallback was used."
        ) from exc
    return [int(value) for value in out_t._data[:N]]


# Composer tests historically requested ``run`` while primitive tests requested
# ``run_m33a``.  Both names intentionally point at the same native-only path.
run = run_m33a
