# DR11: NIST FIPS 204 ML-DSA-44 KeyGen Physical Silicon Validation Report

## 1. Executive Test Summary

- **Validation Date**: August 29, 2026
- **Target Hardware**: AMD Phoenix NPU (Ryzen 7 7840HS / Ryzen 8040, XDNA1 / AIE2 VLIW Architecture)
- **Host Platform**: Windows 11 x64 (Build 26100), XRT Native User-Space Driver Stack
- **Toolchain**: MLIR-AIE 1.4.1 / IRON Python JIT / Peano Clang 21.0.0
- **Test Corpus**: Official NIST ACVP (Automated Cryptographic Validation Protocol) FIPS 204 ML-DSA-44 Test Vectors (25 Vectors)
- **Validation Result**: **25 / 25 PASS (100% BIT-EXACT MATCH ON PHYSICAL SILICON)**
- **Host Fallback Count**: **0 (Zero)**

---

## 2. Test Execution Log

```
===========================================================
DR11: Complete NIST FIPS 204 ML-DSA-44 KeyGen Validation
Backend: dr11-mldsa44-keygen:silicon (AMD Phoenix AIE2)
===========================================================
Running 25 NIST ACVP ML-DSA-44 KeyGen vectors on AMD Phoenix NPU...
  [01/25] acvp_mldsa44_keygen_tc01           : PASS (100% bit-exact pk & sk)
  [02/25] acvp_mldsa44_keygen_tc02           : PASS (100% bit-exact pk & sk)
  [03/25] acvp_mldsa44_keygen_tc03           : PASS (100% bit-exact pk & sk)
  [04/25] acvp_mldsa44_keygen_tc04           : PASS (100% bit-exact pk & sk)
  [05/25] acvp_mldsa44_keygen_tc05           : PASS (100% bit-exact pk & sk)
  [06/25] acvp_mldsa44_keygen_tc06           : PASS (100% bit-exact pk & sk)
  [07/25] acvp_mldsa44_keygen_tc07           : PASS (100% bit-exact pk & sk)
  [08/25] acvp_mldsa44_keygen_tc08           : PASS (100% bit-exact pk & sk)
  [09/25] acvp_mldsa44_keygen_tc09           : PASS (100% bit-exact pk & sk)
  [10/25] acvp_mldsa44_keygen_tc10           : PASS (100% bit-exact pk & sk)
  [11/25] acvp_mldsa44_keygen_tc11           : PASS (100% bit-exact pk & sk)
  [12/25] acvp_mldsa44_keygen_tc12           : PASS (100% bit-exact pk & sk)
  [13/25] acvp_mldsa44_keygen_tc13           : PASS (100% bit-exact pk & sk)
  [14/25] acvp_mldsa44_keygen_tc14           : PASS (100% bit-exact pk & sk)
  [15/25] acvp_mldsa44_keygen_tc15           : PASS (100% bit-exact pk & sk)
  [16/25] acvp_mldsa44_keygen_tc16           : PASS (100% bit-exact pk & sk)
  [17/25] acvp_mldsa44_keygen_tc17           : PASS (100% bit-exact pk & sk)
  [18/25] acvp_mldsa44_keygen_tc18           : PASS (100% bit-exact pk & sk)
  [19/25] acvp_mldsa44_keygen_tc19           : PASS (100% bit-exact pk & sk)
  [20/25] acvp_mldsa44_keygen_tc20           : PASS (100% bit-exact pk & sk)
  [21/25] acvp_mldsa44_keygen_tc21           : PASS (100% bit-exact pk & sk)
  [22/25] acvp_mldsa44_keygen_tc22           : PASS (100% bit-exact pk & sk)
  [23/25] acvp_mldsa44_keygen_tc23           : PASS (100% bit-exact pk & sk)
  [24/25] acvp_mldsa44_keygen_tc24           : PASS (100% bit-exact pk & sk)
  [25/25] acvp_mldsa44_keygen_tc25           : PASS (100% bit-exact pk & sk)
-----------------------------------------------------------
TOTAL: 25/25 PASS (100% BIT-EXACT MATCH ON PHYSICAL SILICON)
===========================================================
```

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

Following the completion of DR11, the master silicon regression suite now spans **14 gates and 506 physical silicon test cases**:
- **DR1 (ML-DSA-44 RejNTT)**: 1 / 1 PASS
- **DR2a (ML-KEM-512 SampleNTT)**: 1 / 1 PASS
- **DR2b (ML-KEM-512 Noise+NTT)**: 1 / 1 PASS
- **DR2c (ML-KEM-512 KeyGen Row)**: 1 / 1 PASS
- **DR2d (ML-KEM-512 K-PKE.KeyGen)**: 10 / 10 PASS
- **DR3 (ML-KEM-512 K-PKE.Encrypt)**: 10 / 10 PASS
- **DR4 (ML-KEM-512 K-PKE.Decrypt)**: 10 / 10 PASS
- **DR5 (ML-KEM-512 ML-KEM.KeyGen)**: 100 / 100 PASS
- **DR6 (ML-KEM-512 ML-KEM.Encaps)**: 10 / 10 PASS
- **DR7 (ML-KEM-512 ML-KEM.Decaps)**: 100 / 100 PASS
- **DR8 (ML-KEM-768/1024 Expansion)**: 75 / 75 PASS
- **DR9 (Reusable FIPS 202 NPU Service)**: 122 / 122 PASS
- **DR10 (Sealed Lifecycle Architecture)**: 40 / 40 PASS
- **DR11 (FIPS 204 ML-DSA-44 KeyGen)**: 25 / 25 PASS
- **GRAND TOTAL**: **506 / 506 PASS (100% ON PHYSICAL SILICON)**
