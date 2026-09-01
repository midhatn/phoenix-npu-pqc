# SPDX-License-Identifier: Apache-2.0
"""ABI definitions and parameter structures for Milestone DR28:
NIST SP 800-208 / RFC 8554 Leighton-Micali Signatures (LMS/HSS) Stateless Verification on AMD Phoenix AIE2.
"""
from __future__ import annotations

import struct
from typing import NamedTuple

MAGIC_DESC_DR28 = 0x01284C4D  # DR28 LMS Verifier magic identifier

# RFC 8554 Type Identifiers
LMS_SHA256_M32_H5    = 0x00000005  # LMS tree depth h=5, hash length m=32
LMOTS_SHA256_N32_W4  = 0x00000003  # LM-OTS hash length n=32, winternitz w=4, p=67

# Operation Modes
MODE_VERIFY_LMS_SIGNATURE = 0  # Full end-to-end LMS verification
MODE_RECOVER_LMOTS_LEAF   = 1  # Reconstruct candidate LM-OTS leaf node
MODE_MERKLE_PATH_TRAVERSE = 2  # Evaluate Merkle authentication path to root


class DR28Descriptor(NamedTuple):
    magic: int
    operation_mode: int
    msg_len: int
    epoch: int
    lms_type: int
    lmots_type: int
    reserved1: int
    reserved2: int


def pack_dr28_descriptor(
    operation_mode: int,
    msg_len: int,
    epoch: int = 1,
    lms_type: int = LMS_SHA256_M32_H5,
    lmots_type: int = LMOTS_SHA256_N32_W4,
) -> bytes:
    """Packs 32-byte hardware descriptor for DR28 LMS verification."""
    desc = bytearray(32)
    struct.pack_into(
        "<IIIIIIII",
        desc,
        0,
        MAGIC_DESC_DR28,
        int(operation_mode),
        int(msg_len),
        int(epoch),
        int(lms_type),
        int(lmots_type),
        0, 0,
    )
    return bytes(desc)


def unpack_dr28_descriptor(data: bytes) -> DR28Descriptor:
    if len(data) < 32:
        raise ValueError(f"Descriptor requires 32 bytes, received {len(data)}")
    magic, op_mode, msg_len, epoch, lms_type, lmots_type, r1, r2 = struct.unpack_from("<IIIIIIII", data, 0)
    if magic != MAGIC_DESC_DR28:
        raise ValueError(f"Invalid DR28 magic: 0x{magic:08X} != 0x{MAGIC_DESC_DR28:08X}")
    return DR28Descriptor(
        magic=magic,
        operation_mode=op_mode,
        msg_len=msg_len,
        epoch=epoch,
        lms_type=lms_type,
        lmots_type=lmots_type,
        reserved1=r1,
        reserved2=r2,
    )
