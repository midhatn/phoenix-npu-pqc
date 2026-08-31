# SPDX-License-Identifier: Apache-2.0
"""DR10 Entropy/Key-Source & Sealed-Lifecycle Graph on AMD Phoenix AIE2."""

import hashlib
import os
from pathlib import Path
from typing import Any
import numpy as np

from . import dr10_sealed_lifecycle_abi as abi

BACKEND_LABEL = "dr10-sealed-lifecycle:silicon"
KERNEL_REL_PATH = "phoenix_sdr_dsp/pqc/kernels/dr10_sealed_lifecycle_service.cc"
_PROGRAM: Any | None = None

REQ_BYTES = 256
DESCRIPTOR_BYTES = 16
RESULT_BYTES = 64


class NativeBackendUnavailable(RuntimeError):
    """The native IRON/XRT DR10 backend is unavailable or failed closed."""


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
        raise NativeBackendUnavailable("DR10 physical silicon requires XRT device(0)") from exc


def get_kernel_artifact_info(repo_root: Path | None = None) -> dict[str, Any]:
    """Return verified path and SHA-256 digest of the DR10 AIE2 kernel source."""
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
            "DR10 requires MLIR-AIE/IRON 1.4.1, XRT, and an XRT-visible Phoenix NPU."
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
    def dr10_program(
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

        of_request = ObjectFifo(request_ty, name="dr10_request")
        of_descriptor = ObjectFifo(descriptor_ty, name="dr10_descriptor")
        of_result = ObjectFifo(result_ty, name="dr10_result")

        kernel_path = Path(__file__).resolve().parent / "kernels"
        lifecycle_fn = ExternalFunction(
            "dr10_sealed_lifecycle_service",
            source_file=str(kernel_path / "dr10_sealed_lifecycle_service.cc"),
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
            fn_args=[of_request.cons(), of_descriptor.cons(), of_result.prod(), lifecycle_fn],
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

    _PROGRAM = dr10_program
    return _PROGRAM

def run_dr10_service(req_bytes: bytes, desc_bytes: bytes) -> tuple[int, int, int, int]:
    """Execute DR10 lifecycle service on physical Phoenix NPU.
    Returns: (request_id, status, active_slot, crc32)
    """
    *_, XRTTensor = _load_iron()

    req_np = np.frombuffer(req_bytes, dtype=np.uint8).copy()
    desc_np = np.frombuffer(desc_bytes, dtype=np.uint8).copy()
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

    req_id = int.from_bytes(raw_output[4:8], "little")
    status = int.from_bytes(raw_output[8:12], "little")
    active_slot = int.from_bytes(raw_output[12:16], "little")
    crc = int.from_bytes(raw_output[16:20], "little")
    return req_id, status, active_slot, crc


__all__ = [
    "BACKEND_LABEL",
    "DESCRIPTOR_BYTES",
    "KERNEL_REL_PATH",
    "NativeBackendUnavailable",
    "REQ_BYTES",
    "RESULT_BYTES",
    "check_emulation_and_redirection_excluded",
    "get_kernel_artifact_info",
    "require_hardware_runtime",
    "run_dr10_service",
]
