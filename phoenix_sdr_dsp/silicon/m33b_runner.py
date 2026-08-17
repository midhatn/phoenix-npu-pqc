"""Native MLIR-AIE/IRON dispatcher for M33b rounding and hint primitives.

``run_m33b`` has no host arithmetic implementation.  A call either dispatches
the existing AIE2 C++ kernel through XRT or reports that native execution could
not be performed.
"""

# Sources consulted for this runner's ABI and topology:
# - MLIR-AIE v1.4.1 IRON documentation:
#   https://xilinx.github.io/mlir-aie/1.4.1/
# - This repository's validated control-buffer/ObjectFifo pattern:
#   tests/m32_mlkem/test_kpke_m32d.py (kpke_program and _dispatch).
# The rounding arithmetic itself remains in
# tests/m33_mldsa/dilithium_sampler_kernel.cc; this file only carries mode and
# param through an ObjectFifo control buffer.

from collections.abc import Sequence
from pathlib import Path
from typing import Any

import numpy as np

N = 256
CTRL_LEN = 2
PACKED_LEN = CTRL_LEN + N
VALID_MODES = frozenset({0, 1, 2, 3, 4, 5})
BACKEND_LABEL = "m33b:silicon"

_PROGRAM: Any | None = None


class NativeRunnerUnavailable(RuntimeError):
    """The MLIR-AIE runtime or physical dispatch path is unavailable."""


def _load_iron() -> tuple[Any, ...]:
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
    except Exception as exc:  # noqa: BLE001
        raise NativeRunnerUnavailable(
            "M33b requires MLIR-AIE/IRON and an XRT-visible Phoenix NPU; "
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
    if values is None:
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


def _checked_i32(name: str, value: int) -> int:
    integer = int(value)
    if not -(1 << 31) <= integer < (1 << 31):
        raise ValueError(f"{name}={integer} is outside signed int32 range")
    return integer


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
    def m33b_program(
        in_a: In,
        in_packed: In,
        out_c: Out,
        out_d: Out,
        *,
        n_poly_slots: CompileTime[int],
        n_packed_slots: CompileTime[int],
        element_type: CompileTime[type],
    ):
        poly_ty = np.ndarray[(n_poly_slots,), np.dtype[element_type]]
        packed_ty = np.ndarray[(n_packed_slots,), np.dtype[element_type]]
        of_a = ObjectFifo(poly_ty, name="m33b_in_a")
        of_packed = ObjectFifo(packed_ty, name="m33b_in_packed")
        of_c = ObjectFifo(poly_ty, name="m33b_out_c")
        of_d = ObjectFifo(poly_ty, name="m33b_out_d")

        kernel = ExternalFunction(
            "dilithium_sampler_packed",
            source_file=str(
                Path(__file__).resolve().parents[2]
                / "tests"
                / "m33_mldsa"
                / "dilithium_sampler_kernel.cc"
            ),
            arg_types=[poly_ty, packed_ty, poly_ty, poly_ty],
            include_dirs=[cxx_header_path()],
        )

        def core_body(of_a, of_packed, of_c, of_d, kernel):
            a = of_a.acquire(1)
            packed = of_packed.acquire(1)
            c = of_c.acquire(1)
            d = of_d.acquire(1)
            kernel(a, packed, c, d)
            of_a.release(1)
            of_packed.release(1)
            of_c.release(1)
            of_d.release(1)

        worker = Worker(
            core_body,
            fn_args=[
                of_a.cons(),
                of_packed.cons(),
                of_c.prod(),
                of_d.prod(),
                kernel,
            ],
            stack_size=0x4000,
        )

        def sequence(
            a_in,
            packed_in,
            c_out,
            d_out,
            a_prod,
            packed_prod,
            c_cons,
            d_cons,
        ):
            a_prod.fill(a_in)
            packed_prod.fill(packed_in)
            c_cons.drain(c_out, wait=True)
            d_cons.drain(d_out, wait=True)

        runtime = Runtime(
            sequence,
            [
                poly_ty,
                packed_ty,
                poly_ty,
                poly_ty,
                of_a.prod(),
                of_packed.prod(),
                of_c.cons(),
                of_d.cons(),
            ],
        )
        return Program(iron.get_current_device(), runtime, workers=[worker]).resolve_program()

    _PROGRAM = m33b_program
    return _PROGRAM


def run_m33b(
    mode: int,
    param: int,
    in_a: Sequence[int],
    in_b: Sequence[int] | None = None,
) -> tuple[list[int], list[int]]:
    """Run one M33b operation on physical Phoenix AIE2 silicon."""
    mode_i = int(mode)
    if mode_i not in VALID_MODES:
        raise ValueError(f"unsupported M33b mode {mode_i}; expected one of {sorted(VALID_MODES)}")
    param_i = _checked_i32("param", param)
    a_np = _checked_poly("in_a", in_a)
    b_np = _checked_poly("in_b", in_b)
    packed_np = np.empty(PACKED_LEN, dtype=np.int32)
    packed_np[0] = mode_i
    packed_np[1] = param_i
    packed_np[CTRL_LEN:] = b_np
    c_np = np.zeros(N, dtype=np.int32)
    d_np = np.zeros(N, dtype=np.int32)

    *_, XRTTensor = _load_iron()
    a_t = XRTTensor(a_np, dtype=np.int32)
    packed_t = XRTTensor(packed_np, dtype=np.int32)
    c_t = XRTTensor(c_np, dtype=np.int32)
    d_t = XRTTensor(d_np, dtype=np.int32)
    try:
        _program()(
            a_t,
            packed_t,
            c_t,
            d_t,
            n_poly_slots=N,
            n_packed_slots=PACKED_LEN,
            element_type=np.int32,
        )
        c_t.to("cpu")
        d_t.to("cpu")
    except Exception as exc:  # noqa: BLE001
        raise NativeRunnerUnavailable(
            "M33b native MLIR-AIE dispatch failed; no reference fallback was used."
        ) from exc
    return (
        [int(value) for value in c_t._data[:N]],
        [int(value) for value in d_t._data[:N]],
    )


run = run_m33b
