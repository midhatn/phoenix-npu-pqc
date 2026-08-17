"""DR0: one-invocation, device-resident ML-DSA polynomial product graph.

There is intentionally no CPU arithmetic path in this module.  A successful
call is labelled ``m33-dr0:silicon`` only after the one IRON invocation drains
the terminal polynomial.  Missing IRON/XRT/Phoenix support raises an explicit
exception rather than returning a host reference result.
"""

from pathlib import Path
from typing import Any

import numpy as np

from .abi import POLYNOMIAL_BYTES, N, reference_negacyclic_product, validate_polynomial

BACKEND_LABEL = "m33-dr0:silicon"
OUTPUT_SENTINEL = -(1 << 31)

_PROGRAM: Any | None = None


class NativeBackendUnavailable(RuntimeError):
    """The only DR0 backend, native IRON/XRT on Phoenix, is unavailable."""


def _load_iron() -> tuple[Any, ...]:
    """Load native dependencies lazily and never install a numerical fallback."""
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
        raise NativeBackendUnavailable(
            "DR0 requires MLIR-AIE/IRON 1.4.1, XRT, and an XRT-visible Phoenix NPU; "
            "no host arithmetic fallback is available."
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
    """Perform a native dependency preflight without constructing a result."""
    _load_iron()


def _program() -> Any:
    """Build the fixed DR0 graph: two ingress FIFOs, one terminal egress FIFO."""
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
    def m33_dr0_program(
        in_a: In,
        in_b: In,
        out_c: Out,
        *,
        n_poly_slots: CompileTime[int],
        element_type: CompileTime[type],
    ):
        poly_ty = np.ndarray[(n_poly_slots,), np.dtype[element_type]]
        of_a = ObjectFifo(poly_ty, name="m33_dr0_in_a")
        of_b = ObjectFifo(poly_ty, name="m33_dr0_in_b")
        of_c = ObjectFifo(poly_ty, name="m33_dr0_out_c")
        kernel = ExternalFunction(
            "m33_product_graph",
            source_file=str(Path(__file__).resolve().parent / "kernels" / "m33_product_graph.cc"),
            arg_types=[poly_ty, poly_ty, poly_ty],
            include_dirs=[cxx_header_path()],
        )

        def core_body(of_a, of_b, of_c, kernel):
            a = of_a.acquire(1)
            b = of_b.acquire(1)
            c = of_c.acquire(1)
            kernel(a, b, c)
            of_a.release(1)
            of_b.release(1)
            of_c.release(1)

        worker = Worker(
            core_body,
            fn_args=[of_a.cons(), of_b.cons(), of_c.prod(), kernel],
            stack_size=0x4000,
        )

        def sequence(a_in, b_in, c_out, a_prod, b_prod, c_cons):
            a_prod.fill(a_in)
            b_prod.fill(b_in)
            c_cons.drain(c_out, wait=True)

        runtime = Runtime(
            sequence,
            [poly_ty, poly_ty, poly_ty, of_a.prod(), of_b.prod(), of_c.cons()],
        )
        return Program(iron.get_current_device(), runtime, workers=[worker]).resolve_program()

    _PROGRAM = m33_dr0_program
    return _PROGRAM


def run_m33_product(a: list[int] | tuple[int, ...], b: list[int] | tuple[int, ...]) -> list[int]:
    """Multiply two ML-DSA polynomials in one resident native graph invocation.

    Input validation completes before native dependencies are loaded.  The only
    host retrieval is the terminal ``c`` buffer after the device has completed
    NTT(a), NTT(b), pointwise Montgomery base multiplication, INTT, and device
    canonicalization.  No stage is transferred back to the host.
    """
    a_checked = validate_polynomial("a", a)
    b_checked = validate_polynomial("b", b)
    a_np = np.asarray(a_checked, dtype=np.int32)
    b_np = np.asarray(b_checked, dtype=np.int32)
    c_np = np.full(N, OUTPUT_SENTINEL, dtype=np.int32)

    *_, XRTTensor = _load_iron()
    a_t = XRTTensor(a_np, dtype=np.int32)
    b_t = XRTTensor(b_np, dtype=np.int32)
    c_t = XRTTensor(c_np, dtype=np.int32)
    try:
        _program()(a_t, b_t, c_t, n_poly_slots=N, element_type=np.int32)
        c_t.to("cpu")  # the one and only terminal host transfer in DR0
    except Exception as exc:
        raise NativeBackendUnavailable(
            "DR0 native MLIR-AIE dispatch failed; no reference fallback was used."
        ) from exc

    result = [int(value) for value in c_t._data[:N]]
    if len(result) != N or any(value == OUTPUT_SENTINEL for value in result):
        raise NativeBackendUnavailable(
            "DR0 terminal output was not fully written by the native graph; refusing partial output."
        )
    if any(value < 0 or value >= 8_380_417 for value in result):
        raise NativeBackendUnavailable(
            "DR0 native graph returned a non-canonical terminal polynomial."
        )
    return result


# A compact production alias for callers that prefer the package operation name.
run = run_m33_product

__all__ = [
    "BACKEND_LABEL",
    "OUTPUT_SENTINEL",
    "POLYNOMIAL_BYTES",
    "NativeBackendUnavailable",
    "reference_negacyclic_product",
    "require_hardware_runtime",
    "run",
    "run_m33_product",
]
