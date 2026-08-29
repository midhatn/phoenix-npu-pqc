# SPDX-License-Identifier: Apache-2.0
"""
Milestone DR27: QRNG-OPENAPI v1.0 & NPU-Resident Key/Entropy Reservoir ABI.
Defines packet structures, NIST SP 800-90B health metrics, and token-bucket hysteresis constants.
"""

import json
import base64
import struct
from typing import Dict, Any, Tuple, Optional

# Magic Constants
DR27_DESC_MAGIC = 0x27527101
DR27_RES_MAGIC  = 0x37325251  # "QR27"

# Buffer Sizes
REQ_BYTES = 128         # Payload buffer (e.g. up to 128B entropy block per transfer)
DESCRIPTOR_BYTES = 32   # Control header: magic(4), req_id(4), op_code(2), flags(2), entropy_len(2), source_id(2), rct_val(4), apt_val(4), reserved(8)
RESULT_BYTES = 64       # Response: magic(4), req_id(4), status(4), fill_level(2), capacity(2), mode(2), reserved(2), crc32(4), payload(32), reserved(8)

# Operations
OP_INGRESS  = 0x0001
OP_DRAIN    = 0x0002
OP_STATUS   = 0x0003
OP_ZEROIZE  = 0x0004

# Status Codes
STATUS_SUCCESS             = 0x0000
STATUS_INVALID_MAGIC       = 0x0001
STATUS_HEALTH_CHECK_FAILED = 0x0002
STATUS_RESERVOIR_FULL      = 0x0003
STATUS_RESERVOIR_EMPTY     = 0x0004
STATUS_TAMPER_ZEROIZED     = 0x0005

# Reservoir Parameters
RESERVOIR_CAPACITY_SLOTS = 16    # 16 slots * 32 bytes = 512 bytes on-chip SRAM
SLOT_SIZE_BYTES          = 32
LOW_WATER_MARK_SLOTS     = 1     # <= 1 slot (~6.25% ~= 5% trigger -> State 1 Degraded)
HIGH_WATER_MARK_SLOTS    = 5     # >= 5 slots (~31.25% ~= 30% trigger -> State 0 Full Hybrid)

# Operational States
STATE_FULL_HYBRID = 0
STATE_DEGRADED_A  = 1

# NIST SP 800-90B Health Test Cutoffs (for 8-bit symbols, alpha = 2^-20)
# Repetition Count Test (RCT): Maximum consecutive identical bytes allowed
SP800_90B_RCT_CUTOFF = 10
# Adaptive Proportion Test (APT): Maximum occurrences of first byte in 512-sample window
SP800_90B_APT_WINDOW = 512
SP800_90B_APT_CUTOFF = 177

def eval_sp800_90b_health(data: bytes) -> Tuple[bool, int, int]:
    """
    Evaluates NIST SP 800-90B Health Tests:
    1. Repetition Count Test (RCT)
    2. Adaptive Proportion Test (APT) on sample windows
    Returns: (is_healthy, max_rct, max_apt)
    """
    if len(data) == 0:
        return False, 0, 0

    # 1. Repetition Count Test (RCT)
    max_rct = 1
    current_rct = 1
    for i in range(1, len(data)):
        if data[i] == data[i - 1]:
            current_rct += 1
            if current_rct > max_rct:
                max_rct = current_rct
        else:
            current_rct = 1

    if max_rct >= SP800_90B_RCT_CUTOFF:
        return False, max_rct, 0

    # 2. Adaptive Proportion Test (APT)
    window_size = min(len(data), SP800_90B_APT_WINDOW)
    max_apt = 0
    if window_size > 1:
        target = data[0]
        count = sum(1 for b in data[:window_size] if b == target)
        max_apt = count
        if count >= SP800_90B_APT_CUTOFF:
            return False, max_rct, max_apt

    return True, max_rct, max_apt

def parse_qrng_openapi_json(payload: Any) -> Dict[str, Any]:
    """
    Parses QRNG-OPENAPI v1.0 JSON container (/v1/entropy endpoint).
    Expected format:
    {
        "version": "1.0",
        "source_id": 1,
        "timestamp": "2026-08-29T19:00:00Z",
        "quality_bits_per_bit": 0.9998,
        "entropy_bytes_b64": "..." or "entropy_hex": "..."
    }
    """
    if isinstance(payload, bytes):
        payload = payload.decode('utf-8')
    if isinstance(payload, str):
        data = json.loads(payload)
    else:
        data = payload

    source_id = data.get("source_id", 1)
    quality = float(data.get("quality_bits_per_bit", 1.0))
    
    if "entropy_bytes_b64" in data:
        raw_entropy = base64.b64decode(data["entropy_bytes_b64"])
    elif "entropy_hex" in data:
        raw_entropy = bytes.fromhex(data["entropy_hex"])
    elif "entropy" in data and isinstance(data["entropy"], list):
        raw_entropy = bytes(data["entropy"])
    else:
        raise ValueError("Missing entropy payload in QRNG-OPENAPI container")

    return {
        "version": data.get("version", "1.0"),
        "source_id": source_id,
        "quality": quality,
        "entropy": raw_entropy,
        "length": len(raw_entropy)
    }

def format_qrng_openapi_json(entropy: bytes, source_id: int = 1, quality: float = 0.9998) -> str:
    """Formats a QRNG-OPENAPI v1.0 standard JSON container."""
    return json.dumps({
        "version": "1.0",
        "source_id": source_id,
        "timestamp": "2026-08-29T19:00:00Z",
        "quality_bits_per_bit": quality,
        "entropy_hex": entropy.hex(),
        "entropy_bytes_b64": base64.b64encode(entropy).decode('ascii'),
        "length_bytes": len(entropy)
    }, indent=2)

def pack_descriptor(
    req_id: int,
    op_code: int,
    entropy_len: int,
    source_id: int = 1,
    rct_val: int = 1,
    apt_val: int = 1
) -> bytes:
    """Packs 32-byte DR27 descriptor."""
    desc = bytearray(DESCRIPTOR_BYTES)
    struct.pack_into("<IIHH", desc, 0, DR27_DESC_MAGIC, req_id, op_code, 0)
    struct.pack_into("<HHII", desc, 12, entropy_len, source_id, rct_val, apt_val)
    return bytes(desc)

def unpack_result(res_bytes: bytes) -> Dict[str, Any]:
    """Unpacks 64-byte DR27 result."""
    if len(res_bytes) < RESULT_BYTES:
        raise ValueError(f"Result buffer too short: {len(res_bytes)} < {RESULT_BYTES}")
    
    magic, req_id, status = struct.unpack_from("<III", res_bytes, 0)
    fill_level, capacity, mode, reserved = struct.unpack_from("<HHHH", res_bytes, 12)
    crc32_val = struct.unpack_from("<I", res_bytes, 20)[0]
    payload = res_bytes[24:56]

    return {
        "magic": hex(magic),
        "req_id": req_id,
        "status": status,
        "status_str": "SUCCESS" if status == STATUS_SUCCESS else f"ERROR_{status}",
        "fill_level": fill_level,
        "capacity": capacity,
        "mode": mode,
        "mode_str": "STATE_0_FULL_HYBRID" if mode == STATE_FULL_HYBRID else "STATE_1_DEGRADED_A",
        "crc32": f"0x{crc32_val:08X}",
        "payload": bytes(payload)
    }
