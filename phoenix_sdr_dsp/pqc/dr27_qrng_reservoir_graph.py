# SPDX-License-Identifier: Apache-2.0
"""
Milestone DR27: QRNG-OPENAPI Ingress & NPU-Resident Token-Bucket Key/Entropy Reservoir on AMD Phoenix NPU (AIE2).
100% Device-Resident Entropy Management with Hysteresis & SP 800-90B Preflight Enforcement.
"""

from pathlib import Path
from typing import Any, Tuple, Dict, Optional
import numpy as np

from . import dr27_qrng_openapi_abi as abi

BACKEND_LABEL = "dr27-qrng-reservoir:silicon"
_PROGRAM: Any | None = None

REQ_BYTES = abi.REQ_BYTES
DESCRIPTOR_BYTES = abi.DESCRIPTOR_BYTES
RESULT_BYTES = abi.RESULT_BYTES

class NativeBackendUnavailable(RuntimeError):
    """The native IRON/XRT DR27 backend is unavailable or failed closed."""

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
            "DR27 requires MLIR-AIE/IRON 1.4.1, XRT, and an XRT-visible Phoenix NPU."
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
    def dr27_program(
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

        of_request = ObjectFifo(request_ty, name="dr27_qrng_request")
        of_descriptor = ObjectFifo(descriptor_ty, name="dr27_qrng_descriptor")
        of_result = ObjectFifo(result_ty, name="dr27_qrng_result")

        kernel_path = Path(__file__).resolve().parent / "kernels"
        dr27_fn = ExternalFunction(
            "dr27_qrng_reservoir_service",
            source_file=str(kernel_path / "dr27_qrng_reservoir_service.cc"),
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
            fn_args=[of_request.cons(), of_descriptor.cons(), of_result.prod(), dr27_fn],
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
            iron.get_current_device(),
            runtime,
            workers=[worker],
        ).resolve_program()

    _PROGRAM = dr27_program
    return _PROGRAM

def execute_dr27_op_on_silicon(
    op_code: int,
    entropy_bytes: bytes = b"",
    req_id: int = 1,
    source_id: int = 1,
    rct_val: int = 1,
    apt_val: int = 1
) -> Dict[str, Any]:
    """Executes a DR27 operation on physical AMD Phoenix AIE2 silicon."""
    *_, XRTTensor = _load_iron()

    req_buf = bytearray(REQ_BYTES)
    if entropy_bytes:
        copy_len = min(len(entropy_bytes), REQ_BYTES)
        req_buf[:copy_len] = entropy_bytes[:copy_len]

    desc_buf = abi.pack_descriptor(
        req_id=req_id,
        op_code=op_code,
        entropy_len=len(entropy_bytes),
        source_id=source_id,
        rct_val=rct_val,
        apt_val=apt_val
    )

    req_tensor = XRTTensor(np.frombuffer(req_buf, dtype=np.uint8), dtype=np.uint8)
    desc_tensor = XRTTensor(np.frombuffer(desc_buf, dtype=np.uint8), dtype=np.uint8)
    res_tensor = XRTTensor(np.zeros(RESULT_BYTES, dtype=np.uint8), dtype=np.uint8)

    prog = _program()
    try:
        prog(
            req_tensor,
            desc_tensor,
            res_tensor,
            request_slots=REQ_BYTES,
            descriptor_slots=DESCRIPTOR_BYTES,
            result_slots=RESULT_BYTES,
            element_type=np.uint8,
        )
        res_tensor.to("cpu")
        res_data = bytes(res_tensor._data)
        return abi.unpack_result(res_data)
    finally:
        _clear_host_staging(req_buf, req_tensor)
        _clear_host_staging(bytearray(DESCRIPTOR_BYTES), desc_tensor)

def ingress_entropy(entropy_bytes: bytes, source_id: int = 1, req_id: int = 1) -> Dict[str, Any]:
    """Evaluates SP 800-90B preflight health and ingresses entropy block into AIE2 reservoir."""
    is_healthy, max_rct, max_apt = abi.eval_sp800_90b_health(entropy_bytes)
    return execute_dr27_op_on_silicon(
        op_code=abi.OP_INGRESS,
        entropy_bytes=entropy_bytes,
        req_id=req_id,
        source_id=source_id,
        rct_val=max_rct,
        apt_val=max_apt
    )

def drain_entropy(req_id: int = 1) -> Tuple[bytes, Dict[str, Any]]:
    """Drains a 32-byte entropy block from AIE2 reservoir."""
    res = execute_dr27_op_on_silicon(op_code=abi.OP_DRAIN, req_id=req_id)
    return res["payload"], res

def get_reservoir_telemetry() -> Dict[str, Any]:
    """Retrieves current on-chip reservoir telemetry and hysteresis mode."""
    return execute_dr27_op_on_silicon(op_code=abi.OP_STATUS)

def zeroize_reservoir() -> Dict[str, Any]:
    """Triggers complete hardware memory wipe of on-chip reservoir."""
    return execute_dr27_op_on_silicon(op_code=abi.OP_ZEROIZE)
