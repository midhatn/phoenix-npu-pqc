# DR35 Architecture & Design: Real-Time AIE2 Silicon Visualizer & Column Occupancy Dashboard

<div align="center">

![Telemetry: Real-Time AIE2 Tile Heatmap](https://img.shields.io/badge/Telemetry-Real--Time%20AIE2%20Grid-005ea8)
![Metrics: Prometheus / OpenMetrics Compatible](https://img.shields.io/badge/Metrics-Prometheus%20%2F%20OpenMetrics-orange)
![UI: Reactive HTML5/CSS3/SVG Dashboard](https://img.shields.io/badge/Dashboard-Reactive%20HTML5%20%2F%20SVG-purple)
![Hardware: AMD Phoenix NPU (AIE2 / XDNA1)](https://img.shields.io/badge/Target-AMD%20Phoenix%20NPU%20(AIE2%20%2F%20XDNA1)-red)
[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.22164124.svg)](https://doi.org/10.5281/zenodo.22164124)

</div>

---

## 1. Executive Summary

Milestone **DR35** implements the **Real-Time AIE2 Silicon Visualizer & Column Occupancy Dashboard (Web UI & Prometheus Telemetry)** for the AMD Phoenix NPU (AIE2 / XDNA1 Architecture).

It provides complete microarchitectural observability into the physical $4 \times 6$ tile grid (Columns 0..3, Rows 0..5), rendering real-time tile activity heatmaps, per-tile SRAM high-water marks, active DMA channel transfers, active PQC/QKD algorithm dispatch, operations/sec throughput counters, and standard Prometheus `/metrics` exposition.

---

## 2. AIE2 $4 \times 6$ Physical Silicon Tile Grid Topology

```
┌──────────────┬──────────────┬──────────────┬──────────────┐
│  Tile (0,5)  │  Tile (1,5)  │  Tile (2,5)  │  Tile (3,5)  │  Row 5: Compute Worker Tiles (512-bit SIMD, 64 KiB SRAM)
├──────────────┼──────────────┼──────────────┼──────────────┤
│  Tile (0,4)  │  Tile (1,4)  │  Tile (2,4)  │  Tile (3,4)  │  Row 4: Compute Worker Tiles (512-bit SIMD, 64 KiB SRAM)
├──────────────┼──────────────┼──────────────┼──────────────┤
│  Tile (0,3)  │  Tile (1,3)  │  Tile (2,3)  │  Tile (3,3)  │  Row 3: Compute Worker Tiles (512-bit SIMD, 64 KiB SRAM)
├──────────────┼──────────────┼──────────────┼──────────────┤
│  Tile (0,2)  │  Tile (1,2)  │  Tile (2,2)  │  Tile (3,2)  │  Row 2: Compute Worker Tiles (512-bit SIMD, 64 KiB SRAM)
├──────────────┼──────────────┼──────────────┼──────────────┤
│ MemTile (0,1)│ MemTile (1,1)│ MemTile (2,1)│ MemTile (3,1)│  Row 1: Shared MemTiles (512 KiB SRAM per tile, 2 MiB Total)
├──────────────┼──────────────┼──────────────┼──────────────┤
│ ShimTile (0,0│ ShimTile (1,0│ ShimTile (2,0│ ShimTile (3,0│  Row 0: Shim / Host PCIe DMA Interface Tiles
└──────────────┴──────────────┴──────────────┴──────────────┘
    Column 0       Column 1       Column 2       Column 3
```

---

## 3. Telemetry Interfaces

1. **Prometheus / OpenMetrics Exporter (`/metrics`)**:
   * `phoenix_npu_tile_active{col="c", row="r", algo="a"}`: 1 if active, 0 if idle.
   * `phoenix_npu_tile_sram_used_bytes{col="c", row="r"}`: Current SRAM consumption.
   * `phoenix_npu_ops_per_second{algorithm="a"}`: Instantaneous throughput.
   * `phoenix_npu_temperature_celsius`: Silicon thermal reading.
   * `phoenix_npu_dma_bandwidth_mbps`: Ingress/egress bandwidth.

2. **Reactive Single-Page Web Dashboard (`/dashboard`)**:
   * Interactive SVG heatmap rendering the physical $4 \times 6$ silicon layout with color-coded tile state indicators (Idle, Ingress DMA, Active Compute, Egress DMA, Zeroizing).
   * Live real-time memory gauges and benchmark trigger controls.

---

## 4. References & Standards Citations

1. **OpenMetrics Specification v1.0.0 (IETF / CNCF)**.
2. **AMD XDNA1 / AIE2 Architecture Reference Manual (2024)**.
3. **Project Provenance & Scientific Repository:** [DOI: 10.5281/zenodo.22164124](https://doi.org/10.5281/zenodo.22164124).
