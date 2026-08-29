# NIST FIPS 204 ML-DSA-44 Verify Silicon Validation Report

**Date**: 2026-08-29  
**Platform**: AMD Phoenix APU (AIE2 / XDNA1, Ryzen 7040/8040 series)  
**Toolchain**: MLIR-AIE 1.4.1 / Peano Clang / XRT 2.20.0  
**Artifact**: `dr13_mldsa44_verify_graph.py` & `dr13_mldsa44_verify_w*.cc`  
**Dataset**: Official NIST ACVP `ML-DSA-sigVer-FIPS204` Internal Test Vectors (30 vectors: 6 valid, 24 mutated/error cases)

---

## 1. Executive Summary

Milestone **DR13** (Complete NIST FIPS 204 ML-DSA-44 100% On-Device Signature Verification) was executed and validated directly on AMD Phoenix AIE2 physical silicon. All 30 test vectors achieved a **100% bit-exact match** against NIST ACVP KAT reference verification verdicts.

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
>>> DR13 (FIPS 204 ML-DSA-44 Verify)   : PASS ( 30 /  30)
================================================================================
ALL 16/16 PQC MILESTONES PASSED (566 / 566 TOTAL PASS - 100% SILICON VALIDATION)
================================================================================
```

---

## 2. Test Execution Log (DR13)

```
============================================================
DR13: Complete NIST FIPS 204 ML-DSA-44 Verify Validation
Backend: dr13-mldsa44-verify:silicon (AMD Phoenix AIE2)
============================================================
Running 30 NIST ACVP ML-DSA-44 Verify vectors on AMD Phoenix NPU...
  [01/30] acvp_mldsa44_verify_tg7_tc91            : PASS (VALID (Accepted))
  [02/30] acvp_mldsa44_verify_tg7_tc92            : PASS (INVALID (Rejected))
  [03/30] acvp_mldsa44_verify_tg7_tc93            : PASS (INVALID (Rejected))
  [04/30] acvp_mldsa44_verify_tg7_tc94            : PASS (INVALID (Rejected))
  [05/30] acvp_mldsa44_verify_tg7_tc95            : PASS (INVALID (Rejected))
  [06/30] acvp_mldsa44_verify_tg7_tc96            : PASS (VALID (Accepted))
  [07/30] acvp_mldsa44_verify_tg7_tc97            : PASS (INVALID (Rejected))
  [08/30] acvp_mldsa44_verify_tg7_tc98            : PASS (INVALID (Rejected))
  [09/30] acvp_mldsa44_verify_tg7_tc99            : PASS (VALID (Accepted))
  [10/30] acvp_mldsa44_verify_tg7_tc100           : PASS (INVALID (Rejected))
  [11/30] acvp_mldsa44_verify_tg7_tc101           : PASS (INVALID (Rejected))
  [12/30] acvp_mldsa44_verify_tg7_tc102           : PASS (INVALID (Rejected))
  [13/30] acvp_mldsa44_verify_tg7_tc103           : PASS (INVALID (Rejected))
  [14/30] acvp_mldsa44_verify_tg7_tc104           : PASS (INVALID (Rejected))
  [15/30] acvp_mldsa44_verify_tg7_tc105           : PASS (INVALID (Rejected))
  [16/30] acvp_mldsa44_verify_tg8_tc106           : PASS (INVALID (Rejected))
  [17/30] acvp_mldsa44_verify_tg8_tc107           : PASS (INVALID (Rejected))
  [18/30] acvp_mldsa44_verify_tg8_tc108           : PASS (INVALID (Rejected))
  [19/30] acvp_mldsa44_verify_tg8_tc109           : PASS (INVALID (Rejected))
  [20/30] acvp_mldsa44_verify_tg8_tc110           : PASS (INVALID (Rejected))
  [21/30] acvp_mldsa44_verify_tg8_tc111           : PASS (INVALID (Rejected))
  [22/30] acvp_mldsa44_verify_tg8_tc112           : PASS (VALID (Accepted))
  [23/30] acvp_mldsa44_verify_tg8_tc113           : PASS (INVALID (Rejected))
  [24/30] acvp_mldsa44_verify_tg8_tc114           : PASS (VALID (Accepted))
  [25/30] acvp_mldsa44_verify_tg8_tc115           : PASS (INVALID (Rejected))
  [26/30] acvp_mldsa44_verify_tg8_tc116           : PASS (VALID (Accepted))
  [27/30] acvp_mldsa44_verify_tg8_tc117           : PASS (INVALID (Rejected))
  [28/30] acvp_mldsa44_verify_tg8_tc118           : PASS (INVALID (Rejected))
  [29/30] acvp_mldsa44_verify_tg8_tc119           : PASS (INVALID (Rejected))
  [30/30] acvp_mldsa44_verify_tg8_tc120           : PASS (INVALID (Rejected))
------------------------------------------------------------
TOTAL: 30/30 PASS (100% BIT-EXACT MATCH ON PHYSICAL SILICON)
============================================================
```

---

## 3. Microarchitectural Physical Metrics

| Tile Worker | Role | ELF Text Size | Data RAM / Stack | Status |
|---|---|---|---|---|
| `Worker 0` | Ingress, Decode z/h/t1, NTTs | 11,552 Bytes | ~14.5 KiB | PASS |
| `Worker 1` | ExpandA, Matrix Acc, UseHint, SHAKE256 Verify | 10,928 Bytes | ~14.5 KiB | PASS |
