"""Diagnostic-only DR2d final-token and serializer discriminator.

This artifact is intentionally separate from the production six-worker graph.
It accepts the same two public records, emits one deterministic canonical final
token for the pinned case-1 request ID, and consumes it with the unchanged
production serializer. It is not a KeyGen implementation or a fallback.
"""

from pathlib import Path
from typing import Any

import numpy as np

from . import dr2d_mlkem512_kpke_keygen_abi as abi

BACKEND_LABEL = "dr2d-mlkem512-kpke-keygen:terminal-probe:diagnostic-only"
DIAGNOSTIC_CASE1_REQUEST_ID = 0xD2D00001
_PROGRAM: Any | None = None


class NativeBackendUnavailable(RuntimeError):
    """The native IRON/XRT terminal-probe path is unavailable or failed closed."""


def _clear_host_staging(array: np.ndarray, tensor: Any | None) -> None:
    array.fill(0)
    backing = getattr(tensor, "_data", None)
    if backing is array:
        return
    if isinstance(backing, np.ndarray):
        backing.fill(0)
    elif isinstance(backing, memoryview) and not backing.readonly:
        backing[:] = b"\0" * backing.nbytes
    elif isinstance(backing, bytearray):
        backing[:] = b"\0" * len(backing)


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
    except Exception as exc:
        raise NativeBackendUnavailable(
            "The DR2d terminal probe requires MLIR-AIE/IRON 1.4.1, XRT, and "
            "an XRT-visible Phoenix NPU; no host probe replacement exists."
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
    """Check the native diagnostic dependencies without making a result."""
    _load_iron()


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
    def dr2d_mlkem512_kpke_keygen_terminal_probe_program(
        d_in: In,
        descriptor_in: In,
        result_out: Out,
        *,
        d_slots: CompileTime[int],
        descriptor_slots: CompileTime[int],
        final_token_slots: CompileTime[int],
        result_slots: CompileTime[int],
        element_type: CompileTime[type],
    ):
        d_ty = np.ndarray[(d_slots,), np.dtype[element_type]]
        descriptor_ty = np.ndarray[(descriptor_slots,), np.dtype[element_type]]
        final_token_ty = np.ndarray[(final_token_slots,), np.dtype[element_type]]
        result_ty = np.ndarray[(result_slots,), np.dtype[element_type]]
        of_d = ObjectFifo(d_ty, name="dr2d_probe_d")
        of_descriptor = ObjectFifo(descriptor_ty, name="dr2d_probe_descriptor")
        of_final = ObjectFifo(final_token_ty, name="dr2d_probe_final_token")
        of_result = ObjectFifo(result_ty, name="dr2d_probe_result")
        kernel_path = Path(__file__).resolve().parent / "kernels"
        probe = ExternalFunction(
            "dr2d_kpke_keygen_terminal_probe",
            source_file=str(
                kernel_path / "dr2d_mlkem512_kpke_keygen_terminal_probe.cc"
            ),
            arg_types=[d_ty, descriptor_ty, final_token_ty],
            include_dirs=[cxx_header_path(), str(kernel_path)],
        )
        serialize = ExternalFunction(
            "dr2d_kpke_keygen_serialize",
            source_file=str(kernel_path / "dr2d_mlkem512_kpke_keygen_serialize.cc"),
            arg_types=[final_token_ty, result_ty],
            include_dirs=[cxx_header_path(), str(kernel_path)],
        )

        def probe_body(of_d, of_descriptor, of_final, probe):
            d, descriptor, final_token = (
                of_d.acquire(1),
                of_descriptor.acquire(1),
                of_final.acquire(1),
            )
            probe(d, descriptor, final_token)
            of_final.release(1)
            of_d.release(1)
            of_descriptor.release(1)

        def serialize_body(of_final, of_result, serialize):
            final_token, result = of_final.acquire(1), of_result.acquire(1)
            serialize(final_token, result)
            of_result.release(1)
            of_final.release(1)

        probe_worker = Worker(
            probe_body,
            fn_args=[of_d.cons(), of_descriptor.cons(), of_final.prod(), probe],
            stack_size=0x0800,
        )
        serialize_worker = Worker(
            serialize_body,
            fn_args=[of_final.cons(), of_result.prod(), serialize],
            stack_size=0x0800,
        )

        def sequence(d, descriptor, result, d_prod, descriptor_prod, result_cons):
            d_prod.fill(d)
            descriptor_prod.fill(descriptor)
            result_cons.drain(result, wait=True)

        runtime = Runtime(
            sequence,
            [
                d_ty,
                descriptor_ty,
                result_ty,
                of_d.prod(),
                of_descriptor.prod(),
                of_result.cons(),
            ],
        )
        return Program(
            iron.get_current_device(), runtime, workers=[probe_worker, serialize_worker]
        ).resolve_program()

    _PROGRAM = dr2d_mlkem512_kpke_keygen_terminal_probe_program
    return _PROGRAM


def run_case1_terminal_probe_record(
    d: bytes | bytearray | memoryview, request_id: int
) -> bytes:
    """Return the complete diagnostic terminal record after fail-closed validation."""
    d_bytes, descriptor_bytes = abi.validate_request(d, request_id)
    if request_id != DIAGNOSTIC_CASE1_REQUEST_ID:
        raise abi.Dr2dAbiError(
            "the diagnostic terminal probe accepts only the pinned case-1 request ID"
        )
    d_np = np.frombuffer(d_bytes, dtype=np.uint8).copy()
    descriptor_np = np.frombuffer(descriptor_bytes, dtype=np.uint8).copy()
    result_np = np.frombuffer(abi.result_sentinel(), dtype=np.uint8).copy()
    d_t = descriptor_t = result_t = None
    try:
        try:
            *_, XRTTensor = _load_iron()
            d_t = XRTTensor(d_np, dtype=np.uint8)
            descriptor_t = XRTTensor(descriptor_np, dtype=np.uint8)
            result_t = XRTTensor(result_np, dtype=np.uint8)
            _program()(
                d_t,
                descriptor_t,
                result_t,
                d_slots=abi.D_BYTES,
                descriptor_slots=abi.DESCRIPTOR_BYTES,
                final_token_slots=abi.PRIVATE_TOKEN_BYTES,
                result_slots=abi.RESULT_BYTES,
                element_type=np.uint8,
            )
            result_t.to("cpu")
        except Exception as exc:
            raise NativeBackendUnavailable(
                "DR2d terminal-probe native dispatch failed; no replacement ran."
            ) from exc
        finally:
            _clear_host_staging(d_np, d_t)
            _clear_host_staging(descriptor_np, descriptor_t)
        try:
            record = bytes(result_t._data[: abi.RESULT_BYTES])
            abi.parse_result(record, request_id)
            return record
        except abi.Dr2dOperationError:
            raise
        except Exception as exc:
            raise NativeBackendUnavailable(
                "DR2d terminal-probe result failed ABI validation."
            ) from exc
    finally:
        _clear_host_staging(d_np, d_t)
        _clear_host_staging(descriptor_np, descriptor_t)
        _clear_host_staging(result_np, result_t)


def run_case1_terminal_probe(
    d: bytes | bytearray | memoryview, request_id: int
) -> tuple[bytes, bytes]:
    """Run only the diagnostic case-1 terminal probe; never run a fallback."""
    return abi.parse_result(run_case1_terminal_probe_record(d, request_id), request_id)


__all__ = [
    "BACKEND_LABEL",
    "DIAGNOSTIC_CASE1_REQUEST_ID",
    "NativeBackendUnavailable",
    "require_hardware_runtime",
    "run_case1_terminal_probe",
    "run_case1_terminal_probe_record",
]
