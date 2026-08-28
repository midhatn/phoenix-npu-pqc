# SPDX-License-Identifier: Apache-2.0
"""DR8 ML-KEM-768 KeyGen dataflow graph on AMD Phoenix NPU (Ryzen 7040 / 8040 AIE2)."""
from pathlib import Path
from typing import Any
import numpy as np

BACKEND_LABEL = "dr8-mlkem768-keygen:silicon"
_PROGRAM: Any | None = None

REQ_BYTES = 64
DESCRIPTOR_BYTES = 16
TOKEN_BYTES = 3152
RESULT_BYTES = 3616

class NativeBackendUnavailable(RuntimeError):
    """The native IRON/XRT DR8 backend is unavailable or failed closed."""

def _clear_host_staging(array: np.ndarray, tensor: Any | None) -> None:
    array.fill(0)
    backing = getattr(tensor, "_data", None)
    if backing is array: return
    if isinstance(backing, np.ndarray): backing.fill(0)
    elif isinstance(backing, memoryview) and not backing.readonly: backing[:] = b"\x00" * backing.nbytes
    elif isinstance(backing, bytearray): backing[:] = b"\x00" * len(backing)

def _load_iron() -> tuple[Any, ...]:
    try:
        from aie import iron
        from aie.iron import (
            CompileTime, ExternalFunction, In, ObjectFifo, Out, Program, Runtime, Worker
        )
        from aie.utils.config import cxx_header_path
        from aie.utils.hostruntime.xrtruntime.tensor import XRTTensor
    except Exception as exc:
        raise NativeBackendUnavailable("DR8 requires MLIR-AIE/IRON 1.4.1, XRT, and Phoenix NPU") from exc
    return (
        iron, CompileTime, ExternalFunction, In, ObjectFifo, Out, Program, Runtime, Worker, cxx_header_path, XRTTensor
    )

def _program() -> Any:
    global _PROGRAM
    if _PROGRAM is not None:
        return _PROGRAM
    (
        iron, CompileTime, ExternalFunction, In, ObjectFifo, Out, Program, Runtime, Worker, cxx_header_path, _
    ) = _load_iron()

    @iron.jit
    def dr8_mlkem768_keygen_program(
        req_in: In,
        descriptor_in: In,
        result_out: Out,
        *,
        req_slots: CompileTime[int],
        descriptor_slots: CompileTime[int],
        token_slots: CompileTime[int],
        result_slots: CompileTime[int],
        element_type: CompileTime[type],
    ):
        req_ty = np.ndarray[(req_slots,), np.dtype[element_type]]
        descriptor_ty = np.ndarray[(descriptor_slots,), np.dtype[element_type]]
        token_ty = np.ndarray[(token_slots,), np.dtype[element_type]]
        result_ty = np.ndarray[(result_slots,), np.dtype[element_type]]

        of_req = ObjectFifo(req_ty, name="dr8_kg_req")
        of_descriptor = ObjectFifo(descriptor_ty, name="dr8_kg_descriptor")
        of_t0 = ObjectFifo(token_ty, name="dr8_kg_t0")
        of_t1 = ObjectFifo(token_ty, name="dr8_kg_t1")
        of_t2 = ObjectFifo(token_ty, name="dr8_kg_t2")
        of_t3 = ObjectFifo(token_ty, name="dr8_kg_t3")
        of_result = ObjectFifo(result_ty, name="dr8_kg_result")

        kernel_path = Path(__file__).resolve().parent / "kernels"

        def external(name: str, filename: str, arg_types: list[Any]) -> Any:
            return ExternalFunction(
                name,
                source_file=str(kernel_path / filename),
                arg_types=arg_types,
                include_dirs=[cxx_header_path(), str(kernel_path)],
            )

        fn_noise = external("dr8_mlkem768_keygen_noise", "dr8_mlkem768_keygen_noise.cc", [req_ty, descriptor_ty, token_ty])
        fn_row0 = external("dr8_mlkem768_keygen_row0", "dr8_mlkem768_keygen_row0.cc", [token_ty, token_ty])
        fn_row1 = external("dr8_mlkem768_keygen_row1", "dr8_mlkem768_keygen_row1.cc", [token_ty, token_ty])
        fn_row2 = external("dr8_mlkem768_keygen_row2", "dr8_mlkem768_keygen_row2.cc", [token_ty, token_ty])
        fn_final = external("dr8_mlkem768_keygen_finalize", "dr8_mlkem768_keygen_finalize.cc", [token_ty, result_ty])

        def noise_body(req_cons, desc_cons, out_prod, kernel):
            req_elem = req_cons.acquire(1)
            desc_elem = desc_cons.acquire(1)
            out_elem = out_prod.acquire(1)
            kernel(req_elem, desc_elem, out_elem)
            req_cons.release(1)
            desc_cons.release(1)
            out_prod.release(1)

        def unary_body(in_cons, out_prod, kernel):
            in_elem = in_cons.acquire(1)
            out_elem = out_prod.acquire(1)
            kernel(in_elem, out_elem)
            in_cons.release(1)
            out_prod.release(1)

        workers = [
            Worker(noise_body, fn_args=[of_req.cons(), of_descriptor.cons(), of_t0.prod(), fn_noise], stack_size=0x2000),
            Worker(unary_body, fn_args=[of_t0.cons(), of_t1.prod(), fn_row0], stack_size=0x2000),
            Worker(unary_body, fn_args=[of_t1.cons(), of_t2.prod(), fn_row1], stack_size=0x2000),
            Worker(unary_body, fn_args=[of_t2.cons(), of_t3.prod(), fn_row2], stack_size=0x2000),
            Worker(unary_body, fn_args=[of_t3.cons(), of_result.prod(), fn_final], stack_size=0x2000),
        ]

        def sequence(req, descriptor, result, req_prod, descriptor_prod, result_cons):
            req_prod.fill(req)
            descriptor_prod.fill(descriptor)
            result_cons.drain(result, wait=True)

        runtime = Runtime(
            sequence,
            [
                req_ty, descriptor_ty, result_ty,
                of_req.prod(), of_descriptor.prod(), of_result.cons()
            ]
        )
        return Program(iron.get_current_device(), runtime, workers=workers).resolve_program()

    _PROGRAM = dr8_mlkem768_keygen_program
    return _PROGRAM

def run_mlkem768_keygen(d: bytes, z: bytes, req_id: int = 1):
    req_buf = bytearray(REQ_BYTES)
    req_buf[:32] = d
    req_buf[32:64] = z

    desc_buf = bytearray(DESCRIPTOR_BYTES)
    desc_buf[0:3] = b"\x01\x71\x52"
    desc_buf[4] = 0x04 # ML-KEM-768
    desc_buf[5] = 0x01 # KeyGen
    desc_buf[6] = 0x08 # DR8
    desc_buf[8:12] = req_id.to_bytes(4, "little")

    req_np = np.frombuffer(req_buf, dtype=np.uint8).copy()
    descriptor_np = np.frombuffer(desc_buf, dtype=np.uint8).copy()
    result_np = np.zeros(RESULT_BYTES, dtype=np.uint8)

    *_, XRTTensor = _load_iron()
    req_t = XRTTensor(req_np, dtype=np.uint8)
    descriptor_t = XRTTensor(descriptor_np, dtype=np.uint8)
    result_t = XRTTensor(result_np, dtype=np.uint8)

    try:
        _program()(
            req_t, descriptor_t, result_t,
            req_slots=REQ_BYTES,
            descriptor_slots=DESCRIPTOR_BYTES,
            token_slots=TOKEN_BYTES,
            result_slots=RESULT_BYTES,
            element_type=np.uint8,
        )
        result_t.to("cpu")
    finally:
        _clear_host_staging(req_np, req_t)
        _clear_host_staging(descriptor_np, descriptor_t)

    res_bytes = bytes(result_t._data[:RESULT_BYTES])
    _clear_host_staging(result_np, result_t)

    status = int.from_bytes(res_bytes[8:12], "little")
    if status != 0:
        raise RuntimeError(f"ML-KEM-768 KeyGen failed on silicon with status {status}")
    ek = res_bytes[32 : 32 + 1184]
    dk = res_bytes[1216 : 1216 + 2400]
    return ek, dk
