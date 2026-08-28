# SPDX-License-Identifier: Apache-2.0
"""Host/device ABI contracts for Milestone DR5 (ML-KEM-512 ML-KEM.KeyGen)."""
from __future__ import annotations

import struct
import zlib

# Operation Constants
DESCRIPTOR_BYTES = 16
REQUEST_PAYLOAD_BYTES = 64  # d[32] || z[32]
EK_BYTES = 800
DK_BYTES = 1632
PAYLOAD_BYTES = 2432       # ek[800] || dk[1632]
RESULT_HEADER_BYTES = 20
RESULT_BYTES = 2452        # header[20] + payload[2432]

# Token Offsets (Inter-Worker Tokens)
SECRET_TOKEN_BYTES = 2128      # header[16] + rho[32] + z[32] + s_hat0[512] + s_hat1[512] + e_hat0[512] + e_hat1[512]
ROW_EXPAND_TOKEN_BYTES = 3152  # secret[2128] + A0[512] + A1[512]
ROW_ACCUMULATE_TOKEN_BYTES = 2128 # header[16] + rho[32] + z[32] + s_hat0[512] + s_hat1[512] + t_hat0[512] + e_hat1[512]
FINAL_TOKEN_BYTES = 2144       # header[16] + rho[32] + z[32] + s_hat0[512] + s_hat1[512] + t_hat0[512] + t_hat1[512]

# Magic Headers
DESCRIPTOR_MAGIC = 0x00525101  # [0x01, 0x51, 0x52, 0x00] -> v1, op=0x51 (DR5 ML-KEM.KeyGen), param=0x52
RESULT_MAGIC = 0x4735524D      # b"MR5G"

# Status Codes
STATUS_OK = 0
STATUS_LIMIT_EXCEEDED = 1
STATUS_BAD_DESCRIPTOR = 2
STATUS_BAD_TOKEN = 3

def build_descriptor(request_id: int = 1) -> bytes:
    """Builds a canonical 16-byte DR5 descriptor."""
    return struct.pack(
        "<BBBBBBBBII",
        1,       # ABI v1
        0x51,    # Opcode 0x51 (DR5 ML-KEM.KeyGen)
        0x52,    # Param 0x52 (ML-KEM-512)
        0,       # Reserved
        2,       # k = 2
        3,       # eta1 = 3
        5,       # SampleNTT block cap = 5
        0,       # Reserved
        request_id,
        0,       # Reserved
    )

def validate_request(d: bytes, z: bytes, request_id: int = 1) -> tuple[bytes, bytes]:
    """Validates seeds and builds descriptor (16 B) and request payload (64 B)."""
    if len(d) != 32:
        raise ValueError(f"Invalid d seed length: {len(d)} (expected 32)")
    if len(z) != 32:
        raise ValueError(f"Invalid z seed length: {len(z)} (expected 32)")
    
    descriptor = build_descriptor(request_id)
    request_payload = d + z
    return descriptor, request_payload

def unpack_result(raw_result: bytes, expected_request_id: int | None = None) -> tuple[bytes, bytes]:
    """Unpacks and validates the 2452-byte result record, returning (ek, dk)."""
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
        
    ek = bytes(payload[:EK_BYTES])
    dk = bytes(payload[EK_BYTES : EK_BYTES + DK_BYTES])
    return ek, dk
