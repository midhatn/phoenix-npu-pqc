import hashlib
import os
import sys
from pathlib import Path
from typing import Any
import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

BACKEND_LABEL = "dr13-mldsa44-verify:silicon"
KERNEL_REL_PATH = "phoenix_sdr_dsp/pqc/kernels/dr13_mldsa44_verify_w1_matrix_w.cc"

# Sizes
REQ_BYTES = 3796        # pk(1312) + mu(64) + sig(2420)
DESCRIPTOR_BYTES = 16
TOKEN0_BYTES = 10376    # req_id(4) + fail_flag(4) + rho(32) + mu(64) + c_tilde(32) + h(1024) + z_hat(4096) + t1_hat(4096) + c_hat(1024)
RESULT_BYTES = 28       # Header(20) + Valid(4) + CRC32(4)

_CACHED_PROGRAM = None


class NativeBackendUnavailable(RuntimeError):
    """The native IRON/XRT DR13 backend is unavailable or failed closed."""


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
        raise NativeBackendUnavailable("DR13 physical silicon requires XRT device(0)") from exc


def get_kernel_artifact_info(repo_root: Path | None = None) -> dict[str, Any]:
    """Return verified path and SHA-256 digest of the DR13 AIE2 kernel source."""
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
            "DR13 requires MLIR-AIE/IRON 1.4.1, XRT, and an XRT-visible Phoenix NPU."
        ) from exc
    return iron, CompileTime, ExternalFunction, In, ObjectFifo, Out, Program, Runtime, Worker, cxx_header_path, XRTTensor

def _build_dr13_verify_program():
    (
        iron, CompileTime, ExternalFunction, In, ObjectFifo, Out, Program, Runtime, Worker, cxx_header_path, _,
    ) = _load_iron()

    @iron.jit
    def dr13_verify_pipeline(
        request_in: In,
        descriptor_in: In,
        result_out: Out,
        *,
        req_slots: CompileTime[int],
        descriptor_slots: CompileTime[int],
        token0_slots: CompileTime[int],
        result_slots: CompileTime[int],
        element_type: CompileTime[type],
    ):
        req_ty = np.ndarray[(req_slots,), np.dtype[element_type]]
        descriptor_ty = np.ndarray[(descriptor_slots,), np.dtype[element_type]]
        token0_ty = np.ndarray[(token0_slots,), np.dtype[element_type]]
        result_ty = np.ndarray[(result_slots,), np.dtype[element_type]]

        of_req = ObjectFifo(req_ty, name="dr13_req")
        of_descriptor = ObjectFifo(descriptor_ty, name="dr13_desc")
        of_token0 = ObjectFifo(token0_ty, name="dr13_tok0")
        of_result = ObjectFifo(result_ty, name="dr13_res")

        kernel_path = Path(__file__).resolve().parent / "kernels"
        inc_dirs = [cxx_header_path(), str(kernel_path)]

        w0_fn = ExternalFunction(
            "dr13_mldsa44_verify_w0_init",
            source_file=str(kernel_path / "dr13_mldsa44_verify_w0_init.cc"),
            arg_types=[req_ty, descriptor_ty, token0_ty],
            include_dirs=inc_dirs,
        )
        w1_fn = ExternalFunction(
            "dr13_mldsa44_verify_w1_matrix_w",
            source_file=str(kernel_path / "dr13_mldsa44_verify_w1_matrix_w.cc"),
            arg_types=[token0_ty, result_ty],
            include_dirs=inc_dirs,
        )

        def worker0_body(of_r, of_d, of_t, fn):
            r = of_r.acquire(1)
            d = of_d.acquire(1)
            t = of_t.acquire(1)
            fn(r, d, t)
            of_t.release(1)
            of_r.release(1)
            of_d.release(1)

        def worker1_body(of_i, of_o, fn):
            inp = of_i.acquire(1)
            outp = of_o.acquire(1)
            fn(inp, outp)
            of_o.release(1)
            of_i.release(1)

        w0 = Worker(worker0_body, fn_args=[of_req.cons(), of_descriptor.cons(), of_token0.prod(), w0_fn], stack_size=0x2000)
        w1 = Worker(worker1_body, fn_args=[of_token0.cons(), of_result.prod(), w1_fn], stack_size=0x2000)

        def sequence(r_in, d_in, res_out, of_rp, of_dp, of_rc):
            of_rp.fill(r_in)
            of_dp.fill(d_in)
            of_rc.drain(res_out, wait=True)

        runtime = Runtime(
            sequence,
            [req_ty, descriptor_ty, result_ty, of_req.prod(), of_descriptor.prod(), of_result.cons()],
        )

        return Program(
            iron.get_current_device(),
            runtime,
            workers=[w0, w1],
        ).resolve_program()

    return dr13_verify_pipeline

def _program():
    global _CACHED_PROGRAM
    if _CACHED_PROGRAM is None:
        _CACHED_PROGRAM = _build_dr13_verify_program()
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

def run_mldsa44_verify(
    pk: bytes,
    m_or_mu: bytes,
    sig: bytes,
    external_mu: bool = False,
    request_id: int = 1,
) -> bool:
    """Execute 100% On-Device ML-DSA-44 Signature Verification on physical Phoenix NPU.
    Returns: bool (True for valid, False for rejected)
    """
    *_, XRTTensor = _load_iron()

    # FIPS 204 Alg 8: if not external_mu, derive tr = H(pk, 64), mu = H(tr || m, 64)
    if not external_mu:
        from hashlib import shake_256
        tr = shake_256(pk).digest(64)
        mu = shake_256(tr + m_or_mu).digest(64)
    else:
        mu = m_or_mu[:64]

    req_buf = bytearray(REQ_BYTES)
    req_buf[:1312] = pk[:1312]
    req_buf[1312 : 1312 + min(len(mu), 64)] = mu[:64]
    req_buf[1376 : 1376 + min(len(sig), 2420)] = sig[:2420]

    desc_buf = bytearray(DESCRIPTOR_BYTES)
    desc_buf[0:4] = b"\x01\x71\x52\x0D" # DR13 Magic
    desc_buf[4] = 0x04 # ML-DSA-44
    desc_buf[5] = 0x03 # Verify
    desc_buf[6] = 0x0D # DR13
    desc_buf[7] = 1
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
            result_slots=RESULT_BYTES,
            element_type=np.uint8,
        )
        res_t.to("cpu")
    finally:
        _clear_host_staging(req_np, req_t)
        _clear_host_staging(desc_np, desc_t)

    raw_output = bytes(res_t._data[:RESULT_BYTES])
    _clear_host_staging(res_np, res_t)

    valid_val = int.from_bytes(raw_output[20:24], "little")
    return valid_val == 1


__all__ = [
    "BACKEND_LABEL",
    "DESCRIPTOR_BYTES",
    "KERNEL_REL_PATH",
    "NativeBackendUnavailable",
    "REQ_BYTES",
    "RESULT_BYTES",
    "TOKEN0_BYTES",
    "check_emulation_and_redirection_excluded",
    "get_kernel_artifact_info",
    "require_hardware_runtime",
    "run_mldsa44_verify",
]
