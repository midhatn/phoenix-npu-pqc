# SPDX-License-Identifier: Apache-2.0
"""
Milestone DR19: Full-Duplex Hybrid QKD-PQC Session Orchestrator Graph.
100% On-Device Execution across AIE2 tile matrix on AMD Phoenix NPU.
"""

import time
import uuid
import numpy as np
from pathlib import Path
from typing import Any, NamedTuple, Tuple

from . import dr16_etsi_qkd014_abi as dr16_abi
from . import dr17_mldsa_qkd_auth_abi as dr17_abi
from . import dr18_dual_key_combiner_abi as dr18_abi

BACKEND_LABEL = "dr19-hybrid-session:silicon"
_PROGRAM: Any | None = None

REQ_BYTES = 256
DESCRIPTOR_BYTES = 64
RESULT_BYTES = 128
MAGIC_DESC_DR19 = b"\x01\x71\x52\x13"

class NativeBackendUnavailable(RuntimeError):
    """The native IRON/XRT DR19 backend is unavailable."""

class HybridSessionResult(NamedTuple):
    session_id: uuid.UUID
    k_final_master: bytes
    k_final_slave: bytes
    is_authenticated: bool
    is_key_matched: bool
    total_latency_ms: float
    zeroized_status: int

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
            "DR19 requires MLIR-AIE/IRON 1.4.1, XRT, and an XRT-visible Phoenix NPU."
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
    def dr19_program(
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

        of_request = ObjectFifo(request_ty, name="dr19_sess_request")
        of_descriptor = ObjectFifo(descriptor_ty, name="dr19_sess_descriptor")
        of_result = ObjectFifo(result_ty, name="dr19_sess_result")

        kernel_path = Path(__file__).resolve().parent / "kernels"
        dr19_fn = ExternalFunction(
            "dr19_hybrid_session_service",
            source_file=str(kernel_path / "dr19_hybrid_session_service.cc"),
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
            fn_args=[of_request.cons(), of_descriptor.cons(), of_result.prod(), dr19_fn],
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

    _PROGRAM = dr19_program
    return _PROGRAM

def run_hybrid_handshake_on_aie2(
    kem_param: str = "ML-KEM-512",
    dsa_param: str = "ML-DSA-44",
    epoch: int = 1000
) -> HybridSessionResult:
    """Execute complete dual-node Hybrid QKD + PQC handshake natively on physical AIE2 silicon."""
    *_, XRTTensor = _load_iron()
    t0 = time.time()
    session_key_id = uuid.uuid4()

    req_buf = bytearray(REQ_BYTES)
    # 0..31: QKD key
    req_buf[0:32] = bytes([(epoch * 7 + i) % 256 for i in range(32)])
    # 32..63: PQC key
    req_buf[32:64] = bytes([(epoch * 19 + i) % 256 for i in range(32)])
    # 64..79: UUID
    req_buf[64:80] = session_key_id.bytes
    # 80..91: Nonce
    req_buf[80:92] = bytes([0xAA] * 12)
    # 92..123: Challenge
    req_buf[92:124] = bytes([0x55] * 32)

    desc_buf = bytearray(DESCRIPTOR_BYTES)
    desc_buf[0:4] = MAGIC_DESC_DR19
    desc_buf[4:8] = int(1).to_bytes(4, "little")
    desc_buf[8:12] = epoch.to_bytes(4, "little")
    desc_buf[12] = 0x01 if kem_param == "ML-KEM-512" else (0x02 if kem_param == "ML-KEM-768" else 0x03)
    desc_buf[13] = 0x44 if dsa_param == "ML-DSA-44" else (0x65 if dsa_param == "ML-DSA-65" else 0x87)

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
    is_auth = int.from_bytes(raw_output[12:16], "little") == 1
    k_master = raw_output[24:56]
    k_slave = raw_output[56:88]

    dt = (time.time() - t0) * 1000
    is_matched = (k_master == k_slave) and (len(k_master) == 32) and (status == 0)

    return HybridSessionResult(
        session_id=session_key_id,
        k_final_master=k_master,
        k_final_slave=k_slave,
        is_authenticated=is_auth,
        is_key_matched=is_matched,
        total_latency_ms=dt,
        zeroized_status=status
    )
