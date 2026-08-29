# SPDX-License-Identifier: Apache-2.0
"""DR12: 100% On-Device ML-DSA-44 Sign Graph on AMD Phoenix AIE2."""

from pathlib import Path
from typing import Any
import numpy as np

BACKEND_LABEL = "dr12-mldsa44-sign:silicon"
_PROGRAM: Any | None = None

REQ_BYTES = 2656
DESCRIPTOR_BYTES = 16
RESULT_BYTES = 2444

TOKEN0_BYTES = 2596
TOKEN1_BYTES = 10660
TOKEN2_BYTES = 12328

class NativeBackendUnavailable(RuntimeError):
    """The native IRON/XRT DR12 backend is unavailable or failed closed."""

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
            "DR12 requires MLIR-AIE/IRON 1.4.1, XRT, and an XRT-visible Phoenix NPU."
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
    def dr12_sign_program(
        request_in: In,
        descriptor_in: In,
        result_out: Out,
        *,
        req_slots: CompileTime[int],
        descriptor_slots: CompileTime[int],
        token0_slots: CompileTime[int],
        token1_slots: CompileTime[int],
        token2_slots: CompileTime[int],
        result_slots: CompileTime[int],
        element_type: CompileTime[type],
    ):
        req_ty = np.ndarray[(req_slots,), np.dtype[element_type]]
        descriptor_ty = np.ndarray[(descriptor_slots,), np.dtype[element_type]]
        token0_ty = np.ndarray[(token0_slots,), np.dtype[element_type]]
        token1_ty = np.ndarray[(token1_slots,), np.dtype[element_type]]
        token2_ty = np.ndarray[(token2_slots,), np.dtype[element_type]]
        result_ty = np.ndarray[(result_slots,), np.dtype[element_type]]

        of_req = ObjectFifo(req_ty, name="dr12_req")
        of_descriptor = ObjectFifo(descriptor_ty, name="dr12_desc")
        of_token0 = ObjectFifo(token0_ty, name="dr12_tok0")
        of_token1 = ObjectFifo(token1_ty, name="dr12_tok1")
        of_token2 = ObjectFifo(token2_ty, name="dr12_tok2")
        of_result = ObjectFifo(result_ty, name="dr12_res")

        kernel_path = Path(__file__).resolve().parent / "kernels"
        inc_dirs = [cxx_header_path(), str(kernel_path)]

        w0_fn = ExternalFunction("dr12_mldsa44_sign_w0_init", source_file=str(kernel_path / "dr12_mldsa44_sign_w0_init.cc"), arg_types=[req_ty, descriptor_ty, token0_ty], include_dirs=inc_dirs)
        w1_fn = ExternalFunction("dr12_mldsa44_sign_w1_mask_a", source_file=str(kernel_path / "dr12_mldsa44_sign_w1_mask_a.cc"), arg_types=[token0_ty, token1_ty], include_dirs=inc_dirs)
        w2_fn = ExternalFunction("dr12_mldsa44_sign_w2_challenge_cs", source_file=str(kernel_path / "dr12_mldsa44_sign_w2_challenge_cs.cc"), arg_types=[token1_ty, token2_ty], include_dirs=inc_dirs)
        w3_fn = ExternalFunction("dr12_mldsa44_sign_w3_hints_seal", source_file=str(kernel_path / "dr12_mldsa44_sign_w3_hints_seal.cc"), arg_types=[token2_ty, result_ty], include_dirs=inc_dirs)

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

        w0 = Worker(worker0_body, fn_args=[of_req.cons(), of_descriptor.cons(), of_token0.prod(), w0_fn], stack_size=0x2000)
        w1 = Worker(worker_step, fn_args=[of_token0.cons(), of_token1.prod(), w1_fn], stack_size=0x2800)
        w2 = Worker(worker_step, fn_args=[of_token1.cons(), of_token2.prod(), w2_fn], stack_size=0x2000)
        w3 = Worker(worker_step, fn_args=[of_token2.cons(), of_result.prod(), w3_fn], stack_size=0x2000)

        def sequence(r, d, res, r_prod, d_prod, res_cons):
            r_prod.fill(r)
            d_prod.fill(d)
            res_cons.drain(res, wait=True)

        runtime = Runtime(
            sequence,
            [
                req_ty,
                descriptor_ty,
                result_ty,
                of_req.prod(),
                of_descriptor.prod(),
                of_result.cons(),
            ],
        )
        return Program(
            iron.get_current_device(), runtime, workers=[w0, w1, w2, w3]
        ).resolve_program()

    _PROGRAM = dr12_sign_program
    return _PROGRAM

def run_mldsa44_sign(
    sk: bytes,
    m_or_mu: bytes,
    rnd: bytes = bytes(32),
    external_mu: bool = False,
    request_id: int = 1,
) -> bytes:
    """Execute 100% On-Device ML-DSA-44 Signing on physical Phoenix NPU.
    Returns: sig[2420]
    """
    *_, XRTTensor = _load_iron()

    # FIPS 204 Alg 7: if not external_mu, derive mu = SHAKE256(tr || m, 64)
    if not external_mu:
        from hashlib import shake_256
        tr = sk[64:128]
        mu = shake_256(tr + m_or_mu).digest(64)
    else:
        mu = m_or_mu[:64]

    req_buf = bytearray(REQ_BYTES)
    req_buf[:2560] = sk[:2560]
    req_buf[2560 : 2560 + min(len(mu), 64)] = mu[:64]
    req_buf[2624 : 2624 + min(len(rnd), 32)] = rnd[:32]

    desc_buf = bytearray(DESCRIPTOR_BYTES)
    desc_buf[0:4] = b"\x01\x71\x52\x0C" # DR12 Magic
    desc_buf[4] = 0x04 # ML-DSA-44
    desc_buf[5] = 0x02 # Sign
    desc_buf[6] = 0x0C # DR12
    desc_buf[7] = 1 # Ingested mu is 64 bytes
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
    if status != 0:
        raise RuntimeError(f"ML-DSA-44 Sign failed on silicon with status {status}")

    sig = raw_output[20 : 20 + 2420]
    return sig
