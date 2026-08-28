# PQC DR3 Silicon Validation Report (2026-08-28)

## 1. Test Setup & Target Hardware
* **Target SoC**: AMD Ryzen 9 7940HS w/ Radeon 780M Graphics
* **NPU Architecture**: AMD XDNA1 (AIE2 Array, IPU 1.0)
* **Compute Grid**: 5 Compute Tiles (Row 2, Cols 0..4) connected via memory-mapped ObjectFIFOs.
* **Compiler**: Peano LLVM Clang++ for AIE2 (`--target=aie2-none-unknown-elf -std=c++20 -O2`)
* **Host Driver**: AMD XRT / Iron Python API (`mlir_aie.ironenv`)

---

## 2. Test Execution & NIST ACVP Test Vector Results

The complete test suite executes all 25 official NIST ACVP ML-KEM-512 `K-PKE.Encrypt` vectors directly on physical silicon:

```
========================================================================
PQC DR3 - complete ML-KEM-512 K-PKE.Encrypt closure
Backend: dr3-mlkem512-kpke-encrypt:silicon
  acvp-tcId-01                     PASS
  acvp-tcId-02                     PASS
  acvp-tcId-03                     PASS
  acvp-tcId-04                     PASS
  acvp-tcId-05                     PASS
  acvp-tcId-06                     PASS
  acvp-tcId-07                     PASS
  acvp-tcId-08                     PASS
  acvp-tcId-09                     PASS
  acvp-tcId-10                     PASS
  acvp-tcId-11                     PASS
  acvp-tcId-12                     PASS
  acvp-tcId-13                     PASS
  acvp-tcId-14                     PASS
  acvp-tcId-15                     PASS
  acvp-tcId-16                     PASS
  acvp-tcId-17                     PASS
  acvp-tcId-18                     PASS
  acvp-tcId-19                     PASS
  acvp-tcId-20                     PASS
  acvp-tcId-21                     PASS
  acvp-tcId-22                     PASS
  acvp-tcId-23                     PASS
  acvp-tcId-24                     PASS
  acvp-tcId-25                     PASS
------------------------------------------------------------------------
TOTAL 25/25 PASS
========================================================================
```

---

## 3. Microarchitectural Invariants & DMA Footprint

| Metric | Measured Value | Requirement | Status |
| :--- | :--- | :--- | :--- |
| **Ingress DMA Transfers** | 2 (`descriptor[16]`, `request[864]`) | Exactly 2 | PASS |
| **Egress DMA Transfers** | 1 (`result[788]`) | Exactly 1 | PASS |
| **Intermediate Host Roundtrips** | 0 | 0 | PASS |
| **Host Cryptographic Fallback** | 0 | 0 | PASS |
| **Output Integrity** | 100% Bit-Exact across 25 vectors | 100% Bit-Exact | PASS |
| **On-Device CRC32** | Validated on-chip before DMA commit | Mandatory | PASS |

---

## 4. Master Silicon Regression Summary

```
================================================================================
ALL 6/6 PQC MILESTONES PASSED 100% BIT-EXACT ON PHYSICAL SILICON!
================================================================================
  - DR1  (ML-DSA-44 RejNTT)       : 33/33 PASS
  - DR2a (ML-KEM-512 SampleNTT)   : 13/13 PASS
  - DR2b (ML-KEM-512 Noise+NTT)   : 13/13 PASS
  - DR2c (ML-KEM-512 KeyGen Row)  : 11/11 PASS
  - DR2d (ML-KEM-512 K-PKE.KeyGen): 25/25 PASS
  - DR3  (ML-KEM-512 K-PKE.Encrypt): 25/25 PASS
--------------------------------------------------------------------------------
TOTAL ON-DEVICE SILICON TESTS: 120/120 PASS (100.0% RELIABILITY)
================================================================================
```
