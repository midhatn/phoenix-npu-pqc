# SPDX-License-Identifier: Apache-2.0
"""Host/device ABI contracts for Milestone DR4 (ML-KEM-512 K-PKE.Decrypt)."""
from __future__ import annotations

import struct
import zlib

# Operation Constants
DESCRIPTOR_BYTES = 16
REQUEST_PAYLOAD_BYTES = 1536  # dk_PKE[768] || c[768]
DECOMPRESS_TOKEN_BYTES = 5136 # header[16] + 5 * 1024 B (s_hat0, s_hat1, u_hat0, u_hat1, v in uint32_t)
RESULT_HEADER_BYTES = 20
PLAINTEXT_BYTES = 32
RESULT_BYTES = 52

# Magic Headers
DESCRIPTOR_MAGIC = 0x00524101  # [0x01, 0x41, 0x52, 0x00] -> v1, op=0x41 (DR4 Decrypt), param=0x52 (ML-KEM-512)
RESULT_MAGIC = 0x4434524D      # b"MR4D"

# Status Codes
STATUS_OK = 0
STATUS_LIMIT_EXCEEDED = 1
STATUS_BAD_DESCRIPTOR = 2
STATUS_BAD_TOKEN = 3

def build_descriptor(request_id: int = 1) -> bytes:
    """Builds a canonical 16-byte DR4 descriptor."""
    return struct.pack(
        "<BBBBBBBBII",
        1,       # ABI v1
        0x41,    # Opcode 0x41 (DR4 K-PKE.Decrypt)
        0x52,    # Param 0x52 (ML-KEM-512)
        0,       # Reserved
        2,       # k = 2
        10,      # du = 10
        4,       # dv = 4
        0,       # Reserved
        request_id,
        0,       # Reserved
    )

def validate_request(dk_pke: bytes, c: bytes, request_id: int = 1) -> tuple[bytes, bytes]:
    """Validates inputs and builds descriptor (16 B) and request payload (1536 B)."""
    if len(dk_pke) != 768:
        raise ValueError(f"Invalid dk_pke length: {len(dk_pke)} (expected 768)")
    if len(c) != 768:
        raise ValueError(f"Invalid ciphertext length: {len(c)} (expected 768)")
    
    descriptor = build_descriptor(request_id)
    request_payload = dk_pke + c
    return descriptor, request_payload

def unpack_result(raw_result: bytes, expected_request_id: int | None = None) -> bytes:
    """Unpacks and validates the 52-byte result record, returning the 32-byte decrypted plaintext."""
    if len(raw_result) < RESULT_BYTES:
        raise ValueError(f"Result truncated: {len(raw_result)} < {RESULT_BYTES} bytes")
    
    magic, req_id, status, length, checksum = struct.unpack("<IIIII", raw_result[:RESULT_HEADER_BYTES])
    
    if magic != RESULT_MAGIC:
        raise ValueError(f"Invalid magic: {magic:#x} (expected {RESULT_MAGIC:#x})")
    if expected_request_id is not None and req_id != expected_request_id:
        raise ValueError(f"Request ID mismatch: {req_id} != {expected_request_id}")
    if status != STATUS_OK:
        raise RuntimeError(f"Device error status: {status}")
    if length != PLAINTEXT_BYTES:
        raise ValueError(f"Invalid plaintext length: {length} (expected {PLAINTEXT_BYTES})")
    
    plaintext = raw_result[RESULT_HEADER_BYTES : RESULT_HEADER_BYTES + PLAINTEXT_BYTES]
    expected_crc = zlib.crc32(plaintext)
    if checksum != expected_crc:
        raise ValueError(f"CRC32 mismatch: {checksum:#x} != {expected_crc:#x}")
        
    return bytes(plaintext)
