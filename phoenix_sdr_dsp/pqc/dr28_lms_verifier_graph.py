# SPDX-License-Identifier: Apache-2.0
"""Computational Graph & Hardware Dispatch Orchestrator for Milestone DR28:
NIST SP 800-208 / RFC 8554 Leighton-Micali Signatures (LMS/HSS) Stateless Verification on AMD Phoenix AIE2.
"""

import hashlib
import os
from pathlib import Path
import struct
import time
from typing import Any, Tuple

import numpy as np

from .dr28_lms_verifier_abi import (
    MAGIC_DESC_DR28,
    LMS_SHA256_M32_H5,
    LMOTS_SHA256_N32_W4,
    MODE_VERIFY_LMS_SIGNATURE,
    MODE_RECOVER_LMOTS_LEAF,
    MODE_MERKLE_PATH_TRAVERSE,
    pack_dr28_descriptor,
)

BACKEND_LABEL = "dr28-lms-verifier:silicon"
KERNEL_REL_PATH = "phoenix_sdr_dsp/pqc/kernels/dr28_lms_verifier_service.cc"
_PROGRAM: Any | None = None

REQ_BYTES = 8192
DESCRIPTOR_BYTES = 32
RESULT_BYTES = 8192


class NativeBackendUnavailable(RuntimeError):
    """The native IRON/XRT DR28 backend is unavailable or failed closed."""


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
        raise NativeBackendUnavailable("DR28 physical silicon requires XRT device(0)") from exc


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
            "DR28 requires MLIR-AIE/IRON 1.4.1, XRT, and an XRT-visible Phoenix NPU."
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
    def dr28_lms_verifier_program(
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

        of_request = ObjectFifo(request_ty, name="dr28_request")
        of_descriptor = ObjectFifo(descriptor_ty, name="dr28_descriptor")
        of_result = ObjectFifo(result_ty, name="dr28_result")

        kernel_path = Path(__file__).resolve().parent / "kernels"
        service_fn = ExternalFunction(
            "dr28_lms_verifier_service",
            source_file=str(kernel_path / "dr28_lms_verifier_service.cc"),
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

    _PROGRAM = dr28_lms_verifier_program
    return _PROGRAM


# =========================================================================
# Hardware Dispatch Operations on AMD Phoenix AIE2
# =========================================================================

def _dispatch_dr28(desc_bytes: bytes, req_buf: bytearray) -> Tuple[bytes, float]:
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
    return raw_res, dt_ms


def verify_lms_signature_on_aie2(
    I: bytes,
    t1_expected: bytes,
    q: int,
    C: bytes,
    y_sigs: bytes,
    auth_path: bytes,
    msg: bytes,
    epoch: int = 1,
) -> Tuple[bool, bytes, float]:
    """Verifies LMS signature against expected root on AMD Phoenix AIE2."""
    desc_bytes = pack_dr28_descriptor(
        operation_mode=MODE_VERIFY_LMS_SIGNATURE,
        msg_len=len(msg),
        epoch=epoch,
    )
    req_buf = bytearray(REQ_BYTES)
    req_buf[0:16] = I[:16]
    req_buf[16:48] = t1_expected[:32]
    struct.pack_into("<I", req_buf, 48, q)
    req_buf[52:84] = C[:32]
    req_buf[84:84 + 2144] = y_sigs[:2144]
    req_buf[84 + 2144:84 + 2144 + 160] = auth_path[:160]
    req_buf[84 + 2144 + 160:84 + 2144 + 160 + len(msg)] = msg

    raw_res, dt_ms = _dispatch_dr28(desc_bytes, req_buf)
    status = struct.unpack_from("<I", raw_res, 8)[0]
    calc_root = raw_res[16:48]
    return (status == 0), calc_root, dt_ms


def recover_lmots_leaf_on_aie2(
    I: bytes,
    q: int,
    C: bytes,
    y_sigs: bytes,
    msg: bytes,
    epoch: int = 1,
) -> Tuple[bytes, float]:
    """Recovers candidate LM-OTS public leaf on AMD Phoenix AIE2."""
    desc_bytes = pack_dr28_descriptor(
        operation_mode=MODE_RECOVER_LMOTS_LEAF,
        msg_len=len(msg),
        epoch=epoch,
    )
    req_buf = bytearray(REQ_BYTES)
    req_buf[0:16] = I[:16]
    struct.pack_into("<I", req_buf, 16, q)
    req_buf[20:52] = C[:32]
    req_buf[52:52 + 2144] = y_sigs[:2144]
    req_buf[52 + 2144:52 + 2144 + len(msg)] = msg

    raw_res, dt_ms = _dispatch_dr28(desc_bytes, req_buf)
    leaf_kc = raw_res[16:48]
    return leaf_kc, dt_ms


def merkle_path_traverse_on_aie2(
    I: bytes,
    q: int,
    leaf_kc: bytes,
    auth_path: bytes,
    epoch: int = 1,
) -> Tuple[bytes, float]:
    """Evaluates Merkle tree authentication path to root on AMD Phoenix AIE2."""
    desc_bytes = pack_dr28_descriptor(
        operation_mode=MODE_MERKLE_PATH_TRAVERSE,
        msg_len=0,
        epoch=epoch,
    )
    req_buf = bytearray(REQ_BYTES)
    req_buf[0:16] = I[:16]
    struct.pack_into("<I", req_buf, 16, q)
    req_buf[20:52] = leaf_kc[:32]
    req_buf[52:52 + 160] = auth_path[:160]

    raw_res, dt_ms = _dispatch_dr28(desc_bytes, req_buf)
    calc_root = raw_res[16:48]
    return calc_root, dt_ms


# =========================================================================
# Independent Host Reference Oracles
# =========================================================================

def _ref_sha256(*chunks: bytes) -> bytes:
    h = hashlib.sha256()
    for c in chunks:
        h.update(c)
    return h.digest()


def ref_lmots_recover_leaf(
    I: bytes,
    q: int,
    C: bytes,
    y_sigs: bytes,
    msg: bytes,
) -> bytes:
    q_hdr = I[:16] + struct.pack(">IH", q, 0x0083)  # D_MESG
    Q = _ref_sha256(q_hdr, C[:32], msg)

    # Checksum and coefficients (w=4)
    a = []
    csum = 0
    for b in Q:
        hi = (b >> 4) & 0x0F
        lo = b & 0x0F
        a.extend([hi, lo])
        csum += (15 - hi) + (15 - lo)
    csum <<= 4
    a.append((csum >> 12) & 0x0F)
    a.append((csum >> 8) & 0x0F)
    a.append((csum >> 4) & 0x0F)

    z_parts = []
    prefix = I[:16] + struct.pack(">I", q)
    for i in range(67):
        cur = y_sigs[i * 32:(i + 1) * 32]
        for j in range(a[i], 15):
            cur = _ref_sha256(prefix + struct.pack(">HB", i, j) + cur)
        z_parts.append(cur)

    pkey_hdr = I[:16] + struct.pack(">IH", q, 0x0080)  # D_PKEY
    return _ref_sha256(pkey_hdr, b"".join(z_parts))


def ref_lms_traverse_path(
    I: bytes,
    q: int,
    leaf_kc: bytes,
    auth_path: bytes,
    h: int = 5,
) -> bytes:
    node_id = (1 << h) + q
    leaf_hdr = I[:16] + struct.pack(">IH", node_id, 0x0082)  # D_LEAF
    cur_node = _ref_sha256(leaf_hdr, leaf_kc[:32])

    for i in range(h):
        parent_id = node_id // 2
        intr_hdr = I[:16] + struct.pack(">IH", parent_id, 0x0081)  # D_INTR
        sibling = auth_path[i * 32:(i + 1) * 32]
        if node_id % 2 == 1:
            cur_node = _ref_sha256(intr_hdr, sibling, cur_node)
        else:
            cur_node = _ref_sha256(intr_hdr, cur_node, sibling)
        node_id = parent_id
    return cur_node


def ref_lms_verify(
    I: bytes,
    t1_expected: bytes,
    q: int,
    C: bytes,
    y_sigs: bytes,
    auth_path: bytes,
    msg: bytes,
    h: int = 5,
) -> bool:
    leaf_kc = ref_lmots_recover_leaf(I, q, C, y_sigs, msg)
    calc_root = ref_lms_traverse_path(I, q, leaf_kc, auth_path, h)
    return calc_root == t1_expected


def ref_lms_generate_test_fixture(
    I: bytes,
    q: int,
    msg: bytes,
    rng: np.random.Generator,
    h: int = 5,
) -> Tuple[bytes, bytes, bytes, bytes]:
    """Generates a mathematically valid LMS signature and root for testing."""
    C = rng.bytes(32)
    # Generate private one-time key secrets x[0..66]
    x = [rng.bytes(32) for _ in range(67)]

    # Compute Q and coefficients
    q_hdr = I[:16] + struct.pack(">IH", q, 0x0083)
    Q = _ref_sha256(q_hdr, C, msg)
    a = []
    csum = 0
    for b in Q:
        hi = (b >> 4) & 0x0F
        lo = b & 0x0F
        a.extend([hi, lo])
        csum += (15 - hi) + (15 - lo)
    csum <<= 4
    a.append((csum >> 12) & 0x0F)
    a.append((csum >> 8) & 0x0F)
    a.append((csum >> 4) & 0x0F)

    # Compute signature y[i] = hash^(a[i])(x[i])
    prefix = I[:16] + struct.pack(">I", q)
    y_parts = []
    for i in range(67):
        cur = x[i]
        for j in range(a[i]):
            cur = _ref_sha256(prefix + struct.pack(">HB", i, j) + cur)
        y_parts.append(cur)
    y_sigs = b"".join(y_parts)

    auth_path = rng.bytes(h * 32)
    leaf_kc = ref_lmots_recover_leaf(I, q, C, y_sigs, msg)
    root = ref_lms_traverse_path(I, q, leaf_kc, auth_path, h)
    return C, y_sigs, auth_path, root
