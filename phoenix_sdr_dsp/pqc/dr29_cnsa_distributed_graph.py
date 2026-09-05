# SPDX-License-Identifier: Apache-2.0
"""Computational Graph & Hardware Dispatch Orchestrator for Milestone DR29:
NSA CNSA 2.0 Level 5 Multi-Tile Distributed Memory Engine on AMD Phoenix AIE2.
"""

import hashlib
import os
from pathlib import Path
import struct
import time
from typing import Any, Tuple, Dict, List

import numpy as np

from .dr29_cnsa_distributed_abi import (
    MAGIC_DESC_DR29,
    CNSA_ALGO_MLDSA87,
    CNSA_ALGO_MLKEM1024,
    MODE_DISTRIBUTED_PARTITION,
    MODE_DISTRIBUTED_ROW_ACCUM,
    MODE_CLUSTER_AGGREGATE,
    pack_dr29_descriptor,
)

BACKEND_LABEL = "dr29-cnsa-distributed:silicon"
KERNEL_REL_PATH = "phoenix_sdr_dsp/pqc/kernels/dr29_cnsa_distributed_service.cc"
_PROGRAM: Any | None = None

REQ_BYTES = 16384  # Sized for 7 polys * 1024 B + 7 polys * 1024 B = 14336 B
DESCRIPTOR_BYTES = 32
RESULT_BYTES = 8192

Q_MLDSA = 8380417
Q_MLKEM = 3329


class NativeBackendUnavailable(RuntimeError):
    """The native IRON/XRT DR29 backend is unavailable or failed closed."""


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
        raise NativeBackendUnavailable("DR29 physical silicon requires XRT device(0)") from exc


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
            "DR29 requires MLIR-AIE/IRON 1.4.1, XRT, and an XRT-visible Phoenix NPU."
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
    def dr29_cnsa_distributed_program(
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

        of_request = ObjectFifo(request_ty, name="dr29_request")
        of_descriptor = ObjectFifo(descriptor_ty, name="dr29_descriptor")
        of_result = ObjectFifo(result_ty, name="dr29_result")

        kernel_path = Path(__file__).resolve().parent / "kernels"
        service_fn = ExternalFunction(
            "dr29_cnsa_distributed_service",
            source_file=str(kernel_path / "dr29_cnsa_distributed_service.cc"),
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

    _PROGRAM = dr29_cnsa_distributed_program
    return _PROGRAM


# =========================================================================
# Hardware Dispatch Operations on AMD Phoenix AIE2
# =========================================================================

def _dispatch_dr29(desc_bytes: bytes, req_buf: bytearray) -> Tuple[bytes, float]:
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
        raise RuntimeError(f"DR29 hardware error status: {status}")

    return raw_res, dt_ms


def query_partition_info_on_aie2(
    algo_type: int,
    tile_index: int,
    num_tiles: int = 4,
    epoch: int = 1,
) -> Tuple[Dict[str, int], float]:
    """Queries cluster distributed memory partition metrics on AIE2."""
    desc_bytes = pack_dr29_descriptor(
        operation_mode=MODE_DISTRIBUTED_PARTITION,
        algo_type=algo_type,
        tile_index=tile_index,
        num_tiles=num_tiles,
        epoch=epoch,
    )
    req_buf = bytearray(REQ_BYTES)
    raw_res, dt_ms = _dispatch_dr29(desc_bytes, req_buf)

    fields = struct.unpack_from("<IIIIIIIIII", raw_res, 16)
    info = {
        "algo_type": fields[0],
        "tile_index": fields[1],
        "start_row": fields[2],
        "num_rows": fields[3],
        "row_length": fields[4],
        "polys_on_tile": fields[5],
        "matrix_bytes": fields[6],
        "vector_bytes": fields[7],
        "total_sram_kb": fields[8],
        "is_under_44kb_bound": bool(fields[9]),
    }
    return info, dt_ms


def compute_row_accum_on_aie2(
    algo_type: int,
    matrix_row: np.ndarray,
    vector_s: np.ndarray,
    epoch: int = 1,
) -> Tuple[np.ndarray, float]:
    """Performs distributed row accumulation on AIE2."""
    desc_bytes = pack_dr29_descriptor(
        operation_mode=MODE_DISTRIBUTED_ROW_ACCUM,
        algo_type=algo_type,
        epoch=epoch,
    )
    req_buf = bytearray(REQ_BYTES)
    m_bytes = matrix_row.tobytes()
    s_bytes = vector_s.tobytes()
    req_buf[0:len(m_bytes)] = m_bytes
    if algo_type == CNSA_ALGO_MLKEM1024:
        req_buf[2048:2048 + len(s_bytes)] = s_bytes
        raw_res, dt_ms = _dispatch_dr29(desc_bytes, req_buf)
        res_poly = np.frombuffer(raw_res[16:16 + 512], dtype=np.uint16).copy()
    else:
        req_buf[7168:7168 + len(s_bytes)] = s_bytes
        raw_res, dt_ms = _dispatch_dr29(desc_bytes, req_buf)
        res_poly = np.frombuffer(raw_res[16:16 + 1024], dtype=np.uint32).copy()

    return res_poly, dt_ms


def aggregate_cluster_on_aie2(
    algo_type: int,
    partial_polys: List[np.ndarray],
    epoch: int = 1,
) -> Tuple[np.ndarray, float]:
    """Aggregates multi-tile partial vectors on AIE2."""
    desc_bytes = pack_dr29_descriptor(
        operation_mode=MODE_CLUSTER_AGGREGATE,
        algo_type=algo_type,
        epoch=epoch,
    )
    req_buf = bytearray(REQ_BYTES)
    offset = 0
    for p in partial_polys[:4]:
        pb = p.tobytes()
        req_buf[offset:offset + len(pb)] = pb
        offset += len(pb)

    raw_res, dt_ms = _dispatch_dr29(desc_bytes, req_buf)
    if algo_type == CNSA_ALGO_MLKEM1024:
        res_poly = np.frombuffer(raw_res[16:16 + 512], dtype=np.uint16).copy()
    else:
        res_poly = np.frombuffer(raw_res[16:16 + 1024], dtype=np.uint32).copy()

    return res_poly, dt_ms


# =========================================================================
# Independent Host Reference Oracles
# =========================================================================

def ref_compute_partition_info(algo_type: int, tile_index: int, num_tiles: int = 4) -> Dict[str, Any]:
    if algo_type == CNSA_ALGO_MLDSA87:
        k = 8
        l = 7
        rows_per_tile = k // num_tiles
        polys = rows_per_tile * l
        m_bytes = polys * 256 * 4
        v_bytes = l * 256 * 4
        total_kb = (m_bytes + v_bytes + (rows_per_tile * 256 * 4) + 1023) // 1024
        return {
            "algo_type": algo_type,
            "tile_index": tile_index,
            "start_row": tile_index * rows_per_tile,
            "num_rows": rows_per_tile,
            "row_length": l,
            "polys_on_tile": polys,
            "matrix_bytes": m_bytes,
            "vector_bytes": v_bytes,
            "total_sram_kb": total_kb,
            "is_under_44kb_bound": total_kb <= 44,
        }
    else:
        k = 4
        l = 4
        rows_per_tile = k // num_tiles
        polys = rows_per_tile * l
        m_bytes = polys * 256 * 2
        v_bytes = l * 256 * 2
        total_kb = (m_bytes + v_bytes + (rows_per_tile * 256 * 2) + 1023) // 1024
        return {
            "algo_type": algo_type,
            "tile_index": tile_index,
            "start_row": tile_index * rows_per_tile,
            "num_rows": rows_per_tile,
            "row_length": l,
            "polys_on_tile": polys,
            "matrix_bytes": m_bytes,
            "vector_bytes": v_bytes,
            "total_sram_kb": total_kb,
            "is_under_44kb_bound": total_kb <= 44,
        }


def ref_compute_row_accum(algo_type: int, matrix_row: np.ndarray, vector_s: np.ndarray) -> np.ndarray:
    if algo_type == CNSA_ALGO_MLDSA87:
        # matrix_row: shape (7, 256), vector_s: shape (7, 256)
        m = matrix_row.astype(np.int64)
        s = vector_s.astype(np.int64)
        prod = (m * s) % Q_MLDSA
        accum = np.sum(prod, axis=0) % Q_MLDSA
        return accum.astype(np.uint32)
    else:
        m = matrix_row.astype(np.int64)
        s = vector_s.astype(np.int64)
        prod = (m * s) % Q_MLKEM
        accum = np.sum(prod, axis=0) % Q_MLKEM
        return accum.astype(np.uint16)


def ref_aggregate_cluster(algo_type: int, partial_polys: List[np.ndarray]) -> np.ndarray:
    q = Q_MLDSA if algo_type == CNSA_ALGO_MLDSA87 else Q_MLKEM
    dtype = np.uint32 if algo_type == CNSA_ALGO_MLDSA87 else np.uint16
    stacked = np.array(partial_polys[:4], dtype=np.int64)
    total = np.sum(stacked, axis=0) % q
    return total.astype(dtype)
