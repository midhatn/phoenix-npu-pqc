# SPDX-License-Identifier: Apache-2.0
"""
Milestone DR18: NIST SP 800-56C Dual-Key Combiner Graph on AMD Phoenix AIE2.
100% On-Device Extraction-then-Expansion inside Tile (3,2).
"""

from pathlib import Path
from typing import Any, Tuple
import numpy as np
import uuid

from . import dr18_dual_key_combiner_abi as abi

BACKEND_LABEL = "dr18-dual-key-combiner:silicon"
_PROGRAM: Any | None = None

REQ_BYTES = 256
DESCRIPTOR_BYTES = 64
RESULT_BYTES = 128

class NativeBackendUnavailable(RuntimeError):
    """The native IRON/XRT DR18 backend is unavailable."""

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
            "DR18 requires MLIR-AIE/IRON 1.4.1, XRT, and an XRT-visible Phoenix NPU."
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
    def dr18_program(
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

        of_request = ObjectFifo(request_ty, name="dr18_comb_request")
        of_descriptor = ObjectFifo(descriptor_ty, name="dr18_comb_descriptor")
        of_result = ObjectFifo(result_ty, name="dr18_comb_result")

        kernel_path = Path(__file__).resolve().parent / "kernels"
        dr18_fn = ExternalFunction(
            "dr18_dual_key_combiner_service",
            source_file=str(kernel_path / "dr18_dual_key_combiner_service.cc"),
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
            fn_args=[of_request.cons(), of_descriptor.cons(), of_result.prod(), dr18_fn],
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

    _PROGRAM = dr18_program
    return _PROGRAM

def combine_keys_on_aie2(
    k_qkd: bytes,
    k_pqc: bytes,
    key_id: uuid.UUID,
    epoch: int = 1,
    out_len: int = 32,
    custom_label: bytes = abi.CUSTOMIZATION_STRING
) -> Tuple[bytes, float]:
    """Execute NIST SP 800-56C extraction on physical Phoenix NPU silicon."""
    *_, XRTTensor = _load_iron()
    import time
    t0 = time.time()

    combiner_input = abi.pack_combiner_input(k_qkd, k_pqc, key_id, epoch, custom_label)
    msg_len = len(combiner_input)

    req_buf = bytearray(REQ_BYTES)
    req_buf[0:min(msg_len, REQ_BYTES)] = combiner_input[:REQ_BYTES]

    desc_buf = bytearray(DESCRIPTOR_BYTES)
    desc_buf[0:4] = abi.MAGIC_DESC_DR18
    desc_buf[4:8] = int(1).to_bytes(4, "little")
    desc_buf[8:12] = epoch.to_bytes(4, "little")
    desc_buf[12:14] = msg_len.to_bytes(2, "little")
    desc_buf[14:16] = out_len.to_bytes(2, "little")

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

    k_final = raw_output[20 : 20 + out_len]
    dt = (time.time() - t0) * 1000
    return k_final, dt
