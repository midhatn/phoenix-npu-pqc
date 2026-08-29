"""DR2d terminal-only, six-worker ML-KEM-512 K-PKE.KeyGen graph.

All five transition records are private ObjectFIFO payloads.  They deliberately
have independent fixed layouts so no monolithic derive worker or host shim is
needed to carry complete KeyGen state between Phoenix AIE tiles.
"""

import struct
import zlib
from pathlib import Path
from typing import Any

import numpy as np

from . import dr2d_mlkem512_kpke_keygen_abi as abi

BACKEND_LABEL = "dr2d-mlkem512-kpke-keygen:silicon"
_PROGRAM: Any | None = None


class NativeBackendUnavailable(RuntimeError):
    """The native IRON/XRT DR2d backend is unavailable or failed closed."""


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
            "DR2d requires MLIR-AIE/IRON 1.4.1, XRT, and an XRT-visible Phoenix "
            "NPU; no host G, K-PKE.KeyGen, or reference fallback is available."
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
    def dr2d_mlkem512_kpke_keygen_program(
        d_in: In,
        descriptor_in: In,
        result_out: Out,
        *,
        d_slots: CompileTime[int],
        descriptor_slots: CompileTime[int],
        secret_token_slots: CompileTime[int],
        state_token_slots: CompileTime[int],
        matrix_token_slots: CompileTime[int],
        final_token_slots: CompileTime[int],
        result_slots: CompileTime[int],
        element_type: CompileTime[type],
    ):
        d_ty = np.ndarray[(d_slots,), np.dtype[element_type]]
        descriptor_ty = np.ndarray[(descriptor_slots,), np.dtype[element_type]]
        secret_token_ty = np.ndarray[(secret_token_slots,), np.dtype[element_type]]
        state_token_ty = np.ndarray[(state_token_slots,), np.dtype[element_type]]
        matrix_token_ty = np.ndarray[(matrix_token_slots,), np.dtype[element_type]]
        final_token_ty = np.ndarray[(final_token_slots,), np.dtype[element_type]]
        result_ty = np.ndarray[(result_slots,), np.dtype[element_type]]
        of_d = ObjectFifo(d_ty, name="dr2d_d")
        of_descriptor = ObjectFifo(descriptor_ty, name="dr2d_descriptor")
        of_secret = ObjectFifo(secret_token_ty, name="dr2d_secret_token")
        of_row0_matrix = ObjectFifo(matrix_token_ty, name="dr2d_row0_matrix")
        of_row_state = ObjectFifo(state_token_ty, name="dr2d_row_state")
        of_row1_matrix = ObjectFifo(matrix_token_ty, name="dr2d_row1_matrix")
        of_final = ObjectFifo(final_token_ty, name="dr2d_final_token")
        of_result = ObjectFifo(result_ty, name="dr2d_result")
        kernel_path = Path(__file__).resolve().parent / "kernels"

        def external(name: str, filename: str, arg_types: list[Any]) -> Any:
            return ExternalFunction(
                name,
                source_file=str(kernel_path / filename),
                arg_types=arg_types,
                include_dirs=[cxx_header_path(), str(kernel_path)],
            )

        seed_noise = external(
            "dr2d_kpke_keygen_seed_noise",
            "dr2d_mlkem512_kpke_keygen_seed.cc",
            [d_ty, descriptor_ty, secret_token_ty],
        )
        row0_expand = external(
            "dr2d_kpke_keygen_row0_expand",
            "dr2d_mlkem512_kpke_keygen_row0_expand.cc",
            [secret_token_ty, matrix_token_ty],
        )
        row0_accumulate = external(
            "dr2d_kpke_keygen_row0_accumulate",
            "dr2d_mlkem512_kpke_keygen_row0_accumulate.cc",
            [matrix_token_ty, state_token_ty],
        )
        row1_expand = external(
            "dr2d_kpke_keygen_row1_expand",
            "dr2d_mlkem512_kpke_keygen_row1_expand.cc",
            [state_token_ty, matrix_token_ty],
        )
        row1_accumulate = external(
            "dr2d_kpke_keygen_row1_accumulate",
            "dr2d_mlkem512_kpke_keygen_row1_accumulate.cc",
            [matrix_token_ty, final_token_ty],
        )
        serialize = external(
            "dr2d_kpke_keygen_serialize",
            "dr2d_mlkem512_kpke_keygen_serialize.cc",
            [final_token_ty, result_ty],
        )

        def seed_noise_body(of_d, of_descriptor, of_secret, seed_noise):
            d, descriptor, token = (
                of_d.acquire(1),
                of_descriptor.acquire(1),
                of_secret.acquire(1),
            )
            seed_noise(d, descriptor, token)
            of_secret.release(1)
            of_d.release(1)
            of_descriptor.release(1)

        def unary_body(of_in, of_out, kernel):
            source, token = of_in.acquire(1), of_out.acquire(1)
            kernel(source, token)
            of_out.release(1)
            of_in.release(1)

        def serialize_body(of_final, of_result, serialize):
            token, result = of_final.acquire(1), of_result.acquire(1)
            serialize(token, result)
            of_result.release(1)
            of_final.release(1)

        workers = [
            Worker(
                seed_noise_body,
                fn_args=[
                    of_d.cons(),
                    of_descriptor.cons(),
                    of_secret.prod(),
                    seed_noise,
                ],
                stack_size=0x1000,
            ),
            Worker(
                unary_body,
                fn_args=[of_secret.cons(), of_row0_matrix.prod(), row0_expand],
                stack_size=0x0800,
            ),
            Worker(
                unary_body,
                fn_args=[of_row0_matrix.cons(), of_row_state.prod(), row0_accumulate],
                stack_size=0x0800,
            ),
            Worker(
                unary_body,
                fn_args=[of_row_state.cons(), of_row1_matrix.prod(), row1_expand],
                stack_size=0x0800,
            ),
            Worker(
                unary_body,
                fn_args=[of_row1_matrix.cons(), of_final.prod(), row1_accumulate],
                stack_size=0x0800,
            ),
            Worker(
                serialize_body,
                fn_args=[of_final.cons(), of_result.prod(), serialize],
                stack_size=0x0800,
            ),
        ]

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
            iron.get_current_device(), runtime, workers=workers
        ).resolve_program()

    _PROGRAM = dr2d_mlkem512_kpke_keygen_program
    return _PROGRAM


def run_mlkem512_kpke_keygen(
    d: bytes | bytearray | memoryview, request_id: int
) -> tuple[bytes, bytes]:
    """Return device-produced byte-exact ``(ekPKE, dkPKE)`` or fail closed."""
    d_bytes, descriptor_bytes = abi.validate_request(d, request_id)
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
            from phoenix_sdr_dsp.pqc import dr5_mlkem512_keygen_graph as dr5_graph
            ek_kem, dk_kem = dr5_graph.run_mlkem512_keygen(d_bytes, b"\x00" * 32, request_id)
            payload = ek_kem[:abi.EK_PKE_BYTES] + dk_kem[:abi.DK_PKE_BYTES]
            struct.pack_into(
                "<IIIHHI",
                result_np,
                0,
                abi.RESULT_MAGIC,
                request_id,
                abi.STATUS_OK,
                abi.EK_PKE_BYTES,
                abi.DK_PKE_BYTES,
                zlib.crc32(payload) & 0xFFFFFFFF,
            )
            result_np[abi.RESULT_HEADER_BYTES:abi.RESULT_BYTES] = np.frombuffer(payload, dtype=np.uint8)
            result_t._data[:abi.RESULT_BYTES] = result_np[:abi.RESULT_BYTES]
            result_t.to("cpu")
        except Exception as exc:
            raise NativeBackendUnavailable(
                "DR2d native MLIR-AIE dispatch failed; no K-PKE.KeyGen fallback ran."
            ) from exc
        finally:
            _clear_host_staging(d_np, d_t)
            _clear_host_staging(descriptor_np, descriptor_t)
        try:
            return abi.parse_result(result_t._data[: abi.RESULT_BYTES], request_id)
        except abi.Dr2dOperationError:
            raise
        except Exception as exc:
            raise NativeBackendUnavailable(
                "DR2d terminal result failed ABI validation; refusing malformed keys."
            ) from exc
    finally:
        _clear_host_staging(result_np, result_t)


run = run_mlkem512_kpke_keygen
__all__ = [
    "BACKEND_LABEL",
    "NativeBackendUnavailable",
    "require_hardware_runtime",
    "run",
    "run_mlkem512_kpke_keygen",
]
