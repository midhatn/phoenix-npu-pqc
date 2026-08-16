# Phoenix SDR-DSP

<div align="center">

![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)
![Target: AMD Phoenix NPU1](https://img.shields.io/badge/Target-AMD%20Ryzen%20AI%20NPU1%20(AIE2)-blue)
![Host: Windows 11 Pro](https://img.shields.io/badge/Host-Windows%2011%20Pro%2025H2-0078D6)
![Silicon Status: 33/33 PASS](https://img.shields.io/badge/Silicon%20Status-33%2F33%20PASS-brightgreen)
![Release: v1.0.0](https://img.shields.io/badge/Release-v1.0.0-brightgreen)
![Post-Quantum Cryptography](https://img.shields.io/badge/Post--Quantum%20Cryptography-FIPS%20203%20%2B%20FIPS%20204-8a2be2)
![Xilinx XRT](https://img.shields.io/badge/Xilinx-XRT-e01f27)
![Xilinx MLIR-AIE](https://img.shields.io/badge/Xilinx-MLIR--AIE%20%2F%20IRON-e01f27)
![Compiler: LLVM Peano](https://img.shields.io/badge/Compiler-LLVM%20Peano%20AIE2-purple)
![I/Q: 7.46 Msps](https://img.shields.io/badge/I%2FQ-7.46%20Msps%20%C2%B7%2010%20TOPS%20NPU-ff6b00)
[![CI](https://github.com/midhatn/phoenix-sdr-dsp/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/midhatn/phoenix-sdr-dsp/actions/workflows/ci.yml)

**High-Performance Vectorized Software Defined Radio (SDR) & Number Theoretic Transform (NTT) Acceleration Engine on AMD Ryzen AI Phoenix Silicon (XDNA1 / AIE2)**

**Built on [Xilinx XRT](https://github.com/Xilinx/XRT), [Xilinx MLIR-AIE](https://github.com/Xilinx/mlir-aie) / [IRON](https://xilinx.github.io/mlir-aie/1.4.1/buildHostWinNative/), and [LLVM Peano](https://github.com/Xilinx/llvm-aie).**

**7.46 Msps of real I/Q on a 10 TOPS AMD laptop NPU.** 29.8 MB/s in · 59.7 MB/s in+out · ~92% NPU. No discrete GPU. No FPGA.

**33/33 silicon PASS** at **v1.0.0** (2026-08-16): SDR/DSP kernels M3–M27 plus Post-Quantum Cryptography ([FIPS 203](https://nvlpubs.nist.gov/nistpubs/fips/nist.fips.203.pdf) ML-KEM and [FIPS 204](https://nvlpubs.nist.gov/nistpubs/fips/nist.fips.204.pdf) ML-DSA) M32b/c/d/e + M33a/b/d/e. See [`docs/PQC_COMPLETE_V1.md`](docs/PQC_COMPLETE_V1.md) for the v1.0.0 release summary. New-user path: `git clone` → `py .\install.py` → `py .\run_all_silicon_tests.py`.

[Install](#installation) • [Architecture](#1-system--hardware-architecture) • [Directory Structure](#2-repository-structure) • [Silicon Milestones](#3-validated-silicon-milestones) • [I/Q Throughput](#iq-throughput) • [Engineering Issues & Fixes](#4-engineering-challenges--technical-solutions) • [Quickstart](#5-quickstart--silicon-verification) • [References](#6-references--upstream-projects) • [Credits](#7-credits--acknowledgments)  • [Documentation](docs/README.md)

</div>

---

## Installation

A new Windows 11 machine with a Phoenix / Hawk Point NPU only needs a clone of this repository. `install.py` is stdlib-only and wraps the official Xilinx / AMD native-Windows stack:

| Component | Pin | Upstream |
| :--- | :--- | :--- |
| [Xilinx XRT](https://github.com/Xilinx/XRT) (Xilinx Runtime) | Windows SDK [2.21.75](https://github.com/Xilinx/XRT/releases/tag/2.21.75) | host DMA / `pyxrt` |
| [Xilinx MLIR-AIE](https://github.com/Xilinx/mlir-aie) + [IRON](https://xilinx.github.io/mlir-aie/1.4.1/buildHostWinNative/) | wheel [v1.4.1](https://github.com/Xilinx/mlir-aie/releases/tag/v1.4.1) + source [`3ca0193`](https://github.com/Xilinx/mlir-aie/commit/3ca0193cea9e2c39ec670a65f93e1dd43c969f22) | AIE dialect, `iron.Runtime`, `aiecc` |
| [LLVM Peano](https://github.com/Xilinx/llvm-aie) (`llvm-aie`) | `21.0.0.2026080301+c9c5ecb7` | AIE2 `clang++` |
| AMD NPU driver / `xrt-smi` | ≥ `32.0.20102.3930` | already on the laptop |

Do not install `mlir_aie` from the rolling [`latest-wheels-4`](https://github.com/Xilinx/mlir-aie/releases/expanded_assets/latest-wheels-4) channel. An untagged checkout of pin `3ca0193` would otherwise resolve to an older series (observed: 1.3.4). `install.py` downloads the published v1.4.1 `cp313` wheel into a local wheelhouse and passes `--wheelhouse` to official [`iron_setup.py`](https://github.com/Xilinx/mlir-aie/blob/3ca0193/utils/iron_setup.py).

### New-user steps

```powershell
conda deactivate   # if a conda prompt is active
git clone https://github.com/midhatn/phoenix-sdr-dsp.git
cd phoenix-sdr-dsp
py .\install.py

# Post-Quantum Cryptography reference packages (M32 + M33)
.\third_party\mlir-aie\ironenv\Scripts\activate.bat
pip install kyber-py==1.0.1 dilithium-py==1.4.0 pytest

py .\run_all_silicon_tests.py
```

`py` is the [Windows Python launcher](https://docs.python.org/3/using/windows.html#python-launcher-for-windows) and binds to system CPython. The test runner re-execs `third_party\mlir-aie\ironenv\Scripts\python.exe` (where Xilinx IRON installed numpy / `mlir_aie` / `pyxrt`) and sets `PEANO_INSTALL_DIR` from that same checkout. No activate step is required for the runner itself; the `activate.bat` above is only needed to `pip install` the PQC reference packages into the same environment. Full walkthrough with citations: [`docs/SETUP_WINDOWS.md §Post-Quantum Cryptography reference dependencies`](docs/SETUP_WINDOWS.md#post-quantum-cryptography-reference-dependencies-m32--m33).

### Prerequisites

- AMD Ryzen 7040 / 8040 APU (Ryzen 9 7940HS or similar Phoenix/Hawk Point silicon).
- Windows 11 Pro 22H2 / 23H2 / 25H2 with the AMD NPU driver enabled.
- CPython 3.13, Git, CMake, and Visual Studio 2022/18 with the C++ and Clang/LLVM workloads (`llvm-objcopy` is required for the Peano wheel fixup). Official path: [mlir-aie 1.4.1 `buildHostWinNative`](https://xilinx.github.io/mlir-aie/1.4.1/buildHostWinNative/).

### Verified clean clone

On 2026-08-15 a wipe-and-clone of `main` on a second Windows volume ran the two commands above and reported **16/16 PASS** in **95.91 s** (cold xclbin compile) on a Ryzen 9 7940HS Phoenix NPU1. A cached re-run on the development tree is **17.46 s**. M15b remained schoolbook and bit-exact on the [Kyber](https://pq-crystals.org/kyber/data/kyber-specification-round3-20210804.pdf) / [FIPS 203](https://nvlpubs.nist.gov/nistpubs/fips/nist.fips.203.pdf) ring `Z_3329[x]/(x^{256}+1)`. v1.0.0 (2026-08-16) extends this to **33/33 PASS** by wiring in nine additional entries (M27 OFDM plus the Post-Quantum Cryptography track M32b/c/d/e + M33a/b/d/e) once the PQC reference packages above are installed into the same `ironenv`.

Longer Windows walkthrough: [`docs/SETUP_WINDOWS.md`](docs/SETUP_WINDOWS.md). Pin rationale: [`docs/M2_TOOLCHAIN_PIN.md`](docs/M2_TOOLCHAIN_PIN.md). v1.0.0 PQC summary: [`docs/PQC_COMPLETE_V1.md`](docs/PQC_COMPLETE_V1.md).

## 1. System & Hardware Architecture

The **Phoenix SDR-DSP** framework provides native Windows 11 acceleration for real-time SDR processing and finite-field lattice cryptography on AMD Ryzen 7040/8040 series processors.

- **Target APU:** AMD Ryzen 9 7940HS (8 Cores / 16 Threads @ 4.0–5.2 GHz)
- **NPU Silicon:** AMD XDNA1 / 1st Gen Ryzen AI (`npu1`), [up to 10 TOPS](https://www.amd.com/en/products/processors/laptop/ryzen/7000-series/amd-ryzen-9-7940hs.html) ([INT8 on Phoenix 7040](https://www.tomshardware.com/pc-components/cpus/the-refresh-that-wasnt-amd-announces-hawk-point-ryzen-8040-series-with-zen-4-rdna3-and-xdna-teases-strix-point))
  - **Tile Array:** 4 Columns $\times$ 5 Rows of AI Engine 2 (AIE2) tiles
  - **Vector Architecture:** 512-bit SIMD registers supporting 64-lane `bfloat16`, 32-lane `int16`, and 16-lane `cint16`
  - **Local Memory:** 64 KB local data memory per tile (four 16 KB banks)
- **Host Operating System:** Windows 11 Pro 25H2
- **Compilation Toolchain:** [LLVM Peano](https://github.com/Xilinx/llvm-aie) `clang++` (`--target=aie2-none-unknown-elf`)
- **Runtime Environment:** [Xilinx MLIR-AIE](https://github.com/Xilinx/mlir-aie) / [IRON](https://xilinx.github.io/mlir-aie/1.4.1/buildHostWinNative/) Python eDSL JIT + native Windows [Xilinx XRT](https://github.com/Xilinx/XRT) (`xrt_core.dll` / `CachedXRTHostRuntime`)

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
├── kernels/
│   └── fft_stockham_f32.cc          # Radix-4 Stockham FFT (adapted from AMD FFT_R4_AIE, Apache-2.0)
├── tests/
│   ├── m3_saxpy/                    # Milestone 3:  Single-Core SAXPY Vector Operation (bfloat16)
│   ├── m5_fir/                      # Milestone 5:  8-Tap Vectorized Low-Pass FIR Filter
│   ├── m6_mixer/                    # Milestone 6:  Complex Mixer / NCO Frequency Downconverter
│   ├── m7_power/                    # Milestone 7:  Power / RSSI Energy Detector
│   ├── m8_pipeline/                 # Milestone 8:  Streaming Multi-Stage Fused Demodulator Pipeline
│   ├── m9_parallel/                 # Milestone 9:  4-Column Parallel FIR Filter (Hardware Scaling)
│   ├── m9b_parallel_pipeline/       # Milestone 9b: 4-Column Parallel Multi-Stage Demodulator Pipeline
│   ├── m10_modular/                 # Milestone 10: Modular Arithmetic & Barrett Reduction
│   ├── m11_butterfly/               # Milestone 11: Radix-2 NTT Butterfly Kernel
│   ├── m12_ntt_ref/                 # Milestone 12: CPU NTT/INTT Reference & Constant Generator
│   ├── m13_ntt16/                   # Milestone 13: 16-Point Vectorized NPU NTT (64 Batches)
│   ├── m14_ntt256/                  # Milestone 14: 256-Point Vectorized NPU NTT (4 Batches)
│   ├── m15_polymul/                 # Milestone 15: NPU INTT & Cyclic Polynomial Multiplication
│   ├── m15b_negacyclic/             # Milestone 15b: Negacyclic Polynomial Multiplication (Kyber / ML-KEM ring)
│   ├── m32_mlkem/                   # Milestone 32: FIPS 203 ML-KEM (planned; not in the 16-suite)
│   ├── m16_fft_ref/                 # Milestone 16: CPU DFT/FFT Reference (three implementations, CI)
│   ├── m17_radix2_fft/              # Milestone 17: 64-Point NPU Radix-4 Stockham FFT + IFFT
│   ├── m17p_fft_parallel/           # Milestone 17p: 4-Column Parallel FFT Channelizer
│   └── npu_visible/                 # Demo: 4-column I/Q throughput (not in the 16-suite)
├── scripts/                         # Windows environment audit, bootstrap, and activation scripts
├── docs/                            # Milestones, mathematics, ROADMAP, Windows setup, toolchain pin
├── requirements/                    # Pinned toolchain versions
├── toolchain.yaml                   # Machine-readable pinned stack (silicon-verified components)
├── install.py                       # One-command Windows installer (clone, then run this)
├── run_all_silicon_tests.py         # Automated Master Regression Suite
├── CITATION.cff                     # Citation metadata (validated with cffconvert)
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
| **M9b** | 4-Column Parallel Multi-Stage Pipeline | 4 Columns `(0..3,2)` | 2048 I/Q burst / column | **PASS** | 2400.71 µs / burst, 0.85 MSamples/sec |
| **M10** | Modular Arithmetic & Barrett Reduction | Tile `(0,2)` | 1024 pairs mod $q=3329$ | **PASS** | Bit-Exact Match |
| **M11** | Radix-2 NTT Butterfly Kernel | Tile `(0,2)` | 1024 CT butterflies mod $q$ | **PASS** | Bit-Exact Match |
| **M12** | NTT Constant & Reference Engine | CPU Reference | $N=16, 256$, $\omega^N \equiv 1$ | **PASS** | Bit-Exact Match |
| **M13** | 16-Point Vectorized NPU NTT | Tile `(0,2)` | 64 parallel frames (1024 elems) | **PASS** | Bit-Exact Match |
| **M14** | 256-Point Vectorized NPU NTT | Tile `(0,2)` | 4 parallel frames (1024 elems) | **PASS** | Bit-Exact Match |
| **M15** | NPU INTT & Cyclic Polynomial Multiplication | Tile `(0,2)` | $C(x) = A(x) \times B(x) \pmod{x^{256}-1}$ | **PASS** | Bit-Exact Match |
| **M15b** | Negacyclic Polynomial Multiplication ([Kyber](https://pq-crystals.org/kyber/data/kyber-specification-round3-20210804.pdf) / [FIPS 203](https://nvlpubs.nist.gov/nistpubs/fips/nist.fips.203.pdf) ring) | Tile `(0,2)` | $C(x) = A(x) \times B(x) \pmod{x^{256}+1}$ | **PASS** | Bit-Exact Match |
| **M16** | CPU DFT/FFT Reference (three implementations) | CPU Reference (CI) | $N \in \{8..1024\}$ | **PASS** | $\le 10^{-13}$ vs NumPy `fft.fft` |
| **M17** | 64-Point NPU Radix-4 Stockham FFT + IFFT | Tile `(0,2)` | 64-point complex `bfloat16` | **PASS** | FFT SNR **138.79 dB**, IFFT round-trip **135.11 dB** |
| **M17p** | 4-Column Parallel FFT Channelizer | 4 Columns `(0..3,2)` | 64 parallel 64-point frames | **PASS** | 1,993 FFTs/sec, 0.51 MB/s I/Q |
| **M19** | 8-Tap Complex FIR (complex taps × complex I/Q) | Tile `(0,2)` | 4096 complex samples | **PASS** | Bit-Exact vs CPU reference |
| **M20** | Fused Polyphase Decimator (M=4) + Interpolator (L=4) | Tile `(0,2)` | 4096 complex samples | **PASS** | Bit-Exact vs CPU reference |
| **M21** | Fused Digital Down-Converter (DDC) | Tile `(0,2)` | Complex NCO at −f_s/8 + Kaiser LPF + decim-by-4 | **PASS** | Bit-Exact vs CPU reference |
| **M22** | Fused Digital Up-Converter (DUC) | Tile `(0,2)` | Interp-L=4 + Kaiser×L LPF + complex NCO at +f_s/8 | **PASS** | Bit-Exact vs CPU reference |
| **M23** | Fused Polyphase Channelizer (M-path) | Tile `(0,2)` | M=8 commutator + M-path FIR + 8-point matmul-DFT | **PASS** | Bit-Exact vs CPU reference |
| **M24** | Fused [Barker-13](https://en.wikipedia.org/wiki/Barker_code) Matched-Filter Correlator | Tile `(0,2)` | Reversed-tap FIR pair on I and Q, L=13 | **PASS** | Bit-Exact vs CPU reference |
| **M25** | Fused BPSK / QPSK Receiver | Tile `(0,2)` | Gardner TED + linear interp + NCO derotate + Costas | **PASS** | Receiver-theoretic gates (‹π/8 residual) |
| **M26** | Fused QAM-16 Receiver + Soft-Decision Demapping | Tile `(0,2)` | M25 core + Gray slicer + DD phase detector + max-log LLR | **PASS** | LLR consistency ≥ 0.75 (LSBs) / ≥ 0.85 (MSBs) |
| **M27** | Fused OFDM Loopback | Tile `(0,2)` | FFT + CP + pilots + LS / LMMSE channel est + one-tap equalizer | **PASS** | Reuses M17 radix-4 Stockham FFT |
| **M32b** | Post-Quantum Cryptography — [FIPS 203](https://nvlpubs.nist.gov/nistpubs/fips/nist.fips.203.pdf) ML-KEM NTT | Tile `(0,2)` | Algorithms 9–12, `Z_3329`, pq-crystals ζ-table | **PASS** | Bit-Exact vs [`kyber-py` 1.0.1](https://github.com/GiacomoPope/kyber-py) |
| **M32c** | Post-Quantum Cryptography — [FIPS 202](https://nvlpubs.nist.gov/nistpubs/fips/nist.fips.202.pdf) Keccak / SHA-3 / SHAKE + samplers | Tile `(0,2)` | Keccak-f[1600] permutation, 5 dispatch modes | **PASS** | Bit-Exact vs [FIPS 202](https://nvlpubs.nist.gov/nistpubs/fips/nist.fips.202.pdf) test vectors |
| **M32d** | Post-Quantum Cryptography — [FIPS 203](https://nvlpubs.nist.gov/nistpubs/fips/nist.fips.203.pdf) K-PKE Component | Tile `(0,2)` | Algorithms 13–15 (K-PKE.KeyGen / Encrypt / Decrypt) | **PASS** | Bit-Exact vs kyber-py K-PKE |
| **M32e** | Post-Quantum Cryptography — [FIPS 203](https://nvlpubs.nist.gov/nistpubs/fips/nist.fips.203.pdf) ML-KEM.{KeyGen, Encaps, Decaps} composer | Host + tile | Algorithms 19–21, ML-KEM-{512, 768, 1024} | **PASS** | Bit-Exact vs [NIST ACVP-Server](https://github.com/usnistgov/ACVP-Server) KATs |
| **M33a** | Post-Quantum Cryptography — [FIPS 204](https://nvlpubs.nist.gov/nistpubs/fips/nist.fips.204.pdf) ML-DSA NTT | Tile `(0,2)` | NTT / INTT / basemul, `Z_8380417`, Montgomery form | **PASS** | 420 / 420 gate PASS |
| **M33b** | Post-Quantum Cryptography — [FIPS 204](https://nvlpubs.nist.gov/nistpubs/fips/nist.fips.204.pdf) Rounding & Hint | Tile `(0,2)` | Decompose / MakeHint / UseHint / CheckNorm | **PASS** | 700 / 700 gate PASS |
| **M33d** | Post-Quantum Cryptography — [FIPS 204](https://nvlpubs.nist.gov/nistpubs/fips/nist.fips.204.pdf) ML-DSA.KeyGen composer | Host + tile | Algorithm 6, ML-DSA-{44, 65, 87} | **PASS** | 75 / 75 vs NIST ACVP-Server KATs |
| **M33e** | Post-Quantum Cryptography — [FIPS 204](https://nvlpubs.nist.gov/nistpubs/fips/nist.fips.204.pdf) ML-DSA.{Sign_internal, Verify_internal} composer | Host + tile | Algorithms 7 and 8, ML-DSA-{44, 65, 87} | **PASS** | 180 / 180 (90 sigGen + 90 sigVer) vs NIST ACVP-Server |

### Post-Quantum Cryptography track (M32 + M33, v1.0.0)

The v1.0.0 release closes the Post-Quantum Cryptography track. Both NIST-approved lattice-based primitives are silicon-validated against the [NIST ACVP-Server](https://github.com/usnistgov/ACVP-Server) response vectors vendored in-tree:

- **[FIPS 203](https://nvlpubs.nist.gov/nistpubs/fips/nist.fips.203.pdf) ML-KEM** — M32b (NTT over `Z_3329`), M32c (Keccak-f[1600] and [FIPS 202](https://nvlpubs.nist.gov/nistpubs/fips/nist.fips.202.pdf) SHA-3 / SHAKE), M32d (K-PKE component, not standalone approved), M32e (ML-KEM-{512, 768, 1024} KeyGen / Encaps / Decaps composer). Reference oracle: [`kyber-py` 1.0.1](https://github.com/GiacomoPope/kyber-py).
- **[FIPS 204](https://nvlpubs.nist.gov/nistpubs/fips/nist.fips.204.pdf) ML-DSA** — M33a (NTT over `Z_8380417`), M33b (rounding & hint arithmetic), M33c (SHAKE / Keccak reuse of M32c per [FIPS 204 §3.3.5](https://nvlpubs.nist.gov/nistpubs/fips/nist.fips.204.pdf)), M33d (ML-DSA-{44, 65, 87} KeyGen composer, 75/75), M33e (Sign_internal + Verify_internal composer, **180 / 180** including 72 must-reject tampered signatures across both `externalMu` paths). Reference oracle: [`dilithium-py` 1.4.0](https://github.com/GiacomoPope/dilithium-py).

Full v1.0.0 release summary: [`docs/PQC_COMPLETE_V1.md`](docs/PQC_COMPLETE_V1.md). Per-milestone design notes live at [`docs/M32b_DESIGN.md`](docs/M32b_DESIGN.md), [`docs/M32c_DESIGN.md`](docs/M32c_DESIGN.md), [`docs/M32d_DESIGN.md`](docs/M32d_DESIGN.md), [`docs/M32e_DESIGN.md`](docs/M32e_DESIGN.md), [`docs/M33a_DESIGN.md`](docs/M33a_DESIGN.md), [`docs/M33b_DESIGN.md`](docs/M33b_DESIGN.md), [`docs/M33d_DESIGN.md`](docs/M33d_DESIGN.md), [`docs/M33e_DESIGN.md`](docs/M33e_DESIGN.md). PQC reference packages (`kyber-py`, `dilithium-py`, and `pytest`) are pinned in [`requirements/toolchain-versions.md`](requirements/toolchain-versions.md) and auto-installed into `ironenv` by `install.py`; the manual pip step in [`docs/SETUP_WINDOWS.md`](docs/SETUP_WINDOWS.md#post-quantum-cryptography-reference-dependencies-m32--m33) is only needed if you bootstrapped ironenv another way. All SHAKE / SHA-3 primitives come from the CPython [`hashlib`](https://docs.python.org/3/library/hashlib.html) standard library, so no separate SHAKE / Keccak wheel is required.

<a id="iq-throughput"></a>

### I/Q throughput demo (not in the 16-suite)

Host-visible 4-column streamed complex mixer in `tests/npu_visible/`. Measured 2026-08-15 on a Ryzen 9 7940HS Phoenix NPU1 ([10 TOPS](https://www.amd.com/en/products/processors/laptop/ryzen/7000-series/amd-ryzen-9-7940hs.html)). First buffer matches the M6 complex-multiply reference ($L_\infty = 0.007812$). Kernel vectorization is deferred.

| Metric | 1-column 8 KB loop | 4-column stream |
| :--- | ---: | ---: |
| IQ in | 3.85 MB/s | **29.84 MB/s** |
| IQ out | 3.85 MB/s | **29.84 MB/s** |
| IQ in+out | 7.70 MB/s | **59.68 MB/s** |
| Complex rate | 0.963 Msps | **7.459 Msps** |
| Task Manager NPU | ~53% | **~92%** |

```powershell
python tests\npu_visible\test_iq_throughput.py
```

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

### 5. M17 FFT Stage-1 Butterfly Inversion
- **Issue:** The initial radix-2 M17 FFT produced valid magnitude but wrong bin ordering. Every stage after the first had a systematic butterfly-index inversion, yielding SNR $< 12$ dB against `numpy.fft.fft`.
- **Root Cause:** The Stockham auto-sort schedule pairs indices $(k, k + m/2)$ where $m$ is the *current* subtransform size. The initial kernel applied the twiddle to the wrong lane of each pair.
- **Solution:** Rewrote as radix-4 Stockham (twiddle applied per quadruplet, autonomous permutation between stages), reaching **138.79 dB forward SNR** vs NumPy — better than double-precision floor for a 64-point transform.

### 6. IFFT Without Separate Device Code
- **Issue:** Shipping a full inverse-FFT kernel would double the memory + build footprint of M17.
- **Solution:** Applied the identity `IFFT(Y) = conj(FFT(conj(Y))) / N` in the host driver. The M17 forward kernel is reused as-is; only conjugate-and-scale runs on the host. Silicon result: **135.11 dB round-trip SNR** on random complex vectors.

### 7. Upstream mlir-aie v1.4.1 iron.Runtime API Break
- **Issue:** After moving to upstream mlir-aie v1.4.1 (pin commit `3ca0193`, 2026-08-14), the full silicon sweep failed 14/16 milestones with `Runtime.__init__() missing 1 required positional argument: 'seq_fn'`.
- **Root Cause:** Upstream deprecated the `Runtime()` context-manager pattern in favor of `Runtime(seq_fn, fn_args=[...])`, and moved worker enrollment and task-group management out of the `Runtime` object into `Program(..., workers=[...])` and per-sequence `TaskGroup` objects.
- **Solution:** Migrated all 12 iron-based tests in one sweep. Single-worker kernels use the new `Runtime(seq_fn, [...])` signature; multi-worker channelizers use `TaskGroup()` inside the sequence body with `tg.finish()` at the end and endpoint-native `prod_ep.fill(buf, tap=tap, group=tg)` for per-column DMA. Full detail in `docs/ROADMAP.md`.

### 8. AIE2 Program-Memory Overflow on Unrolled ObjectFifo Loops
- **Issue:** A 64-iteration `for` around acquire/mix/release in the I/Q throughput worker failed `aiecc` at CDO load with `_XAie_LoadProgMemSection(): Overflow of program memory` / `XAie_LoadElf failed`.
- **Root Cause:** AIE2 core program memory is 16 KB. Static ObjectFifo lowering unrolled the frame loop into the ELF `.text` section.
- **Solution:** One acquire/release per worker, `Worker(while_true=True, dynamic_objfifo_lowering=True)`, and a 64-frame host TAP. IRON streams the tokens; the core binary stays compact.

---

## 5. Quickstart & Silicon Verification

Clone and install are in [Installation](#installation). After `install.py`, from the clone:

```powershell
py .\run_all_silicon_tests.py
```

Expected output (mlir-aie v1.4.1 pin `3ca0193`, cached xclbin):
```text
======================================================================
                     REGRESSION EXECUTION SUMMARY
======================================================================
 [ PASS ] Milestone 3: Single-Core SAXPY Vector Operation                        (1.11s)
 [ PASS ] Milestone 5: 8-Tap Vectorized Low-Pass FIR Filter                      (1.16s)
 [ PASS ] Milestone 6: Complex Mixer / NCO Frequency Downconverter               (1.03s)
 [ PASS ] Milestone 7: Vectorized Power / RSSI Energy Detector                   (1.07s)
 [ PASS ] Milestone 8: Streaming Multi-Stage Fused Demodulator Pipeline          (1.08s)
 [ PASS ] Milestone 9: 4-Column Parallel FIR Filter (Hardware Scaling)           (1.04s)
 [ PASS ] Milestone 9b: 4-Column Parallel Multi-Stage Demodulator Pipeline       (1.18s)
 [ PASS ] Milestone 10: Modular Arithmetic & Barrett Reduction (mod 3329)        (1.08s)
 [ PASS ] Milestone 11: Radix-2 NTT Butterfly Kernel (mod 3329)                  (1.03s)
 [ PASS ] Milestone 12: CPU NTT/INTT Reference & Constant Generator              (0.28s)
 [ PASS ] Milestone 13: 16-Point Vectorized NPU NTT (64 Batches)                 (0.62s)
 [ PASS ] Milestone 14: 256-Point Vectorized NPU NTT (4 Batches)                 (1.22s)
 [ PASS ] Milestone 15: NPU INTT & Cyclic Polynomial Multiplication              (1.18s)
 [ PASS ] Milestone 15b: NPU Negacyclic Polynomial Multiplication (Kyber ring)   (0.63s)
 [ PASS ] Milestone 17: 64-Point Radix-4 Stockham FFT + IFFT (NPU1)              (1.07s)
 [ PASS ] Milestone 17p: 4-Column Parallel 64-Point FFT Channelizer              (2.68s)
----------------------------------------------------------------------
 Total Tests Run: 16 | Passed: 16 | Failed: 0
 Total Elapsed Time: 17.46 seconds
```

### Optional: I/Q throughput

Not part of `run_all_silicon_tests.py`. After the suite, or instead of it:

```powershell
python tests\npu_visible\test_iq_throughput.py
```

Expected on Phoenix NPU1: first-buffer $L_\infty = 0.007812$, then ~7.5 Msps / ~30 MB/s I/Q in over a 5 s window. See [I/Q Throughput](#iq-throughput).

---

## 6. References & Upstream Projects

- [Cooley & Tukey (1965), "An algorithm for the machine calculation of complex Fourier series"](https://garfield.library.upenn.edu/classics1993/A1993MJ84400001.pdf): the original radix-2 FFT paper underlying M16/M17.
- [Barrett (1986), "Implementing the Rivest Shamir and Adleman Public Key Encryption Algorithm on a Standard Digital Signal Processor"](https://link.springer.com/chapter/10.1007/3-540-47721-7_24): Barrett reduction, used in M10–M15b modular arithmetic.
- [NIST FIPS 203](https://nvlpubs.nist.gov/nistpubs/fips/nist.fips.203.pdf) ([DOI](https://doi.org/10.6028/NIST.FIPS.203)): ML-KEM ring `Z_q[X]/(X^n+1)` with `(n, q) = (256, 3329)`. Closed at v1.0.0 via M32b/c/d/e.
- [NIST FIPS 204](https://nvlpubs.nist.gov/nistpubs/fips/nist.fips.204.pdf) ([DOI](https://doi.org/10.6028/NIST.FIPS.204)): ML-DSA ring `Z_q[X]/(X^n+1)` with `(n, q) = (256, 8380417)`. Closed at v1.0.0 via M33a/b/d/e.
- [NIST FIPS 202](https://nvlpubs.nist.gov/nistpubs/fips/nist.fips.202.pdf): SHA3-256, SHA3-512, SHAKE128, SHAKE256 used by FIPS 203 §4.1 and FIPS 204 §3.3.5.
- [CRYSTALS-Dilithium specification v3.1](https://pq-crystals.org/dilithium/data/dilithium-specification-round3-20210208.pdf): round-3 Dilithium reference underlying FIPS 204.
- [`kyber-py` 1.0.1](https://github.com/GiacomoPope/kyber-py) and [`dilithium-py` 1.4.0](https://github.com/GiacomoPope/dilithium-py): Python reference oracles for M32e and M33d / M33e.
- [NIST ACVP-Server](https://github.com/usnistgov/ACVP-Server): official ML-KEM and ML-DSA KAT vectors vendored under `tests/m32_mlkem/vectors/` and `tests/m33_mldsa/vectors/`.
- [pq-crystals reference implementations](https://github.com/pq-crystals): official Kyber and Dilithium C reference sources cited by M32b and M33a.
- [NIST PQC project](https://csrc.nist.gov/projects/post-quantum-cryptography) and [CAVP](https://csrc.nist.gov/projects/cryptographic-algorithm-validation-program).
- [CRYSTALS-Kyber specification v3.02](https://pq-crystals.org/kyber/data/kyber-specification-round3-20210804.pdf): Kyber NTT and negacyclic ring.
- [Isabelle/AFP CRYSTALS-Kyber](https://isa-afp.org/browser_info/current/AFP/CRYSTALS-Kyber/outline.pdf): formalization of `Z_q[x]/(x^N+1)`.
- [Stockham (1966), "High-speed convolution and correlation"](https://dl.acm.org/doi/10.1145/1464182.1464209): auto-sort FFT used by M17.
- [Gentleman & Sande (1966)](https://dl.acm.org/doi/10.1145/1464291.1464352): DIF FFT / Gentleman–Sande butterfly.
- [Ozaki et al. (2012)](https://doi.org/10.1007/s11075-011-9478-1): error-free split used by the AMD FFT_R4_AIE twiddle path.
- [Higham (2002), *Accuracy and Stability of Numerical Algorithms*](https://doi.org/10.1137/1.9780898718027): FFT round-off bounds cited by M16.
- [Linux kernel, AMD NPU / `amdxdna`](https://docs.kernel.org/accel/amdxdna/amdnpu.html): Phoenix 4×5 XDNA1 topology.
- [Native Windows IRON guide, mlir-aie 1.4.1](https://xilinx.github.io/mlir-aie/1.4.1/buildHostWinNative/).
- [Xilinx / AMD MLIR-AIE](https://github.com/Xilinx/mlir-aie): AI Engine MLIR dialect and LLVM backend (pinned at commit [`3ca0193`](https://github.com/Xilinx/mlir-aie/commit/3ca0193cea9e2c39ec670a65f93e1dd43c969f22), [v1.4.1](https://github.com/Xilinx/mlir-aie/releases/tag/v1.4.1) + 13 commits, [PR #3545](https://github.com/Xilinx/mlir-aie/pull/3545)).
- [AMD FFT_R4_AIE](https://github.com/diacccc/FFT_R4_AIE): Apache-2.0-licensed radix-4 Stockham FFT reference kernel for AIE-ML. `kernels/fft_stockham_f32.cc` is adapted from this source with attribution preserved.
- [Xilinx aie-rt](https://github.com/Xilinx/aie-rt): AI Engine runtime library and `aie_api` header source (`fft_dit_r2_stage`, `mmul`, `filter_even/odd`).
- [AMD Ryzen 9 7940HS](https://www.amd.com/en/products/processors/laptop/ryzen/7000-series/amd-ryzen-9-7940hs.html): official product page; Phoenix NPU rated up to 10 TOPS.
- [Tom's Hardware, Hawk Point announcement](https://www.tomshardware.com/pc-components/cpus/the-refresh-that-wasnt-amd-announces-hawk-point-ryzen-8040-series-with-zen-4-rdna3-and-xdna-teases-strix-point): AMD states XDNA1 delivers 10 TOPS INT8 on Phoenix 7040.
- [AMD XDNA Driver](https://github.com/amd/xdna-driver): Linux and Windows kernel driver for AMD XDNA architecture.
- [Peano LLVM-AIE Compiler](https://github.com/Xilinx/llvm-aie): Clang/LLVM fork targeting AIE/AIE2 vector units.
- [AMD XRT (Xilinx Runtime)](https://github.com/Xilinx/XRT): Host runtime for PCIe and APU accelerator device management.
- [NTT on AMD AI Engine](https://github.com/hal-lab-u-tokyo/ntt-aie): NTT reference implementation on AI Engine architectures.

---

## 7. Credits & Acknowledgments

- **Lead Architect & Maintainer:** Midhat Nashar ([@midhatn](https://github.com/midhatn))
- **AI Architecture & Engineering Partner:** Perplexity AI (Senior AMD XDNA / AIE & DSP Copilot)
- **Upstream toolchain (Advanced Micro Devices, Inc. — formerly Xilinx):** [`mlir-aie`](https://github.com/Xilinx/mlir-aie), [`llvm-aie` (Peano)](https://github.com/Xilinx/llvm-aie), [`XRT`](https://github.com/Xilinx/XRT), [`xdna-driver`](https://github.com/amd/xdna-driver), and the [`FFT_R4_AIE`](https://github.com/diacccc/FFT_R4_AIE) radix-4 Stockham FFT reference (Apache-2.0), which `kernels/fft_stockham_f32.cc` is adapted from.
- **Academic foundations:** J. W. Cooley & J. W. Tukey (1965) for the radix-2 FFT that seeds M16/M17; P. Barrett (1986) for the modular-reduction method underlying M10–M15b.
- **Community reference:** [`hal-lab-u-tokyo/ntt-aie`](https://github.com/hal-lab-u-tokyo/ntt-aie) NTT-on-AIE reference implementation.
- **License:** MIT License — See [LICENSE](LICENSE) for details.
