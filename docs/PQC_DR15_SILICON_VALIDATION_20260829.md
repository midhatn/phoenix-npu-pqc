# NIST FIPS 204 ML-DSA-87 Silicon Validation Benchmark Log

**Date**: August 29, 2026  
**Hardware Target**: AMD Phoenix APU (Ryzen 7 7840HS with XDNA1 NPU / AIE2 Architecture)  
**Toolchain**: MLIR-AIE 1.4.1, Peano LLVM-AIE Compiler, XRT 2.20.0  
**Test Suite**: NIST Cryptographic Algorithm Validation Program (ACVP) Official Vectors (85 test cases)

---

## 1. Executive Summary

| Gate / Operation | Algorithm & Parameter | ACVP Test Cases | Physical Silicon Result | Parity / Verdict |
|---|---|---|---|---|
| **Gate 1: KeyGen** | NIST FIPS 204 ML-DSA-87 | 25 | **25 / 25 PASS** | **100% Bit-Exact Match** |
| **Gate 2: Sign** | NIST FIPS 204 ML-DSA-87 | 30 | **30 / 30 PASS** | **Exact Challenge $\widetilde{c}$ & Full Match** |
| **Gate 3: Verify** | NIST FIPS 204 ML-DSA-87 | 30 | **30 / 30 PASS** | **100% Accurate Rejection & Acceptance** |
| **Total Suite** | **DR15 ML-DSA-87** | **85** | **85 / 85 PASS** | **100% Silicon Execution (2.75s total runtime)** |

---

## 2. Kernel Compilation & Resource Allocation

### 2.1 KeyGen Kernels
- `dr15_mldsa87_kg_w0_noise.o`:    8,208 B text (< 16 KiB)
- `dr15_mldsa87_kg_w1_rows0123.o`: 11,200 B text (< 16 KiB)
- `dr15_mldsa87_kg_w2_rows4567.o`: 11,200 B text (< 16 KiB)
- `dr15_mldsa87_kg_w3_fin.o`:      6,304 B text (< 16 KiB)

### 2.2 Sign Kernels
- `dr15_mldsa87_sign_w0_init.o`:   8,208 B text (< 16 KiB)
- `dr15_mldsa87_sign_w1_matrix.o`: 14,080 B text (< 16 KiB)
- `dr15_mldsa87_sign_w2_fin.o`:    8,912 B text (< 16 KiB)

### 2.3 Verify Kernels
- `dr15_mldsa87_verify_w0_init.o`:   15,696 B text (< 16 KiB)
- `dr15_mldsa87_verify_w1_matrix.o`: 11,280 B text (< 16 KiB)
- `dr15_mldsa87_verify_w2_fin.o`:       768 B text (< 16 KiB)

---

## 3. Verification & Acceptance Criteria

1. **100% NPU Residency**: Zero host cryptographic fallback. All SHA-3/SHAKE permutations, Montgomery NTT transforms, matrix expansions, rejection checks, bit-packing routines, and CRC32 calculations executed entirely inside AIE2 tiles.
2. **Deterministic & Constant Bounds**: Peak stack usage < 6 KiB per worker, ObjectFIFOs sized to avoid tile RAM spillover.
3. **Execution Latency**: Complete 85-vector test suite executed in 2.75 seconds on physical silicon (< 35 ms per full ACVP vector including memory copy and host scheduling).
