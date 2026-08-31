# SPDX-License-Identifier: Apache-2.0
"""DR11: 100% On-Device ML-DSA-44 KeyGen Graph on AMD Phoenix AIE2."""

import hashlib
import os
from pathlib import Path
from typing import Any
import numpy as np

BACKEND_LABEL = "dr11-mldsa44-keygen:silicon"
KERNEL_REL_PATH = "phoenix_sdr_dsp/pqc/kernels/dr11_mldsa44_keygen_finalize.cc"
_PROGRAM: Any | None = None

REQ_BYTES = 32
DESCRIPTOR_BYTES = 16
RESULT_BYTES = 3892

TOKEN_NOISE_BYTES = 9028
TOKEN_ROW0_BYTES = 8740
TOKEN_ROW1_BYTES = 8452
TOKEN_ROW2_BYTES = 8164
TOKEN_ROW3_BYTES = 3780


class NativeBackendUnavailable(RuntimeError):
    """The native IRON/XRT DR11 backend is unavailable or failed closed."""


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
        raise NativeBackendUnavailable("DR11 physical silicon requires XRT device(0)") from exc


def get_kernel_artifact_info(repo_root: Path | None = None) -> dict[str, Any]:
    """Return verified path and SHA-256 digest of the DR11 AIE2 kernel source."""
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
    check_emulation_and_redirection_excluded()
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
            "DR11 requires MLIR-AIE/IRON 1.4.1, XRT, and an XRT-visible Phoenix NPU."
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
    def dr11_keygen_program(
        request_in: In,
        descriptor_in: In,
        result_out: Out,
        *,
        req_slots: CompileTime[int],
        descriptor_slots: CompileTime[int],
        token_noise_slots: CompileTime[int],
        token_row0_slots: CompileTime[int],
        token_row1_slots: CompileTime[int],
        token_row2_slots: CompileTime[int],
        token_row3_slots: CompileTime[int],
        result_slots: CompileTime[int],
        element_type: CompileTime[type],
    ):
        req_ty = np.ndarray[(req_slots,), np.dtype[element_type]]
        descriptor_ty = np.ndarray[(descriptor_slots,), np.dtype[element_type]]
        noise_ty = np.ndarray[(token_noise_slots,), np.dtype[element_type]]
        row0_ty = np.ndarray[(token_row0_slots,), np.dtype[element_type]]
        row1_ty = np.ndarray[(token_row1_slots,), np.dtype[element_type]]
        row2_ty = np.ndarray[(token_row2_slots,), np.dtype[element_type]]
        row3_ty = np.ndarray[(token_row3_slots,), np.dtype[element_type]]
        result_ty = np.ndarray[(result_slots,), np.dtype[element_type]]

        of_req = ObjectFifo(req_ty, name="dr11_req")
        of_descriptor = ObjectFifo(descriptor_ty, name="dr11_desc")
        of_noise = ObjectFifo(noise_ty, name="dr11_noise")
        of_row0 = ObjectFifo(row0_ty, name="dr11_row0")
        of_row1 = ObjectFifo(row1_ty, name="dr11_row1")
        of_row2 = ObjectFifo(row2_ty, name="dr11_row2")
        of_row3 = ObjectFifo(row3_ty, name="dr11_row3")
        of_result = ObjectFifo(result_ty, name="dr11_result")

        kernel_path = Path(__file__).resolve().parent / "kernels"
        inc_dirs = [cxx_header_path(), str(kernel_path)]

        w0_fn = ExternalFunction("dr11_mldsa44_keygen_noise", source_file=str(kernel_path / "dr11_mldsa44_keygen_noise.cc"), arg_types=[req_ty, descriptor_ty, noise_ty], include_dirs=inc_dirs)
        w1_fn = ExternalFunction("dr11_mldsa44_keygen_row0", source_file=str(kernel_path / "dr11_mldsa44_keygen_row0.cc"), arg_types=[noise_ty, row0_ty], include_dirs=inc_dirs)
        w2_fn = ExternalFunction("dr11_mldsa44_keygen_row1", source_file=str(kernel_path / "dr11_mldsa44_keygen_row1.cc"), arg_types=[row0_ty, row1_ty], include_dirs=inc_dirs)
        w3_fn = ExternalFunction("dr11_mldsa44_keygen_row2", source_file=str(kernel_path / "dr11_mldsa44_keygen_row2.cc"), arg_types=[row1_ty, row2_ty], include_dirs=inc_dirs)
        w4_fn = ExternalFunction("dr11_mldsa44_keygen_row3", source_file=str(kernel_path / "dr11_mldsa44_keygen_row3.cc"), arg_types=[row2_ty, row3_ty], include_dirs=inc_dirs)
        w5_fn = ExternalFunction("dr11_mldsa44_keygen_finalize", source_file=str(kernel_path / "dr11_mldsa44_keygen_finalize.cc"), arg_types=[row3_ty, result_ty], include_dirs=inc_dirs)

        def worker0_body(of_r, of_d, of_n, fn):
            r = of_r.acquire(1)
            d = of_d.acquire(1)
            n = of_n.acquire(1)
            fn(r, d, n)
            of_n.release(1)
            of_r.release(1)
            of_d.release(1)

        def worker_step(of_in, of_out, fn):
            inp = of_in.acquire(1)
            outp = of_out.acquire(1)
            fn(inp, outp)
            of_out.release(1)
            of_in.release(1)

        w0 = Worker(worker0_body, fn_args=[of_req.cons(), of_descriptor.cons(), of_noise.prod(), w0_fn], stack_size=0x2000)
        w1 = Worker(worker_step, fn_args=[of_noise.cons(), of_row0.prod(), w1_fn], stack_size=0x2000)
        w2 = Worker(worker_step, fn_args=[of_row0.cons(), of_row1.prod(), w2_fn], stack_size=0x2000)
        w3 = Worker(worker_step, fn_args=[of_row1.cons(), of_row2.prod(), w3_fn], stack_size=0x2000)
        w4 = Worker(worker_step, fn_args=[of_row2.cons(), of_row3.prod(), w4_fn], stack_size=0x2000)
        w5 = Worker(worker_step, fn_args=[of_row3.cons(), of_result.prod(), w5_fn], stack_size=0x2000)

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
            iron.get_current_device(), runtime, workers=[w0, w1, w2, w3, w4, w5]
        ).resolve_program()

    _PROGRAM = dr11_keygen_program
    return _PROGRAM

def run_mldsa44_keygen(seed: bytes, request_id: int = 1) -> tuple[bytes, bytes]:
    """Execute 100% On-Device ML-DSA-44 KeyGen on physical Phoenix NPU.
    Returns: (pk[1312], sk[2560])
    """
    *_, XRTTensor = _load_iron()

    req_buf = bytearray(REQ_BYTES)
    req_buf[:32] = seed

    desc_buf = bytearray(DESCRIPTOR_BYTES)
    desc_buf[0:4] = b"\x01\x71\x52\x0B" # DR11 Magic
    desc_buf[4] = 0x04 # ML-DSA-44
    desc_buf[5] = 0x01 # KeyGen
    desc_buf[6] = 0x0B # DR11
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
            token_noise_slots=TOKEN_NOISE_BYTES,
            token_row0_slots=TOKEN_ROW0_BYTES,
            token_row1_slots=TOKEN_ROW1_BYTES,
            token_row2_slots=TOKEN_ROW2_BYTES,
            token_row3_slots=TOKEN_ROW3_BYTES,
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
        raise RuntimeError(f"ML-DSA-44 KeyGen failed on silicon with status {status}")

    pk = raw_output[20 : 20 + 1312]
    sk = raw_output[1332 : 1332 + 2560]
    return pk, sk


__all__ = [
    "BACKEND_LABEL",
    "DESCRIPTOR_BYTES",
    "KERNEL_REL_PATH",
    "NativeBackendUnavailable",
    "REQ_BYTES",
    "RESULT_BYTES",
    "TOKEN_NOISE_BYTES",
    "TOKEN_ROW0_BYTES",
    "TOKEN_ROW1_BYTES",
    "TOKEN_ROW2_BYTES",
    "TOKEN_ROW3_BYTES",
    "check_emulation_and_redirection_excluded",
    "get_kernel_artifact_info",
    "require_hardware_runtime",
    "run_mldsa44_keygen",
]
