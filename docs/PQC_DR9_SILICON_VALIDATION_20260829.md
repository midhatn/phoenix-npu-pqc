# DR9 Silicon Validation Report: Reusable NIST FIPS 202 NPU Service

> [!NOTE]
> <!-- [CLAIM-PROVENANCE: status=HISTORICAL; source=dr9_validation_report; classification=SELF_REPORTED_UNVERIFIED] -->
> [HISTORICAL CLAIM - UNVERIFIED / PENDING PHYSICAL DISPATCH CORROBORATION]
> This historical report documents pre-refactor self-reported metrics. Under current Phase A zero-speculation policy, DR9 is tracked as SELF_REPORTED_UNVERIFIED with 0 independently physically verified gates pending driver-level hardware execution trace corroboration.

**Date:** 2026-08-29  
**Platform:** AMD Phoenix NPU (Ryzen 7040 / 8040 AIE2 Architecture, XDNA1)  
**Host Environment:** Windows 11 x86_64, MLIR-AIE 1.4.1, XRT Native Runtime
**Historical Self-Reported Scope:** 122 test cases tracked across all 6 FIPS 202 functions

---

## 1. Validation Scope

Milestone **DR9** evaluated the on-device reusable NIST FIPS 202 service across:
1. **SHA3-224** (13 test cases: empty, 1-byte, rate boundaries, multi-block up to 1024 B)
2. **SHA3-256** (13 test cases: empty, 1-byte, rate boundaries, multi-block up to 1024 B)
3. **SHA3-384** (13 test cases: empty, 1-byte, rate boundaries, multi-block up to 1024 B)
4. **SHA3-512** (13 test cases: empty, 1-byte, rate boundaries, multi-block up to 1024 B)
5. **SHAKE128** (35 test cases: varying squeeze lengths 16, 32, 64, 168, 256, 512, 1024 B across message patterns)
6. **SHAKE256** (35 test cases: varying squeeze lengths 16, 32, 64, 136, 256, 512, 1024 B across message patterns)

---

## 2. Test Results Summary

| Function | Output Length | Vectors Evaluated | Baseline Scope | Historical Status |
|---|---|---|---|---|
| **SHA3-224** | 28 bytes | 13 | 13 cases | Evaluated |
| **SHA3-256** | 32 bytes | 13 | 13 cases | Evaluated |
| **SHA3-384** | 48 bytes | 13 | 13 cases | Evaluated |
| **SHA3-512** | 64 bytes | 13 | 13 cases | Evaluated |
| **SHAKE128** | Variable (16–1024 B) | 35 | 35 cases | Evaluated |
| **SHAKE256** | Variable (16–1024 B) | 35 | 35 cases | Evaluated |
| **TOTAL DR9** | **All 6 Functions** | **122** | **122 cases** | **Tracked** |

---

## 3. Master Silicon Regression Suite Status

The master regression test runner (`tests/pqc_device_resident/run_all_silicon_tests.py`) was evaluated across all 12 active gates in the legacy baseline:

| Milestone Gate | Algorithm / Component | Cases | Baseline Scope |
|---|---|---|---|
| **DR1** | ML-DSA-44 RejNTT Matrix Expansion | 33 | 33 cases tracked |
| **DR2a** | ML-KEM-512 Bounded SampleNTT | 13 | 13 cases tracked |
| **DR2b** | ML-KEM-512 Noise Sampler + Forward NTT | 13 | 13 cases tracked |
| **DR2c** | ML-KEM-512 KeyGen Row Multiplier | 11 | 11 cases tracked |
| **DR2d** | ML-KEM-512 Complete K-PKE.KeyGen Pipeline | 25 | 25 cases tracked |
| **DR3** | ML-KEM-512 Complete K-PKE.Encrypt Pipeline | 25 | 25 cases tracked |
| **DR4** | ML-KEM-512 Complete K-PKE.Decrypt Pipeline | 25 | 25 cases tracked |
| **DR5** | ML-KEM-512 Complete ML-KEM.KeyGen Pipeline | 25 | 25 cases tracked |
| **DR6** | ML-KEM-512 Complete ML-KEM.Encaps Pipeline | 25 | 25 cases tracked |
| **DR7** | ML-KEM-512 Complete ML-KEM.Decaps Pipeline | 25 | 25 cases tracked |
| **DR8** | ML-KEM Parameter-Set Expansion (768, 1024) | 75 | 75 cases tracked |
| **DR9** | Reusable FIPS 202 NPU Service (SHA3/SHAKE) | 122 | 122 cases tracked |
| **CUMULATIVE TOTAL** | **Master Physical Silicon Regression** | **441** | **441 cases tracked** |
