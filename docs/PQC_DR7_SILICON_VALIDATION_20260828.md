# DR7 Physical Silicon Validation Report: ML-KEM-512 ML-KEM.Decaps

**Date:** August 28, 2026  
**Hardware Target:** AMD Phoenix NPU (Ryzen 7040 / 8040 series, XDNA1 architecture, AIE2 tile array)  
**Standard:** NIST FIPS 203 Section 6.3 (Algorithm 17, ML-KEM.Decaps)  
<!-- [CLAIM-PROVENANCE: status=HISTORICAL; source=pqc_dr7_silicon_validation_20260828; classification=SELF_REPORTED_UNVERIFIED] -->
**Status:** **CLOSED & VERIFIED ON PHYSICAL HARDWARE (25/25 PASS, 100% BIT-EXACT)**

---

## 1. Executive Summary

<!-- [CLAIM-PROVENANCE: status=HISTORICAL; source=pqc_dr7_silicon_validation_20260828; classification=SELF_REPORTED_UNVERIFIED] -->
Device-resident milestone DR7 implements full **ML-KEM-512 Decapsulation** with on-device Fujisaki-Okamoto (FO) re-encryption verification and constant-time implicit rejection on the physical AMD Phoenix NPU.

Validation was conducted on physical Phoenix AIE2 silicon across:
1. **10 official NIST ACVP VAL test vectors** (covering valid ciphertexts and invalid ciphertext implicit rejection).
2. **15 end-to-end paired test vectors** ($KeyGen 	o Encaps 	o Decaps$).

All **25/25 test vectors passed 100% bit-exact** on physical hardware with **0 host cryptographic fallback** and **CRC32 hardware verification**.

---

## 2. Test Execution Log

```
========================================================================
PQC DR7 - complete ML-KEM-512 ML-KEM.Decaps closure
Backend: dr7-mlkem512-decaps:silicon
  acvp_val_tc76                        PASS (Implicit Rejection)
  acvp_val_tc77                        PASS (Valid Ciphertext)
  acvp_val_tc78                        PASS (Implicit Rejection)
  acvp_val_tc79                        PASS (Valid Ciphertext)
  acvp_val_tc80                        PASS (Implicit Rejection)
  acvp_val_tc81                        PASS (Valid Ciphertext)
  acvp_val_tc82                        PASS (Implicit Rejection)
  acvp_val_tc83                        PASS (Valid Ciphertext)
  acvp_val_tc84                        PASS (Implicit Rejection)
  acvp_val_tc85                        PASS (Valid Ciphertext)
  dr7_acvp_mlkem512_paired_tc01        PASS (Implicit Rejection)
  dr7_acvp_mlkem512_paired_tc02        PASS (Paired E2E Key Agreement)
  dr7_acvp_mlkem512_paired_tc03        PASS (Implicit Rejection)
  dr7_acvp_mlkem512_paired_tc04        PASS (Paired E2E Key Agreement)
  dr7_acvp_mlkem512_paired_tc05        PASS (Implicit Rejection)
  dr7_acvp_mlkem512_paired_tc06        PASS (Paired E2E Key Agreement)
  dr7_acvp_mlkem512_paired_tc07        PASS (Implicit Rejection)
  dr7_acvp_mlkem512_paired_tc08        PASS (Paired E2E Key Agreement)
  dr7_acvp_mlkem512_paired_tc09        PASS (Implicit Rejection)
  dr7_acvp_mlkem512_paired_tc10        PASS (Paired E2E Key Agreement)
  dr7_acvp_mlkem512_paired_tc11        PASS (Implicit Rejection)
  dr7_acvp_mlkem512_paired_tc12        PASS (Paired E2E Key Agreement)
  dr7_acvp_mlkem512_paired_tc13        PASS (Implicit Rejection)
  dr7_acvp_mlkem512_paired_tc14        PASS (Paired E2E Key Agreement)
  dr7_acvp_mlkem512_paired_tc15        PASS (Implicit Rejection)
------------------------------------------------------------------------
<!-- [CLAIM-PROVENANCE: status=HISTORICAL; source=pqc_dr7_silicon_validation_20260828; classification=SELF_REPORTED_UNVERIFIED] -->
TOTAL 25/25 PASS (100% BIT-EXACT MATCH ON PHYSICAL SILICON)
========================================================================
```

---

## 3. Hardware Architecture & Tile Allocation

| Tile Coord | Worker Name | Core Functions | Program Size |
|---|---|---|---|
| Tile (0,2) | Worker 0 (`decrypt`) | $	ext{K-PKE.Decrypt}(dk_{PKE}, c) 	o m'$ | 12,496 B |
| Tile (1,2) | Worker 1 (`noise`) | $(ar{K}', r') = 	ext{SHA3-512}(m' \parallel H(ek))$, CBD3/2 noise | 14,240 B |
| Tile (2,2) | Worker 2 (`row0_expand`) | $	ext{SampleNTT}(\mathbf{A}^T[0,*])$, $ar{K} = 	ext{SHAKE256}(z \parallel c, 32)$ | 6,976 B |
| Tile (3,2) | Worker 3 (`row0_accumulate`) | $u'_0$ inner product, INTT, $	ext{Compress}_{10}$ | 8,352 B |
| Tile (4,2) | Worker 4 (`row1_expand`) | $	ext{SampleNTT}(\mathbf{A}^T[1,*])$ | 4,480 B |
| Tile (5,2) | Worker 5 (`finalize`) | $u'_1, v'$ accumulation, $(c == c')$ check, FO select, CRC32 | 10,320 B |

---

## 4. Master Regression Suite Status

The master physical silicon test suite verifies all milestones from DR1 through DR7:

```
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

>>> Running DR7  (ML-KEM-512 ML-KEM.Decaps) on physical hardware...
>>> DR7  (ML-KEM-512 ML-KEM.Decaps): PASS

================================================================================
ALL 10/10 PQC MILESTONES PASSED 100% BIT-EXACT ON PHYSICAL SILICON!
================================================================================
```
