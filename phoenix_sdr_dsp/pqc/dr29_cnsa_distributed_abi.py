# SPDX-License-Identifier: Apache-2.0
"""ABI definitions and parameter structures for Milestone DR29:
NSA CNSA 2.0 Level 5 Multi-Tile Distributed Memory Engine on AMD Phoenix AIE2.
"""
from __future__ import annotations

import struct
from typing import NamedTuple

MAGIC_DESC_DR29 = 0x01294D54  # DR29 Multi-Tile Distributed Memory magic

# CNSA 2.0 Algorithm Types
CNSA_ALGO_MLDSA87   = 1  # ML-DSA-87 (k=8, l=7, 56 polynomials, q=8380417)
CNSA_ALGO_MLKEM1024 = 2  # ML-KEM-1024 (k=4, l=4, 16 polynomials, q=3329)

# Operation Modes
MODE_DISTRIBUTED_PARTITION = 0  # Query cluster memory partitioning & SRAM footprints
MODE_DISTRIBUTED_ROW_ACCUM = 1  # Compute tile-resident matrix-vector row accumulation
MODE_CLUSTER_AGGREGATE    = 2  # Aggregate multi-tile partial vectors into final vector


class DR29Descriptor(NamedTuple):
    magic: int
    operation_mode: int
    algo_type: int
    tile_index: int
    num_tiles: int
    epoch: int
    reserved1: int
    reserved2: int


def pack_dr29_descriptor(
    operation_mode: int,
    algo_type: int,
    tile_index: int = 0,
    num_tiles: int = 4,
    epoch: int = 1,
) -> bytes:
    """Packs 32-byte hardware descriptor for DR29 distributed memory operations."""
    desc = bytearray(32)
    struct.pack_into(
        "<IIIIIIII",
        desc,
        0,
        MAGIC_DESC_DR29,
        int(operation_mode),
        int(algo_type),
        int(tile_index),
        int(num_tiles),
        int(epoch),
        0, 0,
    )
    return bytes(desc)


def unpack_dr29_descriptor(data: bytes) -> DR29Descriptor:
    if len(data) < 32:
        raise ValueError(f"Descriptor requires 32 bytes, received {len(data)}")
    magic, op_mode, algo, tile_idx, num_tiles, epoch, r1, r2 = struct.unpack_from("<IIIIIIII", data, 0)
    if magic != MAGIC_DESC_DR29:
        raise ValueError(f"Invalid DR29 magic: 0x{magic:08X} != 0x{MAGIC_DESC_DR29:08X}")
    return DR29Descriptor(
        magic=magic,
        operation_mode=op_mode,
        algo_type=algo,
        tile_index=tile_idx,
        num_tiles=num_tiles,
        epoch=epoch,
        reserved1=r1,
        reserved2=r2,
    )
