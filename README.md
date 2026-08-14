# Phoenix SDR-DSP

<div align="center">

![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)
![Target: AMD Phoenix NPU1](https://img.shields.io/badge/Target-AMD%20Ryzen%20AI%20NPU1%20(AIE2)-blue)
![Host: Windows 11 Pro](https://img.shields.io/badge/Host-Windows%2011%20Pro%2025H2-0078D6)
![Silicon Status: 100% Verified](https://img.shields.io/badge/Silicon%20Status-100%25%20PASS%20(12%2F12)-brightgreen)
![Compiler: LLVM Peano](https://img.shields.io/badge/Compiler-LLVM%20Peano%20AIE2-purple)

**High-Performance Vectorized Software Defined Radio (SDR) & Number Theoretic Transform (NTT) Acceleration Engine on AMD Ryzen AI Phoenix Silicon (XDNA1 / AIE2)**

[Architecture](#1-system--hardware-architecture) • [Directory Structure](#2-repository-structure) • [Silicon Milestones](#3-validated-silicon-milestones) • [Engineering Issues & Fixes](#4-engineering-challenges--technical-solutions) • [Quickstart](#5-quickstart--silicon-verification) • [References](#6-references--upstream-projects) • [Credits](#7-credits--acknowledgments)

</div>

---

## 1. System & Hardware Architecture

The **Phoenix SDR-DSP** framework provides native Windows 11 acceleration for real-time SDR processing and finite-field lattice cryptography on AMD Ryzen 7040/8040 series processors.

- **Target APU:** AMD Ryzen 9 7940HS (8 Cores / 16 Threads @ 4.0–5.2 GHz)
- **NPU Silicon:** AMD XDNA1 / 1st Gen Ryzen AI (`npu1`)
  - **Tile Array:** 4 Columns $\times$ 5 Rows of AI Engine 2 (AIE2) tiles
  - **Vector Architecture:** 512-bit SIMD registers supporting 64-lane `bfloat16`, 32-lane `int16`, and 16-lane `cint16`
  - **Local Memory:** 64 KB local data memory per tile (four 16 KB banks)
- **Host Operating System:** Windows 11 Pro 25H2
- **Compilation Toolchain:** LLVM Peano `clang++` (`--target=aie2-none-unknown-elf`)
- **Runtime Environment:** IRON Python eDSL JIT + Native Windows XRT Runtime (`xrt_core.dll` / `CachedXRTHostRuntime`)

---

## 2. Repository Structure

```text
phoenix-sdr-dsp/
├── include/
│   └── sdr_dsp/
│       ├── sdr_dsp_common.hpp      # Vector types, lane constants, Q15 definitions
│       ├── fir_filter.hpp           # 64-lane vectorized FIR filtering
│       ├── complex_mixer.hpp        # Complex NCO & I/Q frequency shifter
│       ├── power_detector.hpp       # I^2 + Q^2 energy / RSSI detector
│       ├── modular_arithmetic.hpp   # Barrett & Montgomery modular reduction mod q=3329
│       └── ntt_butterfly.hpp        # Cooley-Tukey & Gentleman-Sande butterflies
├── tests/
│   ├── m5_fir/                      # Milestone 5: 8-Tap Vectorized Low-Pass FIR Filter
│   ├── m6_mixer/                    # Milestone 6: Complex Mixer / NCO Frequency Downconverter
│   ├── m7_power/                    # Milestone 7: Power / RSSI Energy Detector
│   ├── m8_pipeline/                 # Milestone 8: Streaming Multi-Stage Fused Demodulator Pipeline
│   ├── m9_parallel/                 # Milestone 9: 4-Column Parallel FIR Filter (Hardware Scaling)
│   ├── m10_modular/                 # Milestone 10: Modular Arithmetic & Barrett Reduction
│   ├── m11_butterfly/               # Milestone 11: Radix-2 NTT Butterfly Kernel
│   ├── m12_ntt_ref/                 # Milestone 12: CPU NTT/INTT Reference & Constant Generator
│   ├── m13_ntt16/                   # Milestone 13: 16-Point Vectorized NPU NTT (64 Batches)
│   ├── m14_ntt256/                  # Milestone 14: 256-Point Vectorized NPU NTT (4 Batches)
│   └── m15_polymul/                 # Milestone 15: NPU INTT & Cyclic Polynomial Multiplication
├── run_all_silicon_tests.py         # Automated Master Regression Suite
├── LICENSE                          # MIT License
├── CONTRIBUTING.md                  # Contribution Guidelines
└── README.md                        # Master Project Documentation
```

---

## 3. Validated Silicon Milestones

Every milestone is verified on physical Phoenix NPU silicon (`npu1`) against an independent mathematical reference:

| Milestone | Component / DSP Primitive | Target Array | Workload / Dimensions | Silicon Status | Verification Result |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **M3** | Single-Core SAXPY Vector Operation | Tile `(0,2)` | 4096 `bfloat16` elements | **PASS** | Bit-Exact ($0.0$ error) |
| **M5** | 8-Tap Vectorized Low-Pass FIR | Tile `(0,2)` | 4096 elements | **PASS** | $L_\infty \le 0.007812$ |
| **M6** | Complex Mixer / NCO Downconverter | Tile `(0,2)` | 2048 I/Q pairs | **PASS** | $L_\infty \le 0.007812$ |
| **M7** | Power / RSSI Energy Detector | Tile `(0,2)` | 2048 I/Q $\to$ 2048 P | **PASS** | $L_\infty \le 0.015625$ |
| **M8** | Multi-Stage Fused Demodulator | Tile `(0,2)` | RF I/Q $\to$ Mix $\to$ FIR $\to$ Pwr | **PASS** | Zero stack allocation |
| **M9** | 4-Column Parallel FIR Scaling | 4 Columns `(0..3,2)` | 4096 samples (1024/core) | **PASS** | 4-Core Parallel Lockstep |
| **M10** | Modular Arithmetic & Barrett Reduction | Tile `(0,2)` | 1024 pairs mod $q=3329$ | **PASS** | Bit-Exact Match |
| **M11** | Radix-2 NTT Butterfly Kernel | Tile `(0,2)` | 1024 CT butterflies mod $q$ | **PASS** | Bit-Exact Match |
| **M12** | NTT Constant & Reference Engine | CPU Reference | $N=16, 256$, $\omega^N \equiv 1$ | **PASS** | Bit-Exact Match |
| **M13** | 16-Point Vectorized NPU NTT | Tile `(0,2)` | 64 parallel frames (1024 elems) | **PASS** | Bit-Exact Match |
| **M14** | 256-Point Vectorized NPU NTT | Tile `(0,2)` | 4 parallel frames (1024 elems) | **PASS** | Bit-Exact Match |
| **M15** | NPU INTT & Polynomial Multiplication | Tile `(0,2)` | $C(x) = A(x) \times B(x) \pmod{x^{256}-1}$ | **PASS** | Bit-Exact Match |

---

## 4. Engineering Challenges & Technical Solutions

During development on native Windows 11 with the AMD IRON/AIE2 toolchain, several architecture-specific hurdles were identified and resolved:

### 1. `XRTTensor` Host Buffer Alignment & Type Constraints
- **Issue:** Passing 16-bit integers directly to `XRTTensor` failed with `TypeError: Cannot cast array data from dtype('int16') to dtype('uint32') according to the rule 'same_kind'`.
- **Root Cause:** AMD XRT DMA host buffers enforce 32-bit word alignment.
- **Solution:** Packed adjacent 16-bit operands ($I/Q$ sample pairs or modular $(A, B)$ polynomials) into native `uint32` arrays on the host, unpacking them into SIMD vector registers inside the AIE2 kernel.

### 2. AIE2 Tile Local Data Memory Overflow (64 KB Bank Budget)
- **Issue:** Kernel compilation aborted with `[aiecc] error: 'aie.tile' op allocated buffers exceeded available memory`.
- **Root Cause:** AIE2 tile data memory is strictly 64 KB (divided into four 16 KB banks). Allocating 16 KB double-buffered ping-pong ObjectFIFOs for both input and output exceeded available SRAM.
- **Solution:** Right-sized burst buffer lengths to 1024 elements (4 KB per buffer), allowing input/output ping-pong buffering ($16\text{ KB}$ total) while reserving remaining banks for kernel stack and precomputed twiddle LUTs.

### 3. Peano Header Resolution Across Cache Directories
- **Issue:** Peano failed with `fatal error: 'sdr_dsp/...' file not found` during JIT compilation.
- **Root Cause:** IRON generates temporary compilation units in user cache directories (`%USERPROFILE%\.npu\cache\...`), breaking relative C++ include paths.
- **Solution:** Implemented self-contained kernels or programmatically forwarded absolute include paths via `include_dirs=[cxx_header_path(), str(include_sdr_dir)]`.

### 4. Decimation-in-Time NTT Twiddle Table Stride Indexing
- **Issue:** 16-Point and 256-Point NTT stage-2/stage-3 butterflies exhibited non-trivial bin mismatches against direct $O(N^2)$ DFT.
- **Root Cause:** Radix-2 Decimation-in-Time (DIT) butterflies require twiddle powers $\omega^{j \cdot (N / 2^s)}$ at stage $s$. Using flat twiddle indexing introduced phase errors.
- **Solution:** Derived programmatic stage stride step indexing (`W[j * (N >> stage)]`), achieving bit-exact match ($0$ error) across all transform sizes.

---

## 5. Quickstart & Silicon Verification

### Prerequisites
- AMD Ryzen 7040 / 8040 APU (Ryzen 9 7940HS or similar Phoenix/Hawk Point silicon).
- Windows 11 Pro 22H2 / 23H2 / 25H2 with AMD NPU driver enabled.
- Python 3.10+ virtual environment (`ironenv`) containing MLIR-AIE, IRON, and LLVM Peano compiler.

### Running the Full Silicon Test Suite
In PowerShell:

```powershell
& "C:\phoenix-sdr-dsp\third_party\mlir-aie\ironenv\Scripts\Activate.ps1"
Set-Location C:\phoenix-sdr-dsp
python run_all_silicon_tests.py
```

Expected output:
```text
======================================================================
                     REGRESSION EXECUTION SUMMARY
======================================================================
 [ PASS ] Milestone 3: Single-Core SAXPY Vector Operation              (3.98s)
 [ PASS ] Milestone 5: 8-Tap Vectorized Low-Pass FIR Filter            (4.06s)
 [ PASS ] Milestone 6: Complex Mixer / NCO Frequency Downconverter     (3.86s)
 [ PASS ] Milestone 7: Vectorized Power / RSSI Energy Detector         (3.82s)
 [ PASS ] Milestone 8: Streaming Multi-Stage Fused Demodulator Pipeline (4.32s)
 [ PASS ] Milestone 9: 4-Column Parallel FIR Filter (Hardware Scaling) (4.15s)
 [ PASS ] Milestone 10: Modular Arithmetic & Barrett Reduction (mod 3329) (3.88s)
 [ PASS ] Milestone 11: Radix-2 NTT Butterfly Kernel (mod 3329)        (3.85s)
 [ PASS ] Milestone 12: CPU NTT/INTT Reference & Constant Generator    (0.12s)
 [ PASS ] Milestone 13: 16-Point Vectorized NPU NTT (64 Batches)       (3.91s)
 [ PASS ] Milestone 14: 256-Point Vectorized NPU NTT (4 Batches)       (3.95s)
 [ PASS ] Milestone 15: NPU INTT & Cyclic Polynomial Multiplication    (4.08s)
----------------------------------------------------------------------
 Total Tests Run: 12 | Passed: 12 | Failed: 0
 Total Elapsed Time: 44.18 seconds

 *** ALL SILICON DSP & NTT REGRESSION TESTS PASSED BIT-ACCURATELY! ***
```

---

## 6. References & Upstream Projects

- [Xilinx / AMD MLIR-AIE](https://github.com/Xilinx/mlir-aie): AI Engine MLIR dialect and LLVM backend.
- [AMD XDNA Driver](https://github.com/amd/xdna-driver): Linux and Windows kernel driver for AMD XDNA architecture.
- [Peano LLVM-AIE Compiler](https://github.com/Xilinx/mlir-aie/tree/main/peano): Clang/LLVM fork targeting AIE/AIE2 vector units.
- [AMD XRT (Xilinx Runtime)](https://github.com/Xilinx/XRT): Host runtime for PCIe and APU accelerator device management.
- [NTT on AMD AI Engine](https://github.com/hal-lab-u-tokyo/ntt-aie): NTT reference implementation on AI Engine architectures.

---

## 7. Credits & Acknowledgments

- **Lead Architect & Maintainer:** Midhat ([@midhatn](https://github.com/midhatn))
- **AI Architecture & Engineering Partner:** Perplexity AI (Senior AMD XDNA / AIE & DSP Copilot)
- **License:** MIT License — See [LICENSE](LICENSE) for details.