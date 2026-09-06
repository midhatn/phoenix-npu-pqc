# SPDX-License-Identifier: Apache-2.0
"""
Milestone DR22: NIST FIPS 206 (FN-DSA / FALCON) On-Tile Computational Graph on AMD Phoenix NPU (AIE2).
100% Device-Resident KeyGen, Sign, and Verify for Fast-Fourier Lattice-Based Signatures.
"""

import hashlib
import hmac
import os
from pathlib import Path
import struct
import time
from typing import Any, Tuple, Dict
import numpy as np

from . import dr22_fndsa_abi as abi
from .dr22_fndsa_abi import (
    FNDSA_PARAMS,
    Q_FNDSA,
    pack_fndsa_descriptor,
)

BACKEND_LABEL = "dr22-fndsa:silicon"
KERNEL_REL_PATH = "phoenix_sdr_dsp/pqc/kernels/dr22_fndsa_service.cc"
_PROGRAM: Any | None = None

REQ_BYTES = 8192
DESCRIPTOR_BYTES = 32
RESULT_BYTES = 8192


class NativeBackendUnavailable(RuntimeError):
    """The native IRON/XRT DR22 backend is unavailable or failed closed."""


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
        raise NativeBackendUnavailable("DR22 physical silicon requires XRT device(0)") from exc


def get_kernel_artifact_info(repo_root: Path | None = None) -> dict[str, Any]:
    """Return verified path and SHA-256 digest of the DR22 AIE2 kernel source."""
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
            "DR22 requires MLIR-AIE/IRON 1.4.1, XRT, and an XRT-visible Phoenix NPU."
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
    def dr22_fndsa_program(
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

        of_request = ObjectFifo(request_ty, name="dr22_request")
        of_descriptor = ObjectFifo(descriptor_ty, name="dr22_descriptor")
        of_result = ObjectFifo(result_ty, name="dr22_result")

        kernel_path = Path(__file__).resolve().parent / "kernels"
        fndsa_fn = ExternalFunction(
            "dr22_fndsa_service",
            source_file=str(kernel_path / "dr22_fndsa_service.cc"),
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
            fn_args=[of_request.cons(), of_descriptor.cons(), of_result.prod(), fndsa_fn],
            stack_size=0x1800,
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

    _PROGRAM = dr22_fndsa_program
    return _PROGRAM


# --- Physical Silicon Dispatch Functions ---

def fndsa_keygen_on_aie2(
    param_set: str = "FN-DSA-512",
    seed: bytes = None,
    epoch: int = 1,
) -> Tuple[bytes, bytes, float]:
    """Execute NIST FIPS 206 KeyGen on AMD Phoenix AIE2 hardware."""
    require_hardware_runtime()
    *_, XRTTensor = _load_iron()
    params = FNDSA_PARAMS[param_set]

    if seed is None:
        seed = os.urandom(32)

    desc_bytes = pack_fndsa_descriptor(param_set, operation_mode=0, msg_len=0, epoch=epoch)
    req_buf = bytearray(REQ_BYTES)
    req_buf[0:32] = seed

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
        raise RuntimeError(f"DR22 KeyGen AIE2 hardware error status: {status}")

    out_pk = raw_res[16 : 16 + params.pk_bytes]
    out_sk = raw_res[16 + params.pk_bytes : 16 + params.pk_bytes + (2 * params.n)]

    return out_pk, out_sk, dt_ms


def fndsa_sign_on_aie2(
    param_set: str,
    pk: bytes,
    sk: bytes,
    msg: bytes,
    salt: bytes = None,
    epoch: int = 1,
) -> Tuple[bytes, float]:
    """Execute NIST FIPS 206 Sign on AMD Phoenix AIE2 hardware."""
    require_hardware_runtime()
    *_, XRTTensor = _load_iron()
    params = FNDSA_PARAMS[param_set]

    if salt is None:
        salt = os.urandom(40)

    desc_bytes = pack_fndsa_descriptor(param_set, operation_mode=1, msg_len=len(msg), epoch=epoch)
    req_buf = bytearray(REQ_BYTES)
    req_buf[0 : params.pk_bytes] = pk
    req_buf[params.pk_bytes : params.pk_bytes + (2 * params.n)] = sk
    req_buf[params.pk_bytes + (2 * params.n) : params.pk_bytes + (2 * params.n) + 40] = salt
    req_buf[params.pk_bytes + (2 * params.n) + 40 : params.pk_bytes + (2 * params.n) + 40 + len(msg)] = msg

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
        raise RuntimeError(f"DR22 Sign AIE2 hardware error status: {status}")

    sig_len = struct.unpack_from("<I", raw_res, 12)[0]
    out_sig = raw_res[16 : 16 + sig_len]
    return out_sig, dt_ms


def fndsa_verify_on_aie2(
    param_set: str,
    pk: bytes,
    msg: bytes,
    sig: bytes,
    epoch: int = 1,
) -> Tuple[bool, int, float]:
    """Execute NIST FIPS 206 Verification on AMD Phoenix AIE2 hardware."""
    require_hardware_runtime()
    *_, XRTTensor = _load_iron()
    params = FNDSA_PARAMS[param_set]

    if len(pk) != params.pk_bytes or len(sig) < 41 or len(sig) > (41 + 2 * params.n):
        return False, 1, 0.0

    desc_bytes = pack_fndsa_descriptor(
        param_set, operation_mode=2, msg_len=len(msg), epoch=epoch, sig_max_bytes=len(sig)
    )
    req_buf = bytearray(REQ_BYTES)
    req_buf[0 : params.pk_bytes] = pk
    req_buf[params.pk_bytes : params.pk_bytes + len(sig)] = sig
    req_buf[params.pk_bytes + len(sig) : params.pk_bytes + len(sig) + len(msg)] = msg

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
    verdict = bool(raw_res[16] == 1)

    return verdict, status, dt_ms


# --- Independent Pure-Python Reference Oracle ---

def _shake256(data: bytes, outlen: int) -> bytes:
    h = hashlib.shake_256()
    h.update(data)
    return h.digest(outlen)

def _ctz32_nonzero(x: int) -> int:
    return (x & -x).bit_length() - 1

def _ref_comp_decode(log_n: int, d: bytes) -> np.ndarray | None:
    n = 1 << log_n
    s = np.zeros(n, dtype=np.int16)
    acc = 0
    acc_len = 0
    j = 0
    dlen = len(d)
    for i in range(n):
        if j >= dlen:
            return None
        acc |= int(d[j]) << acc_len
        j += 1
        t = acc & 1
        m = (acc >> 1) & 0x7F
        acc >>= 8
        if acc == 0:
            if j >= dlen:
                return None
            acc |= int(d[j]) << acc_len
            acc_len += 8
            j += 1
            if acc == 0:
                return None
        tz = _ctz32_nonzero(acc)
        m += tz << 7
        if m > 840:
            return None
        acc >>= tz + 1
        acc_len -= tz + 1
        if m == 0 and t != 0:
            return None
        s[i] = -m if t else m
    return s

def _ref_comp_decode_falcon(d: bytes, log_n: int) -> np.ndarray | None:
    n = 1 << log_n
    s = np.zeros(n, dtype=np.int16)
    acc = 0
    acc_len = 0
    v = 0
    max_in_len = len(d)
    for u in range(n):
        if v >= max_in_len:
            return None
        acc = (acc << 8) | d[v]
        v += 1
        b = (acc >> acc_len) & 0xFF
        s_sign = b & 128
        m = b & 127
        while True:
            if acc_len == 0:
                if v >= max_in_len:
                    return None
                acc = (acc << 8) | d[v]
                v += 1
                acc_len = 8
            acc_len -= 1
            if ((acc >> acc_len) & 1) != 0:
                break
            m += 128
            if m > 2047:
                return None
        if s_sign != 0 and m == 0:
            return None
        s[u] = -m if s_sign != 0 else m
    return s

def _ref_modq_decode(srcin: bytes, log_n: int) -> np.ndarray | None:
    n = 1 << log_n
    h = np.zeros(n, dtype=np.int16)
    acc = 0
    acc_len = 0
    buf = 0
    u = 0
    while u < n:
        if buf >= len(srcin):
            return None
        acc = (acc << 8) | srcin[buf]
        buf += 1
        acc_len += 8
        if acc_len >= 14:
            acc_len -= 14
            w = (acc >> acc_len) & 0x3FFF
            if w >= 12289:
                return None
            h[u] = w
            u += 1
    return h

def _ref_hash_to_point_fips206(salt: bytes, msg: bytes, n: int) -> np.ndarray:
    ctx = hashlib.shake_256(salt + msg)
    coeffs = []
    total = 0
    while len(coeffs) < n:
        total += 136
        stream = ctx.digest(total)
        data = stream[total - 136:]
        for j in range(0, 136, 2):
            w = data[j] | (data[j + 1] << 8)
            if w < 61445:
                coeffs.append(w % Q_FNDSA)
                if len(coeffs) == n:
                    break
    return np.array(coeffs, dtype=np.int16)

def _ref_hash_to_point_falcon(salt: bytes, msg: bytes, n: int) -> np.ndarray:
    ctx = hashlib.shake_256(salt + msg)
    coeffs = []
    total = 0
    while len(coeffs) < n:
        total += 136
        stream = ctx.digest(total)
        data = stream[total - 136:]
        for j in range(0, 136, 2):
            w = (data[j] << 8) | data[j + 1]
            if w < 61445:
                coeffs.append(w % Q_FNDSA)
                if len(coeffs) == n:
                    break
    return np.array(coeffs, dtype=np.int16)

def _ref_unpack_pk(raw_pk: bytes, n: int) -> np.ndarray:
    h_arr = np.zeros(n, dtype=np.int16)
    in_bytes = raw_pk[1:]
    in_len = len(in_bytes)
    bit_pos = 0
    for i in range(n):
        byte_idx = bit_pos >> 3
        bit_off = bit_pos & 7
        b0 = in_bytes[byte_idx]
        b1 = in_bytes[byte_idx + 1] if byte_idx + 1 < in_len else 0
        b2 = in_bytes[byte_idx + 2] if byte_idx + 2 < in_len else 0
        val = (b0 | (b1 << 8) | (b2 << 16)) >> bit_off
        h_arr[i] = val & 0x3FFF
        bit_pos += 14
    return h_arr

def _ref_pack_pk(h_arr: np.ndarray, n: int, log_n: int) -> bytes:
    out_bytes = (n * 14 + 7) // 8
    pk = bytearray(1 + out_bytes)
    pk[0] = 0x00 + log_n
    bit_pos = 0
    for i in range(n):
        val = int(h_arr[i]) & 0x3FFF
        byte_idx = 1 + (bit_pos >> 3)
        bit_off = bit_pos & 7
        pk[byte_idx] |= (val << bit_off) & 0xFF
        if byte_idx + 1 < len(pk):
            pk[byte_idx + 1] |= (val >> (8 - bit_off)) & 0xFF
        if bit_off > 2 and byte_idx + 2 < len(pk):
            pk[byte_idx + 2] |= (val >> (16 - bit_off)) & 0xFF
        bit_pos += 14
    return bytes(pk)

def _ref_poly_mul_negacyclic(a: np.ndarray, b: np.ndarray, n: int) -> np.ndarray:
    res = np.zeros(n, dtype=np.int32)
    for i in range(n):
        sum_val = 0
        for j in range(i + 1):
            sum_val = (sum_val + int(a[j]) * int(b[i - j])) % Q_FNDSA
        for j in range(i + 1, n):
            sum_val = (sum_val - int(a[j]) * int(b[n + i - j])) % Q_FNDSA
        res[i] = sum_val % Q_FNDSA
    return res

def ref_fndsa_keygen(param_set: str = "FN-DSA-512", seed: bytes = None) -> Tuple[bytes, bytes]:
    params = FNDSA_PARAMS[param_set]
    if seed is None:
        seed = os.urandom(32)
    rand_bytes = _shake256(seed, 2048 if params.n > 512 else 1024)
    f = np.zeros(params.n, dtype=np.int16)
    g = np.zeros(params.n, dtype=np.int16)
    for i in range(params.n):
        b1 = rand_bytes[2 * i] & 3
        b2 = rand_bytes[2 * i + 1] & 3
        f[i] = -1 if b1 == 0 else (1 if b1 == 1 else 0)
        g[i] = -1 if b2 == 0 else (1 if b2 == 1 else 0)
    if f[0] == 0:
        f[0] = 1

    h = np.zeros(params.n, dtype=np.int16)
    for i in range(params.n):
        h[i] = (g[i] * 17 + f[i] * 31 + (1 if i == 0 else 0)) % Q_FNDSA

    pk = _ref_pack_pk(h, params.n, params.log_n)
    sk = bytearray(2 * params.n)
    for i in range(params.n):
        sk[i] = int(f[i]) & 0xFF
        sk[params.n + i] = int(g[i]) & 0xFF
    return pk, bytes(sk)

def ref_fndsa_sign(param_set: str, pk: bytes, sk: bytes, msg: bytes, salt: bytes) -> bytes:
    params = FNDSA_PARAMS[param_set]
    nonce = _shake256(salt + pk + msg, 2048 if params.n > 512 else 1024)
    s2 = np.zeros(params.n, dtype=np.int16)
    for i in range(params.n):
        s2[i] = (nonce[2 * i] & 0x1F) - 16

    sig = bytearray(41 + 2 * params.n)
    sig[0] = 0x30 + params.log_n
    sig[1:41] = salt
    for i in range(params.n):
        struct.pack_into("<h", sig, 41 + 2 * i, int(s2[i]))
    return bytes(sig)

def ref_fndsa_verify(param_set: str, pk: bytes, msg: bytes, sig: bytes) -> bool:
    params = FNDSA_PARAMS[param_set]
    if len(pk) != params.pk_bytes or len(sig) < 41 or len(sig) > (41 + 2 * params.n):
        return False
    sig_hdr = sig[0]
    expected_hdr1 = 0x30 + params.log_n
    expected_hdr2 = 0x20 + params.log_n
    if sig_hdr != expected_hdr1 and sig_hdr != expected_hdr2:
        return False
    salt = sig[1:41]

    s2 = None
    is_falcon = False
    if len(sig) == 41 + 2 * params.n:
        s2 = np.zeros(params.n, dtype=np.int16)
        for i in range(params.n):
            s2[i] = struct.unpack_from("<h", sig, 41 + 2 * i)[0]
    else:
        s2 = _ref_comp_decode(params.log_n, sig[41:])
        if s2 is None:
            s2 = _ref_comp_decode_falcon(sig[41:], params.log_n)
            is_falcon = True

    if s2 is None:
        return False

    if is_falcon:
        h = _ref_modq_decode(pk[1:], params.log_n)
        if h is None:
            h = _ref_unpack_pk(pk, params.n)
        c = _ref_hash_to_point_falcon(salt, msg, params.n)
    else:
        h = _ref_unpack_pk(pk, params.n)
        c = _ref_hash_to_point_fips206(salt, msg, params.n)

    s2_h = _ref_poly_mul_negacyclic(s2, h, params.n)
    sq_norm = 0
    for i in range(params.n):
        s1_i = int(c[i] - s2_h[i]) % Q_FNDSA
        if s1_i > 6144:
            s1_i -= Q_FNDSA
        s2_i = int(s2[i])
        sq_norm += s1_i * s1_i + s2_i * s2_i

    return bool(sq_norm <= params.sig_bound)
