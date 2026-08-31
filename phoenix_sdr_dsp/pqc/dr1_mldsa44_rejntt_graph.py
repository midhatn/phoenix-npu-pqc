"""DR1: fixed ML-DSA-44 ExpandA SHAKE128/RejNTT device graph.

The public request has exactly two host ingress transfers (rho and descriptor),
one device-local 180-byte ObjectFIFO between the two workers, and one terminal
result transfer.  There is deliberately no host SHAKE, sampler, or fallback
implementation in this production module.
"""

import hashlib
import os
from pathlib import Path
from typing import Any

import numpy as np

from . import dr1_abi as abi

BACKEND_LABEL = "dr1-mldsa44-expanda-rejntt:silicon"
KERNEL_REL_PATH = "phoenix_sdr_dsp/pqc/kernels/dr1_mldsa44_rejntt.cc"
SERVICE_REL_PATH = "phoenix_sdr_dsp/pqc/kernels/dr1_shake128_service.cc"
_PROGRAM: Any | None = None


class NativeBackendUnavailable(RuntimeError):
    """The native IRON/XRT DR1 backend is unavailable or failed closed."""


def check_emulation_and_redirection_excluded() -> None:
    """Fail closed if XCL_EMULATION_MODE or XRT_INI_PATH runtime redirection variables are set."""
    emulation_mode = os.environ.get("XCL_EMULATION_MODE")
    if emulation_mode and emulation_mode.strip():
        raise NativeBackendUnavailable(
            f"Physical silicon execution rejected: XCL_EMULATION_MODE={emulation_mode!r} is set. "
            "Hardware ground truth forbids simulation or emulation backends."
        )
    xrt_ini = os.environ.get("XRT_INI_PATH")
    if xrt_ini and xrt_ini.strip():
        raise NativeBackendUnavailable(
            f"Physical silicon execution rejected: XRT_INI_PATH={xrt_ini!r} is set. "
            "Hardware ground truth forbids custom runtime configuration redirection."
        )


def get_kernel_artifact_info(repo_root: Path | None = None) -> dict[str, Any]:
    """Return verified path and SHA-256 digest of the DR1 AIE2 kernel source."""
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
    """Load native dependencies lazily, after all public inputs are checked."""
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
            "DR1 requires MLIR-AIE/IRON 1.4.1, XRT, and an XRT-visible Phoenix NPU; "
            "no host SHAKE or rejection-sampling fallback is available."
        ) from exc
    return (
        iron, CompileTime, ExternalFunction, In, ObjectFifo, Out, Program, Runtime,
        Worker, cxx_header_path, XRTTensor,
    )


def require_hardware_runtime() -> None:
    """Check native dependencies without creating an output or fallback result."""
    _load_iron()


def _program() -> Any:
    """Build the fixed two-worker DR1 topology once per Python process."""
    global _PROGRAM
    if _PROGRAM is not None:
        return _PROGRAM

    (
        iron, CompileTime, ExternalFunction, In, ObjectFifo, Out, Program, Runtime,
        Worker, cxx_header_path, _,
    ) = _load_iron()

    @iron.jit
    def dr1_mldsa44_program(
        rho_in: In,
        descriptor_in: In,
        result_out: Out,
        *,
        rho_slots: CompileTime[int],
        descriptor_slots: CompileTime[int],
        xof_block_slots: CompileTime[int],
        result_slots: CompileTime[int],
        element_type: CompileTime[type],
    ):
        rho_ty = np.ndarray[(rho_slots,), np.dtype[element_type]]
        descriptor_ty = np.ndarray[(descriptor_slots,), np.dtype[element_type]]
        xof_block_ty = np.ndarray[(xof_block_slots,), np.dtype[element_type]]
        result_ty = np.ndarray[(result_slots,), np.dtype[element_type]]

        # Exactly two host ingress FIFOs, one internal Keccak-to-sampler FIFO,
        # and one terminal result FIFO.  The toolchain owns the internal FIFO
        # placement/depth decision; no third host DMA channel is introduced.
        of_rho = ObjectFifo(rho_ty, name="dr1_rho")
        of_descriptor = ObjectFifo(descriptor_ty, name="dr1_descriptor")
        of_xof_block = ObjectFifo(xof_block_ty, name="dr1_xof_block")
        of_result = ObjectFifo(result_ty, name="dr1_result")

        kernel_path = Path(__file__).resolve().parent / "kernels"
        # One declaration per source is essential: physical IRON compilation
        # compiled repeated source_file declarations into separate objects and
        # hit duplicate exported-symbol errors.  Each entry point is instead
        # called eight times and retains state inside its one worker.
        emit_next = ExternalFunction(
            "dr1_shake128_emit_next",
            source_file=str(kernel_path / "dr1_shake128_service.cc"),
            arg_types=[rho_ty, descriptor_ty, xof_block_ty],
            include_dirs=[cxx_header_path(), str(kernel_path)],
        )
        consume_next = ExternalFunction(
            "dr1_rejntt_consume_next",
            source_file=str(kernel_path / "dr1_mldsa44_rejntt.cc"),
            arg_types=[xof_block_ty, result_ty],
            include_dirs=[cxx_header_path(), str(kernel_path)],
        )

        def keccak_body(of_rho, of_descriptor, of_xof_block, emit_next):
            rho = of_rho.acquire(1)
            descriptor = of_descriptor.acquire(1)
            for _ in range(abi.BLOCK_CAP):
                xof_block = of_xof_block.acquire(1)
                emit_next(rho, descriptor, xof_block)
                of_xof_block.release(1)
            of_rho.release(1)
            of_descriptor.release(1)

        def sampler_body(of_xof_block, of_result, consume_next):
            result = of_result.acquire(1)
            for _ in range(abi.BLOCK_CAP):
                xof_block = of_xof_block.acquire(1)
                consume_next(xof_block, result)
                of_xof_block.release(1)
            of_result.release(1)

        keccak_worker = Worker(
            keccak_body,
            fn_args=[of_rho.cons(), of_descriptor.cons(), of_xof_block.prod(), emit_next],
            stack_size=0x4000,
        )
        sampler_worker = Worker(
            sampler_body,
            fn_args=[of_xof_block.cons(), of_result.prod(), consume_next],
            stack_size=0x4000,
        )

        def sequence(rho, descriptor, result, rho_prod, descriptor_prod, result_cons):
            rho_prod.fill(rho)
            descriptor_prod.fill(descriptor)
            result_cons.drain(result, wait=True)

        runtime = Runtime(
            sequence,
            [rho_ty, descriptor_ty, result_ty, of_rho.prod(), of_descriptor.prod(), of_result.cons()],
        )
        return Program(
            iron.get_current_device(), runtime, workers=[keccak_worker, sampler_worker]
        ).resolve_program()

    _PROGRAM = dr1_mldsa44_program
    return _PROGRAM


def run_mldsa44_expanda_rejntt(
    rho: bytes | bytearray | memoryview, j: int, i: int, request_id: int
) -> list[int]:
    """Return one native ML-DSA-44 ``ExpandA`` polynomial or fail closed.

    The device consumes SHAKE128(rho || j || i) incrementally and drains all
    eight scheduled blocks even after 256 accepted coefficients have frozen.
    A defined device error, malformed terminal record, absent NPU runtime, or
    dispatch failure never triggers a Python/reference replacement calculation.
    """
    rho_bytes, descriptor_bytes = abi.validate_request(rho, j, i, request_id)
    rho_np = np.frombuffer(rho_bytes, dtype=np.uint8).copy()
    descriptor_np = np.frombuffer(descriptor_bytes, dtype=np.uint8).copy()
    result_np = np.frombuffer(abi.result_sentinel(), dtype=np.uint8).copy()

    *_, XRTTensor = _load_iron()
    rho_t = XRTTensor(rho_np, dtype=np.uint8)
    descriptor_t = XRTTensor(descriptor_np, dtype=np.uint8)
    result_t = XRTTensor(result_np, dtype=np.uint8)
    try:
        _program()(
            rho_t,
            descriptor_t,
            result_t,
            rho_slots=abi.RHO_BYTES,
            descriptor_slots=abi.DESCRIPTOR_BYTES,
            xof_block_slots=abi.XOF_BLOCK_BYTES,
            result_slots=abi.RESULT_BYTES,
            element_type=np.uint8,
        )
        result_t.to("cpu")  # DR1's one and only host-visible result transfer.
    except Exception as exc:
        raise NativeBackendUnavailable(
            "DR1 native MLIR-AIE dispatch failed; no SHAKE/reference fallback was used."
        ) from exc

    try:
        return abi.parse_result(result_t._data[:abi.RESULT_BYTES], request_id)
    except abi.Dr1OperationError:
        raise
    except Exception as exc:
        raise NativeBackendUnavailable(
            "DR1 terminal result failed ABI validation; refusing an incomplete or malformed polynomial."
        ) from exc


run = run_mldsa44_expanda_rejntt

__all__ = [
    "BACKEND_LABEL",
    "KERNEL_REL_PATH",
    "SERVICE_REL_PATH",
    "NativeBackendUnavailable",
    "check_emulation_and_redirection_excluded",
    "get_kernel_artifact_info",
    "require_hardware_runtime",
    "run",
    "run_mldsa44_expanda_rejntt",
]
