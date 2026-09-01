# DR26 Research and Citation Provenance: Multi-Architecture Hardware Scaling

## Milestone Deliverable Context
- Deliverable: **DR26 (AMD XDNA 2 & AMD Alveo V70 Multi-Architecture Scaling)**
- Target: AMD Phoenix (XDNA 1 / 20 tiles), AMD Strix Point (XDNA 2 / 32 tiles), AMD Alveo V70 (AIE2 / 304 tiles)
- Objective: Provide multi-architecture hardware topology descriptors, column/row partitioners, memory map validators, and multi-target compilation generators across client and datacenter AIE2/XDNA platforms.

## Citation Ledger

### Citation 1: AMD XDNA 1 Architecture Whitepaper (Phoenix APU)
- Source Title: AMD Ryzen 7040 Series Processors with AMD XDNA Architecture
- Author / Organization: Advanced Micro Devices (AMD)
- URL: https://www.amd.com/en/technologies/xdna.html
- Publication Date: May 2023
- Exact Technical Specifications:
  - Architecture: AIE2 (AIE-ML v1), 20 compute tiles arranged in a 4-row by 5-column spatial array.
  - Per-tile local SRAM: 64 KiB data memory, 16 KiB program memory.
  - Shim architecture: 1 row of shim interface/DMA tiles interfacing with host memory via XRT.
- Implementation Impact: Implemented baseline 4x5 spatial grid allocator and DMA channel binding for Phoenix client NPU.

### Citation 2: AMD XDNA 2 Architecture (Strix Point Ryzen AI 300 Series)
- Source Title: AMD Ryzen AI 300 Series Processors with AMD XDNA 2 Architecture
- Author / Organization: Advanced Micro Devices (AMD)
- URL: https://www.amd.com/en/products/processors/laptop/ryzen/ryzen-ai-300-series.html
- Publication Date: July 2024
- Exact Technical Specifications:
  - Architecture: AIE2P (XDNA 2), 32 compute tiles arranged in a 4-row by 8-column spatial array delivering up to 50 TOPS.
  - Enhanced stream switches and doubled DMA routing channels across columns.
- Implementation Impact: Implemented 4x8 spatial topology partitioner and multi-column cryptographic stream mapper for Strix Point.

### Citation 3: AMD Alveo V70 Data Center Accelerator Architecture
- Source Title: AMD Alveo V70 Accelerator Card User Guide (UG1575)
- Author / Organization: Advanced Micro Devices (AMD)
- URL: https://docs.amd.com/r/en-US/ug1575-alveo-v70
- Publication Date: 2023
- Exact Technical Specifications:
  - Architecture: AIE2 datacenter matrix with 304 compute tiles arranged in an 8-row by 38-column array.
  - Highly parallel spatial scheduling permitting concurrent dispatch of up to 38 independent PQC kernel columns.
- Implementation Impact: Implemented datacenter 8x38 spatial topology allocator and multi-instance stream balancer on Alveo V70.
