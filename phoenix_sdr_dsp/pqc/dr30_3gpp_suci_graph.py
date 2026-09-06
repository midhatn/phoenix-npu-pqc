# SPDX-License-Identifier: Apache-2.0
"""Computational Graph & Hardware Dispatch Orchestrator for Milestone DR30:
3GPP TS 33.501 5G/6G Core Network SUCI Co-Processor on AMD Phoenix AIE2.
"""

import hashlib
import os
from pathlib import Path
import struct
import time
from typing import Any, Tuple, Dict, List, Optional

import numpy as np

from .dr30_3gpp_suci_abi import (
    MAGIC_DESC_DR30,
    PROFILE_C_MLKEM768,
    PROFILE_D_MLKEM1024,
    MODE_SUCI_PARSE_VALIDATE,
    MODE_SUCI_DECAPSULATE_DERIVE,
    MODE_SUCI_DECONCEAL_VERIFY,
    MODE_SUCI_PIPELINE_FULL,
    pack_dr30_descriptor,
)

BACKEND_LABEL = "dr30-3gpp-suci:silicon"
KERNEL_REL_PATH = "phoenix_sdr_dsp/pqc/kernels/dr30_3gpp_suci_service.cc"
_PROGRAM: Any | None = None

REQ_BYTES = 4096
DESCRIPTOR_BYTES = 32
RESULT_BYTES = 2048


class NativeBackendUnavailable(RuntimeError):
    """The native IRON/XRT DR30 backend is unavailable or failed closed."""


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
        raise NativeBackendUnavailable("DR30 physical silicon requires XRT device(0)") from exc


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
            "DR30 requires MLIR-AIE/IRON 1.4.1, XRT, and an XRT-visible Phoenix NPU."
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
    def dr30_3gpp_suci_program(
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

        of_request = ObjectFifo(request_ty, name="dr30_request")
        of_descriptor = ObjectFifo(descriptor_ty, name="dr30_descriptor")
        of_result = ObjectFifo(result_ty, name="dr30_result")

        kernel_path = Path(__file__).resolve().parent / "kernels"
        service_fn = ExternalFunction(
            "dr30_3gpp_suci_service",
            source_file=str(kernel_path / "dr30_3gpp_suci_service.cc"),
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

    _PROGRAM = dr30_3gpp_suci_program
    return _PROGRAM


# =========================================================================
# Hardware Dispatch Operations on AMD Phoenix AIE2
# =========================================================================

def _dispatch_dr30(desc_bytes: bytes, req_buf: bytearray) -> Tuple[bytes, float]:
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
        raise RuntimeError(f"DR30 hardware error status: 0x{status:02X}")

    return raw_res, dt_ms


def suci_parse_validate_on_aie2(
    profile_id: int,
    hn_key_id: int,
    suci_len: int,
    epoch: int = 1,
    routing_indicator: int = 0x0001,
    mcc_mnc: int = 0x0310260,
) -> Tuple[dict[str, Any], float]:
    desc = pack_dr30_descriptor(
        operation_mode=MODE_SUCI_PARSE_VALIDATE,
        profile_id=profile_id,
        hn_key_id=hn_key_id,
        suci_len=suci_len,
        epoch=epoch,
        routing_indicator=routing_indicator,
        mcc_mnc=mcc_mnc,
    )
    req = bytearray(REQ_BYTES)
    raw_res, dt_ms = _dispatch_dr30(desc, req)
    fields = struct.unpack_from("<IIIIII", raw_res, 16)
    return {
        "is_valid": bool(fields[0]),
        "profile_id": fields[1],
        "hn_key_id": fields[2],
        "routing_indicator": fields[3],
        "mcc_mnc": fields[4],
        "suci_len": fields[5],
    }, dt_ms


def suci_decapsulate_derive_on_aie2(
    shared_secret: bytes = b"",
    ephem_pubkey: bytes = b"",
    epoch: int = 1,
    dk: Optional[bytes] = None,
    c: Optional[bytes] = None,
) -> Tuple[dict[str, bytes], float]:
    total_dt_ms = 0.0
    actual_ss = shared_secret
    if dk is not None and c is not None and len(dk) >= 1632 and len(c) >= 768:
        from .dr7_mlkem512_decaps_graph import run_mlkem512_decaps
        t0 = time.perf_counter()
        actual_ss = run_mlkem512_decaps(dk=dk, c=c, request_id=epoch)
        total_dt_ms += (time.perf_counter() - t0) * 1000

    desc = pack_dr30_descriptor(
        operation_mode=MODE_SUCI_DECAPSULATE_DERIVE,
        epoch=epoch,
    )
    req = bytearray(REQ_BYTES)
    req[0:32] = actual_ss[:32]
    req[32:64] = ephem_pubkey[:32]
    raw_res, dt_ms = _dispatch_dr30(desc, req)
    total_dt_ms += dt_ms
    k_enc = raw_res[16:32]
    k_mac = raw_res[32:48]
    return {"k_enc": k_enc, "k_mac": k_mac}, total_dt_ms


def suci_deconceal_verify_on_aie2(
    k_enc: bytes,
    k_mac: bytes,
    recv_mac: bytes,
    enc_payload: bytes,
    epoch: int = 1,
) -> Tuple[bytes, float]:
    payload_len = len(enc_payload)
    desc = pack_dr30_descriptor(
        operation_mode=MODE_SUCI_DECONCEAL_VERIFY,
        suci_len=48 + payload_len,
        epoch=epoch,
    )
    req = bytearray(REQ_BYTES)
    req[0:16] = k_enc[:16]
    req[16:32] = k_mac[:16]
    req[32:48] = recv_mac[:16]
    req[48:48 + payload_len] = enc_payload[:payload_len]
    raw_res, dt_ms = _dispatch_dr30(desc, req)
    plain_supi = raw_res[16:16 + payload_len]
    return plain_supi, dt_ms


def suci_pipeline_full_on_aie2(
    shared_secret: bytes = b"",
    ephem_pubkey: bytes = b"",
    recv_mac: bytes = b"",
    enc_payload: bytes = b"",
    epoch: int = 1,
    dk: Optional[bytes] = None,
    c: Optional[bytes] = None,
) -> Tuple[bytes, float]:
    total_dt_ms = 0.0
    actual_ss = shared_secret
    if dk is not None and c is not None and len(dk) >= 1632 and len(c) >= 768:
        from .dr7_mlkem512_decaps_graph import run_mlkem512_decaps
        t0 = time.perf_counter()
        actual_ss = run_mlkem512_decaps(dk=dk, c=c, request_id=epoch)
        total_dt_ms += (time.perf_counter() - t0) * 1000

    payload_len = len(enc_payload)
    desc = pack_dr30_descriptor(
        operation_mode=MODE_SUCI_PIPELINE_FULL,
        suci_len=80 + payload_len,
        epoch=epoch,
    )
    req = bytearray(REQ_BYTES)
    req[0:32] = actual_ss[:32]
    req[32:64] = ephem_pubkey[:32]
    req[64:80] = recv_mac[:16]
    req[80:80 + payload_len] = enc_payload[:payload_len]
    raw_res, dt_ms = _dispatch_dr30(desc, req)
    total_dt_ms += dt_ms
    plain_supi = raw_res[16:16 + payload_len]
    return plain_supi, total_dt_ms


# =========================================================================
# Independent Host Reference Oracle (Mathematical & Ground Truth)
# =========================================================================

def ref_suci_validate_header(profile_id: int, hn_key_id: int, suci_len: int) -> bool:
    return (profile_id in (3, 4)) and (hn_key_id > 0) and (suci_len >= 32)


def ref_derive_suci_keys(shared_secret: bytes, ephem_pubkey: bytes) -> dict[str, bytes]:
    state = [0] * 16
    ss_words = struct.unpack_from("<8I", shared_secret[:32], 0)
    ephem_words = struct.unpack_from("<8I", ephem_pubkey[:32], 0)
    for i in range(8):
        state[i] = (ss_words[i] ^ 0x6A09E667) & 0xFFFFFFFF
        state[i + 8] = (ephem_words[i] ^ 0xBB67AE85) & 0xFFFFFFFF

    for r in range(8):
        for i in range(16):
            s_next = state[(i + 1) % 16]
            rot = ((s_next << 13) | (s_next >> 19)) & 0xFFFFFFFF
            state[i] = (state[i] ^ (rot + state[(i + 7) % 16] + 0x9E3779B9 + r)) & 0xFFFFFFFF

    st_bytes = struct.pack("<16I", *state)
    return {
        "k_enc": st_bytes[0:16],
        "k_mac": st_bytes[16:32],
    }


def ref_compute_suci_mac(k_mac: bytes, payload: bytes) -> bytes:
    km_words = struct.unpack_from("<4I", k_mac[:16], 0)
    acc = [
        (km_words[0] ^ 0x55555555) & 0xFFFFFFFF,
        (km_words[1] ^ 0xAAAAAAAA) & 0xFFFFFFFF,
        (km_words[2] ^ 0x33333333) & 0xFFFFFFFF,
        (km_words[3] ^ 0xCCCCCCCC) & 0xFFFFFFFF,
    ]
    full_words = len(payload) // 4
    for w in range(full_words):
        word = struct.unpack_from("<I", payload, w * 4)[0]
        acc[w % 4] = (acc[w % 4] ^ (word + ((acc[(w + 1) % 4] << 5) & 0xFFFFFFFF))) & 0xFFFFFFFF

    rem = len(payload) % 4
    if rem > 0:
        tail = 0
        for r in range(rem):
            tail |= payload[full_words * 4 + r] << (r * 8)
        acc[full_words % 4] = (acc[full_words % 4] ^ tail) & 0xFFFFFFFF

    for i in range(4):
        acc[i] = ((acc[i] >> 11) | ((acc[i] << 21) & 0xFFFFFFFF)) & 0xFFFFFFFF

    return struct.pack("<4I", *acc)


def ref_decrypt_supi(k_enc: bytes, enc_payload: bytes) -> bytes:
    plain = bytearray(len(enc_payload))
    for i in range(len(enc_payload)):
        key_byte = k_enc[i % 16] ^ ((i * 31) & 0xFF)
        plain[i] = enc_payload[i] ^ key_byte
    return bytes(plain)


def ref_full_deconceal(
    shared_secret: bytes,
    ephem_pubkey: bytes,
    recv_mac: bytes,
    enc_payload: bytes,
) -> Tuple[bool, bytes]:
    keys = ref_derive_suci_keys(shared_secret, ephem_pubkey)
    calc_mac = ref_compute_suci_mac(keys["k_mac"], enc_payload)
    if calc_mac != recv_mac:
        return False, b""
    plain = ref_decrypt_supi(keys["k_enc"], enc_payload)
    return True, plain
