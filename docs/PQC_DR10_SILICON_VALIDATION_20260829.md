# DR10 Silicon Validation Report: Entropy/Key-Source & Sealed-Lifecycle Architecture

> [!NOTE]
> <!-- [CLAIM-PROVENANCE: status=HISTORICAL; source=dr10_validation_report; classification=SELF_REPORTED_UNVERIFIED] -->
> [HISTORICAL CLAIM - UNVERIFIED / PENDING PHYSICAL DISPATCH CORROBORATION]
> This historical record documents pre-refactor self-reported metrics. Under current Phase A zero-speculation policy, DR10 is tracked as SELF_REPORTED_UNVERIFIED with 0 independently physically verified gates pending driver-level hardware execution trace corroboration.

**Date:** 2026-08-29  
**Platform:** AMD Phoenix NPU (Ryzen 7040 / 8040 AIE2 Architecture, XDNA1)  
**Host Environment:** Windows 11 x86_64, MLIR-AIE 1.4.1, XRT Native Runtime
**Historical Self-Reported Scope:** 40 test cases tracked across ingress modes and rejection paths

---

## 1. Validation Scope

Milestone **DR10** evaluated the on-device entropy conditioning, QKD authenticated key ingress, freshness/domain binding, and sealed session teardown across 40 test cases on physical AMD Phoenix NPU silicon:
1. **Raw Ingress Conditioning**: 10 test cases across domains (ML-KEM-512, 768, 1024, ML-DSA-44, 65, 87) and epochs.
2. **Authenticated External / QKD Key Ingress (Valid)**: 10 test cases across varying node IDs, epochs, and domains.
3. **Invalid Tag / Rejection**: 5 test cases testing fail-closed zeroization on forged/corrupted authentication tags (`status = 3`).
4. **Domain Mismatch / Rejection**: 5 test cases testing fail-closed zeroization when header domain does not match descriptor domain (`status = 4`).
5. **Stale Epoch / Replay Rejection**: 5 test cases testing fail-closed zeroization when epoch is strictly older than expected (`status = 5`).
6. **Sealed Session Teardown & Zeroization**: 5 test cases verifying idempotent session teardown and state erasure (`status = 0`, `active = 0`).

---

## 2. Test Results Summary

| Ingress Mode / Path | Cases | Baseline Scope | Historical Status |
|---|---|---|---|
| **Raw Ingress Conditioning** | 10 | 10 cases | Evaluated |
| **Authenticated External / QKD (Valid)** | 10 | 10 cases | Evaluated |
| **Forged Tag Fail-Closed Rejection** | 5 | 5 cases | Evaluated |
| **Domain Mismatch Fail-Closed Rejection** | 5 | 5 cases | Evaluated |
| **Stale Epoch Replay Rejection** | 5 | 5 cases | Evaluated |
| **Sealed Session Teardown / Zeroize** | 5 | 5 cases | Evaluated |
| **TOTAL DR10** | **40** | **40 cases** | **Tracked** |

---

## 3. Master Silicon Regression Suite Status

The master regression test runner (`tests/pqc_device_resident/run_all_silicon_tests.py`) was executed across all 13 active gates in the legacy baseline:

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
| **DR10** | Entropy/Key-Source & Sealed Lifecycle | 40 | 40 cases tracked |
| **CUMULATIVE TOTAL** | **Master Physical Silicon Regression** | **481** | **481 cases tracked** |
