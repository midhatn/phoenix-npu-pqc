# SPDX-License-Identifier: Apache-2.0
"""
Milestone DR35: Real-Time AIE2 Silicon Visualizer & Column Occupancy Dashboard ABI
----------------------------------------------------------------------------------
Microarchitectural telemetry descriptors and snapshot dataclasses for AMD Phoenix AIE2.
Target: AMD Phoenix NPU (AIE2 / XDNA1 Architecture - 4x6 Tile Grid).
DOI: 10.5281/zenodo.22164124
"""

import struct
from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Optional, Any

MAGIC_DESC_DR35 = b"\x01\x35\x56\x49"   # DR35 Descriptor Magic ('\x015VI')
MAGIC_RESULT_DR35 = b"VI35"                # DR35 Result Magic

# Tile States
TILE_STATE_IDLE           = "IDLE"
TILE_STATE_INGRESS_DMA    = "INGRESS_DMA"
TILE_STATE_ACTIVE_COMPUTE = "ACTIVE_COMPUTE"
TILE_STATE_EGRESS_DMA     = "EGRESS_DMA"
TILE_STATE_ZEROIZING      = "ZEROIZING"
TILE_STATE_LOCKED         = "LOCKED_FAULT"

# Tile Types
TILE_TYPE_SHIM            = "SHIM_DMA"  # Row 0
TILE_TYPE_MEMTILE         = "MEMTILE"   # Row 1
TILE_TYPE_COMPUTE         = "COMPUTE"   # Rows 2..5

NUM_COLUMNS = 4
NUM_ROWS = 6

@dataclass
class TileTelemetrySnapshot:
    col: int
    row: int
    tile_type: str
    state: str = TILE_STATE_IDLE
    active_algo: Optional[str] = None
    sram_used_bytes: int = 0
    sram_capacity_bytes: int = 65536
    cycle_count: int = 0
    utilization_pct: float = 0.0

@dataclass
class NpuArraySnapshot:
    timestamp: float
    device_bdf: str
    firmware_version: str
    tiles: List[TileTelemetrySnapshot] = field(default_factory=list)
    total_sram_used_bytes: int = 0
    total_sram_capacity_bytes: int = 0
    ops_per_sec: Dict[str, float] = field(default_factory=dict)
    temperature_celsius: float = 48.5
    dma_bandwidth_mbps: float = 0.0
    active_tiles_count: int = 0
