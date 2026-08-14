# Phoenix SDR-DSP

High-Performance Vectorized Software Defined Radio (SDR) and Finite-Field DSP Acceleration Framework targeting the **AMD Ryzen AI NPU (Phoenix / XDNA1 / AIE2)** on Windows 11 Pro.

---

## 1. Hardware & System Architecture

- **Processor:** AMD Ryzen 9 7940HS APU (8 Cores / 16 Threads @ 4.0–5.2 GHz)
- **NPU Silicon:** AMD XDNA1 / 1st Gen Ryzen AI (`npu1`)
  - **Tile Array:** 4 Columns $\times$ 5 Rows of AI Engine 2 (AIE2) tiles
  - **Vector Units:** 512-bit SIMD registers supporting 64-lane `bfloat16`, 32-lane `int16`, and 16-lane `cint16`
  - **Local Memory:** 64 KB data memory per tile (four 16 KB banks)
- **Host OS:** Windows 11 Pro 25H2
- **Compiler Backend:** LLVM Peano `clang++` (`--target=aie2-none-unknown-elf`)
- **Runtime:** IRON Python eDSL JIT + AMD XRT Windows Native Runtime (`xrt_core.dll`)

---

## 2. Directory Structure

```text
phoenix-sdr-dsp/
├── include/
│   └── sdr_dsp/
│       ├── sdr_dsp_common.hpp      # Vector types, lane constants, Q15 definitions
│       ├── fir_filter.hpp           # 64-lane vectorized FIR filtering
│       ├── complex_mixer.hpp        # Complex NCO & I/Q frequency shifter
│       ├── power_detector.hpp       # I^2 + Q^2 energy / RSSI meter
│       ├── modular_arithmetic.hpp   # Barrett & Montgomery reduction mod q=3329
│       └── ntt_butterfly.hpp        # Cooley-Tukey & Gentleman-Sande butterflies
├── tests/
│   ├── m5_fir/                      # 8-Tap Vectorized Low-Pass FIR
│   ├── m6_mixer/                    # Complex Mixer / NCO Frequency Downconverter
│   ├── m7_power/                    # Power / RSSI Energy Detector
│   ├── m8_pipeline/                 # Streaming Multi-Stage Fused Demodulator
│   ├── m9_parallel/                 # 4-Column Parallel FIR Filter Scaling
│   ├── m10_modular/                 # Modular Arithmetic & Barrett Reduction
│   ├── m11_butterfly/               # Radix-2 NTT Butterfly Kernel
│   ├── m12_ntt_ref/                 # CPU NTT/INTT Reference & Constant Engine
│   ├── m13_ntt16/                   # 16-Point Vectorized NPU NTT (64 Batches)
│   ├── m14_ntt256/                  # 256-Point Vectorized NPU NTT (4 Batches)
│   └── m15_polymul/                 # NPU INTT & Cyclic Polynomial Multiplication
├── run_all_silicon_tests.py         # Automated regression test runner
└── README.md                        # Master repository documentation
```

---

## 3. Validated Silicon DSP Milestones

All kernels are compiled with LLVM Peano and executed on the physical Ryzen 9 7940HS NPU:

| Milestone | Component / DSP Primitive | Target Hardware | Workload / Dimensions | Silicon Status | Verification |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **M3** | Single-Core SAXPY Vector Operation | Tile `(0,2)` | 4096 `bfloat16` | **PASS** | Bit-Exact Match |
| **M5** | 8-Tap Vectorized Low-Pass FIR | Tile `(0,2)` | 4096 samples | **PASS** | $L_\infty \le 0.007812$ |
| **M6** | Complex Mixer / NCO Downconverter | Tile `(0,2)` | 2048 I/Q pairs | **PASS** | $L_\infty \le 0.007812$ |
| **M7** | Power / RSSI Energy Detector | Tile `(0,2)` | 2048 I/Q $\to$ 2048 P | **PASS** | $L_\infty \le 0.015625$ |
| **M8** | Multi-Stage Fused Demodulator | Tile `(0,2)` | RF I/Q $\to$ Mix $\to$ FIR $\to$ Pwr | **PASS** | Zero stack memory |
| **M9** | 4-Column Parallel FIR Scaling | 4 Columns `(0..3,2)` | 4096 samples (1024/core) | **PASS** | 4-Core Parallel Lockstep |
| **M10** | Modular Arithmetic (Barrett) | Tile `(0,2)` | 1024 pairs mod 3329 | **PASS** | Bit-Exact Match |
| **M11** | Radix-2 NTT Butterfly Kernel | Tile `(0,2)` | 1024 CT butterflies | **PASS** | Bit-Exact Match |
| **M12** | NTT Constant & Reference Engine | CPU Reference | $N=16, N=256$, $\omega^N \equiv 1$ | **PASS** | Bit-Exact Match |
| **M13** | 16-Point Vectorized NPU NTT | Tile `(0,2)` | 64 parallel frames (1024 elems) | **PASS** | Bit-Exact Match |
| **M14** | 256-Point Vectorized NPU NTT | Tile `(0,2)` | 4 parallel frames (1024 elems) | **PASS** | Bit-Exact Match |
| **M15** | NPU INTT & Polynomial Multiplication | Tile `(0,2)` | $C(x) = A(x) \times B(x) \pmod{x^{256}-1}$ | **PASS** | Bit-Exact Match |

---

## 4. Engineering Issues Encountered & Technical Resolutions

1. **`XRTTensor` Type Casting Constraint (`TypeError: Cannot cast array data from dtype('int16') to dtype('uint32')`):**
   - *Cause:* The underlying IRON `XRTTensor` buffer mapping initializes memory buffers as 32-bit aligned uint32 words.
   - *Resolution:* Packed adjacent 16-bit integers (or $I/Q$ sample pairs / $A/B$ modular operand pairs) into native `uint32` arrays on the host, unpacking via SIMD vector unpack instructions inside the AIE2 C++ kernel.
2. **Tile Local Memory Budget Overflow (`aie.tile op allocated buffers exceeded available memory`):**
   - *Cause:* The AIE2 tile local data memory is 64 KB (divided into four 16 KB banks). Allocating double-buffered ping-pong ObjectFIFOs of 16 KB for both inputs and outputs exceeded the 64 KB hardware capacity.
   - *Resolution:* Right-sized burst buffer lengths to 1024 elements (4 KB per buffer), ensuring ping-pong buffers consume $< 16\text{ KB}$ and leave headroom for kernel stack and lookup tables.
3. **Peano Header Resolution in Temporary Compilation Directories:**
   - *Cause:* IRON compiles external C++ kernels in temporary cache directories (`C:\Users\<user>\.npu\cache\...`) where relative include paths to `sdr_dsp/` can break if include paths aren't explicitly forwarded.
   - *Resolution:* Embedded self-contained standalone kernels with direct static constants or passed absolute include directory paths through `include_dirs=[cxx_header_path(), str(include_sdr_dir)]`.
4. **Decimation-in-Time NTT Twiddle Table Stride Alignment:**
   - *Cause:* In multi-stage Cooley-Tukey NTTs, stage $s$ requires twiddle factors $\omega^{j \cdot (N / 2^s)}$. Using a flat twiddle LUT index without the $N / 2^s$ stride factor caused spectral phase errors.
   - *Resolution:* Derived programmatic stage stride step indexing (`W[j * (N >> stage)]`), achieving bit-exact match against direct $O(N^2)$ finite-field DFTs.

---

## 5. Quickstart & Verification

Activate the IRON environment in PowerShell and execute all silicon tests:

```powershell
& "C:\phoenix-sdr-dsp\third_party\mlir-aie\ironenv\Scripts\Activate.ps1"
Set-Location C:\phoenix-sdr-dsp
python run_all_silicon_tests.py
```
