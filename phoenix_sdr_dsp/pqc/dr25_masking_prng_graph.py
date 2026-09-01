# SPDX-License-Identifier: Apache-2.0
"""Computational Graph & Hardware Dispatch Orchestrator for Milestone DR25:
Higher-Order Masking & On-Chip Local PRNG Entropy Expansion on AMD Phoenix AIE2.
"""

import hashlib
import os
from pathlib import Path
import struct
import time
from typing import Any, Tuple

import numpy as np

from .dr25_masking_prng_abi import (
    MAGIC_DESC_DR25,
    MODE_PRNG_EXPAND,
    MODE_MASK_1ST_ORDER,
    MODE_MASK_2ND_ORDER,
    MODE_UNMASK_1ST_ORDER,
    MODE_UNMASK_2ND_ORDER,
    MODE_MASKED_ADD_1ST,
    MODE_MASKED_ADD_2ND,
    MODE_SNI_REFRESH_1ST,
    MODE_SNI_REFRESH_2ND,
    MODULUS_MLKEM,
    pack_dr25_descriptor,
)

BACKEND_LABEL = "dr25-masking-prng:silicon"
KERNEL_REL_PATH = "phoenix_sdr_dsp/pqc/kernels/dr25_masking_prng_service.cc"
_PROGRAM: Any | None = None

REQ_BYTES = 8192
DESCRIPTOR_BYTES = 32
RESULT_BYTES = 8192


class NativeBackendUnavailable(RuntimeError):
    """The native IRON/XRT DR25 backend is unavailable or failed closed."""


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
        raise NativeBackendUnavailable("DR25 physical silicon requires XRT device(0)") from exc


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
            "DR25 requires MLIR-AIE/IRON 1.4.1, XRT, and an XRT-visible Phoenix NPU."
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
    def dr25_masking_prng_program(
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

        of_request = ObjectFifo(request_ty, name="dr25_request")
        of_descriptor = ObjectFifo(descriptor_ty, name="dr25_descriptor")
        of_result = ObjectFifo(result_ty, name="dr25_result")

        kernel_path = Path(__file__).resolve().parent / "kernels"
        service_fn = ExternalFunction(
            "dr25_masking_prng_service",
            source_file=str(kernel_path / "dr25_masking_prng_service.cc"),
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

    _PROGRAM = dr25_masking_prng_program
    return _PROGRAM


# =========================================================================
# Hardware Dispatch Operations on AMD Phoenix AIE2
# =========================================================================

def _dispatch_dr25(desc_bytes: bytes, req_buf: bytearray) -> Tuple[bytes, float]:
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
        raise RuntimeError(f"DR25 hardware error status: {status}")

    return raw_res, dt_ms


def prng_expand_mask_on_aie2(
    seed: bytes,
    domain_sep: int,
    modulus: int = MODULUS_MLKEM,
    num_coeffs: int = 256,
    epoch: int = 1,
) -> Tuple[np.ndarray, float]:
    """Generates uniform polynomial mask using on-tile FIPS 202 SHAKE-128 PRNG."""
    desc_bytes = pack_dr25_descriptor(
        operation_mode=MODE_PRNG_EXPAND,
        modulus=modulus,
        num_coeffs=num_coeffs,
        epoch=epoch,
    )
    req_buf = bytearray(REQ_BYTES)
    req_buf[0:32] = seed[:32]
    struct.pack_into("<I", req_buf, 32, domain_sep)

    raw_res, dt_ms = _dispatch_dr25(desc_bytes, req_buf)
    poly = np.frombuffer(raw_res[16:16 + num_coeffs * 2], dtype=np.uint16).copy()
    return poly, dt_ms


def mask_1st_order_on_aie2(
    s: np.ndarray,
    mask: np.ndarray,
    modulus: int = MODULUS_MLKEM,
    epoch: int = 1,
) -> Tuple[np.ndarray, np.ndarray, float]:
    """Performs 1st-order polynomial blinding into 2 shares on AIE2."""
    num_coeffs = len(s)
    poly_bytes = num_coeffs * 2
    desc_bytes = pack_dr25_descriptor(
        operation_mode=MODE_MASK_1ST_ORDER,
        modulus=modulus,
        num_coeffs=num_coeffs,
        epoch=epoch,
    )
    req_buf = bytearray(REQ_BYTES)
    req_buf[0:poly_bytes] = s.astype(np.uint16).tobytes()
    req_buf[poly_bytes:2 * poly_bytes] = mask.astype(np.uint16).tobytes()

    raw_res, dt_ms = _dispatch_dr25(desc_bytes, req_buf)
    s0 = np.frombuffer(raw_res[16:16 + poly_bytes], dtype=np.uint16).copy()
    s1 = np.frombuffer(raw_res[16 + poly_bytes:16 + 2 * poly_bytes], dtype=np.uint16).copy()
    return s0, s1, dt_ms


def mask_2nd_order_on_aie2(
    s: np.ndarray,
    mask1: np.ndarray,
    mask2: np.ndarray,
    modulus: int = MODULUS_MLKEM,
    epoch: int = 1,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, float]:
    """Performs 2nd-order polynomial blinding into 3 shares on AIE2."""
    num_coeffs = len(s)
    poly_bytes = num_coeffs * 2
    desc_bytes = pack_dr25_descriptor(
        operation_mode=MODE_MASK_2ND_ORDER,
        modulus=modulus,
        num_coeffs=num_coeffs,
        epoch=epoch,
    )
    req_buf = bytearray(REQ_BYTES)
    req_buf[0:poly_bytes] = s.astype(np.uint16).tobytes()
    req_buf[poly_bytes:2 * poly_bytes] = mask1.astype(np.uint16).tobytes()
    req_buf[2 * poly_bytes:3 * poly_bytes] = mask2.astype(np.uint16).tobytes()

    raw_res, dt_ms = _dispatch_dr25(desc_bytes, req_buf)
    s0 = np.frombuffer(raw_res[16:16 + poly_bytes], dtype=np.uint16).copy()
    s1 = np.frombuffer(raw_res[16 + poly_bytes:16 + 2 * poly_bytes], dtype=np.uint16).copy()
    s2 = np.frombuffer(raw_res[16 + 2 * poly_bytes:16 + 3 * poly_bytes], dtype=np.uint16).copy()
    return s0, s1, s2, dt_ms


def unmask_1st_order_on_aie2(
    s0: np.ndarray,
    s1: np.ndarray,
    modulus: int = MODULUS_MLKEM,
    epoch: int = 1,
) -> Tuple[np.ndarray, float]:
    """Unmasks 1st-order shares on AIE2."""
    num_coeffs = len(s0)
    poly_bytes = num_coeffs * 2
    desc_bytes = pack_dr25_descriptor(
        operation_mode=MODE_UNMASK_1ST_ORDER,
        modulus=modulus,
        num_coeffs=num_coeffs,
        epoch=epoch,
    )
    req_buf = bytearray(REQ_BYTES)
    req_buf[0:poly_bytes] = s0.astype(np.uint16).tobytes()
    req_buf[poly_bytes:2 * poly_bytes] = s1.astype(np.uint16).tobytes()

    raw_res, dt_ms = _dispatch_dr25(desc_bytes, req_buf)
    s = np.frombuffer(raw_res[16:16 + poly_bytes], dtype=np.uint16).copy()
    return s, dt_ms


def unmask_2nd_order_on_aie2(
    s0: np.ndarray,
    s1: np.ndarray,
    s2: np.ndarray,
    modulus: int = MODULUS_MLKEM,
    epoch: int = 1,
) -> Tuple[np.ndarray, float]:
    """Unmasks 2nd-order shares on AIE2."""
    num_coeffs = len(s0)
    poly_bytes = num_coeffs * 2
    desc_bytes = pack_dr25_descriptor(
        operation_mode=MODE_UNMASK_2ND_ORDER,
        modulus=modulus,
        num_coeffs=num_coeffs,
        epoch=epoch,
    )
    req_buf = bytearray(REQ_BYTES)
    req_buf[0:poly_bytes] = s0.astype(np.uint16).tobytes()
    req_buf[poly_bytes:2 * poly_bytes] = s1.astype(np.uint16).tobytes()
    req_buf[2 * poly_bytes:3 * poly_bytes] = s2.astype(np.uint16).tobytes()

    raw_res, dt_ms = _dispatch_dr25(desc_bytes, req_buf)
    s = np.frombuffer(raw_res[16:16 + poly_bytes], dtype=np.uint16).copy()
    return s, dt_ms


def masked_add_1st_order_on_aie2(
    a0: np.ndarray, a1: np.ndarray,
    b0: np.ndarray, b1: np.ndarray,
    modulus: int = MODULUS_MLKEM,
    epoch: int = 1,
) -> Tuple[np.ndarray, np.ndarray, float]:
    """Component-wise 1st-order masked polynomial addition on AIE2."""
    num_coeffs = len(a0)
    poly_bytes = num_coeffs * 2
    desc_bytes = pack_dr25_descriptor(
        operation_mode=MODE_MASKED_ADD_1ST,
        modulus=modulus,
        num_coeffs=num_coeffs,
        epoch=epoch,
    )
    req_buf = bytearray(REQ_BYTES)
    req_buf[0:poly_bytes] = a0.astype(np.uint16).tobytes()
    req_buf[poly_bytes:2 * poly_bytes] = a1.astype(np.uint16).tobytes()
    req_buf[2 * poly_bytes:3 * poly_bytes] = b0.astype(np.uint16).tobytes()
    req_buf[3 * poly_bytes:4 * poly_bytes] = b1.astype(np.uint16).tobytes()

    raw_res, dt_ms = _dispatch_dr25(desc_bytes, req_buf)
    c0 = np.frombuffer(raw_res[16:16 + poly_bytes], dtype=np.uint16).copy()
    c1 = np.frombuffer(raw_res[16 + poly_bytes:16 + 2 * poly_bytes], dtype=np.uint16).copy()
    return c0, c1, dt_ms


def sni_refresh_1st_order_on_aie2(
    s0: np.ndarray,
    s1: np.ndarray,
    r: np.ndarray,
    modulus: int = MODULUS_MLKEM,
    epoch: int = 1,
) -> Tuple[np.ndarray, np.ndarray, float]:
    """Strong Non-Interfering (SNI) 1st-order share refresh on AIE2."""
    num_coeffs = len(s0)
    poly_bytes = num_coeffs * 2
    desc_bytes = pack_dr25_descriptor(
        operation_mode=MODE_SNI_REFRESH_1ST,
        modulus=modulus,
        num_coeffs=num_coeffs,
        epoch=epoch,
    )
    req_buf = bytearray(REQ_BYTES)
    req_buf[0:poly_bytes] = s0.astype(np.uint16).tobytes()
    req_buf[poly_bytes:2 * poly_bytes] = s1.astype(np.uint16).tobytes()
    req_buf[2 * poly_bytes:3 * poly_bytes] = r.astype(np.uint16).tobytes()

    raw_res, dt_ms = _dispatch_dr25(desc_bytes, req_buf)
    out_s0 = np.frombuffer(raw_res[16:16 + poly_bytes], dtype=np.uint16).copy()
    out_s1 = np.frombuffer(raw_res[16 + poly_bytes:16 + 2 * poly_bytes], dtype=np.uint16).copy()
    return out_s0, out_s1, dt_ms


def sni_refresh_2nd_order_on_aie2(
    s0: np.ndarray,
    s1: np.ndarray,
    s2: np.ndarray,
    r01: np.ndarray,
    r02: np.ndarray,
    r12: np.ndarray,
    modulus: int = MODULUS_MLKEM,
    epoch: int = 1,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, float]:
    """Strong Non-Interfering (SNI) 2nd-order share refresh on AIE2."""
    num_coeffs = len(s0)
    poly_bytes = num_coeffs * 2
    desc_bytes = pack_dr25_descriptor(
        operation_mode=MODE_SNI_REFRESH_2ND,
        modulus=modulus,
        num_coeffs=num_coeffs,
        epoch=epoch,
    )
    req_buf = bytearray(REQ_BYTES)
    req_buf[0:poly_bytes] = s0.astype(np.uint16).tobytes()
    req_buf[poly_bytes:2 * poly_bytes] = s1.astype(np.uint16).tobytes()
    req_buf[2 * poly_bytes:3 * poly_bytes] = s2.astype(np.uint16).tobytes()
    req_buf[3 * poly_bytes:4 * poly_bytes] = r01.astype(np.uint16).tobytes()
    req_buf[4 * poly_bytes:5 * poly_bytes] = r02.astype(np.uint16).tobytes()
    req_buf[5 * poly_bytes:6 * poly_bytes] = r12.astype(np.uint16).tobytes()

    raw_res, dt_ms = _dispatch_dr25(desc_bytes, req_buf)
    out_s0 = np.frombuffer(raw_res[16:16 + poly_bytes], dtype=np.uint16).copy()
    out_s1 = np.frombuffer(raw_res[16 + poly_bytes:16 + 2 * poly_bytes], dtype=np.uint16).copy()
    out_s2 = np.frombuffer(raw_res[16 + 2 * poly_bytes:16 + 3 * poly_bytes], dtype=np.uint16).copy()
    return out_s0, out_s1, out_s2, dt_ms


# =========================================================================
# Independent Host Reference Oracles
# =========================================================================

def _ref_shake128(data: bytes, outlen: int) -> bytes:
    h = hashlib.shake_128()
    h.update(data)
    return h.digest(outlen)


def ref_prng_expand_mask(
    seed: bytes,
    domain_sep: int,
    modulus: int = MODULUS_MLKEM,
    num_coeffs: int = 256,
) -> np.ndarray:
    raw_input = seed[:32] + struct.pack("<I", domain_sep)
    raw_bytes = _ref_shake128(raw_input, num_coeffs * 2)
    poly = np.zeros(num_coeffs, dtype=np.uint16)
    for i in range(num_coeffs):
        val = raw_bytes[2 * i] | (raw_bytes[2 * i + 1] << 8)
        poly[i] = val % modulus
    return poly


def ref_mask_1st_order(
    s: np.ndarray,
    mask: np.ndarray,
    modulus: int = MODULUS_MLKEM,
) -> Tuple[np.ndarray, np.ndarray]:
    s0 = (s + modulus - mask) % modulus
    s1 = mask % modulus
    return s0.astype(np.uint16), s1.astype(np.uint16)


def ref_mask_2nd_order(
    s: np.ndarray,
    mask1: np.ndarray,
    mask2: np.ndarray,
    modulus: int = MODULUS_MLKEM,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    s0 = (s + 2 * modulus - mask1 - mask2) % modulus
    s1 = mask1 % modulus
    s2 = mask2 % modulus
    return s0.astype(np.uint16), s1.astype(np.uint16), s2.astype(np.uint16)


def ref_unmask_1st_order(
    s0: np.ndarray,
    s1: np.ndarray,
    modulus: int = MODULUS_MLKEM,
) -> np.ndarray:
    return ((s0.astype(np.uint32) + s1.astype(np.uint32)) % modulus).astype(np.uint16)


def ref_unmask_2nd_order(
    s0: np.ndarray,
    s1: np.ndarray,
    s2: np.ndarray,
    modulus: int = MODULUS_MLKEM,
) -> np.ndarray:
    return ((s0.astype(np.uint32) + s1.astype(np.uint32) + s2.astype(np.uint32)) % modulus).astype(np.uint16)


def ref_masked_add_1st(
    a0: np.ndarray, a1: np.ndarray,
    b0: np.ndarray, b1: np.ndarray,
    modulus: int = MODULUS_MLKEM,
) -> Tuple[np.ndarray, np.ndarray]:
    c0 = (a0.astype(np.uint32) + b0.astype(np.uint32)) % modulus
    c1 = (a1.astype(np.uint32) + b1.astype(np.uint32)) % modulus
    return c0.astype(np.uint16), c1.astype(np.uint16)


def ref_sni_refresh_1st(
    s0: np.ndarray,
    s1: np.ndarray,
    r: np.ndarray,
    modulus: int = MODULUS_MLKEM,
) -> Tuple[np.ndarray, np.ndarray]:
    out_s0 = (s0.astype(np.uint32) + r.astype(np.uint32)) % modulus
    out_s1 = (s1.astype(np.uint32) + modulus - (r.astype(np.uint32) % modulus)) % modulus
    return out_s0.astype(np.uint16), out_s1.astype(np.uint16)


def ref_sni_refresh_2nd(
    s0: np.ndarray,
    s1: np.ndarray,
    s2: np.ndarray,
    r01: np.ndarray,
    r02: np.ndarray,
    r12: np.ndarray,
    modulus: int = MODULUS_MLKEM,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    m01 = r01.astype(np.uint32) % modulus
    m02 = r02.astype(np.uint32) % modulus
    m12 = r12.astype(np.uint32) % modulus

    out_s0 = (s0.astype(np.uint32) + m01 + m02) % modulus
    out_s1 = (s1.astype(np.uint32) + modulus - m01 + m12) % modulus
    out_s2 = (s2.astype(np.uint32) + 2 * modulus - m02 - m12) % modulus
    return out_s0.astype(np.uint16), out_s1.astype(np.uint16), out_s2.astype(np.uint16)
