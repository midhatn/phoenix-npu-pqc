# SPDX-License-Identifier: Apache-2.0
"""Computational Graph & Hardware Dispatch Orchestrator for Milestone DR26:
AMD XDNA 2 & AMD Alveo V70 Multi-Architecture Scaling on AMD Phoenix AIE2.
"""

import hashlib
import os
from pathlib import Path
import struct
import time
from typing import Any, Tuple, Dict, List

import numpy as np

from .dr26_multi_arch_abi import (
    MAGIC_DESC_DR26,
    ARCH_PHOENIX_XDNA1,
    ARCH_STRIX_XDNA2,
    ARCH_ALVEO_V70,
    MODE_QUERY_ARCH_TOPOLOGY,
    MODE_VALIDATE_GRID_FIT,
    MODE_PARTITION_COLUMNS,
    MODE_EMIT_MLIR_TOPOLOGY,
    ARCH_SPECS,
    pack_dr26_descriptor,
)

BACKEND_LABEL = "dr26-multi-arch:silicon"
KERNEL_REL_PATH = "phoenix_sdr_dsp/pqc/kernels/dr26_multi_arch_service.cc"
_PROGRAM: Any | None = None

REQ_BYTES = 8192
DESCRIPTOR_BYTES = 32
RESULT_BYTES = 8192


class NativeBackendUnavailable(RuntimeError):
    """The native IRON/XRT DR26 backend is unavailable or failed closed."""


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
        raise NativeBackendUnavailable("DR26 physical silicon requires XRT device(0)") from exc


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
            "DR26 requires MLIR-AIE/IRON 1.4.1, XRT, and an XRT-visible Phoenix NPU."
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
    def dr26_multi_arch_program(
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

        of_request = ObjectFifo(request_ty, name="dr26_request")
        of_descriptor = ObjectFifo(descriptor_ty, name="dr26_descriptor")
        of_result = ObjectFifo(result_ty, name="dr26_result")

        kernel_path = Path(__file__).resolve().parent / "kernels"
        service_fn = ExternalFunction(
            "dr26_multi_arch_service",
            source_file=str(kernel_path / "dr26_multi_arch_service.cc"),
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

    _PROGRAM = dr26_multi_arch_program
    return _PROGRAM


# =========================================================================
# Hardware Dispatch Operations on AMD Phoenix AIE2
# =========================================================================

def _dispatch_dr26(desc_bytes: bytes, req_buf: bytearray) -> Tuple[bytes, float]:
    require_hardware_runtime()
    *_, XRTTensor = _load_iron()

    desc_np = np.frombuffer(desc_bytes, dtype=np.uint8).copy()
    req_np = np.frombuffer(req_buf, dtype=np.uint8).copy()
    res_np = np.zeros(RESULT_BYTES, dtype=np.uint8)

    req_t = XRTTensor(req_np, dtype=np.uint8)
    desc_t = XRTTensor(desc_np, dtype=np.uint8)
    res_t = XRTTensor(res_np, dtype=np.uint8)

    t0 = time.perf_counter()
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

    dt_ms = (time.perf_counter() - t0) * 1000
    raw_res = bytes(res_t._data[:RESULT_BYTES])
    _clear_host_staging(res_np, res_t)

    status = struct.unpack_from("<I", raw_res, 8)[0]
    if status != 0:
        raise RuntimeError(f"DR26 hardware error status: {status}")

    return raw_res, dt_ms


def query_arch_topology_on_aie2(target_arch: int, epoch: int = 1) -> Tuple[Dict[str, int], float]:
    """Queries architecture geometry on target AIE2 device."""
    desc_bytes = pack_dr26_descriptor(
        operation_mode=MODE_QUERY_ARCH_TOPOLOGY,
        target_arch=target_arch,
        epoch=epoch,
    )
    req_buf = bytearray(REQ_BYTES)
    raw_res, dt_ms = _dispatch_dr26(desc_bytes, req_buf)

    rows, cols, total_tiles, dma_channels, sram_kb, prog_kb, peak_tops = struct.unpack_from(
        "<IIIIIII", raw_res, 16
    )
    geom = {
        "rows": rows,
        "cols": cols,
        "total_tiles": total_tiles,
        "dma_channels_per_col": dma_channels,
        "sram_per_tile_kb": sram_kb,
        "prog_mem_per_tile_kb": prog_kb,
        "peak_tops": peak_tops,
    }
    return geom, dt_ms


def validate_grid_fit_on_aie2(target_arch: int, req_tiles: int, epoch: int = 1) -> Tuple[bool, int, float]:
    """Validates spatial fit on target architecture on AIE2."""
    desc_bytes = pack_dr26_descriptor(
        operation_mode=MODE_VALIDATE_GRID_FIT,
        target_arch=target_arch,
        requested_tiles=req_tiles,
        epoch=epoch,
    )
    req_buf = bytearray(REQ_BYTES)
    raw_res, dt_ms = _dispatch_dr26(desc_bytes, req_buf)

    is_valid, max_concurrent = struct.unpack_from("<II", raw_res, 16)
    return bool(is_valid), max_concurrent, dt_ms


def partition_columns_on_aie2(target_arch: int, requested_instances: int, epoch: int = 1) -> Tuple[List[Tuple[int, int]], float]:
    """Computes column partition layout across concurrent instances on AIE2."""
    desc_bytes = pack_dr26_descriptor(
        operation_mode=MODE_PARTITION_COLUMNS,
        target_arch=target_arch,
        requested_tiles=requested_instances,
        epoch=epoch,
    )
    req_buf = bytearray(REQ_BYTES)
    raw_res, dt_ms = _dispatch_dr26(desc_bytes, req_buf)

    actual_instances = struct.unpack_from("<I", raw_res, 16)[0]
    partitions = []
    for i in range(actual_instances):
        start_col, num_cols = struct.unpack_from("<II", raw_res, 20 + 8 * i)
        partitions.append((start_col, num_cols))
    return partitions, dt_ms


def emit_mlir_topology_on_aie2(target_arch: int, epoch: int = 1) -> Tuple[Dict[str, int], float]:
    """Emits multi-target MLIR device topology vector on AIE2."""
    desc_bytes = pack_dr26_descriptor(
        operation_mode=MODE_EMIT_MLIR_TOPOLOGY,
        target_arch=target_arch,
        epoch=epoch,
    )
    req_buf = bytearray(REQ_BYTES)
    raw_res, dt_ms = _dispatch_dr26(desc_bytes, req_buf)

    magic, arch_id, rows, cols, total_tiles, shim_rows, total_dma = struct.unpack_from(
        "<IIIIIII", raw_res, 16
    )
    topo = {
        "magic": magic,
        "arch_id": arch_id,
        "rows": rows,
        "cols": cols,
        "total_tiles": total_tiles,
        "shim_rows": shim_rows,
        "total_dma_streams": total_dma,
    }
    return topo, dt_ms


# =========================================================================
# Independent Host Reference Oracles
# =========================================================================

def ref_query_arch_topology(target_arch: int) -> Dict[str, int]:
    spec = ARCH_SPECS.get(target_arch, ARCH_SPECS[ARCH_PHOENIX_XDNA1])
    return {
        "rows": spec.rows,
        "cols": spec.cols,
        "total_tiles": spec.total_tiles,
        "dma_channels_per_col": spec.dma_channels_per_col,
        "sram_per_tile_kb": spec.sram_per_tile_kb,
        "prog_mem_per_tile_kb": spec.prog_mem_per_tile_kb,
        "peak_tops": spec.peak_tops,
    }


def ref_validate_grid_fit(target_arch: int, req_tiles: int) -> Tuple[bool, int]:
    spec = ARCH_SPECS.get(target_arch, ARCH_SPECS[ARCH_PHOENIX_XDNA1])
    if req_tiles <= 0 or req_tiles > spec.total_tiles:
        return False, 0
    return True, spec.total_tiles // req_tiles


def ref_partition_columns(target_arch: int, requested_instances: int) -> List[Tuple[int, int]]:
    spec = ARCH_SPECS.get(target_arch, ARCH_SPECS[ARCH_PHOENIX_XDNA1])
    instances = max(1, min(requested_instances, spec.cols))
    cols_per_instance = spec.cols // instances
    remainder = spec.cols % instances

    partitions = []
    cur_col = 0
    for i in range(instances):
        num = cols_per_instance + (1 if i < remainder else 0)
        partitions.append((cur_col, num))
        cur_col += num
    return partitions


def ref_emit_mlir_topology(target_arch: int) -> Dict[str, int]:
    spec = ARCH_SPECS.get(target_arch, ARCH_SPECS[ARCH_PHOENIX_XDNA1])
    shim_rows = 2 if target_arch == ARCH_ALVEO_V70 else 1
    return {
        "magic": 0x4D4C4952,
        "arch_id": target_arch,
        "rows": spec.rows,
        "cols": spec.cols,
        "total_tiles": spec.total_tiles,
        "shim_rows": shim_rows,
        "total_dma_streams": spec.dma_channels_per_col * spec.cols,
    }
