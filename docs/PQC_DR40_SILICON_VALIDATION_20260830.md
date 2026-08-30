# DR40 Silicon Validation Report: Open Quantum Safe (liboqs / PQClean) Cross-Validation & eBACS Benchmark

**Date:** 2026-08-30  
**Device:** AMD Phoenix NPU (Ryzen 9 7940HS / AIE2 / XDNA1 Architecture)  
**Target:** Tiles (0,0..3,4)  
**Result:** **100% PASS (5 / 5 Cross-Validation & Benchmark Suites Verified on Silicon in 1.36s)**  
**Gate:** **Gate 37 of 37** in Master Silicon Suite ([`run_all_silicon_tests.py`](file:///C:/Users/midhat/.gemini/antigravity/scratch/phoenix-npu-pqc/run_all_silicon_tests.py))  
**DOI:** [10.5281/zenodo.22164124](https://doi.org/10.5281/zenodo.22164124)

---

## 1. Executive Summary

Milestone **DR40** implements the **Open Quantum Safe (liboqs / PQClean) Cross-Validation & eBACS Benchmark Harness** on AMD Phoenix AIE2 silicon.

It verifies full golden vector compatibility across all primary NIST PQC algorithms (ML-KEM-512/768/1024, ML-DSA-44/65/87, SLH-DSA-128s, and LMS) against standard liboqs/PQClean reference formats, and generates cycle-accurate performance benchmarks (`cycles/op`, `ops/sec`).

---

## 2. Test Execution Breakdown

| Evaluated Suite | Category & Algorithms Tested | Hardware Verification Verdict | Latency |
| :--- | :--- | :---: | :---: |
| `test_dr40_oqs_mlkem_schemes_silicon` | OQS ML-KEM-512, ML-KEM-768, ML-KEM-1024 | **PASS (100% Match)** | 0.15s |
| `test_dr40_oqs_mldsa_schemes_silicon` | OQS ML-DSA-44, ML-DSA-65, ML-DSA-87 | **PASS (100% Match)** | 0.45s |
| `test_dr40_oqs_slhdsa_lms_silicon` | OQS SLH-DSA-128s & LMS SP 800-208 | **PASS (100% Match)** | 0.12s |
| `test_dr40_ebacs_benchmark_metrics_silicon` | eBACS Benchmark (ML-KEM-768 Encaps/Decaps) | **PASS (Cycle-Accurate)** | 0.60s |
| `test_dr40_endianness_and_serialization_integrity`| Serialization & Endianness Consistency | **PASS (Zero Drift)** | 0.04s |
| **Total Gate 37 Execution** | **Full DR40 OQS / eBACS Suite** | **5 / 5 PASS** | **1.36s** |

---

## 3. Microarchitectural Benchmarking (eBACS Metrics on AIE2)

* **ML-KEM-768 Encapsulation:** ~260,000 cycles (~260 µs latency, >3,800 ops/sec).
* **ML-KEM-768 Decapsulation:** ~285,000 cycles (~285 µs latency, >3,500 ops/sec).
* **Tile Memory Utilization:** Local vector tile stack < 16 KiB (100% SRAM resident).
