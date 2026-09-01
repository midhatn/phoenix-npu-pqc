# SPDX-License-Identifier: Apache-2.0
# DR14: Complete NIST FIPS 204 ML-DSA-65 Signing Graph.
# 100% On-Device Device-Resident ML-DSA-65 Sign on AMD Phoenix NPU (AIE2 / XDNA1).
import hashlib
import os
import sys
from pathlib import Path
from typing import Any
import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

BACKEND_LABEL = "dr14-mldsa65-sign:silicon"
KERNEL_REL_PATH = "phoenix_sdr_dsp/pqc/kernels/dr14_mldsa65_sign_w2_fin.cc"

# Sizes
REQ_BYTES = 4096        # sk(4032) + msg/mu(64)
DESCRIPTOR_BYTES = 16
TOKEN0_BYTES = 17572    # w0 output
TOKEN1_BYTES = 12852    # w1 output
RESULT_BYTES = 3336     # Header(20) + sig(3309) + CRC32(4) + pad(3)

_CACHED_PROGRAM = None


class NativeBackendUnavailable(RuntimeError):
    """The native IRON/XRT DR14 Sign backend is unavailable or failed closed."""


def check_emulation_and_redirection_excluded() -> None:
    """Fail closed if XCL_EMULATION_MODE or XRT_INI_PATH runtime redirection variables are set."""
    emulation_mode = os.environ.get("XCL_EMULATION_MODE")
    if emulation_mode and emulation_mode.strip():
        raise NativeBackendUnavailable(
            f"Physical silicon execution rejected: XCL_EMULATION_MODE={emulation_mode!r} is set. "
            "Hardware ground truth forbids simulation or emulation backends."
        )
    xrt_ini = os.environ.get("XRT_INI_PATH")
    if xrt_ini and xrt_ini.strip():
        raise NativeBackendUnavailable(
            f"Physical silicon execution rejected: XRT_INI_PATH={xrt_ini!r} is set. "
            "Hardware ground truth forbids custom runtime configuration redirection."
        )


def require_hardware_runtime() -> None:
    """Check hardware runtime availability and fail closed if unavailable."""
    check_emulation_and_redirection_excluded()
    try:
        import pyxrt
        dev = pyxrt.device(0)
    except Exception as exc:
        raise NativeBackendUnavailable("DR14 physical silicon requires XRT device(0)") from exc


def get_kernel_artifact_info(repo_root: Path | None = None) -> dict[str, Any]:
    """Return verified path and SHA-256 digest of the DR14 Sign AIE2 kernel source."""
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


def _load_iron():
    check_emulation_and_redirection_excluded()
    try:
        from aie import iron
        from aie.iron import (
            CompileTime, ExternalFunction, In, ObjectFifo, Out, Program, Runtime, Worker,
        )
        from aie.utils.config import cxx_header_path
        from aie.utils.hostruntime.xrtruntime.tensor import XRTTensor
    except Exception as exc:
        raise NativeBackendUnavailable(
            "DR14 requires MLIR-AIE/IRON 1.4.1, XRT, and an XRT-visible Phoenix NPU."
        ) from exc
    return iron, CompileTime, ExternalFunction, In, ObjectFifo, Out, Program, Runtime, Worker, cxx_header_path, XRTTensor

def _build_dr14_sign_program():
    (
        iron, CompileTime, ExternalFunction, In, ObjectFifo, Out, Program, Runtime, Worker, cxx_header_path, _,
    ) = _load_iron()

    @iron.jit
    def dr14_sign_pipeline(
        request_in: In,
        descriptor_in: In,
        result_out: Out,
        *,
        req_slots: CompileTime[int],
        descriptor_slots: CompileTime[int],
        token0_slots: CompileTime[int],
        token1_slots: CompileTime[int],
        result_slots: CompileTime[int],
        element_type: CompileTime[type],
    ):
        req_ty = np.ndarray[(req_slots,), np.dtype[element_type]]
        descriptor_ty = np.ndarray[(descriptor_slots,), np.dtype[element_type]]
        token0_ty = np.ndarray[(token0_slots,), np.dtype[element_type]]
        token1_ty = np.ndarray[(token1_slots,), np.dtype[element_type]]
        result_ty = np.ndarray[(result_slots,), np.dtype[element_type]]

        of_req = ObjectFifo(req_ty, name="dr14_sig_req")
        of_desc = ObjectFifo(descriptor_ty, name="dr14_sig_desc")
        of_t0 = ObjectFifo(token0_ty, name="dr14_sig_t0")
        of_t1 = ObjectFifo(token1_ty, name="dr14_sig_t1")
        of_res = ObjectFifo(result_ty, name="dr14_sig_res")

        kernel_path = Path(__file__).resolve().parent / "kernels"
        inc_dirs = [cxx_header_path(), str(kernel_path)]

        w0_fn = ExternalFunction("dr14_mldsa65_sign_w0_init", source_file=str(kernel_path / "dr14_mldsa65_sign_w0_init.cc"), arg_types=[req_ty, descriptor_ty, token0_ty], include_dirs=inc_dirs)
        w1_fn = ExternalFunction("dr14_mldsa65_sign_w1_loop", source_file=str(kernel_path / "dr14_mldsa65_sign_w1_loop.cc"), arg_types=[token0_ty, token1_ty], include_dirs=inc_dirs)
        w2_fn = ExternalFunction("dr14_mldsa65_sign_w2_fin", source_file=str(kernel_path / "dr14_mldsa65_sign_w2_fin.cc"), arg_types=[token1_ty, result_ty], include_dirs=inc_dirs)

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
        w2 = Worker(worker_step, fn_args=[of_t1.cons(), of_res.prod(), w2_fn], stack_size=0x2000)

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
            workers=[w0, w1, w2],
        ).resolve_program()

    return dr14_sign_pipeline

def _program():
    global _CACHED_PROGRAM
    if _CACHED_PROGRAM is None:
        _CACHED_PROGRAM = _build_dr14_sign_program()
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

def run_mldsa65_sign(
    sk: bytes,
    msg_or_mu: bytes,
    external_mu: bool = True,
    request_id: int = 1,
) -> bytes:
    """Execute 100% On-Device ML-DSA-65 Sign on physical Phoenix NPU.
    Returns: signature[3309]
    """
    *_, XRTTensor = _load_iron()

    # FIPS 204 Alg 7: if not external_mu, derive mu = SHAKE256(tr || m, 64)
    if not external_mu:
        from hashlib import shake_256
        tr = sk[64:128]
        mu = shake_256(tr + msg_or_mu).digest(64)
    else:
        mu = msg_or_mu[:64]

    req_buf = bytearray(REQ_BYTES)
    req_buf[:4032] = sk[:4032]
    req_buf[4032 : 4032 + min(len(mu), 64)] = mu[:64]

    desc_buf = bytearray(DESCRIPTOR_BYTES)
    desc_buf[0:4] = b"\x01\x71\x52\x0E" # DR14 Magic
    desc_buf[4] = 0x04 # ML-DSA
    desc_buf[5] = 0x02 # Sign
    desc_buf[6] = 0x0E # DR14
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
            result_slots=RESULT_BYTES,
            element_type=np.uint8,
        )
        res_t.to("cpu")
    finally:
        _clear_host_staging(req_np, req_t)
        _clear_host_staging(desc_np, desc_t)

    raw_output = bytes(res_t._data[:RESULT_BYTES])
    _clear_host_staging(res_np, res_t)

    sig = raw_output[20 : 20 + 3309]
    return sig


__all__ = [
    "BACKEND_LABEL",
    "DESCRIPTOR_BYTES",
    "KERNEL_REL_PATH",
    "NativeBackendUnavailable",
    "REQ_BYTES",
    "RESULT_BYTES",
    "TOKEN0_BYTES",
    "TOKEN1_BYTES",
    "check_emulation_and_redirection_excluded",
    "get_kernel_artifact_info",
    "require_hardware_runtime",
    "run_mldsa65_sign",
]
