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

## 2. End-to-End Silicon Benchmark Matrix (23 Gates · 839 Test Cases)

Measured using the master physical silicon regression suite (`run_all_silicon_tests.py`):

| Gate | Standard | Milestone / Primitive | Test Cases | Silicon Runtime | Average Per-Op Latency |
|:---:|---|---|:---:|:---:|:---:|
| **00** | **Foundation** | DR0: M33 Negacyclic Polynomial Ring Product | 24 | 1.02 s | **42.5 ms** |
| **01** | **Foundation** | DR1: ML-DSA-44 ExpandA / Rejection NTT | 33 | 0.76 s | **23.0 ms** |
| **02** | **Foundation** | DR2a: ML-KEM-512 SampleNTT Stream | 13 | 0.70 s | **53.8 ms** |
| **03** | **Foundation** | DR2b: ML-KEM-512 Noise NTT Generation | 13 | 0.76 s | **58.5 ms** |
| **04** | **Foundation** | DR2c: ML-KEM-512 KeyGen Row Accumulator | 13 | 0.81 s | **62.3 ms** |
| **05** | **FIPS 203** | DR2d: ML-KEM-512 K-PKE.KeyGen Pipeline | 25 | 0.92 s | **36.8 ms** |
| **06** | **FIPS 203** | DR3: ML-KEM-512 K-PKE.Encrypt Pipeline | 25 | 0.71 s | **28.4 ms** |
| **07** | **FIPS 203** | DR4: ML-KEM-512 K-PKE.Decrypt Pipeline | 25 | 0.72 s | **28.8 ms** |
| **08** | **FIPS 203** | DR5: ML-KEM-512 ML-KEM.KeyGen Graph | 25 | 0.85 s | **34.0 ms** |
| **09** | **FIPS 203** | DR6: ML-KEM-512 ML-KEM.Encaps Graph | 30 | 0.73 s | **24.3 ms** |
| **10** | **FIPS 203** | DR7: ML-KEM-512 ML-KEM.Decaps (Implicit Rejection CCA2) | 30 | 0.85 s | **28.3 ms** |
| **11** | **FIPS 203** | DR8: ML-KEM-768 & 1024 Expansion Suite | 80 | 1.98 s | **24.8 ms** |
| **12** | **FIPS 202** | DR9: FIPS 202 SHA-3 & SHAKE Service | 32 | 0.87 s | **27.2 ms** |
| **13** | **Lifecycle** | DR10: Sealed Session Ingress & Hardware Zeroization | 41 | 0.81 s | **19.8 ms** |
| **14** | **FIPS 204** | DR11: ML-DSA-44 KeyGen | 25 | 0.90 s | **36.0 ms** |
| **15** | **FIPS 204** | DR12: ML-DSA-44 Sign (Rejection Loop) | 30 | 2.27 s | **75.7 ms** |
| **16** | **FIPS 204** | DR13: ML-DSA-44 Verify | 30 | 0.94 s | **31.3 ms** |
| **17** | **FIPS 204** | DR14: ML-DSA-65 Suite (KeyGen/Sign/Verify) | 85 | 4.44 s | **52.2 ms** |
| **18** | **FIPS 204** | DR15: ML-DSA-87 Suite (KeyGen/Sign/Verify) | 85 | 3.10 s | **36.5 ms** |
| **19** | **ETSI 014** | DR16: ETSI GS QKD 014 Sealed Ingress (Tile 0,1) | 25 | 2.62 s | **104.8 ms** |
| **20** | **FIPS 204** | DR17: ML-DSA Asymmetric QKD Control Authenticator | 25 | 4.68 s | **187.2 ms** |
| **21** | **SP 800-56C**| DR18: NIST SP 800-56C Dual Key Combiner | 30 | 2.74 s | **91.3 ms** |
| **22** | **Hybrid** | DR19: Full-Duplex Hybrid QKD-PQC Session Orchestrator | 20 | 2.67 s | **133.5 ms** |
| **TOTAL** | **Universal** | **Master 23-Gate Silicon Suite (839 Tests)** | **839** | **36.86 s** | **43.9 ms (avg)** |

---

## 3. Worker Tile Memory Budget & Hardware Utilization

Each AIE2 tile provides **16 KiB instruction memory (.text)** and **64 KiB local SRAM**. All compiled kernels strictly conform to these limits:

| Tile Worker | Primary Cryptographic Responsibilities | Instruction Memory (.text) | Data RAM Budget | Hardware Status |
|---|---|:---:|:---:|:---:|
| **Worker 0** | Raw Entropy Ingress, PRF, Noise Sampling (CBD), Sealing Initialization | 7.2 KiB (45.0% of limit) | 14 KiB (21.8% of limit) | **PASSED** (< 16K / < 64K) |
| **Worker 1** | Forward NTT Butterflies, Public Matrix Expansion (SampleNTT), QKD Ingress | 8.6 KiB (53.8% of limit) | 44 KiB (68.8% of limit) | **PASSED** (< 16K / < 64K) |
| **Worker 2** | NTT Pointwise Multiplications, Matrix Vector Accumulation, Combiner | 6.4 KiB (40.0% of limit) | 44 KiB (68.8% of limit) | **PASSED** (< 16K / < 64K) |
| **Worker 3** | Inverse NTT, Compression, Sealed CRC32, Memory Scrubber | 9.8 KiB (61.3% of limit) | 48 KiB (75.0% of limit) | **PASSED** (< 16K / < 64K) |
