# SPDX-License-Identifier: Apache-2.0
"""
Milestone DR29: NSA CNSA 2.0 Level 5 Multi-Tile Distributed Memory Engine ABI
-----------------------------------------------------------------------------
Spatial 4-tile cluster and MemTile distributed memory layout for Category 5 PQC.
Target: AMD Phoenix NPU (AIE2 / XDNA1 Architecture).
DOI: 10.5281/zenodo.22164124
"""

import struct
from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional

MAGIC_DESC_DR29 = b"\x01\x29\x43\x4E"   # DR29 Descriptor Magic ('\x01)CN')
MAGIC_RESULT_DR29 = b"CN29"                # DR29 Result Magic

# CNSA 2.0 Algorithm Constants
CNSA_ALGO_MLKEM_1024 = 0x00001024
CNSA_ALGO_MLDSA_87   = 0x00000087

# Moduli Constants
MOD_MLKEM_Q3329    = 3329
MOD_MLDSA_Q8380417  = 8380417

# Polynomial Degree
N_DEGREE = 256

# Tile Hardware Memory Limits
TILE_SRAM_BYTES = 64 * 1024      # 64 KiB physical limit per AIE2 tile
TARGET_PEAK_SRAM_BYTES = 25 * 1024 # 25 KiB ceiling target (< 44 KiB requirement)

@dataclass(frozen=True)
class CnsaParams:
    algo_id: int
    name: str
    modulus: int
    rows: int      # k (rows of matrix A)
    cols: int      # l (columns of matrix A)
    total_polys: int # k * l
    bytes_per_poly: int

CNSA_PARAMS: Dict[int, CnsaParams] = {
    CNSA_ALGO_MLKEM_1024: CnsaParams(
        algo_id=CNSA_ALGO_MLKEM_1024,
        name="ML-KEM-1024",
        modulus=MOD_MLKEM_Q3329,
        rows=4, cols=4, total_polys=16,
        bytes_per_poly=512 # 256 * 2 bytes
    ),
    CNSA_ALGO_MLDSA_87: CnsaParams(
        algo_id=CNSA_ALGO_MLDSA_87,
        name="ML-DSA-87",
        modulus=MOD_MLDSA_Q8380417,
        rows=8, cols=7, total_polys=56,
        bytes_per_poly=1024 # 256 * 4 bytes
    ),
}

@dataclass
class SubMatrixChunk:
    """Represents a spatial sub-matrix assigned to one AIE2 tile in the 2x2 cluster."""
    node_id: int        # Node 0 (2,0), Node 1 (2,1), Node 2 (2,2), Node 3 (2,3)
    row_start: int
    row_end: int        # Exclusive
    col_start: int
    col_end: int        # Exclusive
    polys: List[List[List[int]]] # Matrix of polynomials [row][col][256]

    @property
    def num_polys(self) -> int:
        return (self.row_end - self.row_start) * (self.col_end - self.col_start)

    @property
    def sram_bytes(self) -> int:
        """Computes active memory working set on this compute tile."""
        bytes_per_coeff = 2 if self.row_end <= 4 and self.col_end <= 4 else 4
        poly_bytes = self.num_polys * N_DEGREE * bytes_per_coeff
        vec_bytes = (self.col_end - self.col_start) * N_DEGREE * bytes_per_coeff
        accum_bytes = (self.row_end - self.row_start) * N_DEGREE * bytes_per_coeff
        return poly_bytes + vec_bytes + accum_bytes + 512 # 512B ping-pong overhead
