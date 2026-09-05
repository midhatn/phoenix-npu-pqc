# SPDX-License-Identifier: Apache-2.0
"""Computational Graph & Hardware Dispatch Orchestrator for Milestone DR37:
Dual-Scheme Hybrid Classical / Quantum-Safe KEM Engine on AMD Phoenix AIE2.
Compliant with ETSI TS 103 744, BSI TR-02102-1, IETF RFC 9180, and NIST SP 800-56C Rev. 2.
"""

import hashlib
import os
from pathlib import Path
import struct
import time
from typing import Any, Tuple, Dict, List, Optional

import numpy as np

from .dr37_hybrid_kem_abi import (
    MAGIC_HEADER,
    MAGIC_RESULT,
    MODE_HYBRID_ENCAPS_COMBINE,
    MODE_HYBRID_DECAPS_COMBINE,
    MODE_HYBRID_SPLIT_SECRET,
    MODE_HYBRID_POLICY_ENFORCE,
    MODE_HYBRID_ZEROIZE,
    PROFILE_X25519_MLKEM768,
    PROFILE_SECP384R1_MLKEM1024,
    STATUS_SUCCESS,
    STATUS_ERR_INVALID_MAGIC,
    STATUS_ERR_DEGENERATE_KEY,
    STATUS_ERR_POLICY_VIOLATION,
    STATUS_ERR_INVALID_PROFILE,
    STATUS_ERR_INTEGRITY_FAIL,
    REQ_TOTAL_BYTES,
    DESC_TOTAL_BYTES,
    RESULT_TOTAL_BYTES,
    pack_dr37_descriptor,
    pack_dr37_request,
    unpack_dr37_result,
)

BACKEND_LABEL = "dr37-hybrid-kem:silicon"
KERNEL_REL_PATH = "phoenix_sdr_dsp/pqc/kernels/dr37_hybrid_kem_service.cc"
_PROGRAM: Any | None = None


class NativeBackendUnavailable(RuntimeError):
    """The native IRON/XRT DR37 backend is unavailable or failed closed."""


def check_emulation_and_redirection_excluded() -> None:
    emulation_mode = os.environ.get("XCL_EMULATION_MODE")
    if emulation_mode and emulation_mode.strip():
        raise NativeBackendUnavailable(
            f"Physical silicon execution rejected: XCL_EMULATION_MODE={emulation_mode!r} is set."
        )
    xrt_ini = os.environ.get("XRT_INI_PATH")
    if xrt_ini and xrt_ini.strip():
        raise NativeBackendUnavailable(
            f"Physical silicon execution rejected: XRT_INI_PATH={xrt_ini!r} is set."
        )


def require_hardware_runtime() -> None:
    check_emulation_and_redirection_excluded()
    try:
        import pyxrt
        dev = pyxrt.device(0)
    except Exception as exc:
        raise NativeBackendUnavailable("DR37 physical silicon requires XRT device(0)") from exc


def get_kernel_artifact_info(repo_root: Path | None = None) -> dict[str, Any]:
    root = repo_root or Path(__file__).resolve().parents[2]
    kernel_path = root / KERNEL_REL_PATH
    if not kernel_path.is_file():
        raise FileNotFoundError(f"Kernel source file not found: {kernel_path}")
    data = kernel_path.read_bytes()
    return {
        "path": KERNEL_REL_PATH,
        "size_bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest().lower(),
    }


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
            "DR37 requires MLIR-AIE/IRON, XRT, and an XRT-visible Phoenix NPU."
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
    if staging_tensor is not None and hasattr(staging_tensor, "_data"):
        try:
            staging_tensor._data[:] = 0
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
    def dr37_hybrid_kem_program(
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

        of_request = ObjectFifo(request_ty, name="dr37_request")
        of_descriptor = ObjectFifo(descriptor_ty, name="dr37_descriptor")
        of_result = ObjectFifo(result_ty, name="dr37_result")

        kernel_path = Path(__file__).resolve().parent / "kernels"
        service_fn = ExternalFunction(
            "dr37_hybrid_kem_service",
            source_file=str(kernel_path / "dr37_hybrid_kem_service.cc"),
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
            fn_args=[of_request.cons(), of_descriptor.cons(), of_result.prod(), service_fn],
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

    _PROGRAM = dr37_hybrid_kem_program
    return _PROGRAM


def _dispatch_dr37(desc_bytes: bytes, req_buf: bytes) -> Tuple[bytes, float]:
    require_hardware_runtime()
    *_, XRTTensor = _load_iron()

    desc_np = np.frombuffer(desc_bytes, dtype=np.uint8).copy()
    req_np = np.frombuffer(req_buf, dtype=np.uint8).copy()
    res_np = np.zeros(RESULT_TOTAL_BYTES, dtype=np.uint8)

    req_t = XRTTensor(req_np, dtype=np.uint8)
    desc_t = XRTTensor(desc_np, dtype=np.uint8)
    res_t = XRTTensor(res_np, dtype=np.uint8)

    t0 = time.perf_counter()
    try:
        _program()(
            req_t,
            desc_t,
            res_t,
            request_slots=REQ_TOTAL_BYTES,
            descriptor_slots=DESC_TOTAL_BYTES,
            result_slots=RESULT_TOTAL_BYTES,
            element_type=np.uint8,
        )
        res_t.to("cpu")
    finally:
        _clear_host_staging(req_np, req_t)
        _clear_host_staging(desc_np, desc_t)

    dt_ms = (time.perf_counter() - t0) * 1000
    raw_res = bytes(res_t._data[:RESULT_TOTAL_BYTES])
    _clear_host_staging(res_np, res_t)

    return raw_res, dt_ms


def run_dr37_hybrid_kem_on_aie2(
    op_mode: int,
    profile_id: int = PROFILE_X25519_MLKEM768,
    classical_ss: bytes = bytes(32),
    pqc_ss: bytes = bytes(32),
    classical_ct: bytes = bytes(32),
    salt: bytes = bytes(32),
    pqc_ct: bytes = bytes(1088),
    seq_id: int = 1,
) -> Tuple[bytes, float]:
    """[ON-TILE SILICON] Dispatches Dual-Scheme Hybrid KEM combiner operation to AMD Phoenix AIE2."""
    desc = pack_dr37_descriptor(
        op_mode=op_mode,
        profile_id=profile_id,
        ss_c_len=len(classical_ss),
        ss_pqc_len=len(pqc_ss),
        ct_c_len=len(classical_ct),
        ct_pqc_len=len(pqc_ct),
        flags=0,
        seq_id=seq_id,
    )
    req = pack_dr37_request(
        classical_ss=classical_ss,
        pqc_ss=pqc_ss,
        classical_ct=classical_ct,
        salt=salt,
        pqc_ct=pqc_ct,
    )
    return _dispatch_dr37(desc, req)
