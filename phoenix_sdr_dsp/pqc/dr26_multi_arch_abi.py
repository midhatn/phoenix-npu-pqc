# SPDX-License-Identifier: Apache-2.0
"""ABI definitions and hardware topology structures for Milestone DR26:
AMD XDNA 2 & AMD Alveo V70 Multi-Architecture Scaling on AMD Phoenix AIE2.
"""
from __future__ import annotations

import struct
from typing import NamedTuple, Dict, Any

MAGIC_DESC_DR26 = 0x01264152  # DR26 Multi-Arch Scaling magic identifier

# Architecture Identifiers
ARCH_PHOENIX_XDNA1 = 0  # Phoenix (XDNA 1): 4 rows x 5 cols (20 compute tiles)
ARCH_STRIX_XDNA2   = 1  # Strix Point (XDNA 2): 4 rows x 8 cols (32 compute tiles)
ARCH_ALVEO_V70     = 2  # Alveo V70 (AIE2): 8 rows x 38 cols (304 compute tiles)

# Operation Modes
MODE_QUERY_ARCH_TOPOLOGY = 0  # Query array geometry and tile capacity
MODE_VALIDATE_GRID_FIT   = 1  # Validate spatial allocation and DMA constraints
MODE_PARTITION_COLUMNS   = 2  # Partition spatial array into concurrent PQC pipelines
MODE_EMIT_MLIR_TOPOLOGY  = 3  # Generate multi-target MLIR device topology map


class ArchitectureSpec(NamedTuple):
    arch_id: int
    name: str
    rows: int
    cols: int
    total_tiles: int
    dma_channels_per_col: int
    sram_per_tile_kb: int
    prog_mem_per_tile_kb: int
    peak_tops: int


ARCH_SPECS: Dict[int, ArchitectureSpec] = {
    ARCH_PHOENIX_XDNA1: ArchitectureSpec(
        arch_id=ARCH_PHOENIX_XDNA1,
        name="AMD Phoenix (XDNA 1)",
        rows=4,
        cols=5,
        total_tiles=20,
        dma_channels_per_col=2,
        sram_per_tile_kb=64,
        prog_mem_per_tile_kb=16,
        peak_tops=10,
    ),
    ARCH_STRIX_XDNA2: ArchitectureSpec(
        arch_id=ARCH_STRIX_XDNA2,
        name="AMD Strix Point (XDNA 2)",
        rows=4,
        cols=8,
        total_tiles=32,
        dma_channels_per_col=4,
        sram_per_tile_kb=64,
        prog_mem_per_tile_kb=16,
        peak_tops=50,
    ),
    ARCH_ALVEO_V70: ArchitectureSpec(
        arch_id=ARCH_ALVEO_V70,
        name="AMD Alveo V70 (Datacenter)",
        rows=8,
        cols=38,
        total_tiles=304,
        dma_channels_per_col=4,
        sram_per_tile_kb=64,
        prog_mem_per_tile_kb=16,
        peak_tops=200,
    ),
}


class DR26Descriptor(NamedTuple):
    magic: int
    operation_mode: int
    target_arch: int
    requested_tiles: int
    epoch: int
    reserved: int


def pack_dr26_descriptor(
    operation_mode: int,
    target_arch: int = ARCH_PHOENIX_XDNA1,
    requested_tiles: int = 1,
    epoch: int = 1,
) -> bytes:
    """Packs 32-byte hardware descriptor for DR26 multi-architecture scaling."""
    desc = bytearray(32)
    struct.pack_into(
        "<IIIIIIII",
        desc,
        0,
        MAGIC_DESC_DR26,
        int(operation_mode),
        int(target_arch),
        int(requested_tiles),
        int(epoch),
        0, 0, 0,
    )
    return bytes(desc)


def unpack_dr26_descriptor(data: bytes) -> DR26Descriptor:
    if len(data) < 32:
        raise ValueError(f"Descriptor requires 32 bytes, received {len(data)}")
    magic, op_mode, target_arch, req_tiles, epoch, r1, r2, r3 = struct.unpack_from("<IIIIIIII", data, 0)
    if magic != MAGIC_DESC_DR26:
        raise ValueError(f"Invalid DR26 magic: 0x{magic:08X} != 0x{MAGIC_DESC_DR26:08X}")
    return DR26Descriptor(
        magic=magic,
        operation_mode=op_mode,
        target_arch=target_arch,
        requested_tiles=req_tiles,
        epoch=epoch,
        reserved=r1,
    )
