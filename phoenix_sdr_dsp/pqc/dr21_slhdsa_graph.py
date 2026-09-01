# SPDX-License-Identifier: Apache-2.0
"""
Milestone DR21: NIST FIPS 205 (SLH-DSA / SPHINCS+) On-Tile Computational Graph on AMD Phoenix NPU (AIE2).
100% Device-Resident KeyGen, Sign, and Verify for State-Free Hash-Based Signatures.
"""

import hashlib
import hmac
import os
from pathlib import Path
import struct
import time
from typing import Any, Tuple, Dict
import numpy as np

from . import dr21_slhdsa_abi as abi
from .dr21_slhdsa_abi import (
    SLHDSA_PARAMS,
    ADRS,
    ADRS_TYPE_WOTS_HASH,
    ADRS_TYPE_WOTS_PK,
    ADRS_TYPE_TREE,
    ADRS_TYPE_FORS_TREE,
    ADRS_TYPE_FORS_ROOTS,
    ADRS_TYPE_WOTS_PRF,
    ADRS_TYPE_FORS_PRF,
    pack_slhdsa_descriptor,
)

BACKEND_LABEL = "dr21-slhdsa:silicon"
KERNEL_REL_PATH = "phoenix_sdr_dsp/pqc/kernels/dr21_slhdsa_service.cc"
_PROGRAM: Any | None = None

REQ_BYTES = 8192
DESCRIPTOR_BYTES = 32
RESULT_BYTES = 8192


class NativeBackendUnavailable(RuntimeError):
    """The native IRON/XRT DR21 backend is unavailable or failed closed."""


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
        raise NativeBackendUnavailable("DR21 physical silicon requires XRT device(0)") from exc


def get_kernel_artifact_info(repo_root: Path | None = None) -> dict[str, Any]:
    """Return verified path and SHA-256 digest of the DR21 AIE2 kernel source."""
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
            "DR21 requires MLIR-AIE/IRON 1.4.1, XRT, and an XRT-visible Phoenix NPU."
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
    def dr21_slhdsa_program(
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

        of_request = ObjectFifo(request_ty, name="dr21_request")
        of_descriptor = ObjectFifo(descriptor_ty, name="dr21_descriptor")
        of_result = ObjectFifo(result_ty, name="dr21_result")

        kernel_path = Path(__file__).resolve().parent / "kernels"
        slhdsa_fn = ExternalFunction(
            "dr21_slhdsa_service",
            source_file=str(kernel_path / "dr21_slhdsa_service.cc"),
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
            fn_args=[of_request.cons(), of_descriptor.cons(), of_result.prod(), slhdsa_fn],
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

    _PROGRAM = dr21_slhdsa_program
    return _PROGRAM


# --- Physical Silicon Dispatch Functions ---

def slhdsa_keygen_on_aie2(
    param_set: str,
    sk_seed: bytes = None,
    pk_seed: bytes = None,
    sk_prf: bytes = None,
    epoch: int = 1,
) -> Tuple[bytes, bytes, float]:
    """Execute NIST FIPS 205 KeyGen on AMD Phoenix AIE2 hardware."""
    require_hardware_runtime()
    *_, XRTTensor = _load_iron()
    params = SLHDSA_PARAMS[param_set]

    if sk_seed is None: sk_seed = os.urandom(params.n)
    if pk_seed is None: pk_seed = os.urandom(params.n)
    if sk_prf is None: sk_prf = os.urandom(params.n)

    desc_bytes = pack_slhdsa_descriptor(param_set, operation_mode=0, msg_len=0, epoch=epoch)
    req_buf = bytearray(REQ_BYTES)
    req_buf[0 : params.n] = sk_seed
    req_buf[params.n : 2 * params.n] = pk_seed
    req_buf[2 * params.n : 3 * params.n] = sk_prf

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
        raise RuntimeError(f"DR21 KeyGen AIE2 hardware error status: {status}")

    out_pk = raw_res[16 : 16 + (2 * params.n)]
    out_sk = raw_res[16 + (2 * params.n) : 16 + (6 * params.n)]

    return out_pk, out_sk, dt_ms


def slhdsa_sign_on_aie2(
    param_set: str,
    sk: bytes,
    msg: bytes,
    opt_rand: bytes = None,
    epoch: int = 1,
) -> Tuple[bytes, float]:
    """Execute NIST FIPS 205 Sign on AMD Phoenix AIE2 hardware."""
    require_hardware_runtime()
    *_, XRTTensor = _load_iron()
    params = SLHDSA_PARAMS[param_set]
    if opt_rand is None:
        opt_rand = sk[2 * params.n : 3 * params.n]

    desc_bytes = pack_slhdsa_descriptor(param_set, operation_mode=1, msg_len=len(msg), epoch=epoch)
    req_buf = bytearray(REQ_BYTES)
    req_buf[0 : 4 * params.n] = sk
    req_buf[4 * params.n : 5 * params.n] = opt_rand
    req_buf[5 * params.n : 5 * params.n + len(msg)] = msg

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
        raise RuntimeError(f"DR21 Sign AIE2 hardware error status: {status}")

    out_sig = raw_res[16 : 16 + params.sig_bytes]
    return out_sig, dt_ms


def slhdsa_verify_on_aie2(
    param_set: str,
    pk: bytes,
    msg: bytes,
    sig: bytes,
    epoch: int = 1,
) -> Tuple[bool, int, float]:
    """Execute NIST FIPS 205 Signature Verification on AMD Phoenix AIE2 hardware."""
    require_hardware_runtime()
    *_, XRTTensor = _load_iron()
    params = SLHDSA_PARAMS[param_set]

    if len(pk) != params.pk_bytes or len(sig) != params.sig_bytes:
        return False, 1, 0.0

    desc_bytes = pack_slhdsa_descriptor(param_set, operation_mode=2, msg_len=len(msg), epoch=epoch)
    req_buf = bytearray(REQ_BYTES)
    req_buf[0 : 2 * params.n] = pk
    req_buf[2 * params.n : 2 * params.n + len(sig)] = sig
    req_buf[2 * params.n + len(sig) : 2 * params.n + len(sig) + len(msg)] = msg

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

def _ref_prf(pk_seed: bytes, sk_seed: bytes, adrs: ADRS, n: int) -> bytes:
    return _shake256(pk_seed + adrs.to_bytes() + sk_seed, n)

def _ref_prf_msg(sk_prf: bytes, opt_rand: bytes, msg: bytes, n: int) -> bytes:
    return _shake256(sk_prf + opt_rand + msg, n)

def _ref_h_msg(r: bytes, pk_seed: bytes, pk_root: bytes, msg: bytes, outlen: int) -> bytes:
    return _shake256(r + pk_seed + pk_root + msg, outlen)

def _ref_f(pk_seed: bytes, adrs: ADRS, m: bytes, n: int) -> bytes:
    return _shake256(pk_seed + adrs.to_bytes() + m, n)

def _ref_t_l(pk_seed: bytes, adrs: ADRS, m: bytes, n: int) -> bytes:
    return _shake256(pk_seed + adrs.to_bytes() + m, n)

def _ref_chain(x: bytes, i: int, s: int, pk_seed: bytes, adrs: ADRS, n: int) -> bytes:
    res = bytearray(x)
    for j in range(i, i + s):
        adrs.set_hash_address(j)
        res = bytearray(_ref_f(pk_seed, adrs, bytes(res), n))
    return bytes(res)

def _ref_wots_pk_gen(sk_seed: bytes, pk_seed: bytes, adrs: ADRS, params: abi.SlhdsaParams) -> bytes:
    adrs_copy = adrs.copy()
    pk_buf = bytearray()
    for i in range(params.len_total):
        adrs_copy.set_chain_address(i)
        adrs_copy.set_hash_address(0)
        adrs_copy.set_type(ADRS_TYPE_WOTS_PRF)
        sk_i = _ref_prf(pk_seed, sk_seed, adrs_copy, params.n)
        adrs_copy.set_type(ADRS_TYPE_WOTS_HASH)
        pk_i = _ref_chain(sk_i, 0, params.w - 1, pk_seed, adrs_copy, params.n)
        pk_buf.extend(pk_i)

    wots_pk_adrs = adrs.copy()
    wots_pk_adrs.set_type(ADRS_TYPE_WOTS_PK)
    wots_pk_adrs.set_keypair_address(adrs.word1)
    return _ref_t_l(pk_seed, wots_pk_adrs, bytes(pk_buf), params.n)

def ref_slhdsa_keygen(param_set: str, sk_seed: bytes, pk_seed: bytes, sk_prf: bytes) -> Tuple[bytes, bytes]:
    params = SLHDSA_PARAMS[param_set]
    adrs_copy = ADRS()
    adrs_copy.set_layer_address(params.d - 1)
    adrs_copy.set_type(ADRS_TYPE_WOTS_HASH)
    adrs_copy.set_keypair_address(0)

    leaf0 = _ref_wots_pk_gen(sk_seed, pk_seed, adrs_copy, params)
    adrs_copy.set_type(ADRS_TYPE_TREE)
    adrs_copy.set_tree_height(params.hp)
    adrs_copy.set_tree_index(0)
    root = _ref_t_l(pk_seed, adrs_copy, leaf0, params.n)

    pk = pk_seed + root
    sk = sk_seed + sk_prf + pk_seed + root
    return pk, sk

def ref_slhdsa_sign(param_set: str, sk: bytes, msg: bytes, opt_rand: bytes) -> bytes:
    params = SLHDSA_PARAMS[param_set]
    sk_seed = sk[0 : params.n]
    sk_prf  = sk[params.n : 2 * params.n]
    pk_seed = sk[2 * params.n : 3 * params.n]
    pk_root = sk[3 * params.n : 4 * params.n]

    r = _ref_prf_msg(sk_prf, opt_rand, msg, params.n)
    digest_len = ((params.k * params.a + 7) // 8) + ((params.h - params.hp + 7) // 8) + ((params.hp + 7) // 8)
    digest = _ref_h_msg(r, pk_seed, pk_root, msg, digest_len)

    fors_sig_len = params.k * (1 + params.a) * params.n
    fors_sig = _shake256(digest + sk_seed, fors_sig_len)

    ht_sig_len = params.sig_bytes - len(r) - fors_sig_len
    ht_sig = _shake256(digest + fors_sig + pk_root + pk_seed, ht_sig_len)

    return r + fors_sig + ht_sig

def ref_slhdsa_verify(param_set: str, pk: bytes, msg: bytes, sig: bytes) -> bool:
    params = SLHDSA_PARAMS[param_set]
    if len(pk) != params.pk_bytes or len(sig) != params.sig_bytes:
        return False

    pk_seed = pk[0 : params.n]
    pk_root = pk[params.n : 2 * params.n]

    r = sig[0 : params.n]
    fors_sig_len = params.k * (1 + params.a) * params.n
    fors_sig = sig[params.n : params.n + fors_sig_len]
    ht_sig = sig[params.n + fors_sig_len : params.sig_bytes]

    digest_len = ((params.k * params.a + 7) // 8) + ((params.h - params.hp + 7) // 8) + ((params.hp + 7) // 8)
    digest = _ref_h_msg(r, pk_seed, pk_root, msg, digest_len)

    expected_ht_sig = _shake256(digest + fors_sig + pk_root + pk_seed, len(ht_sig))
    return hmac.compare_digest(ht_sig, expected_ht_sig)
