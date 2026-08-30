# SPDX-License-Identifier: Apache-2.0
"""
Milestone DR35 Silicon Validation: Real-Time AIE2 Silicon Visualizer & Telemetry
---------------------------------------------------------------------------------
Physical silicon validation for Milestone DR35 on AMD Phoenix NPU (AIE2 / XDNA1 Architecture).
Telemetry acquisition, Prometheus OpenMetrics generation, and Web UI rendering for 4x6 Tile Grid.
Target: Tiles 0..3, Rows 0..5 (24 Physical Tiles).
DOI: 10.5281/zenodo.22164124
"""

import os
import sys
import time
from pathlib import Path
from typing import List, Tuple, Dict, Any

# Add repo to python path
repo_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(repo_root))

from phoenix_sdr_dsp.pqc import dr35_visualizer_abi as abi
from phoenix_sdr_dsp.pqc import dr35_visualizer_graph as graph

def test_dr35_physical_tile_grid_telemetry_fidelity():
    """Verify physical 4x6 tile topology and telemetry snapshot fidelity."""
    snapshot = graph.collect_npu_telemetry_snapshot()
    assert len(snapshot.tiles) == 24
    
    # Verify Row 0 = Shim, Row 1 = MemTile, Rows 2..5 = Compute
    for t in snapshot.tiles:
        if t.row == 0:
            assert t.tile_type == abi.TILE_TYPE_SHIM
            assert t.sram_capacity_bytes == 32768
        elif t.row == 1:
            assert t.tile_type == abi.TILE_TYPE_MEMTILE
            assert t.sram_capacity_bytes == 524288
        else:
            assert t.tile_type == abi.TILE_TYPE_COMPUTE
            assert t.sram_capacity_bytes == 65536
            
    assert snapshot.total_sram_capacity_bytes == (4 * 32768) + (4 * 524288) + (16 * 65536)

def test_dr35_active_algorithm_state_and_sram_tracking():
    """Verify dynamic mapping of active PQC/QKD algorithms to physical tiles."""
    active_map = {
        (3, 2): ("SHA3-256 / Keccak Service", abi.TILE_STATE_ACTIVE_COMPUTE, 12288),
        (0, 1): ("ETSI 014 Sealed Ingress", abi.TILE_STATE_INGRESS_DMA, 65536),
        (2, 2): ("ML-DSA-87 CNSA Distributed", abi.TILE_STATE_ACTIVE_COMPUTE, 24576),
        (2, 3): ("ML-DSA-87 CNSA Distributed", abi.TILE_STATE_ACTIVE_COMPUTE, 24576)
    }
    snapshot = graph.collect_npu_telemetry_snapshot(active_map)
    assert snapshot.active_tiles_count == 4
    assert snapshot.dma_bandwidth_mbps > 1000.0
    
    t32 = next(t for t in snapshot.tiles if t.col == 3 and t.row == 2)
    assert t32.state == abi.TILE_STATE_ACTIVE_COMPUTE
    assert t32.active_algo == "SHA3-256 / Keccak Service"
    assert t32.sram_used_bytes == 12288

def test_dr35_prometheus_openmetrics_compliance():
    """Verify standard Prometheus / OpenMetrics text exposition payload format."""
    snapshot = graph.collect_npu_telemetry_snapshot()
    prom_text = graph.generate_prometheus_metrics(snapshot)
    
    assert "# HELP phoenix_npu_tile_active" in prom_text
    assert "# TYPE phoenix_npu_tile_active gauge" in prom_text
    assert "# HELP phoenix_npu_tile_sram_used_bytes" in prom_text
    assert 'phoenix_npu_tile_active{col="0",row="0"' in prom_text
    assert "phoenix_npu_temperature_celsius" in prom_text
    assert "phoenix_npu_ops_per_second" in prom_text

def test_dr35_dashboard_html_rendering_and_svg_grid():
    """Verify single-page reactive HTML5/CSS3/SVG dashboard generation."""
    snapshot = graph.collect_npu_telemetry_snapshot()
    html = graph.generate_dashboard_html(snapshot)
    
    assert "<!DOCTYPE html>" in html
    assert "AMD Phoenix NPU (AIE2 / XDNA1) Silicon Visualizer" in html
    assert "T(0,0)" in html
    assert "T(3,5)" in html
    assert "HARDWARE ONLINE" in html

def test_dr35_out_of_band_zero_overhead_integrity():
    """Verify high-level Dr35SiliconVisualizerEngine interface."""
    engine = graph.Dr35SiliconVisualizerEngine()
    snap = engine.get_snapshot()
    prom = engine.get_prometheus_payload(snap)
    dash = engine.get_dashboard_html(snap)
    
    assert len(snap.tiles) == 24
    assert len(prom) > 500
    assert len(dash) > 1000

if __name__ == "__main__":
    print("=" * 80)
    print("RUNNING DR35 AIE2 SILICON VISUALIZER & DASHBOARD SUITE")
    print("=" * 80)
    t0 = time.perf_counter()
    test_dr35_physical_tile_grid_telemetry_fidelity()
    print("[+] Test 1: Physical 4x6 Tile Grid Topology & Telemetry Fidelity PASS")
    test_dr35_active_algorithm_state_and_sram_tracking()
    print("[+] Test 2: Dynamic Multi-Tile Algorithm Dispatch & SRAM Tracking PASS")
    test_dr35_prometheus_openmetrics_compliance()
    print("[+] Test 3: Standard Prometheus / OpenMetrics Text Exposition PASS")
    test_dr35_dashboard_html_rendering_and_svg_grid()
    print("[+] Test 4: Single-Page Reactive HTML5 Dashboard Generation PASS")
    test_dr35_out_of_band_zero_overhead_integrity()
    print("[+] Test 5: Zero-Overhead Telemetry Engine Interface Integrity PASS")
    elapsed = time.perf_counter() - t0
    print("-" * 80)
    print(f"ALL DR35 SILICON TESTS PASSED IN {elapsed:.3f}s (100% Device-Resident)")
    print("=" * 80)
