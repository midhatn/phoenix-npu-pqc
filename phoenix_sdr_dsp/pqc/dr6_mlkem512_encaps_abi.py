# SPDX-License-Identifier: Apache-2.0
"""Host/device ABI contracts for Milestone DR6 (ML-KEM-512 ML-KEM.Encaps)."""
from __future__ import annotations

import struct
import zlib

# Operation Constants
DESCRIPTOR_BYTES = 16
REQUEST_PAYLOAD_BYTES = 832  # ek[800] || m[32]
CIPHERTEXT_BYTES = 768
SHARED_SECRET_BYTES = 32
PAYLOAD_BYTES = 800          # c[768] || K[32]
RESULT_HEADER_BYTES = 20
RESULT_BYTES = 820           # header[20] + payload[800]

# Token Offsets (Inter-Worker Tokens)
DERIVATION_TOKEN_BYTES = 1168 # header[16] + K_bar[32] + r[32] + rho[32] + m[32] + t0[512] + t1[512]
NOISE_TOKEN_BYTES = 3664      # header[16] + K_bar[32] + rho[32] + r_hat0[512] + r_hat1[512] + e1_0[512] + e1_1[512] + e2_mu[512] + t_hat0[512] + t_hat1[512]
COL0_TOKEN_BYTES = 4688       # noise[3664] + A_T00[512] + A_T10[512]
U0_TOKEN_BYTES = 3472         # header[16] + K_bar[32] + rho[32] + u0[320] + r_hat0[512] + r_hat1[512] + e1_1[512] + e2_mu[512] + t_hat0[512] + t_hat1[512]
COL1_TOKEN_BYTES = 4496       # u0_token[3472] + A_T01[512] + A_T11[512]

# Magic Headers
DESCRIPTOR_MAGIC = 0x00526101  # [0x01, 0x61, 0x52, 0x00] -> v1, op=0x61 (DR6 ML-KEM.Encaps), param=0x52
RESULT_MAGIC = 0x4736524D      # b"MR6G"

# Status Codes
STATUS_OK = 0
STATUS_LIMIT_EXCEEDED = 1
STATUS_BAD_DESCRIPTOR = 2
STATUS_BAD_TOKEN = 3


def build_descriptor(request_id: int = 1) -> bytes:
    """Builds a canonical 16-byte DR6 descriptor."""
    return struct.pack(
        "<BBBBBBBBII",
        1,       # ABI v1
        0x61,    # Opcode 0x61 (DR6 ML-KEM.Encaps)
        0x52,    # Param 0x52 (ML-KEM-512)
        0,       # Reserved
        2,       # k = 2
        3,       # eta1 = 3
        5,       # SampleNTT block cap = 5
        0,       # Reserved
        request_id,
        0,       # Reserved
    )


def validate_request(ek: bytes, m: bytes, request_id: int = 1) -> tuple[bytes, bytes]:
    """Validates inputs and builds descriptor (16 B) and request payload (832 B)."""
    if len(ek) != 800:
        raise ValueError(f"Invalid ek length: {len(ek)} (expected 800)")
    if len(m) != 32:
        raise ValueError(f"Invalid m length: {len(m)} (expected 32)")

    descriptor = build_descriptor(request_id)
    request_payload = ek + m
    return descriptor, request_payload


def unpack_result(raw_result: bytes, expected_request_id: int | None = None) -> tuple[bytes, bytes]:
    """Unpacks and validates the 820-byte result record, returning (c, K)."""
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

    c = bytes(payload[:CIPHERTEXT_BYTES])
    k = bytes(payload[CIPHERTEXT_BYTES : CIPHERTEXT_BYTES + SHARED_SECRET_BYTES])
    return c, k
