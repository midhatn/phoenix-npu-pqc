# SPDX-License-Identifier: Apache-2.0
"""ABI definitions and descriptor structures for Milestone DR25:
Higher-Order Masking & On-Chip Local PRNG Entropy Expansion on AMD Phoenix AIE2.
"""
from __future__ import annotations

import struct
from typing import NamedTuple

MAGIC_DESC_DR25 = 0x01254D53  # DR25 Masking/PRNG magic identifier

# Operation Modes
MODE_PRNG_EXPAND        = 0  # Local SHAKE-128 seed expansion into uniform polynomial masks
MODE_MASK_1ST_ORDER     = 1  # 1st-order polynomial blinding (split into 2 shares)
MODE_MASK_2ND_ORDER     = 2  # 2nd-order polynomial blinding (split into 3 shares)
MODE_UNMASK_1ST_ORDER   = 3  # 1st-order polynomial unmasking (reconstruct secret)
MODE_UNMASK_2ND_ORDER   = 4  # 2nd-order polynomial unmasking (reconstruct secret)
MODE_MASKED_ADD_1ST     = 5  # Component-wise masked addition (1st-order, 2 shares)
MODE_MASKED_ADD_2ND     = 6  # Component-wise masked addition (2nd-order, 3 shares)
MODE_SNI_REFRESH_1ST    = 7  # Strong Non-Interfering (SNI) 1st-order share refresh
MODE_SNI_REFRESH_2ND    = 8  # Strong Non-Interfering (SNI) 2nd-order share refresh

# Modulus selection
MODULUS_MLKEM = 3329       # ML-KEM modulus q
MODULUS_MLDSA = 8380417    # ML-DSA modulus q


class DR25Descriptor(NamedTuple):
    magic: int
    operation_mode: int
    modulus: int
    num_coeffs: int  # Typically 256
    epoch: int
    reserved: int


def pack_dr25_descriptor(
    operation_mode: int,
    modulus: int = MODULUS_MLKEM,
    num_coeffs: int = 256,
    epoch: int = 1,
) -> bytes:
    """Packs 32-byte hardware descriptor for DR25 tile processing."""
    desc = bytearray(32)
    struct.pack_into(
        "<IIIIIIII",
        desc,
        0,
        MAGIC_DESC_DR25,
        int(operation_mode),
        int(modulus),
        int(num_coeffs),
        int(epoch),
        0, 0, 0,
    )
    return bytes(desc)


def unpack_dr25_descriptor(data: bytes) -> DR25Descriptor:
    if len(data) < 32:
        raise ValueError(f"Descriptor requires 32 bytes, received {len(data)}")
    magic, op_mode, modulus, num_coeffs, epoch, r1, r2, r3 = struct.unpack_from("<IIIIIIII", data, 0)
    if magic != MAGIC_DESC_DR25:
        raise ValueError(f"Invalid DR25 magic: 0x{magic:08X} != 0x{MAGIC_DESC_DR25:08X}")
    return DR25Descriptor(
        magic=magic,
        operation_mode=op_mode,
        modulus=modulus,
        num_coeffs=num_coeffs,
        epoch=epoch,
        reserved=r1,
    )
