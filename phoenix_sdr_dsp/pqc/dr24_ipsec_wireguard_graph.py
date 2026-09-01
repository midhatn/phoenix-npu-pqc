# SPDX-License-Identifier: Apache-2.0
"""Computational Graph & Hardware Dispatch Orchestrator for Milestone DR24:
RFC 9370 Multi-KEM IPsec / WireGuard Inline VPN Co-Processor on AMD Phoenix AIE2.
"""

import hashlib
import os
from pathlib import Path
import struct
import sys
import time
from typing import Any, Tuple

import numpy as np

from .dr24_ipsec_wireguard_abi import (
    MAGIC_DESC_DR24,
    MODE_RFC9370_COMBINE,
    MODE_WIREGUARD_ENCAPS,
    MODE_WIREGUARD_DECAPS,
    MODE_ASYNC_REKEY,
    pack_dr24_descriptor,
)

BACKEND_LABEL = "dr24-ipsec-wireguard:silicon"
KERNEL_REL_PATH = "phoenix_sdr_dsp/pqc/kernels/dr24_ipsec_wireguard_service.cc"
_PROGRAM: Any | None = None

REQ_BYTES = 8192
DESCRIPTOR_BYTES = 32
RESULT_BYTES = 8192


class NativeBackendUnavailable(RuntimeError):
    """The native IRON/XRT DR24 backend is unavailable or failed closed."""


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
        raise NativeBackendUnavailable("DR24 physical silicon requires XRT device(0)") from exc


def get_kernel_artifact_info(repo_root: Path | None = None) -> dict[str, Any]:
    """Return verified path and SHA-256 digest of the DR24 AIE2 kernel source."""
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
            "DR24 requires MLIR-AIE/IRON 1.4.1, XRT, and an XRT-visible Phoenix NPU."
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
    def dr24_ipsec_wireguard_program(
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

        of_request = ObjectFifo(request_ty, name="dr24_request")
        of_descriptor = ObjectFifo(descriptor_ty, name="dr24_descriptor")
        of_result = ObjectFifo(result_ty, name="dr24_result")

        kernel_path = Path(__file__).resolve().parent / "kernels"
        service_fn = ExternalFunction(
            "dr24_ipsec_wireguard_service",
            source_file=str(kernel_path / "dr24_ipsec_wireguard_service.cc"),
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

    _PROGRAM = dr24_ipsec_wireguard_program
    return _PROGRAM


# =========================================================================
# Hardware Dispatch Operations on AMD Phoenix AIE2
# =========================================================================

def rfc9370_combine_on_aie2(
    k_classic: bytes,
    k_pqc: bytes,
    k_qkd: bytes,
    ni_nr: bytes,
    epoch: int = 1,
) -> Tuple[bytes, bytes, bytes, float]:
    """Executes RFC 9370 Multi-KEM Combiner on AMD Phoenix AIE2 hardware."""
    require_hardware_runtime()
    *_, XRTTensor = _load_iron()

    desc_bytes = pack_dr24_descriptor(operation_mode=MODE_RFC9370_COMBINE, payload_len=160, epoch=epoch)
    req_buf = bytearray(REQ_BYTES)
    req_buf[0:32] = k_classic[:32]
    req_buf[32:64] = k_pqc[:32]
    req_buf[64:96] = k_qkd[:32] if k_qkd else b"\x00" * 32
    req_buf[96:160] = ni_nr[:64]

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
        raise RuntimeError(f"DR24 RFC 9370 Combiner hardware error status: {status}")

    ske = raw_res[16:48]
    ska = raw_res[48:80]
    skd = raw_res[80:112]
    return ske, ska, skd, dt_ms


def wireguard_encaps_on_aie2(
    ske: bytes,
    ska: bytes,
    seq_num: int,
    plaintext: bytes,
    epoch: int = 1,
) -> Tuple[bytes, float]:
    """Executes WireGuard Packet Encapsulation on AMD Phoenix AIE2 hardware."""
    require_hardware_runtime()
    *_, XRTTensor = _load_iron()

    desc_bytes = pack_dr24_descriptor(
        operation_mode=MODE_WIREGUARD_ENCAPS,
        payload_len=len(plaintext),
        seq_num=seq_num,
        epoch=epoch,
    )
    req_buf = bytearray(REQ_BYTES)
    req_buf[0:32] = ske[:32]
    req_buf[32:64] = ska[:32]
    req_buf[64:64 + len(plaintext)] = plaintext

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
        raise RuntimeError(f"DR24 WireGuard Encaps hardware error status: {status}")

    packet_len = struct.unpack_from("<I", raw_res, 12)[0]
    out_packet = raw_res[16:16 + packet_len]
    return out_packet, dt_ms


def wireguard_decaps_on_aie2(
    ske: bytes,
    ska: bytes,
    packet: bytes,
    epoch: int = 1,
) -> Tuple[int, bytes, int, float]:
    """Executes WireGuard Packet Decapsulation on AMD Phoenix AIE2 hardware."""
    require_hardware_runtime()
    *_, XRTTensor = _load_iron()

    desc_bytes = pack_dr24_descriptor(
        operation_mode=MODE_WIREGUARD_DECAPS,
        payload_len=len(packet),
        epoch=epoch,
    )
    req_buf = bytearray(REQ_BYTES)
    req_buf[0:32] = ske[:32]
    req_buf[32:64] = ska[:32]
    req_buf[64:64 + len(packet)] = packet

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
        return 0, b"", status, dt_ms

    seq_num = struct.unpack_from("<Q", raw_res, 16)[0]
    pt_len = struct.unpack_from("<Q", raw_res, 24)[0]
    plaintext = raw_res[32:32 + pt_len]
    return seq_num, plaintext, status, dt_ms


def async_rekey_on_aie2(
    skd: bytes,
    rekey_seed: bytes,
    epoch: int = 1,
) -> Tuple[bytes, bytes, bytes, float]:
    """Executes Asynchronous Background Rekeying on AMD Phoenix AIE2 hardware."""
    require_hardware_runtime()
    *_, XRTTensor = _load_iron()

    desc_bytes = pack_dr24_descriptor(operation_mode=MODE_ASYNC_REKEY, payload_len=64, epoch=epoch)
    req_buf = bytearray(REQ_BYTES)
    req_buf[0:32] = skd[:32]
    req_buf[32:64] = rekey_seed[:32]

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
        raise RuntimeError(f"DR24 Async Rekey hardware error status: {status}")

    ske = raw_res[16:48]
    ska = raw_res[48:80]
    skd_next = raw_res[80:112]
    return ske, ska, skd_next, dt_ms


# =========================================================================
# Independent Host Reference Oracles
# =========================================================================

def _ref_shake256(data: bytes, outlen: int) -> bytes:
    h = hashlib.shake_256()
    h.update(data)
    return h.digest(outlen)


def ref_rfc9370_combine(
    k_classic: bytes,
    k_pqc: bytes,
    k_qkd: bytes,
    ni_nr: bytes,
) -> Tuple[bytes, bytes, bytes]:
    combo = bytearray(160)
    combo[0:32] = k_classic[:32]
    combo[32:64] = k_pqc[:32]
    if k_qkd:
        combo[64:96] = k_qkd[:32]
    combo[96:160] = ni_nr[:64]

    derived = _ref_shake256(bytes(combo), 96)
    return derived[0:32], derived[32:64], derived[64:96]


def ref_wireguard_encaps(
    ske: bytes,
    ska: bytes,
    seq_num: int,
    plaintext: bytes,
) -> bytes:
    seq_bytes = struct.pack("<Q", seq_num)
    keystream = _ref_shake256(ske[:32] + seq_bytes, len(plaintext))
    ciphertext = bytes(a ^ b for a, b in zip(plaintext, keystream))
    tag = _ref_shake256(ska[:32] + seq_bytes + ciphertext, 16)
    return seq_bytes + tag + ciphertext


def ref_wireguard_decaps(
    ske: bytes,
    ska: bytes,
    packet: bytes,
) -> Tuple[int, bytes, int]:
    if len(packet) < 24:
        return 0, b"", 1
    seq_num = struct.unpack_from("<Q", packet, 0)[0]
    tag = packet[8:24]
    ciphertext = packet[24:]
    seq_bytes = packet[0:8]
    expected_tag = _ref_shake256(ska[:32] + seq_bytes + ciphertext, 16)
    if tag != expected_tag:
        return seq_num, b"", 2
    keystream = _ref_shake256(ske[:32] + seq_bytes, len(ciphertext))
    plaintext = bytes(a ^ b for a, b in zip(ciphertext, keystream))
    return seq_num, plaintext, 0


def ref_async_rekey(
    skd: bytes,
    rekey_seed: bytes,
) -> Tuple[bytes, bytes, bytes]:
    new_keys = _ref_shake256(skd[:32] + rekey_seed[:32], 96)
    return new_keys[0:32], new_keys[32:64], new_keys[64:96]
