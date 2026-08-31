# DR11: NIST FIPS 204 ML-DSA-44 KeyGen Physical Silicon Validation Report

> [!NOTE]
> <!-- [CLAIM-PROVENANCE: status=HISTORICAL; source=dr11_validation_report; classification=SELF_REPORTED_UNVERIFIED] -->
> [HISTORICAL CLAIM - UNVERIFIED / PENDING PHYSICAL DISPATCH CORROBORATION]
> This historical report documents pre-refactor self-reported metrics. Under current Phase A zero-speculation policy, DR11 is tracked as SELF_REPORTED_UNVERIFIED with 0 independently physically verified gates pending driver-level hardware execution trace corroboration.

## 1. Executive Test Summary

- **Validation Date**: August 29, 2026
- **Target Hardware**: AMD Phoenix NPU (Ryzen 7 7840HS / Ryzen 8040, XDNA1 / AIE2 VLIW Architecture)
- **Host Platform**: Windows 11 x64 (Build 26100), XRT Native User-Space Driver Stack
- **Toolchain**: MLIR-AIE 1.4.1 / IRON Python JIT / Peano Clang 21.0.0
- **Test Corpus**: Official NIST ACVP (Automated Cryptographic Validation Protocol) FIPS 204 ML-DSA-44 Test Vectors (25 Vectors)
- **Historical Scope**: 25 test cases evaluated
- **Host Fallback Count**: **0 (Zero)**

---

## 2. Test Execution Overview

The DR11 test suite evaluates 25 NIST ACVP ML-DSA-44 KeyGen test vectors on the AMD Phoenix NPU across test cases `acvp_mldsa44_keygen_tc01` through `acvp_mldsa44_keygen_tc25` for bit-exact public key and secret key generation.

---

## 3. Microarchitectural Performance & Memory Verification

- **Public Key Size (pk)**: 1312 Bytes
- **Private Key Size (sk)**: 2560 Bytes
- **Total Sealed Output Size**: 3892 Bytes (including 20-byte hardware record header & CRC32)
- **AIE2 Program Memory Consumption**: < 8 KiB per worker tile (Limit: 16 KiB)
- **AIE2 Tile Local Data Stack**: < 2 KiB per worker tile (Limit: 32 KiB)
- **Intermediate Tokens**: 3.7 KiB to 9.0 KiB across ObjectFIFOs

---

## 4. Cumulative Regression State

Following DR11, the legacy regression scope spanned 14 gates and 506 test cases:
- **DR1 (ML-DSA-44 RejNTT)**: 1 case tracked
- **DR2a (ML-KEM-512 SampleNTT)**: 1 case tracked
- **DR2b (ML-KEM-512 Noise+NTT)**: 1 case tracked
- **DR2c (ML-KEM-512 KeyGen Row)**: 1 case tracked
- **DR2d (ML-KEM-512 K-PKE.KeyGen)**: 10 cases tracked
- **DR3 (ML-KEM-512 K-PKE.Encrypt)**: 10 cases tracked
- **DR4 (ML-KEM-512 K-PKE.Decrypt)**: 10 cases tracked
- **DR5 (ML-KEM-512 ML-KEM.KeyGen)**: 100 cases tracked
- **DR6 (ML-KEM-512 ML-KEM.Encaps)**: 10 cases tracked
- **DR7 (ML-KEM-512 ML-KEM.Decaps)**: 100 cases tracked
- **DR8 (ML-KEM-768/1024 Expansion)**: 75 cases tracked
- **DR9 (Reusable FIPS 202 NPU Service)**: 122 cases tracked
- **DR10 (Sealed Lifecycle Architecture)**: 40 cases tracked
- **DR11 (FIPS 204 ML-DSA-44 KeyGen)**: 25 cases tracked
- **TOTAL**: **506 cases tracked across historical baseline**
