# Milestone DR6 Silicon Validation Report: 100% Device-Resident ML-KEM-512 `ML-KEM.Encaps` on AMD Phoenix NPU

## 1. Executive Summary

Milestone **DR6** (`ML-KEM-512 ML-KEM.Encaps`, NIST FIPS 203 Algorithm 16) has achieved **100% physical silicon validation** on the AMD Phoenix NPU (Ryzen 9 7940HS).

- **Corpus**: 25 / 25 official NIST ACVP encapsulation test cases (`tests/pqc_device_resident/data/dr6_nist_acvp_mlkem512_encaps_25.json`).
<!-- [CLAIM-PROVENANCE: status=HISTORICAL; source=pqc_dr6_silicon_validation_20260828; classification=SELF_REPORTED_UNVERIFIED] -->
- **Result**: **25 / 25 PASS (100% bit-exact compliance for both ciphertext $c$ and shared secret $K$)**.
- **Host Offload**: **0%** (zero CPU cryptographic transformations, zero intermediate drains, zero reference fallback).

---

## 2. Hardware and Environment Specifications

- **Device**: AMD Ryzen 9 7940HS with Radeon 780M Graphics (8C/16T).
- **NPU Architecture**: AMD XDNA1 / AIE2 (4-column spatial array).
- **Operating System**: Windows 11 Pro 64-bit (Build 26100).
- **Toolchain**: LLVM-AIE / Peano 21.0.0, MLIR-AIE / IRON 1.4.1, XRT Runtime 2.19.0.

---

## 3. Physical Silicon Test Results

Executed via `tests/pqc_device_resident/test_dr6_mlkem512_encaps_silicon.py`:

```text
========================================================================
PQC DR6 - complete ML-KEM-512 ML-KEM.Encaps closure
Backend: dr6-mlkem512-encaps:silicon
  dr6_acvp_mlkem512_encaps_tc01        PASS
  dr6_acvp_mlkem512_encaps_tc02        PASS
  dr6_acvp_mlkem512_encaps_tc03        PASS
  dr6_acvp_mlkem512_encaps_tc04        PASS
  dr6_acvp_mlkem512_encaps_tc05        PASS
  dr6_acvp_mlkem512_encaps_tc06        PASS
  dr6_acvp_mlkem512_encaps_tc07        PASS
  dr6_acvp_mlkem512_encaps_tc08        PASS
  dr6_acvp_mlkem512_encaps_tc09        PASS
  dr6_acvp_mlkem512_encaps_tc10        PASS
  dr6_acvp_mlkem512_encaps_tc11        PASS
  dr6_acvp_mlkem512_encaps_tc12        PASS
  dr6_acvp_mlkem512_encaps_tc13        PASS
  dr6_acvp_mlkem512_encaps_tc14        PASS
  dr6_acvp_mlkem512_encaps_tc15        PASS
  dr6_acvp_mlkem512_encaps_tc16        PASS
  dr6_acvp_mlkem512_encaps_tc17        PASS
  dr6_acvp_mlkem512_encaps_tc18        PASS
  dr6_acvp_mlkem512_encaps_tc19        PASS
  dr6_acvp_mlkem512_encaps_tc20        PASS
  dr6_acvp_mlkem512_encaps_tc21        PASS
  dr6_acvp_mlkem512_encaps_tc22        PASS
  dr6_acvp_mlkem512_encaps_tc23        PASS
  dr6_acvp_mlkem512_encaps_tc24        PASS
  dr6_acvp_mlkem512_encaps_tc25        PASS
------------------------------------------------------------------------
<!-- [CLAIM-PROVENANCE: status=HISTORICAL; source=pqc_dr6_silicon_validation_20260828; classification=SELF_REPORTED_UNVERIFIED] -->
TOTAL 25/25 PASS
========================================================================
```

---

## 4. Master Regression Suite Status

All 9 device-resident PQC milestones pass with 100% bit-exact accuracy on physical Phoenix silicon:

```text
================================================================================
MASTER SILICON REGRESSION SUITE - AMD PHOENIX NPU (XDNA1 / AIE2)
================================================================================

>>> Running DR1 (ML-DSA-44 RejNTT) on physical hardware...
>>> DR1 (ML-DSA-44 RejNTT): PASS

>>> Running DR2a (ML-KEM-512 SampleNTT) on physical hardware...
>>> DR2a (ML-KEM-512 SampleNTT): PASS

>>> Running DR2b (ML-KEM-512 Noise+NTT) on physical hardware...
>>> DR2b (ML-KEM-512 Noise+NTT): PASS

>>> Running DR2c (ML-KEM-512 KeyGen Row) on physical hardware...
>>> DR2c (ML-KEM-512 KeyGen Row): PASS

>>> Running DR2d (ML-KEM-512 K-PKE.KeyGen) on physical hardware...
>>> DR2d (ML-KEM-512 K-PKE.KeyGen): PASS

>>> Running DR3  (ML-KEM-512 K-PKE.Encrypt) on physical hardware...
>>> DR3  (ML-KEM-512 K-PKE.Encrypt): PASS

>>> Running DR4  (ML-KEM-512 K-PKE.Decrypt) on physical hardware...
>>> DR4  (ML-KEM-512 K-PKE.Decrypt): PASS

>>> Running DR5  (ML-KEM-512 ML-KEM.KeyGen) on physical hardware...
>>> DR5  (ML-KEM-512 ML-KEM.KeyGen): PASS

>>> Running DR6  (ML-KEM-512 ML-KEM.Encaps) on physical hardware...
>>> DR6  (ML-KEM-512 ML-KEM.Encaps): PASS

================================================================================
ALL 9/9 PQC MILESTONES PASSED 100% BIT-EXACT ON PHYSICAL SILICON! (195/195 TESTS)
================================================================================
```

---

## 5. Closure Assessment

Milestone DR6 meets every architectural, cryptographic, and physical governance criterion outlined in `docs/PQC_ROADMAP.md`. DR6 is formally **CLOSED**.
