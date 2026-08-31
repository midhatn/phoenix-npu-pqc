# SPDX-License-Identifier: Apache-2.0
"""Unified ABI and descriptor packers for DR9 Reusable FIPS 202 NPU Service."""
import struct
from typing import Tuple

MAGIC_DESC = b"\x01\x71\x52\x00"  # Descriptor Magic
MAGIC_RESULT = b"MR9H"              # Result Magic (0x4839524D)

DESCRIPTOR_BYTES = 16
REQ_BYTES = 2048
RESULT_HEADER_BYTES = 20
RESULT_BYTES = 1044

FUNC_IDS = {
    "SHA3-224": 1,
    "SHA3-256": 2,
    "SHA3-384": 3,
    "SHA3-512": 4,
    "SHAKE128": 5,
    "SHAKE256": 6,
}

def pack_dr9_descriptor(func_name: str, msg_len: int, out_len: int, request_id: int = 1) -> bytes:
    """Pack 16-byte DR9 descriptor."""
    func_id = FUNC_IDS[func_name.upper()]
    return struct.pack("<4sBBBBII", MAGIC_DESC, func_id, 1, 9, 0, request_id, msg_len | (out_len << 16))

def pack_dr9_request(msg: bytes) -> bytes:
    """Pack 2048-byte request buffer with zero-padding."""
    if len(msg) > 2048:
        raise ValueError(f"Message length {len(msg)} exceeds 2048 bytes capacity")
    return msg.ljust(2048, b"\x00")

def pack_dr9_result_header(request_id: int, status: int, out_len: int, crc32: int) -> bytes:
    """Pack 20-byte result header."""
    return struct.pack("<4sIIII", MAGIC_RESULT, request_id, status, out_len, crc32)

def unpack_dr9_result(raw_result: bytes) -> Tuple[int, int, int, bytes, int]:
    """Unpack 1044-byte result buffer."""
    magic = raw_result[:4]
    req_id, status, out_len, crc32 = struct.unpack("<IIII", raw_result[4:20])
    digest = raw_result[20:20 + out_len]
    return req_id, status, out_len, digest, crc32
