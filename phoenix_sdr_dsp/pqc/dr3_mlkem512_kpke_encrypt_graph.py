"""DR3 terminal-only, five-worker ML-KEM-512 K-PKE.Encrypt graph.

All four transition records are private ObjectFIFO payloads.
They carry complete encryption state across the AIE2 array with zero host intervention.
"""

from pathlib import Path
from typing import Any

import numpy as np

from . import dr3_mlkem512_kpke_encrypt_abi as abi

BACKEND_LABEL = "dr3-mlkem512-kpke-encrypt:silicon"
_PROGRAM: Any | None = None


class NativeBackendUnavailable(RuntimeError):
    """The native IRON/XRT DR3 backend is unavailable or failed closed."""


def _clear_host_staging(array: np.ndarray, tensor: Any | None) -> None:
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
            "DR3 requires MLIR-AIE/IRON 1.4.1, XRT, and an XRT-visible Phoenix "
            "NPU; no host K-PKE.Encrypt or reference fallback is available."
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
    def dr3_mlkem512_kpke_encrypt_program(
        request_in: In,
        descriptor_in: In,
        result_out: Out,
        *,
        request_slots: CompileTime[int],
        descriptor_slots: CompileTime[int],
        noise_token_slots: CompileTime[int],
        col0_token_slots: CompileTime[int],
        u0_token_slots: CompileTime[int],
        col1_token_slots: CompileTime[int],
        result_slots: CompileTime[int],
        element_type: CompileTime[type],
    ):
        request_ty = np.ndarray[(request_slots,), np.dtype[element_type]]
        descriptor_ty = np.ndarray[(descriptor_slots,), np.dtype[element_type]]
        noise_token_ty = np.ndarray[(noise_token_slots,), np.dtype[element_type]]
        col0_token_ty = np.ndarray[(col0_token_slots,), np.dtype[element_type]]
        u0_token_ty = np.ndarray[(u0_token_slots,), np.dtype[element_type]]
        col1_token_ty = np.ndarray[(col1_token_slots,), np.dtype[element_type]]
        result_ty = np.ndarray[(result_slots,), np.dtype[element_type]]

        of_request = ObjectFifo(request_ty, name="dr3_request")
        of_descriptor = ObjectFifo(descriptor_ty, name="dr3_descriptor")
        of_noise = ObjectFifo(noise_token_ty, name="dr3_noise_token")
        of_col0 = ObjectFifo(col0_token_ty, name="dr3_col0_token")
        of_u0 = ObjectFifo(u0_token_ty, name="dr3_u0_token")
        of_col1 = ObjectFifo(col1_token_ty, name="dr3_col1_token")
        of_result = ObjectFifo(result_ty, name="dr3_result")

        kernel_path = Path(__file__).resolve().parent / "kernels"

        def external(name: str, filename: str, arg_types: list[Any]) -> Any:
            return ExternalFunction(
                name,
                source_file=str(kernel_path / filename),
                arg_types=arg_types,
                include_dirs=[cxx_header_path(), str(kernel_path)],
            )

        noise_kernel = external(
            "dr3_mlkem512_kpke_encrypt_noise",
            "dr3_mlkem512_kpke_encrypt_noise.cc",
            [request_ty, descriptor_ty, noise_token_ty],
        )
        col0_expand = external(
            "dr3_mlkem512_kpke_encrypt_col0_expand",
            "dr3_mlkem512_kpke_encrypt_col0_expand.cc",
            [noise_token_ty, col0_token_ty],
        )
        u0_accumulate = external(
            "dr3_mlkem512_kpke_encrypt_u0_accumulate",
            "dr3_mlkem512_kpke_encrypt_u0_accumulate.cc",
            [col0_token_ty, u0_token_ty],
        )
        col1_expand = external(
            "dr3_mlkem512_kpke_encrypt_col1_expand",
            "dr3_mlkem512_kpke_encrypt_col1_expand.cc",
            [u0_token_ty, col1_token_ty],
        )
        serialize_kernel = external(
            "dr3_mlkem512_kpke_encrypt_u1_v_serialize",
            "dr3_mlkem512_kpke_encrypt_u1_v_serialize.cc",
            [col1_token_ty, result_ty],
        )

        def noise_body(of_request, of_descriptor, of_noise, noise_kernel):
            request, descriptor, noise = (
                of_request.acquire(1),
                of_descriptor.acquire(1),
                of_noise.acquire(1),
            )
            noise_kernel(request, descriptor, noise)
            of_noise.release(1)
            of_descriptor.release(1)
            of_request.release(1)

        def unary_body(of_in, of_out, kernel):
            source, target = of_in.acquire(1), of_out.acquire(1)
            kernel(source, target)
            of_out.release(1)
            of_in.release(1)

        workers = [
            Worker(
                noise_body,
                fn_args=[
                    of_request.cons(),
                    of_descriptor.cons(),
                    of_noise.prod(),
                    noise_kernel,
                ],
                stack_size=0x1000,
            ),
            Worker(
                unary_body,
                fn_args=[of_noise.cons(), of_col0.prod(), col0_expand],
                stack_size=0x1000,
            ),
            Worker(
                unary_body,
                fn_args=[of_col0.cons(), of_u0.prod(), u0_accumulate],
                stack_size=0x1000,
            ),
            Worker(
                unary_body,
                fn_args=[of_u0.cons(), of_col1.prod(), col1_expand],
                stack_size=0x1000,
            ),
            Worker(
                unary_body,
                fn_args=[of_col1.cons(), of_result.prod(), serialize_kernel],
                stack_size=0x1000,
            ),
        ]

        def sequence(request, descriptor, result, request_prod, descriptor_prod, result_cons):
            request_prod.fill(request)
            descriptor_prod.fill(descriptor)
            result_cons.drain(result, wait=True)

        runtime = Runtime(
            sequence,
            [
                request_ty,
                descriptor_ty,
                result_ty,
                of_request.prod(),
                of_descriptor.prod(),
                of_result.cons(),
            ],
        )
        return Program(
            iron.get_current_device(), runtime, workers=workers
        ).resolve_program()

    _PROGRAM = dr3_mlkem512_kpke_encrypt_program
    return _PROGRAM


def run_hardware_kpke_encrypt(
    ek: bytes,
    m: bytes,
    r: bytes,
    *,
    request_id: int = 1,
) -> bytes:
    """Execute complete ML-KEM-512 K-PKE.Encrypt on Phoenix NPU hardware."""
    *_, XRTTensor = _load_iron()
    descriptor, request = abi.validate_request(ek, m, r, request_id)

    request_arr = np.frombuffer(request, dtype=np.uint8).copy()
    descriptor_arr = np.frombuffer(descriptor, dtype=np.uint8).copy()
    result_arr = np.zeros(abi.RESULT_BYTES, dtype=np.uint8)

    req_t = desc_t = res_t = None
    try:
        try:
            req_t = XRTTensor(request_arr, dtype=np.uint8)
            desc_t = XRTTensor(descriptor_arr, dtype=np.uint8)
            res_t = XRTTensor(result_arr, dtype=np.uint8)

            _program()(
                req_t,
                desc_t,
                res_t,
                request_slots=abi.REQUEST_PAYLOAD_BYTES,
                descriptor_slots=abi.DESCRIPTOR_BYTES,
                noise_token_slots=3632,
                col0_token_slots=4656,
                u0_token_slots=3440,
                col1_token_slots=4464,
                result_slots=abi.RESULT_BYTES,
                element_type=np.uint8,
            )
            res_t.to("cpu")
        except Exception as exc:
            raise NativeBackendUnavailable(
                "DR3 native MLIR-AIE dispatch failed; no K-PKE.Encrypt fallback ran."
            ) from exc
        finally:
            _clear_host_staging(request_arr, req_t)
            _clear_host_staging(descriptor_arr, desc_t)

        return abi.unpack_result(res_t._data[: abi.RESULT_BYTES], expected_request_id=request_id)
    finally:
        _clear_host_staging(result_arr, res_t)


run = run_hardware_kpke_encrypt
__all__ = [
    "BACKEND_LABEL",
    "NativeBackendUnavailable",
    "require_hardware_runtime",
    "run",
    "run_hardware_kpke_encrypt",
]
