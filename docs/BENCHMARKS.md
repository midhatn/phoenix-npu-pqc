# Performance & Microarchitectural Benchmarks on Physical AMD Phoenix NPU (v1.1.0)

This document records the empirical latency, memory footprint, and microarchitectural efficiency of the 100% on-device Post-Quantum Cryptography and Quantum Key Distribution engine executing directly on AMD Phoenix NPU silicon (Ryzen 7 7840HS / Ryzen 9 7940HS / AIE2 / XDNA1 Architecture).

---

## 1. Physical Hardware Test Environment

| Parameter | Specification |
|---|---|
| **SoC / APU** | AMD Ryzen 7 7840HS / Ryzen 9 7940HS (Phoenix APU) |
| **NPU Architecture** | AMD XDNA1 / AIE2 (AI Engine-ML) |
| **Tile Topology** | 4x4 compute grid (20 VLIW tiles + 5 MemTiles + 5 Shim DMAs) connected via hardware ObjectFIFOs |
| **Host Interface** | PCIe Gen 4 x4 to NPU subsystem |
| **Operating System** | Windows 11 Pro 64-bit (Build 22631+) |
| **NPU Driver** | AMD NPU Driver 10.1109.8.100+ (XDNA Driver) |
| **Toolchain** | MLIR-AIE 1.4.1 (commit 3ca0193), Peano LLVM-AIE, XRT 2.21.0 |

---

## 2. End-to-End Silicon Benchmark Matrix (24 Gates · 857 Test Cases)

Measured using the master physical silicon regression suite (`run_all_silicon_tests.py`):

| Gate | Standard | Milestone / Primitive | Test Cases | Silicon Runtime | Average Per-Op Latency |
|:---:|---|---|:---:|:---:|:---:|
| **00** | **Foundation** | DR0: M33 Negacyclic Polynomial Ring Product | 24 | 0.91 s | **37.9 ms** |
| **01** | **Foundation** | DR1: ML-DSA-44 ExpandA / Rejection NTT | 33 | 0.75 s | **22.7 ms** |
| **02** | **Foundation** | DR2a: ML-KEM-512 SampleNTT Stream | 13 | 0.69 s | **53.1 ms** |
| **03** | **Foundation** | DR2b: ML-KEM-512 CBD3/NTT Noise | 13 | 0.71 s | **54.6 ms** |
| **04** | **Foundation** | DR2c: ML-KEM-512 KeyGen Row Accumulator | 11 | 0.71 s | **64.5 ms** |
| **05** | **FIPS 203** | DR2d: ML-KEM-512 K-PKE.KeyGen Pipeline | 25 | 0.78 s | **31.2 ms** |
| **06** | **FIPS 203** | DR3: ML-KEM-512 K-PKE.Encrypt Pipeline | 25 | 0.75 s | **30.0 ms** |
| **07** | **FIPS 203** | DR4: ML-KEM-512 K-PKE.Decrypt Pipeline | 25 | 0.71 s | **28.4 ms** |
| **08** | **FIPS 203** | DR5: ML-KEM-512 ML-KEM.KeyGen Graph | 25 | 0.76 s | **30.4 ms** |
| **09** | **FIPS 203** | DR6: ML-KEM-512 ML-KEM.Encaps Graph | 25 | 0.75 s | **30.0 ms** |
| **10** | **FIPS 203** | DR7: ML-KEM-512 ML-KEM.Decaps Graph | 25 | 0.80 s | **32.0 ms** |
| **11** | **FIPS 203** | DR8: ML-KEM-768 & 1024 Expansion Suite | 75 | 1.82 s | **24.3 ms** |
| **12** | **FIPS 202** | DR9: NIST FIPS 202 SHA-3/SHAKE Service | 122 | 0.86 s | **7.0 ms** |
| **13** | **Lifecycle** | DR10: Sealed Session Ingress & Hardware Zeroization | 40 | 0.80 s | **20.0 ms** |
| **14** | **FIPS 204** | DR11: ML-DSA-44 KeyGen | 25 | 0.89 s | **35.6 ms** |
| **15** | **FIPS 204** | DR12: ML-DSA-44 Sign (Rejection Loop) | 30 | 2.30 s | **76.7 ms** |
| **16** | **FIPS 204** | DR13: ML-DSA-44 Verify | 30 | 1.35 s | **45.0 ms** |
| **17** | **FIPS 204** | DR14: ML-DSA-65 Suite (KeyGen/Sign/Verify) | 85 | 4.84 s | **56.9 ms** |
| **18** | **FIPS 204** | DR15: ML-DSA-87 Suite (KeyGen/Sign/Verify) | 85 | 3.56 s | **41.9 ms** |
| **19** | **ETSI 014** | DR16: ETSI GS QKD 014 Sealed Ingress (Tile 0,1) | 25 | 0.70 s | **28.0 ms** |
| **20** | **FIPS 204** | DR17: ML-DSA Asymmetric QKD Control Authenticator | 25 | 2.71 s | **108.4 ms** |
| **21** | **SP 800-56C**| DR18: NIST SP 800-56C Dual Key Combiner | 25 | 1.11 s | **44.4 ms** |
| **22** | **Hybrid** | DR19: Full-Duplex Hybrid QKD-PQC Session Orchestrator | 25 | 0.65 s | **26.0 ms** |
| **23** | **Entropy** | DR27: QRNG-OPENAPI & Reservoir Core | 21 | 1.23 s | **58.6 ms** |
| **TOTAL** | **Universal** | **Master 24-Gate Silicon Suite (857 Tests)** | **857** | **31.14 s** | **36.3 ms (avg)** |

---

## 3. Worker Tile Memory Budget & Hardware Utilization

Each AIE2 tile provides **16 KiB instruction memory (.text)** and **64 KiB local SRAM**. All compiled kernels strictly conform to these limits:

| Tile Worker | Primary Cryptographic Responsibilities | Instruction Memory (.text) | Data RAM Budget | Hardware Status |
|---|---|:---:|:---:|:---:|
| **Worker 0** | Raw Entropy Ingress, PRF, Noise Sampling (CBD), Sealing Initialization | 7.2 KiB (45.0% of limit) | 14 KiB (21.8% of limit) | **PASSED** (< 16K / < 64K) |
| **Worker 1** | Forward NTT Butterflies, Public Matrix Expansion (SampleNTT), QKD Ingress | 8.6 KiB (53.8% of limit) | 44 KiB (68.8% of limit) | **PASSED** (< 16K / < 64K) |
| **Worker 2** | NTT Pointwise Multiplications, Matrix Vector Accumulation, Combiner | 6.4 KiB (40.0% of limit) | 44 KiB (68.8% of limit) | **PASSED** (< 16K / < 64K) |
| **Worker 3** | Inverse NTT, Compression, Sealed CRC32, Memory Scrubber | 9.8 KiB (61.3% of limit) | 48 KiB (75.0% of limit) | **PASSED** (< 16K / < 64K) |
