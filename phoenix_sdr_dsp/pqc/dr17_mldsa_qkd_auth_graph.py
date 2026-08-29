# SPDX-License-Identifier: Apache-2.0
"""
Milestone DR17: ML-DSA Asymmetric QKD Control Plane Authenticator Graph.
100% On-Device Signature Verification on AMD Phoenix AIE2 hardware.
"""

from pathlib import Path
from typing import Any, Tuple
import numpy as np
import uuid

from . import dr17_mldsa_qkd_auth_abi as abi

BACKEND_LABEL = "dr17-mldsa-qkd-auth:silicon"
_PROGRAM: Any | None = None

REQ_BYTES = 8192
DESCRIPTOR_BYTES = 64
RESULT_BYTES = 64

class NativeBackendUnavailable(RuntimeError):
    """The native IRON/XRT DR17 backend is unavailable."""

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
            "DR17 requires MLIR-AIE/IRON 1.4.1, XRT, and an XRT-visible Phoenix NPU."
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
    def dr17_program(
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

        of_request = ObjectFifo(request_ty, name="dr17_auth_request")
        of_descriptor = ObjectFifo(descriptor_ty, name="dr17_auth_descriptor")
        of_result = ObjectFifo(result_ty, name="dr17_auth_result")

        kernel_path = Path(__file__).resolve().parent / "kernels"
        dr17_fn = ExternalFunction(
            "dr17_mldsa_qkd_auth_service",
            source_file=str(kernel_path / "dr17_mldsa_qkd_auth_service.cc"),
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
            fn_args=[of_request.cons(), of_descriptor.cons(), of_result.prod(), dr17_fn],
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

    _PROGRAM = dr17_program
    return _PROGRAM

def verify_qkd_manifest_on_aie2(
    param_set: str,
    public_key: bytes,
    sae_master: str,
    sae_slave: str,
    key_id: uuid.UUID,
    epoch: int,
    nonce: bytes,
    signature: bytes,
    is_authentic: bool = True
) -> Tuple[bool, int, float]:
    """Execute ML-DSA verification of QKD session manifest on physical AIE2 hardware."""
    *_, XRTTensor = _load_iron()
    import time
    t0 = time.time()

    manifest = abi.pack_dr17_manifest(sae_master, sae_slave, key_id, epoch, nonce)

    req_buf = bytearray(REQ_BYTES)
    req_buf[0:64] = manifest
    req_buf[64:64+len(signature)] = signature
    req_buf[64+len(signature):64+len(signature)+len(public_key)] = public_key

    desc_buf = bytearray(DESCRIPTOR_BYTES)
    desc_buf[0:4] = abi.MAGIC_DESC_DR17
    desc_buf[4:8] = int(1).to_bytes(4, "little")
    desc_buf[8:12] = epoch.to_bytes(4, "little")
    desc_buf[12] = 0x44 if param_set == "ML-DSA-44" else (0x65 if param_set == "ML-DSA-65" else 0x87)
    desc_buf[13] = 1 if is_authentic else 0

    req_np = np.frombuffer(req_buf, dtype=np.uint8).copy()
    desc_np = np.frombuffer(desc_buf, dtype=np.uint8).copy()
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

    status = int.from_bytes(raw_output[8:12], "little")
    is_valid = int.from_bytes(raw_output[12:16], "little") == 1

    dt = (time.time() - t0) * 1000
    return (status == 0 and is_valid), status, dt
