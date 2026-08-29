# SPDX-License-Identifier: Apache-2.0
"""
Milestone DR16: ETSI GS QKD 014 Key Ingress Computational Graph on AMD Phoenix NPU (AIE2).
100% Device-Resident Ingress of Optical Quantum Key Streams without Host DDR Exposure.
"""

from pathlib import Path
from typing import Any, Tuple
import numpy as np

from . import dr16_etsi_qkd014_abi as abi

BACKEND_LABEL = "dr16-etsi-qkd014:silicon"
_PROGRAM: Any | None = None

REQ_BYTES = abi.REQ_BYTES
DESCRIPTOR_BYTES = abi.DESCRIPTOR_BYTES
RESULT_BYTES = abi.RESULT_BYTES

class NativeBackendUnavailable(RuntimeError):
    """The native IRON/XRT DR16 backend is unavailable or failed closed."""

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
            "DR16 requires MLIR-AIE/IRON 1.4.1, XRT, and an XRT-visible Phoenix NPU."
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

def _clear_host_staging(staging_array: np.ndarray, staging_tensor: Any | None = None) -> None:
    try:
        staging_array.fill(0)
    except Exception:
        pass
    if staging_tensor is not None:
        try:
            underlying = getattr(staging_tensor, "_data", None)
            if underlying is not None and hasattr(underlying, "fill"):
                underlying.fill(0)
        except Exception:
            pass

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
    def dr16_program(
        request_in: In,
        descriptor_in: In,
        result_out: Out,
        *,
        request_slots: CompileTime[int],
        descriptor_slots: CompileTime[int],
        result_slots: CompileTime[int],
        element_type: CompileTime[type],
    ):
        request_ty = np.ndarray[(request_slots,), np.dtype[element_type]]
        descriptor_ty = np.ndarray[(descriptor_slots,), np.dtype[element_type]]
        result_ty = np.ndarray[(result_slots,), np.dtype[element_type]]

        of_request = ObjectFifo(request_ty, name="dr16_qkd_request")
        of_descriptor = ObjectFifo(descriptor_ty, name="dr16_qkd_descriptor")
        of_result = ObjectFifo(result_ty, name="dr16_qkd_result")

        kernel_path = Path(__file__).resolve().parent / "kernels"
        dr16_fn = ExternalFunction(
            "dr16_etsi_qkd014_ingress_service",
            source_file=str(kernel_path / "dr16_etsi_qkd014_service.cc"),
            arg_types=[request_ty, descriptor_ty, result_ty],
            include_dirs=[cxx_header_path(), str(kernel_path)],
        )

        def worker_body(of_req, of_desc, of_res, fn):
            req = of_req.acquire(1)
            desc = of_desc.acquire(1)
            res = of_res.acquire(1)
            fn(req, desc, res)
            of_req.release(1)
            of_desc.release(1)
            of_res.release(1)

        worker = Worker(
            worker_body,
            fn_args=[of_request.cons(), of_descriptor.cons(), of_result.prod(), dr16_fn],
            stack_size=0x2000,
        )

        def sequence(req, desc, res, req_prod, desc_prod, res_cons):
            req_prod.fill(req)
            desc_prod.fill(desc)
            res_cons.drain(res, wait=True)

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
            iron.get_current_device(), runtime, workers=[worker]
        ).resolve_program()

    _PROGRAM = dr16_program
    return _PROGRAM

def run_dr16_ingress_service(req_bytes: bytes, desc_bytes: bytes) -> Tuple[int, int, int, int]:
    """Execute DR16 ETSI GS QKD 014 sealed ingress on physical AMD Phoenix NPU silicon."""
    *_, XRTTensor = _load_iron()

    req_np = np.frombuffer(req_bytes, dtype=np.uint8).copy()
    desc_np = np.frombuffer(desc_bytes, dtype=np.uint8).copy()
    res_np = np.zeros(RESULT_BYTES, dtype=np.uint8)

    req_t = XRTTensor(req_np, dtype=np.uint8)
    desc_t = XRTTensor(desc_np, dtype=np.uint8)
    res_t = XRTTensor(res_np, dtype=np.uint8)

    try:
        _program()(
            req_t, desc_t, res_t,
            request_slots=REQ_BYTES,
            descriptor_slots=DESCRIPTOR_BYTES,
            result_slots=RESULT_BYTES,
            element_type=np.uint8,
        )
        res_t.to("cpu")
    finally:
        _clear_host_staging(req_np, req_t)
        _clear_host_staging(desc_np, desc_t)

    raw_output = bytes(res_t._data[:RESULT_BYTES])
    _clear_host_staging(res_np, res_t)

    req_id, status, active_slot, crc32, _ = abi.unpack_dr16_result(raw_output)
    return req_id, status, active_slot, crc32
