# SPDX-License-Identifier: Apache-2.0
# DR14: Complete NIST FIPS 204 ML-DSA-65 Key Generation Graph.
# 100% On-Device Device-Resident ML-DSA-65 KeyGen on AMD Phoenix NPU (AIE2 / XDNA1).
import os
import sys
from pathlib import Path
from typing import Any
import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Sizes
REQ_BYTES = 32          # 32-byte seed (xi)
DESCRIPTOR_BYTES = 16
TOKEN0_BYTES = 12800    # noise output
TOKEN1_BYTES = 12160    # rows 0-1 output
TOKEN2_BYTES = 11588    # rows 2-3 output
TOKEN3_BYTES = 5892     # rows 4-5 output
RESULT_BYTES = 6008     # Header(20) + pk(1952) + sk(4032) + CRC32(4)

_CACHED_PROGRAM = None

def _load_iron():
    from aie import iron
    from aie.iron import (
        CompileTime, ExternalFunction, In, ObjectFifo, Out, Program, Runtime, Worker,
    )
    from aie.utils.config import cxx_header_path
    from aie.utils.hostruntime.xrtruntime.tensor import XRTTensor
    return iron, CompileTime, ExternalFunction, In, ObjectFifo, Out, Program, Runtime, Worker, cxx_header_path, XRTTensor

def _build_dr14_keygen_program():
    (
        iron, CompileTime, ExternalFunction, In, ObjectFifo, Out, Program, Runtime, Worker, cxx_header_path, _,
    ) = _load_iron()

    @iron.jit
    def dr14_keygen_pipeline(
        request_in: In,
        descriptor_in: In,
        result_out: Out,
        *,
        req_slots: CompileTime[int],
        descriptor_slots: CompileTime[int],
        token0_slots: CompileTime[int],
        token1_slots: CompileTime[int],
        token2_slots: CompileTime[int],
        token3_slots: CompileTime[int],
        result_slots: CompileTime[int],
        element_type: CompileTime[type],
    ):
        req_ty = np.ndarray[(req_slots,), np.dtype[element_type]]
        descriptor_ty = np.ndarray[(descriptor_slots,), np.dtype[element_type]]
        token0_ty = np.ndarray[(token0_slots,), np.dtype[element_type]]
        token1_ty = np.ndarray[(token1_slots,), np.dtype[element_type]]
        token2_ty = np.ndarray[(token2_slots,), np.dtype[element_type]]
        token3_ty = np.ndarray[(token3_slots,), np.dtype[element_type]]
        result_ty = np.ndarray[(result_slots,), np.dtype[element_type]]

        of_req = ObjectFifo(req_ty, name="dr14_kg_req")
        of_desc = ObjectFifo(descriptor_ty, name="dr14_kg_desc")
        of_t0 = ObjectFifo(token0_ty, name="dr14_kg_t0")
        of_t1 = ObjectFifo(token1_ty, name="dr14_kg_t1")
        of_t2 = ObjectFifo(token2_ty, name="dr14_kg_t2")
        of_t3 = ObjectFifo(token3_ty, name="dr14_kg_t3")
        of_res = ObjectFifo(result_ty, name="dr14_kg_res")

        kernel_path = Path(__file__).resolve().parent / "kernels"
        inc_dirs = [cxx_header_path(), str(kernel_path)]

        w0_fn = ExternalFunction("dr14_mldsa65_keygen_noise", source_file=str(kernel_path / "dr14_mldsa65_keygen_noise.cc"), arg_types=[req_ty, descriptor_ty, token0_ty], include_dirs=inc_dirs)
        w1_fn = ExternalFunction("dr14_mldsa65_keygen_row01", source_file=str(kernel_path / "dr14_mldsa65_keygen_rows.cc"), arg_types=[token0_ty, token1_ty], include_dirs=inc_dirs)
        w2_fn = ExternalFunction("dr14_mldsa65_keygen_row23", source_file=str(kernel_path / "dr14_mldsa65_keygen_rows.cc"), arg_types=[token1_ty, token2_ty], include_dirs=inc_dirs)
        w3_fn = ExternalFunction("dr14_mldsa65_keygen_row45", source_file=str(kernel_path / "dr14_mldsa65_keygen_rows.cc"), arg_types=[token2_ty, token3_ty], include_dirs=inc_dirs)
        w4_fn = ExternalFunction("dr14_mldsa65_keygen_finalize", source_file=str(kernel_path / "dr14_mldsa65_keygen_finalize.cc"), arg_types=[token3_ty, result_ty], include_dirs=inc_dirs)

        def worker0_body(of_r, of_d, of_t, fn):
            r = of_r.acquire(1)
            d = of_d.acquire(1)
            t = of_t.acquire(1)
            fn(r, d, t)
            of_t.release(1)
            of_r.release(1)
            of_d.release(1)

        def worker_step(of_i, of_o, fn):
            inp = of_i.acquire(1)
            outp = of_o.acquire(1)
            fn(inp, outp)
            of_o.release(1)
            of_i.release(1)

        w0 = Worker(worker0_body, fn_args=[of_req.cons(), of_desc.cons(), of_t0.prod(), w0_fn], stack_size=0x2000)
        w1 = Worker(worker_step, fn_args=[of_t0.cons(), of_t1.prod(), w1_fn], stack_size=0x2000)
        w2 = Worker(worker_step, fn_args=[of_t1.cons(), of_t2.prod(), w2_fn], stack_size=0x2000)
        w3 = Worker(worker_step, fn_args=[of_t2.cons(), of_t3.prod(), w3_fn], stack_size=0x2000)
        w4 = Worker(worker_step, fn_args=[of_t3.cons(), of_res.prod(), w4_fn], stack_size=0x2000)

        def sequence(r_in, d_in, res_out, of_rp, of_dp, of_rc):
            of_rp.fill(r_in)
            of_dp.fill(d_in)
            of_rc.drain(res_out, wait=True)

        runtime = Runtime(
            sequence,
            [req_ty, descriptor_ty, result_ty, of_req.prod(), of_desc.prod(), of_res.cons()],
        )

        return Program(
            iron.get_current_device(),
            runtime,
            workers=[w0, w1, w2, w3, w4],
        ).resolve_program()

    return dr14_keygen_pipeline

def _program():
    global _CACHED_PROGRAM
    if _CACHED_PROGRAM is None:
        _CACHED_PROGRAM = _build_dr14_keygen_program()
    return _CACHED_PROGRAM

def _clear_host_staging(buf: np.ndarray, tensor: Any) -> None:
    try:
        buf.fill(0)
    except Exception:
        pass
    try:
        raw_data = getattr(tensor, "_data", None)
        if raw_data is not None:
            raw_data.fill(0)
    except Exception:
        pass

def run_mldsa65_keygen(
    seed: bytes,
    request_id: int = 1,
) -> tuple[bytes, bytes]:
    """Execute 100% On-Device ML-DSA-65 KeyGen on physical Phoenix NPU.
    Returns: (pk[1952], sk[4032])
    """
    *_, XRTTensor = _load_iron()

    req_buf = bytearray(REQ_BYTES)
    req_buf[:32] = seed[:32]

    desc_buf = bytearray(DESCRIPTOR_BYTES)
    desc_buf[0:4] = b"\x01\x71\x52\x0E" # DR14 Magic
    desc_buf[4] = 0x04 # ML-DSA
    desc_buf[5] = 0x01 # KeyGen
    desc_buf[6] = 0x0E # DR14
    desc_buf[7] = 0x65 # ML-DSA-65
    desc_buf[8:12] = request_id.to_bytes(4, "little")

    req_np = np.frombuffer(req_buf, dtype=np.uint8).copy()
    desc_np = np.frombuffer(desc_buf, dtype=np.uint8).copy()
    res_np = np.zeros(RESULT_BYTES, dtype=np.uint8)

    req_t = XRTTensor(req_np, dtype=np.uint8)
    desc_t = XRTTensor(desc_np, dtype=np.uint8)
    res_t = XRTTensor(res_np, dtype=np.uint8)

    try:
        _program()(
            req_t, desc_t, res_t,
            req_slots=REQ_BYTES,
            descriptor_slots=DESCRIPTOR_BYTES,
            token0_slots=TOKEN0_BYTES,
            token1_slots=TOKEN1_BYTES,
            token2_slots=TOKEN2_BYTES,
            token3_slots=TOKEN3_BYTES,
            result_slots=RESULT_BYTES,
            element_type=np.uint8,
        )
        res_t.to("cpu")
    finally:
        _clear_host_staging(req_np, req_t)
        _clear_host_staging(desc_np, desc_t)

    raw_output = bytes(res_t._data[:RESULT_BYTES])
    _clear_host_staging(res_np, res_t)

    pk = raw_output[20 : 20 + 1952]
    sk = raw_output[20 + 1952 : 20 + 1952 + 4032]
    return pk, sk
