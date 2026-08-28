# SPDX-License-Identifier: Apache-2.0
"""Host/device ABI contracts for Milestone DR7 (ML-KEM-512 ML-KEM.Decaps)."""
from __future__ import annotations

import struct
import zlib

# Operation Constants
DESCRIPTOR_BYTES = 16
DK_BYTES = 1632              # dk_PKE[768] || ek[800] || H(ek)[32] || z[32]
CIPHERTEXT_BYTES = 768
REQUEST_PAYLOAD_BYTES = 2400 # dk[1632] || c[768]
SHARED_SECRET_BYTES = 32
PAYLOAD_BYTES = 32           # K[32]
RESULT_HEADER_BYTES = 20
RESULT_BYTES = 52            # header[20] + K[32]

# Token Offsets (Inter-Worker Tokens)
DERIVATION_TOKEN_BYTES = 1968
NOISE_TOKEN_BYTES = 4464
COL0_TOKEN_BYTES = 5488
U0_TOKEN_BYTES = 4272
COL1_TOKEN_BYTES = 5296

# Magic Headers
DESCRIPTOR_MAGIC = 0x00527101  # [0x01, 0x71, 0x52, 0x00] -> v1, op=0x71 (DR7 ML-KEM.Decaps), param=0x52
RESULT_MAGIC = 0x4737524D      # b"MR7G"

# Status Codes
STATUS_OK = 0
STATUS_LIMIT_EXCEEDED = 1
STATUS_BAD_DESCRIPTOR = 2
STATUS_BAD_TOKEN = 3


def build_descriptor(request_id: int = 1) -> bytes:
    """Builds a canonical 16-byte DR7 descriptor."""
    return struct.pack(
        "<BBBBBBBBII",
        1,       # ABI v1
        0x71,    # Opcode 0x71 (DR7 ML-KEM.Decaps)
        0x52,    # Param 0x52 (ML-KEM-512)
        0,       # Reserved
        2,       # k = 2
        3,       # eta1 = 3
        5,       # SampleNTT block cap = 5
        0,       # Reserved
        request_id,
        0,       # Reserved
    )


def validate_request(dk: bytes, c: bytes, request_id: int = 1) -> tuple[bytes, bytes]:
    """Validates inputs and builds descriptor (16 B) and request payload (2400 B)."""
    if len(dk) != DK_BYTES:
        raise ValueError(f"Invalid dk length: {len(dk)} (expected {DK_BYTES})")
    if len(c) != CIPHERTEXT_BYTES:
        raise ValueError(f"Invalid c length: {len(c)} (expected {CIPHERTEXT_BYTES})")

    descriptor = build_descriptor(request_id)
    request_payload = dk + c
    return descriptor, request_payload


def unpack_result(raw_result: bytes, expected_request_id: int | None = None) -> bytes:
    """Unpacks and validates the 52-byte result record, returning shared secret K (32 B)."""
    if len(raw_result) < RESULT_BYTES:
        raise ValueError(f"Result truncated: {len(raw_result)} < {RESULT_BYTES} bytes")

    magic, req_id, status, length, checksum = struct.unpack("<IIIII", raw_result[:RESULT_HEADER_BYTES])

    if magic != RESULT_MAGIC:
        raise ValueError(f"Invalid magic: {magic:#x} (expected {RESULT_MAGIC:#x})")
    if expected_request_id is not None and req_id != expected_request_id:
        raise ValueError(f"Request ID mismatch: {req_id} != {expected_request_id}")
    if status != STATUS_OK:
        raise RuntimeError(f"Device error status: {status}")
    if length != PAYLOAD_BYTES:
        raise ValueError(f"Invalid payload length: {length} (expected {PAYLOAD_BYTES})")

    payload = raw_result[RESULT_HEADER_BYTES : RESULT_HEADER_BYTES + PAYLOAD_BYTES]
    expected_crc = zlib.crc32(payload)
    if checksum != expected_crc:
        raise ValueError(f"CRC32 mismatch: {checksum:#x} != {expected_crc:#x}")

    return bytes(payload)
