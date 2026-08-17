"""DR2a: fixed ML-KEM-512 SHAKE128/SampleNTT device graph.

The public request performs exactly two ingress transfers (rho and descriptor),
passes five SHAKE128 rate tokens through one device-local ObjectFIFO, and drains
one terminal result.  No host SHAKE, partial polynomial, or fallback exists.
"""

from pathlib import Path
from typing import Any

import numpy as np

from . import dr2_mlkem512_samplentt_abi as abi

BACKEND_LABEL = "dr2a-mlkem512-samplentt:silicon"
_PROGRAM: Any | None = None


class NativeBackendUnavailable(RuntimeError):
    """The native IRON/XRT DR2a backend is unavailable or failed closed."""


def _load_iron() -> tuple[Any, ...]:
    """Load native dependencies lazily, after public inputs are checked."""
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
            "DR2a requires MLIR-AIE/IRON 1.4.1, XRT, and an XRT-visible Phoenix "
            "NPU; no host SHAKE or SampleNTT fallback is available."
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
    """Check native dependencies without creating an output or fallback result."""
    _load_iron()


def _program() -> Any:
    """Build the fixed two-worker DR2a topology once per Python process."""
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
    def dr2a_mlkem512_program(
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

        of_rho = ObjectFifo(rho_ty, name="dr2a_rho")
        of_descriptor = ObjectFifo(descriptor_ty, name="dr2a_descriptor")
        of_xof_block = ObjectFifo(xof_block_ty, name="dr2a_xof_block")
        of_result = ObjectFifo(result_ty, name="dr2a_result")

        kernel_path = Path(__file__).resolve().parent / "kernels"
        emit_next = ExternalFunction(
            "dr2a_shake128_emit_next",
            source_file=str(kernel_path / "dr2_mlkem512_shake128_service.cc"),
            arg_types=[rho_ty, descriptor_ty, xof_block_ty],
            include_dirs=[cxx_header_path(), str(kernel_path)],
        )
        consume_next = ExternalFunction(
            "dr2a_samplentt_consume_next",
            source_file=str(kernel_path / "dr2_mlkem512_samplentt.cc"),
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
            fn_args=[
                of_rho.cons(),
                of_descriptor.cons(),
                of_xof_block.prod(),
                emit_next,
            ],
            stack_size=0x4000,
        )
        sampler_worker = Worker(
            sampler_body,
            fn_args=[of_xof_block.cons(), of_result.prod(), consume_next],
            stack_size=0x4000,
        )

        def sequence(
            rho, descriptor, result, rho_prod, descriptor_prod, result_cons
        ):
            rho_prod.fill(rho)
            descriptor_prod.fill(descriptor)
            result_cons.drain(result, wait=True)

        runtime = Runtime(
            sequence,
            [
                rho_ty,
                descriptor_ty,
                result_ty,
                of_rho.prod(),
                of_descriptor.prod(),
                of_result.cons(),
            ],
        )
        return Program(
            iron.get_current_device(), runtime, workers=[keccak_worker, sampler_worker]
        ).resolve_program()

    _PROGRAM = dr2a_mlkem512_program
    return _PROGRAM


def run_mlkem512_samplentt(
    rho: bytes | bytearray | memoryview, j: int, i: int, request_id: int
) -> list[int]:
    """Return one complete native ML-KEM-512 matrix polynomial or fail closed."""
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
        result_t.to("cpu")  # The one and only DR2a host-visible output transfer.
    except Exception as exc:
        raise NativeBackendUnavailable(
            "DR2a native MLIR-AIE dispatch failed; no SHAKE/reference fallback ran."
        ) from exc

    try:
        return abi.parse_result(result_t._data[: abi.RESULT_BYTES], request_id)
    except abi.Dr2aOperationError:
        raise
    except Exception as exc:
        raise NativeBackendUnavailable(
            "DR2a terminal result failed ABI validation; refusing a partial or "
            "malformed polynomial."
        ) from exc


run = run_mlkem512_samplentt

__all__ = [
    "BACKEND_LABEL",
    "NativeBackendUnavailable",
    "require_hardware_runtime",
    "run",
    "run_mlkem512_samplentt",
]
