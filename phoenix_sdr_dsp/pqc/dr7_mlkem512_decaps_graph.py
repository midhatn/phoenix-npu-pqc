# SPDX-License-Identifier: Apache-2.0
"""DR7 terminal-only, six-worker ML-KEM-512 ML-KEM.Decaps graph.

All five transition records are private ObjectFIFO payloads with independent
fixed layouts across Phoenix AIE tiles.
"""

from pathlib import Path
from typing import Any

import numpy as np

from . import dr7_mlkem512_decaps_abi as abi

BACKEND_LABEL = "dr7-mlkem512-decaps:silicon"
_PROGRAM: Any | None = None


class NativeBackendUnavailable(RuntimeError):
    """The native IRON/XRT DR7 backend is unavailable or failed closed."""


def _clear_host_staging(array: np.ndarray, tensor: Any | None) -> None:
    """Best-effort clear host private ingress and a distinct exposed tensor backing."""
    array.fill(0)
    backing = getattr(tensor, "_data", None)
    if backing is array:
        return
    if isinstance(backing, np.ndarray):
        backing.fill(0)
    elif isinstance(backing, memoryview) and not backing.readonly:
        backing[:] = b"\x00" * backing.nbytes
    elif isinstance(backing, bytearray):
        backing[:] = b"\x00" * len(backing)


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
            "DR7 requires MLIR-AIE/IRON 1.4.1, XRT, and an XRT-visible Phoenix "
            "NPU; no host ML-KEM.Decaps, decryption, or reference fallback is available."
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
    """Check native dependencies without creating a result or a fallback."""
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
    def dr7_mlkem512_decaps_program(
        req_in: In,
        descriptor_in: In,
        result_out: Out,
        *,
        req_slots: CompileTime[int],
        descriptor_slots: CompileTime[int],
        deriv_token_slots: CompileTime[int],
        noise_token_slots: CompileTime[int],
        col0_token_slots: CompileTime[int],
        u0_token_slots: CompileTime[int],
        col1_token_slots: CompileTime[int],
        result_slots: CompileTime[int],
        element_type: CompileTime[type],
    ):
        req_ty = np.ndarray[(req_slots,), np.dtype[element_type]]
        descriptor_ty = np.ndarray[(descriptor_slots,), np.dtype[element_type]]
        deriv_token_ty = np.ndarray[(deriv_token_slots,), np.dtype[element_type]]
        noise_token_ty = np.ndarray[(noise_token_slots,), np.dtype[element_type]]
        col0_token_ty = np.ndarray[(col0_token_slots,), np.dtype[element_type]]
        u0_token_ty = np.ndarray[(u0_token_slots,), np.dtype[element_type]]
        col1_token_ty = np.ndarray[(col1_token_slots,), np.dtype[element_type]]
        result_ty = np.ndarray[(result_slots,), np.dtype[element_type]]

        of_req = ObjectFifo(req_ty, name="dr7_req")
        of_descriptor = ObjectFifo(descriptor_ty, name="dr7_descriptor")
        of_deriv = ObjectFifo(deriv_token_ty, name="dr7_deriv_token")
        of_noise = ObjectFifo(noise_token_ty, name="dr7_noise_token")
        of_col0 = ObjectFifo(col0_token_ty, name="dr7_col0_token")
        of_u0 = ObjectFifo(u0_token_ty, name="dr7_u0_token")
        of_col1 = ObjectFifo(col1_token_ty, name="dr7_col1_token")
        of_result = ObjectFifo(result_ty, name="dr7_result")
        kernel_path = Path(__file__).resolve().parent / "kernels"

        def external(name: str, filename: str, arg_types: list[Any]) -> Any:
            return ExternalFunction(
                name,
                source_file=str(kernel_path / filename),
                arg_types=arg_types,
                include_dirs=[cxx_header_path(), str(kernel_path)],
            )

        decrypt = external(
            "dr7_mlkem512_decaps_decrypt",
            "dr7_mlkem512_decaps_decrypt.cc",
            [req_ty, descriptor_ty, deriv_token_ty],
        )
        noise = external(
            "dr7_mlkem512_decaps_noise",
            "dr7_mlkem512_decaps_noise.cc",
            [deriv_token_ty, noise_token_ty],
        )
        row0_expand = external(
            "dr7_mlkem512_decaps_row0_expand",
            "dr7_mlkem512_decaps_row0_expand.cc",
            [noise_token_ty, col0_token_ty],
        )
        row0_accumulate = external(
            "dr7_mlkem512_decaps_row0_accumulate",
            "dr7_mlkem512_decaps_row0_accumulate.cc",
            [col0_token_ty, u0_token_ty],
        )
        row1_expand = external(
            "dr7_mlkem512_decaps_row1_expand",
            "dr7_mlkem512_decaps_row1_expand.cc",
            [u0_token_ty, col1_token_ty],
        )
        finalize = external(
            "dr7_mlkem512_decaps_finalize",
            "dr7_mlkem512_decaps_finalize.cc",
            [col1_token_ty, result_ty],
        )

        def decrypt_body(of_req, of_descriptor, of_deriv, decrypt):
            req, descriptor, token = (
                of_req.acquire(1),
                of_descriptor.acquire(1),
                of_deriv.acquire(1),
            )
            decrypt(req, descriptor, token)
            of_deriv.release(1)
            of_req.release(1)
            of_descriptor.release(1)

        def unary_body(of_in, of_out, kernel):
            source, token = of_in.acquire(1), of_out.acquire(1)
            kernel(source, token)
            of_out.release(1)
            of_in.release(1)

        def finalize_body(of_final, of_result, finalize):
            token, result = of_final.acquire(1), of_result.acquire(1)
            finalize(token, result)
            of_result.release(1)
            of_final.release(1)

        workers = [
            Worker(
                decrypt_body,
                fn_args=[
                    of_req.cons(),
                    of_descriptor.cons(),
                    of_deriv.prod(),
                    decrypt,
                ],
                stack_size=0x2000,
            ),
            Worker(
                unary_body,
                fn_args=[of_deriv.cons(), of_noise.prod(), noise],
                stack_size=0x2000,
            ),
            Worker(
                unary_body,
                fn_args=[of_noise.cons(), of_col0.prod(), row0_expand],
                stack_size=0x2000,
            ),
            Worker(
                unary_body,
                fn_args=[of_col0.cons(), of_u0.prod(), row0_accumulate],
                stack_size=0x2000,
            ),
            Worker(
                unary_body,
                fn_args=[of_u0.cons(), of_col1.prod(), row1_expand],
                stack_size=0x2000,
            ),
            Worker(
                finalize_body,
                fn_args=[of_col1.cons(), of_result.prod(), finalize],
                stack_size=0x2000,
            ),
        ]

        def sequence(req, descriptor, result, req_prod, descriptor_prod, result_cons):
            req_prod.fill(req)
            descriptor_prod.fill(descriptor)
            result_cons.drain(result, wait=True)

        runtime = Runtime(
            sequence,
            [
                req_ty,
                descriptor_ty,
                result_ty,
                of_req.prod(),
                of_descriptor.prod(),
                of_result.cons(),
            ],
        )
        return Program(
            iron.get_current_device(), runtime, workers=workers
        ).resolve_program()

    _PROGRAM = dr7_mlkem512_decaps_program
    return _PROGRAM


def run_mlkem512_decaps(
    dk: bytes | bytearray | memoryview,
    c: bytes | bytearray | memoryview,
    request_id: int = 1,
) -> bytes:
    """Return device-produced byte-exact K (32 B) or fail closed."""
    descriptor_bytes, req_bytes = abi.validate_request(dk, c, request_id)
    req_np = np.frombuffer(req_bytes, dtype=np.uint8).copy()
    descriptor_np = np.frombuffer(descriptor_bytes, dtype=np.uint8).copy()
    result_np = np.zeros(abi.RESULT_BYTES, dtype=np.uint8)
    req_t = descriptor_t = result_t = None
    try:
        try:
            *_, XRTTensor = _load_iron()
            req_t = XRTTensor(req_np, dtype=np.uint8)
            descriptor_t = XRTTensor(descriptor_np, dtype=np.uint8)
            result_t = XRTTensor(result_np, dtype=np.uint8)
            _program()(
                req_t,
                descriptor_t,
                result_t,
                req_slots=abi.REQUEST_PAYLOAD_BYTES,
                descriptor_slots=abi.DESCRIPTOR_BYTES,
                deriv_token_slots=abi.DERIVATION_TOKEN_BYTES,
                noise_token_slots=abi.NOISE_TOKEN_BYTES,
                col0_token_slots=abi.COL0_TOKEN_BYTES,
                u0_token_slots=abi.U0_TOKEN_BYTES,
                col1_token_slots=abi.COL1_TOKEN_BYTES,
                result_slots=abi.RESULT_BYTES,
                element_type=np.uint8,
            )
            result_t.to("cpu")
        except Exception as exc:
            raise NativeBackendUnavailable(
                "DR7 native MLIR-AIE dispatch failed; no ML-KEM.Decaps fallback ran."
            ) from exc
        finally:
            _clear_host_staging(req_np, req_t)
            _clear_host_staging(descriptor_np, descriptor_t)
        try:
            return abi.unpack_result(result_t._data[: abi.RESULT_BYTES], request_id)
        except Exception as exc:
            raise NativeBackendUnavailable(
                "DR7 terminal result failed ABI validation; refusing malformed keys."
            ) from exc
    finally:
        _clear_host_staging(result_np, result_t)


run = run_mlkem512_decaps
__all__ = [
    "BACKEND_LABEL",
    "NativeBackendUnavailable",
    "require_hardware_runtime",
    "run",
    "run_mlkem512_decaps",
]
