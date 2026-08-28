# SPDX-License-Identifier: Apache-2.0
"""DR4 terminal-only, two-worker ML-KEM-512 K-PKE.Decrypt graph."""

from pathlib import Path
from typing import Any

import numpy as np

from . import dr4_mlkem512_kpke_decrypt_abi as abi

BACKEND_LABEL = "dr4-mlkem512-kpke-decrypt:silicon"
_PROGRAM: Any | None = None


class NativeBackendUnavailable(RuntimeError):
    """The native IRON/XRT DR4 backend is unavailable or failed closed."""


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
            "DR4 requires MLIR-AIE/IRON 1.4.1, XRT, and an XRT-visible Phoenix "
            "NPU; no host K-PKE.Decrypt or reference fallback is available."
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
    def dr4_mlkem512_kpke_decrypt_program(
        request_in: In,
        descriptor_in: In,
        result_out: Out,
        *,
        request_slots: CompileTime[int],
        descriptor_slots: CompileTime[int],
        decompress_token_slots: CompileTime[int],
        result_slots: CompileTime[int],
        element_type: CompileTime[type],
    ):
        request_ty = np.ndarray[(request_slots,), np.dtype[element_type]]
        descriptor_ty = np.ndarray[(descriptor_slots,), np.dtype[element_type]]
        decompress_token_ty = np.ndarray[(decompress_token_slots,), np.dtype[element_type]]
        result_ty = np.ndarray[(result_slots,), np.dtype[element_type]]

        of_request = ObjectFifo(request_ty, name="dr4_request")
        of_descriptor = ObjectFifo(descriptor_ty, name="dr4_descriptor")
        of_decompress = ObjectFifo(decompress_token_ty, name="dr4_decompress_token")
        of_result = ObjectFifo(result_ty, name="dr4_result")

        kernel_path = Path(__file__).resolve().parent / "kernels"

        def external(name: str, filename: str, arg_types: list[Any]) -> Any:
            return ExternalFunction(
                name,
                source_file=str(kernel_path / filename),
                arg_types=arg_types,
                include_dirs=[cxx_header_path(), str(kernel_path)],
            )

        decompress_kernel = external(
            "dr4_decompress_ntt",
            "dr4_mlkem512_kpke_decrypt_decompress_ntt.cc",
            [request_ty, descriptor_ty, decompress_token_ty],
        )
        accumulate_kernel = external(
            "dr4_accumulate_serialize",
            "dr4_mlkem512_kpke_decrypt_accumulate_serialize.cc",
            [decompress_token_ty, result_ty],
        )

        def decompress_body(of_req, of_desc, of_decomp, kernel):
            req = of_req.acquire(1)
            desc = of_desc.acquire(1)
            decomp = of_decomp.acquire(1)
            kernel(req, desc, decomp)
            of_decomp.release(1)
            of_req.release(1)
            of_desc.release(1)

        def accumulate_body(of_decomp, of_res, kernel):
            decomp = of_decomp.acquire(1)
            res = of_res.acquire(1)
            kernel(decomp, res)
            of_decomp.release(1)
            of_res.release(1)

        workers = [
            Worker(
                decompress_body,
                fn_args=[
                    of_request.cons(),
                    of_descriptor.cons(),
                    of_decompress.prod(),
                    decompress_kernel,
                ],
                stack_size=0x4000,
            ),
            Worker(
                accumulate_body,
                fn_args=[
                    of_decompress.cons(),
                    of_result.prod(),
                    accumulate_kernel,
                ],
                stack_size=0x4000,
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

    _PROGRAM = dr4_mlkem512_kpke_decrypt_program
    return _PROGRAM


def run_hardware_kpke_decrypt(
    dk_pke: bytes,
    c: bytes,
    *,
    request_id: int = 1,
) -> bytes:
    """Execute complete ML-KEM-512 K-PKE.Decrypt on Phoenix NPU hardware."""
    *_, XRTTensor = _load_iron()
    descriptor, request = abi.validate_request(dk_pke, c, request_id)

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
                decompress_token_slots=abi.DECOMPRESS_TOKEN_BYTES,
                result_slots=abi.RESULT_BYTES,
                element_type=np.uint8,
            )
            res_t.to("cpu")
        except Exception as exc:
            raise NativeBackendUnavailable(
                f"DR4 hardware execution failed: {exc}"
            ) from exc
        finally:
            _clear_host_staging(request_arr, req_t)
            _clear_host_staging(descriptor_arr, desc_t)

        return abi.unpack_result(res_t._data[: abi.RESULT_BYTES], expected_request_id=request_id)
    finally:
        _clear_host_staging(result_arr, res_t)
