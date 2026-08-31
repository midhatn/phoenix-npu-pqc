"""DR2c terminal-only ML-KEM-512 K-PKE.KeyGen t-hat row graph."""

import hashlib
import os
from pathlib import Path
from typing import Any

import numpy as np

from . import dr2c_mlkem512_keygen_row_abi as abi

BACKEND_LABEL = "dr2c-mlkem512-keygen-row:silicon"
KERNEL_REL_PATH = "phoenix_sdr_dsp/pqc/kernels/dr2c_mlkem512_keygen_row_accumulate.cc"
SERVICE_REL_PATH = "phoenix_sdr_dsp/pqc/kernels/dr2c_mlkem512_keygen_row_expand.cc"
_PROGRAM: Any | None = None


class NativeBackendUnavailable(RuntimeError):
    """The native IRON/XRT DR2c backend is unavailable or failed closed."""


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


def get_kernel_artifact_info(repo_root: Path | None = None) -> dict[str, Any]:
    """Return verified path and SHA-256 digest of the DR2c AIE2 kernel source."""
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
            "DR2c requires MLIR-AIE/IRON 1.4.1, XRT, and an XRT-visible Phoenix NPU; "
            "no host KeyGen-row fallback is available."
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


def require_hardware_runtime() -> None:
    _load_iron()


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
    def dr2c_mlkem512_keygen_row_program(
        seeds_in: In,
        descriptor_in: In,
        result_out: Out,
        *,
        seeds_slots: CompileTime[int],
        descriptor_slots: CompileTime[int],
        row_token_slots: CompileTime[int],
        result_slots: CompileTime[int],
        element_type: CompileTime[type],
    ):
        seeds_ty = np.ndarray[(seeds_slots,), np.dtype[element_type]]
        descriptor_ty = np.ndarray[(descriptor_slots,), np.dtype[element_type]]
        row_token_ty = np.ndarray[(row_token_slots,), np.dtype[element_type]]
        result_ty = np.ndarray[(result_slots,), np.dtype[element_type]]
        of_seeds = ObjectFifo(seeds_ty, name="dr2c_seeds")
        of_descriptor = ObjectFifo(descriptor_ty, name="dr2c_descriptor")
        of_row_token = ObjectFifo(row_token_ty, name="dr2c_row_token")
        of_result = ObjectFifo(result_ty, name="dr2c_result")
        kernel_path = Path(__file__).resolve().parent / "kernels"
        expand = ExternalFunction(
            "dr2c_keygen_row_expand",
            source_file=str(kernel_path / "dr2c_mlkem512_keygen_row_expand.cc"),
            arg_types=[seeds_ty, descriptor_ty, row_token_ty],
            include_dirs=[cxx_header_path(), str(kernel_path)],
        )
        accumulate = ExternalFunction(
            "dr2c_keygen_row_accumulate",
            source_file=str(kernel_path / "dr2c_mlkem512_keygen_row_accumulate.cc"),
            arg_types=[row_token_ty, result_ty],
            include_dirs=[cxx_header_path(), str(kernel_path)],
        )

        def expand_body(of_seeds, of_descriptor, of_row_token, expand):
            seeds = of_seeds.acquire(1)
            descriptor = of_descriptor.acquire(1)
            row_token = of_row_token.acquire(1)
            expand(seeds, descriptor, row_token)
            of_row_token.release(1)
            of_seeds.release(1)
            of_descriptor.release(1)

        def accumulate_body(of_row_token, of_result, accumulate):
            row_token = of_row_token.acquire(1)
            result = of_result.acquire(1)
            accumulate(row_token, result)
            of_row_token.release(1)
            of_result.release(1)

        expand_worker = Worker(
            expand_body,
            fn_args=[
                of_seeds.cons(),
                of_descriptor.cons(),
                of_row_token.prod(),
                expand,
            ],
            stack_size=0x4000,
        )
        accumulate_worker = Worker(
            accumulate_body,
            fn_args=[of_row_token.cons(), of_result.prod(), accumulate],
            stack_size=0x4000,
        )

        def sequence(
            seeds,
            descriptor,
            result,
            seeds_prod,
            descriptor_prod,
            result_cons,
        ):
            seeds_prod.fill(seeds)
            descriptor_prod.fill(descriptor)
            result_cons.drain(result, wait=True)

        runtime = Runtime(
            sequence,
            [
                seeds_ty,
                descriptor_ty,
                result_ty,
                of_seeds.prod(),
                of_descriptor.prod(),
                of_result.cons(),
            ],
        )
        return Program(
            iron.get_current_device(), runtime, workers=[expand_worker, accumulate_worker]
        ).resolve_program()

    _PROGRAM = dr2c_mlkem512_keygen_row_program
    return _PROGRAM


def run_mlkem512_keygen_row(
    rho: bytes | bytearray | memoryview,
    sigma: bytes | bytearray | memoryview,
    row_index: int,
    request_id: int,
) -> list[int]:
    """Return one device-produced canonical t-hat row, or fail closed."""
    seeds_bytes, descriptor_bytes = abi.validate_request(rho, sigma, row_index, request_id)
    seeds_np = np.frombuffer(seeds_bytes, dtype=np.uint8).copy()
    descriptor_np = np.frombuffer(descriptor_bytes, dtype=np.uint8).copy()
    result_np = np.frombuffer(abi.result_sentinel(), dtype=np.uint8).copy()
    *_, XRTTensor = _load_iron()
    seeds_t = XRTTensor(seeds_np, dtype=np.uint8)
    descriptor_t = XRTTensor(descriptor_np, dtype=np.uint8)
    result_t = XRTTensor(result_np, dtype=np.uint8)
    try:
        _program()(
            seeds_t,
            descriptor_t,
            result_t,
            seeds_slots=abi.SEEDS_BYTES,
            descriptor_slots=abi.DESCRIPTOR_BYTES,
            row_token_slots=abi.INTERNAL_TOKEN_BYTES,
            result_slots=abi.RESULT_BYTES,
            element_type=np.uint8,
        )
        result_t.to("cpu")
    except Exception as exc:
        raise NativeBackendUnavailable(
            "DR2c native MLIR-AIE dispatch failed; no KeyGen-row fallback ran."
        ) from exc
    try:
        return abi.parse_result(result_t._data[: abi.RESULT_BYTES], row_index, request_id)
    except abi.Dr2cOperationError:
        raise
    except Exception as exc:
        raise NativeBackendUnavailable(
            "DR2c terminal result failed ABI validation; refusing malformed output."
        ) from exc


run = run_mlkem512_keygen_row
__all__ = [
    "BACKEND_LABEL",
    "KERNEL_REL_PATH",
    "SERVICE_REL_PATH",
    "NativeBackendUnavailable",
    "check_emulation_and_redirection_excluded",
    "get_kernel_artifact_info",
    "require_hardware_runtime",
    "run",
    "run_mlkem512_keygen_row",
]
