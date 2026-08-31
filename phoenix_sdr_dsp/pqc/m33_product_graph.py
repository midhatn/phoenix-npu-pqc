"""DR0: one-invocation, device-resident ML-DSA polynomial product graph.

There is intentionally no CPU arithmetic path in this module.  A successful
call is labelled ``m33-dr0:silicon`` only after the one IRON invocation drains
the terminal polynomial.  Missing IRON/XRT/Phoenix support raises an explicit
exception rather than returning a host reference result.
"""

import hashlib
import os
from pathlib import Path
from typing import Any

import numpy as np

from .abi import POLYNOMIAL_BYTES, N, reference_negacyclic_product, validate_polynomial

BACKEND_LABEL = "m33-dr0:silicon"
OUTPUT_SENTINEL = -(1 << 31)

KERNEL_REL_PATH = "phoenix_sdr_dsp/pqc/kernels/m33_product_graph.cc"
ARITHMETIC_REL_PATH = "phoenix_sdr_dsp/pqc/kernels/m33a_arithmetic.hpp"

_PROGRAM: Any | None = None


class NativeBackendUnavailable(RuntimeError):
    """The only DR0 backend, native IRON/XRT on Phoenix, is unavailable."""


def check_emulation_and_redirection_excluded() -> None:
    """Fail closed if XCL_EMULATION_MODE or runtime redirection variables are set."""
    emulation_mode = os.environ.get("XCL_EMULATION_MODE")
    if emulation_mode and emulation_mode.strip():
        raise NativeBackendUnavailable(
            f"Physical silicon execution rejected: XCL_EMULATION_MODE={emulation_mode!r} is set. "
            "Hardware ground truth forbids simulation or emulation backends."
        )


def get_kernel_artifact_info(repo_root: Path | None = None) -> dict[str, Any]:
    """Return verified path and SHA-256 digest of the DR0 AIE2 kernel source."""
    root = repo_root or Path(__file__).resolve().parents[2]
    kernel_path = root / KERNEL_REL_PATH
    if not kernel_path.is_file():
        raise FileNotFoundError(f"Kernel source file not found: {kernel_path}")
    data = kernel_path.read_bytes()
    return {
        "path": KERNEL_REL_PATH,
        "size_bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest().lower(),
    }


def _load_iron() -> tuple[Any, ...]:
    """Load native dependencies lazily and never install a numerical fallback."""
    check_emulation_and_redirection_excluded()
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
    check_emulation_and_redirection_excluded()
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
    "ARITHMETIC_REL_PATH",
    "BACKEND_LABEL",
    "KERNEL_REL_PATH",
    "OUTPUT_SENTINEL",
    "POLYNOMIAL_BYTES",
    "NativeBackendUnavailable",
    "check_emulation_and_redirection_excluded",
    "get_kernel_artifact_info",
    "reference_negacyclic_product",
    "require_hardware_runtime",
    "run",
    "run_m33_product",
]
