# SPDX-License-Identifier: Apache-2.0
"""
Milestone DR16: ETSI GS QKD 014 Key Container Parser & Sealed Ingress ABI
-------------------------------------------------------------------------
Compliant with ETSI GS QKD 014 (v1.1.1 / v1.3.1) REST Key Delivery API.
Target: AMD Phoenix NPU (AIE2 / XDNA1 Architecture).
"""

import base64
import json
import struct
import uuid
from typing import NamedTuple, Tuple

MAGIC_DESC_DR16 = b"\x01\x71\x52\x10"  # DR16 Descriptor Magic
MAGIC_RESULT_DR16 = b"QK16"                # DR16 Result Magic

# Descriptor Sizes
DESCRIPTOR_BYTES = 64
REQ_BYTES = 256
RESULT_BYTES = 64

# Status Codes
STATUS_SUCCESS = 0
STATUS_INVALID_MAGIC = 1
STATUS_CRC_MISMATCH = 2
STATUS_STALE_EPOCH = 3
STATUS_MALFORMED_KEY_ID = 4
STATUS_BUFFER_FULL = 5

class EtsiQkdKey(NamedTuple):
    key_id: uuid.UUID
    key_bytes: bytes
    epoch: int
    source_sae_id: str
    target_sae_id: str

def parse_etsi_014_json(json_str, epoch: int = 1, source_sae: str = "SAE_MASTER", target_sae: str = "SAE_SLAVE") -> list[EtsiQkdKey]:
    """Parse standard ETSI GS QKD 014 JSON Key Container response."""
    if isinstance(json_str, dict):
        data = json_str
    elif isinstance(json_str, (bytes, bytearray)):
        data = json.loads(json_str.decode('utf-8'))
    elif isinstance(json_str, str):
        data = json.loads(json_str)
    else:
        raise TypeError(f"Expected dict, str, or bytes, got {type(json_str)}")
    keys_list = []
    if "keys" not in data or not isinstance(data["keys"], list):
        raise ValueError("Invalid ETSI GS QKD 014 format: missing 'keys' list.")

    for k in data["keys"]:
        raw_id = k.get("key_ID") or k.get("key_id")
        raw_key = k.get("key")
        if not raw_id or not raw_key:
            continue

        parsed_uuid = uuid.UUID(str(raw_id))
        # Handle base64 or hex key format
        try:
            key_bytes = base64.b64decode(raw_key)
        except Exception:
            key_bytes = bytes.fromhex(raw_key)

        keys_list.append(EtsiQkdKey(
            key_id=parsed_uuid,
            key_bytes=key_bytes,
            epoch=epoch,
            source_sae_id=source_sae,
            target_sae_id=target_sae
        ))

    return keys_list

def pack_dr16_descriptor(key_id: uuid.UUID, epoch: int, key_len: int = 32, request_id: int = 1, flags: int = 0) -> bytes:
    """Pack 64-byte DR16 AIE2 Ingress Descriptor."""
    # Layout:
    # 0..3: Magic (4B)
    # 4..7: request_id (uint32)
    # 8..11: epoch (uint32)
    # 12..13: key_len (uint16)
    # 14: milestone (16)
    # 15: flags (uint8)
    # 16..31: UUID bytes (16B)
    # 32..63: reserved padding (32B)
    buf = bytearray(DESCRIPTOR_BYTES)
    buf[0:4] = MAGIC_DESC_DR16
    buf[4:8] = request_id.to_bytes(4, "little")
    buf[8:12] = epoch.to_bytes(4, "little")
    buf[12:14] = key_len.to_bytes(2, "little")
    buf[14] = 16
    buf[15] = flags
    buf[16:32] = key_id.bytes
    return bytes(buf)

def pack_dr16_request(key_bytes: bytes, source_sae: str = "SAE_MASTER", target_sae: str = "SAE_SLAVE") -> bytes:
    """Pack 256-byte DR16 Ingress Payload."""
    # Layout:
    # 0..63: key material (up to 64B)
    # 64..95: source SAE ID (32B utf-8 string)
    # 96..127: target SAE ID (32B utf-8 string)
    # 128..255: reserved zero padding
    buf = bytearray(REQ_BYTES)
    buf[0:min(len(key_bytes), 64)] = key_bytes[:64]
    src_b = source_sae.encode("utf-8")[:32]
    tgt_b = target_sae.encode("utf-8")[:32]
    buf[64:64+len(src_b)] = src_b
    buf[96:96+len(tgt_b)] = tgt_b
    return bytes(buf)

def unpack_dr16_result(raw_bytes: bytes) -> Tuple[int, int, int, int, uuid.UUID]:
    """Unpack 64-byte DR16 AIE2 Ingress Result.
    Returns: (request_id, status, active_slot, crc32, uuid)
    """
    if len(raw_bytes) < RESULT_BYTES:
        raise ValueError(f"DR16 result buffer too small: {len(raw_bytes)} < {RESULT_BYTES}")

    magic = raw_bytes[0:4]
    req_id = int.from_bytes(raw_bytes[4:8], "little")
    status = int.from_bytes(raw_bytes[8:12], "little")
    active_slot = int.from_bytes(raw_bytes[12:16], "little")
    crc32 = int.from_bytes(raw_bytes[16:20], "little")
    key_uuid = uuid.UUID(bytes=raw_bytes[20:36])
    return req_id, status, active_slot, crc32, key_uuid
