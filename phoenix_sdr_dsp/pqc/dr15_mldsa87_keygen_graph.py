# SPDX-License-Identifier: Apache-2.0
# DR15: Complete NIST FIPS 204 ML-DSA-87 Key Generation Graph.
# 100% On-Device Device-Resident ML-DSA-87 KeyGen on AMD Phoenix NPU (AIE2 / XDNA1).
import os
import sys
from pathlib import Path
from typing import Any
import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Sizes
SEED_BYTES = 32
DESCRIPTOR_BYTES = 16
TOKEN0_BYTES = 8704
TOKEN1_BYTES = 11648
TOKEN2_BYTES = 14592
RESULT_BYTES = 7512     # Header(20) + pk(2592) + sk(4896) + CRC32(4)

_CACHED_PROGRAM = None

def _load_iron():
    from aie import iron
    from aie.iron import (
        CompileTime, ExternalFunction, In, ObjectFifo, Out, Program, Runtime, Worker,
    )
    from aie.utils.config import cxx_header_path
    from aie.utils.hostruntime.xrtruntime.tensor import XRTTensor
    return iron, CompileTime, ExternalFunction, In, ObjectFifo, Out, Program, Runtime, Worker, cxx_header_path, XRTTensor

def _build_dr15_keygen_program():
    (
        iron, CompileTime, ExternalFunction, In, ObjectFifo, Out, Program, Runtime, Worker, cxx_header_path, _,
    ) = _load_iron()

    @iron.jit
    def dr15_keygen_pipeline(
        seed_in: In,
        descriptor_in: In,
        result_out: Out,
        *,
        seed_slots: CompileTime[int],
        descriptor_slots: CompileTime[int],
        token0_slots: CompileTime[int],
        token1_slots: CompileTime[int],
        token2_slots: CompileTime[int],
        result_slots: CompileTime[int],
        element_type: CompileTime[type],
    ):
        seed_ty = np.ndarray[(seed_slots,), np.dtype[element_type]]
        descriptor_ty = np.ndarray[(descriptor_slots,), np.dtype[element_type]]
        token0_ty = np.ndarray[(token0_slots,), np.dtype[element_type]]
        token1_ty = np.ndarray[(token1_slots,), np.dtype[element_type]]
        token2_ty = np.ndarray[(token2_slots,), np.dtype[element_type]]
        result_ty = np.ndarray[(result_slots,), np.dtype[element_type]]

        of_seed = ObjectFifo(seed_ty, name="dr15_kg_seed")
        of_desc = ObjectFifo(descriptor_ty, name="dr15_kg_desc")
        of_t0 = ObjectFifo(token0_ty, name="dr15_kg_t0")
        of_t1 = ObjectFifo(token1_ty, name="dr15_kg_t1")
        of_t2 = ObjectFifo(token2_ty, name="dr15_kg_t2")
        of_res = ObjectFifo(result_ty, name="dr15_kg_res")

        kernel_path = Path(__file__).resolve().parent / "kernels"
        inc_dirs = [cxx_header_path(), str(kernel_path)]

        w0_fn = ExternalFunction("dr15_mldsa87_keygen_noise", source_file=str(kernel_path / "dr15_mldsa87_keygen_noise.cc"), arg_types=[seed_ty, descriptor_ty, token0_ty], include_dirs=inc_dirs)
        w1_fn = ExternalFunction("dr15_mldsa87_keygen_rows0123", source_file=str(kernel_path / "dr15_mldsa87_keygen_rows0123.cc"), arg_types=[token0_ty, token1_ty], include_dirs=inc_dirs)
        w2_fn = ExternalFunction("dr15_mldsa87_keygen_rows4567", source_file=str(kernel_path / "dr15_mldsa87_keygen_rows4567.cc"), arg_types=[token1_ty, token2_ty], include_dirs=inc_dirs)
        w3_fn = ExternalFunction("dr15_mldsa87_keygen_finalize", source_file=str(kernel_path / "dr15_mldsa87_keygen_finalize.cc"), arg_types=[token2_ty, result_ty], include_dirs=inc_dirs)

        def worker0_body(of_s, of_d, of_t, fn):
            s = of_s.acquire(1)
            d = of_d.acquire(1)
            t = of_t.acquire(1)
            fn(s, d, t)
            of_t.release(1)
            of_s.release(1)
            of_d.release(1)

        def worker_step(of_i, of_o, fn):
            inp = of_i.acquire(1)
            outp = of_o.acquire(1)
            fn(inp, outp)
            of_o.release(1)
            of_i.release(1)

        w0 = Worker(worker0_body, fn_args=[of_seed.cons(), of_desc.cons(), of_t0.prod(), w0_fn], stack_size=0x1800)
        w1 = Worker(worker_step, fn_args=[of_t0.cons(), of_t1.prod(), w1_fn], stack_size=0x1800)
        w2 = Worker(worker_step, fn_args=[of_t1.cons(), of_t2.prod(), w2_fn], stack_size=0x1800)
        w3 = Worker(worker_step, fn_args=[of_t2.cons(), of_res.prod(), w3_fn], stack_size=0x1800)

        def sequence(s_in, d_in, res_out, of_sp, of_dp, of_rc):
            of_sp.fill(s_in)
            of_dp.fill(d_in)
            of_rc.drain(res_out, wait=True)

        runtime = Runtime(
            sequence,
            [seed_ty, descriptor_ty, result_ty, of_seed.prod(), of_desc.prod(), of_res.cons()],
        )

        return Program(
            iron.get_current_device(),
            runtime,
            workers=[w0, w1, w2, w3],
        ).resolve_program()

    return dr15_keygen_pipeline

def _program():
    global _CACHED_PROGRAM
    if _CACHED_PROGRAM is None:
        _CACHED_PROGRAM = _build_dr15_keygen_program()
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

def run_mldsa87_keygen(
    seed: bytes,
    request_id: int = 1,
) -> tuple[bytes, bytes]:
    """Execute 100% On-Device ML-DSA-87 KeyGen on physical Phoenix NPU.
    Returns: (pk[2592], sk[4896])
    """
    *_, XRTTensor = _load_iron()

    seed_buf = bytearray(SEED_BYTES)
    seed_buf[: len(seed)] = seed[:32]

    desc_buf = bytearray(DESCRIPTOR_BYTES)
    desc_buf[0:4] = b"\x01\x71\x52\x0F" # DR15 Magic
    desc_buf[4] = 0x04 # ML-DSA
    desc_buf[5] = 0x01 # KeyGen
    desc_buf[6] = 0x0F # DR15
    desc_buf[7] = 0
    desc_buf[8:12] = request_id.to_bytes(4, "little")

    seed_np = np.frombuffer(seed_buf, dtype=np.uint8).copy()
    desc_np = np.frombuffer(desc_buf, dtype=np.uint8).copy()
    res_np = np.zeros(RESULT_BYTES, dtype=np.uint8)

    seed_t = XRTTensor(seed_np, dtype=np.uint8)
    desc_t = XRTTensor(desc_np, dtype=np.uint8)
    res_t = XRTTensor(res_np, dtype=np.uint8)

    try:
        _program()(
            seed_t, desc_t, res_t,
            seed_slots=SEED_BYTES,
            descriptor_slots=DESCRIPTOR_BYTES,
            token0_slots=TOKEN0_BYTES,
            token1_slots=TOKEN1_BYTES,
            token2_slots=TOKEN2_BYTES,
            result_slots=RESULT_BYTES,
            element_type=np.uint8,
        )
        res_t.to("cpu")
    finally:
        _clear_host_staging(seed_np, seed_t)
        _clear_host_staging(desc_np, desc_t)

    raw_output = bytes(res_t._data[:RESULT_BYTES])
    _clear_host_staging(res_np, res_t)

    pk = raw_output[20 : 20 + 2592]
    sk = raw_output[2612 : 2612 + 4896]
    return pk, sk
