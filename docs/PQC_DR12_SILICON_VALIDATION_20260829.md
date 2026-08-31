# NIST FIPS 204 ML-DSA-44 Sign Silicon Validation Report

**Date**: 2026-08-29  
**Platform**: AMD Phoenix APU (AIE2 / XDNA1, Ryzen 7040/8040 series)  
**Toolchain**: MLIR-AIE 1.4.1 / Peano Clang / XRT 2.20.0  
**Artifact**: `dr12_mldsa44_sign_graph.py` & `dr12_mldsa44_sign_w*.cc`  
**Dataset**: Official NIST ACVP `ML-DSA-sigGen-FIPS204` Internal Deterministic Test Vectors (30 vectors)

---

## 1. Executive Summary

Milestone **DR12** (Complete NIST FIPS 204 ML-DSA-44 100% On-Device Signing) was executed and validated directly on AMD Phoenix AIE2 physical silicon. All 30 test vectors achieved a **100% bit-exact match** against NIST ACVP KAT reference signatures.

```
================================================================================
MASTER SILICON REGRESSION SUITE - AMD PHOENIX NPU (XDNA1 / AIE2)
================================================================================
>>> DR1  (ML-DSA-44 RejNTT)            : PASS ( 25 /  25)
>>> DR2a (ML-KEM-512 SampleNTT)        : PASS ( 14 /  14)
>>> DR2b (ML-KEM-512 Noise+NTT)        : PASS ( 20 /  20)
>>> DR2c (ML-KEM-512 KeyGen Row)       : PASS ( 20 /  20)
>>> DR2d (ML-KEM-512 K-PKE.KeyGen)     : PASS ( 25 /  25)
>>> DR3  (ML-KEM-512 K-PKE.Encrypt)    : PASS ( 30 /  30)
>>> DR4  (ML-KEM-512 K-PKE.Decrypt)    : PASS ( 30 /  30)
>>> DR5  (ML-KEM-512 ML-KEM.KeyGen)    : PASS ( 25 /  25)
>>> DR6  (ML-KEM-512 ML-KEM.Encaps)    : PASS ( 25 /  25)
>>> DR7  (ML-KEM-512 ML-KEM.Decaps)    : PASS ( 30 /  30)
>>> DR8  (ML-KEM-768/1024 Expansion)   : PASS ( 75 /  75)
>>> DR9  (Reusable FIPS 202 Service)   : PASS (122 / 122)
>>> DR10 (Sealed Lifecycle Architecture): PASS ( 40 /  40)
>>> DR11 (FIPS 204 ML-DSA-44 KeyGen)   : PASS ( 25 /  25)
>>> DR12 (FIPS 204 ML-DSA-44 Sign)     : PASS ( 30 /  30)
================================================================================
ALL 15/15 PQC MILESTONES PASSED (536 / 536 TOTAL PASS - 100% SILICON VALIDATION)
================================================================================
```

---

## 2. Test Execution Log (DR12)

```
============================================================
DR12: Complete NIST FIPS 204 ML-DSA-44 Sign Validation
Backend: dr12-mldsa44-sign:silicon (AMD Phoenix AIE2)
============================================================
Running 30 NIST ACVP ML-DSA-44 Sign vectors on AMD Phoenix NPU...
  [01/30] acvp_mldsa44_sign_tg7_tc91          : PASS (100% bit-exact signature)
  [02/30] acvp_mldsa44_sign_tg7_tc92          : PASS (100% bit-exact signature)
  [03/30] acvp_mldsa44_sign_tg7_tc93          : PASS (100% bit-exact signature)
  [04/30] acvp_mldsa44_sign_tg7_tc94          : PASS (100% bit-exact signature)
  [05/30] acvp_mldsa44_sign_tg7_tc95          : PASS (100% bit-exact signature)
  [06/30] acvp_mldsa44_sign_tg7_tc96          : PASS (100% bit-exact signature)
  [07/30] acvp_mldsa44_sign_tg7_tc97          : PASS (100% bit-exact signature)
  [08/30] acvp_mldsa44_sign_tg7_tc98          : PASS (100% bit-exact signature)
  [09/30] acvp_mldsa44_sign_tg7_tc99          : PASS (100% bit-exact signature)
  [10/30] acvp_mldsa44_sign_tg7_tc100         : PASS (100% bit-exact signature)
  [11/30] acvp_mldsa44_sign_tg7_tc101         : PASS (100% bit-exact signature)
  [12/30] acvp_mldsa44_sign_tg7_tc102         : PASS (100% bit-exact signature)
  [13/30] acvp_mldsa44_sign_tg7_tc103         : PASS (100% bit-exact signature)
  [14/30] acvp_mldsa44_sign_tg7_tc104         : PASS (100% bit-exact signature)
  [15/30] acvp_mldsa44_sign_tg7_tc105         : PASS (100% bit-exact signature)
  [16/30] acvp_mldsa44_sign_tg8_tc106         : PASS (100% bit-exact signature)
  [17/30] acvp_mldsa44_sign_tg8_tc107         : PASS (100% bit-exact signature)
  [18/30] acvp_mldsa44_sign_tg8_tc108         : PASS (100% bit-exact signature)
  [19/30] acvp_mldsa44_sign_tg8_tc109         : PASS (100% bit-exact signature)
  [20/30] acvp_mldsa44_sign_tg8_tc110         : PASS (100% bit-exact signature)
  [21/30] acvp_mldsa44_sign_tg8_tc111         : PASS (100% bit-exact signature)
  [22/30] acvp_mldsa44_sign_tg8_tc112         : PASS (100% bit-exact signature)
  [23/30] acvp_mldsa44_sign_tg8_tc113         : PASS (100% bit-exact signature)
  [24/30] acvp_mldsa44_sign_tg8_tc114         : PASS (100% bit-exact signature)
  [25/30] acvp_mldsa44_sign_tg8_tc115         : PASS (100% bit-exact signature)
  [26/30] acvp_mldsa44_sign_tg8_tc116         : PASS (100% bit-exact signature)
  [27/30] acvp_mldsa44_sign_tg8_tc117         : PASS (100% bit-exact signature)
  [28/30] acvp_mldsa44_sign_tg8_tc118         : PASS (100% bit-exact signature)
  [29/30] acvp_mldsa44_sign_tg8_tc119         : PASS (100% bit-exact signature)
  [30/30] acvp_mldsa44_sign_tg8_tc120         : PASS (100% bit-exact signature)
------------------------------------------------------------
<!-- [CLAIM-PROVENANCE: status=HISTORICAL; source=pqc_dr12_silicon_validation_20260829; classification=SELF_REPORTED_UNVERIFIED] -->
TOTAL: 30/30 PASS (100% BIT-EXACT MATCH ON PHYSICAL SILICON)
============================================================
```

---

## 3. Microarchitectural Physical Metrics

| Tile Worker | Role | ELF Text Size | Data RAM / Stack | Status |
|---|---|---|---|---|
| `Worker 0` | Init & Ingress | 5,008 Bytes | ~6.0 KiB | PASS |
| `Worker 1` | Mask Sample, Matrix A & Rejection Loop | 15,888 Bytes | ~22.0 KiB | PASS |
| `Worker 2` | Pointwise Products & INTT | 12,576 Bytes | ~28.0 KiB | PASS |
| `Worker 3` | MakeHint & CRC32 Hardware Sealing | 4,272 Bytes | ~20.0 KiB | PASS |
