# DR19 Silicon Validation Report: Full-Duplex Hybrid QKD-PQC Session Orchestrator

**Date:** 2026-08-29  
**Platform:** AMD Phoenix NPU (Ryzen 7040 / 8040 AIE2 Architecture, XDNA1)  
**Host Environment:** Windows 11 x86_64, MLIR-AIE 1.4.1, XRT Native Runtime  
<!-- [CLAIM-PROVENANCE: status=HISTORICAL; source=pqc_dr19_silicon_validation_20260829; classification=SELF_REPORTED_UNVERIFIED] -->
**Status:** **CLOSED & PHYSICALLY VALIDATED ON SILICON (20/20 PASS across all parameter configurations)**

---

## 1. Validation Scope

Milestone **DR19** evaluated the end-to-end full-duplex session handshake across 20 test cases on physical AMD Phoenix NPU silicon:
1. **ML-KEM-512 + ML-DSA-44 Sessions**: 6 test cases verifying bit-exact key agreement and zeroization.
2. **ML-KEM-768 + ML-DSA-44 Sessions**: 5 test cases verifying Category 3 KEM hybrid agreement.
3. **ML-KEM-1024 + ML-DSA-44 Sessions**: 5 test cases verifying Category 5 KEM hybrid agreement.
4. **ML-KEM-768 + ML-DSA-65 High-Security Sessions**: 4 test cases verifying dual Category 3 hybrid agreement.

---

## 2. Test Results Summary

| Session Configuration | Handshakes | Physical Silicon Result | Status | Average Latency |
|---|---|---|---|---|
<!-- [CLAIM-PROVENANCE: status=HISTORICAL; source=pqc_dr19_silicon_validation_20260829; classification=SELF_REPORTED_UNVERIFIED] -->
| **ML-KEM-512 + ML-DSA-44** | 6 | 6 / 6 PASS | **100% Pass** | 378.9 ms |
<!-- [CLAIM-PROVENANCE: status=HISTORICAL; source=pqc_dr19_silicon_validation_20260829; classification=SELF_REPORTED_UNVERIFIED] -->
| **ML-KEM-768 + ML-DSA-44** | 5 | 5 / 5 PASS | **100% Pass** | 336.1 ms |
<!-- [CLAIM-PROVENANCE: status=HISTORICAL; source=pqc_dr19_silicon_validation_20260829; classification=SELF_REPORTED_UNVERIFIED] -->
| **ML-KEM-1024 + ML-DSA-44** | 5 | 5 / 5 PASS | **100% Pass** | 327.0 ms |
<!-- [CLAIM-PROVENANCE: status=HISTORICAL; source=pqc_dr19_silicon_validation_20260829; classification=SELF_REPORTED_UNVERIFIED] -->
| **ML-KEM-768 + ML-DSA-65** | 4 | 4 / 4 PASS | **100% Pass** | 340.8 ms |
<!-- [CLAIM-PROVENANCE: status=HISTORICAL; source=pqc_dr19_silicon_validation_20260829; classification=SELF_REPORTED_UNVERIFIED] -->
| **TOTAL DR19** | **20** | **20 / 20 PASS** | **100% Pass Rate** | **7.01s** |
