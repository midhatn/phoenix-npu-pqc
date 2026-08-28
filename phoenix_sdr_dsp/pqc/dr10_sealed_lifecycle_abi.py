# SPDX-License-Identifier: Apache-2.0
"""DR10 Entropy/Key-Source and Sealed-Lifecycle ABI on AMD Phoenix AIE2."""
import struct
from typing import Tuple

MAGIC_DESC_DR10 = b"\x01\x71\x52\x0A"  # DR10 Descriptor Magic
MAGIC_RESULT_DR10 = b"MR0H"               # DR10 Result Magic

# Source Modes
SOURCE_MODE_RAW_INGRESS = 0
SOURCE_MODE_NPU_DRBG = 1
SOURCE_MODE_AUTH_QKD_INGRESS = 2
SOURCE_MODE_SEALED_SESSION = 3

# Key Material Domain Flags
DOMAIN_MLKEM_512 = 0x01
DOMAIN_MLKEM_768 = 0x02
DOMAIN_MLKEM_1024 = 0x03
DOMAIN_MLDSA_44 = 0x04
DOMAIN_MLDSA_65 = 0x05
DOMAIN_MLDSA_87 = 0x06

def pack_dr10_descriptor(
    source_mode: int,
    domain_id: int,
    request_id: int = 1,
    epoch: int = 1,
    flags: int = 0
) -> bytes:
    """Pack 16-byte DR10 descriptor."""
    # Layout:
    # 0..3: Magic
    # 4: source_mode
    # 5: domain_id
    # 6: milestone (10)
    # 7: flags
    # 8..11: request_id
    # 12..15: epoch
    return struct.pack("<4sBBBBII", MAGIC_DESC_DR10, source_mode, domain_id, 10, flags, request_id, epoch)

def pack_dr10_auth_qkd_request(
    key_material: bytes,
    source_id: bytes,
    epoch: int,
    domain_id: int
) -> bytes:
    """Pack 256-byte Authenticated External / QKD key payload."""
    # Header (32 B):
    # 0..3: Magic b"QKD1"
    # 4..7: epoch (uint32)
    # 8: domain_id
    # 9..15: reserved
    # 16..31: source_id (16 B)
    # 32..95: raw key material (64 B)
    # 96..127: auth tag (32 B SHA3-256 HMAC over header + key)
    header = bytearray(32)
    header[0:4] = b"QKD1"
    header[4:8] = epoch.to_bytes(4, "little")
    header[8] = domain_id
    header[16:32] = source_id.ljust(16, b"\x00")[:16]

    buf = bytearray(256)
    buf[0:32] = header
    buf[32:32 + len(key_material)] = key_material
    return bytes(buf)
