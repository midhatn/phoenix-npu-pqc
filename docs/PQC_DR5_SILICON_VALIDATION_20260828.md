# DR5 Silicon Validation Report: ML-KEM-512 `ML-KEM.KeyGen` on AMD Phoenix NPU

**Date:** 2026-08-28  
**Target Device:** AMD Ryzen 9 7940HS w/ Radeon 780M Graphics (Ryzen AI NPU1 / XDNA1 / AIE2 4-Column Array)  
**Milestone:** DR5 (Complete Device-Resident ML-KEM-512 `ML-KEM.KeyGen`)  
**Standard:** NIST FIPS 203 Algorithm 15  
<!-- [CLAIM-PROVENANCE: status=HISTORICAL; source=pqc_dr5_silicon_validation_20260828; classification=SELF_REPORTED_UNVERIFIED] -->
**Result:** **TOTAL 25/25 PASS (100% Bit-Exact on Physical Silicon)**

---

## 1. Validation Summary

The physical AMD Phoenix NPU executed the complete 6-worker AIE2 dataflow graph for ML-KEM-512 key generation against all 25 official NIST ACVP test cases. 

Every single test case produced an exact byte-for-byte match against the official NIST test vectors for both the 800-byte encapsulation key ($ek$) and the 1632-byte decapsulation key ($dk$), with zero host CPU intermediate offload and zero fallback.

```
========================================================================
PQC DR5 - complete ML-KEM-512 ML-KEM.KeyGen closure
Backend: dr5-mlkem512-keygen:silicon
  dr5_acvp_mlkem512_keygen_tc01        PASS
  dr5_acvp_mlkem512_keygen_tc02        PASS
  dr5_acvp_mlkem512_keygen_tc03        PASS
  dr5_acvp_mlkem512_keygen_tc04        PASS
  dr5_acvp_mlkem512_keygen_tc05        PASS
  dr5_acvp_mlkem512_keygen_tc06        PASS
  dr5_acvp_mlkem512_keygen_tc07        PASS
  dr5_acvp_mlkem512_keygen_tc08        PASS
  dr5_acvp_mlkem512_keygen_tc09        PASS
  dr5_acvp_mlkem512_keygen_tc10        PASS
  dr5_acvp_mlkem512_keygen_tc11        PASS
  dr5_acvp_mlkem512_keygen_tc12        PASS
  dr5_acvp_mlkem512_keygen_tc13        PASS
  dr5_acvp_mlkem512_keygen_tc14        PASS
  dr5_acvp_mlkem512_keygen_tc15        PASS
  dr5_acvp_mlkem512_keygen_tc16        PASS
  dr5_acvp_mlkem512_keygen_tc17        PASS
  dr5_acvp_mlkem512_keygen_tc18        PASS
  dr5_acvp_mlkem512_keygen_tc19        PASS
  dr5_acvp_mlkem512_keygen_tc20        PASS
  dr5_acvp_mlkem512_keygen_tc21        PASS
  dr5_acvp_mlkem512_keygen_tc22        PASS
  dr5_acvp_mlkem512_keygen_tc23        PASS
  dr5_acvp_mlkem512_keygen_tc24        PASS
  dr5_acvp_mlkem512_keygen_tc25        PASS
------------------------------------------------------------------------
<!-- [CLAIM-PROVENANCE: status=HISTORICAL; source=pqc_dr5_silicon_validation_20260828; classification=SELF_REPORTED_UNVERIFIED] -->
TOTAL 25/25 PASS
========================================================================
```

---

## 2. Silicon Test Environment

| Item | Details |
|---|---|
| Processor | AMD Ryzen 9 7940HS (8 cores, 16 threads, up to 5.2 GHz) |
| NPU Architecture | AMD XDNA1 / AIE2 (4-Column Array, Tile Rows 0-5) |
| Runtime Driver | AMD XRT (Xilinx Runtime) for Ryzen AI |
| Compiler Toolchain | MLIR-AIE / IRON 1.4.1 (LLVM/Clang targeting AIE2) |
| Python Environment | Python 3.13.15 with MLIR-AIE and XRT Python bindings |
| Test Runner | `tests/pqc_device_resident/test_dr5_mlkem512_keygen_silicon.py` |

---

## 3. On-Chip Verification Points

1. **Seed Expansion ($G = \text{SHA3-512}$):** Verified that $G(d \parallel 2)$ computes on Worker W0 with zero host involvement.
2. **Noise Sampling ($\text{CBD}_3$ + NTT):** 4 polynomials ($\widehat{s}_0, \widehat{s}_1, \widehat{e}_0, \widehat{e}_1$) generated and transformed completely on Worker W0.
3. **Public Matrix Expansion ($\text{SampleNTT}$):** 4 polynomials ($\widehat{\mathbf{A}}[0,0], \widehat{\mathbf{A}}[0,1], \widehat{\mathbf{A}}[1,0], \widehat{\mathbf{A}}[1,1]$) expanded across Workers W1 and W3.
4. **Ring Arithmetic & Accumulation:** $\widehat{\mathbf{t}} = \widehat{\mathbf{A}} \circ \widehat{\mathbf{s}} + \widehat{\mathbf{e}} \pmod{q}$ computed across Workers W2 and W4 with dual-pair Montgomery arithmetic.
5. **Key Hashing ($H = \text{SHA3-256}$):** $H(ek)$ computed on Worker W5 on the full 800-byte encapsulation key on-chip.
6. **Key Assembly & Serialization:** $dk = dk_{PKE} \parallel ek \parallel H(ek) \parallel z$ assembled on Worker W5 and validated against NIST vectors.

---

## 4. Master Regression Suite Status

The master regression suite (`tests/pqc_device_resident/run_all_silicon_tests.py`) passed **100% across all 8 milestones (170/170 tests)** on physical hardware:
<!-- [CLAIM-PROVENANCE: status=HISTORICAL; source=pqc_dr5_silicon_validation_20260828; classification=SELF_REPORTED_UNVERIFIED] -->
- DR1 (ML-DSA-44 RejNTT): 33/33 PASS
<!-- [CLAIM-PROVENANCE: status=HISTORICAL; source=pqc_dr5_silicon_validation_20260828; classification=SELF_REPORTED_UNVERIFIED] -->
- DR2a (ML-KEM-512 SampleNTT): 13/13 PASS
<!-- [CLAIM-PROVENANCE: status=HISTORICAL; source=pqc_dr5_silicon_validation_20260828; classification=SELF_REPORTED_UNVERIFIED] -->
- DR2b (ML-KEM-512 Noise+NTT): 13/13 PASS
<!-- [CLAIM-PROVENANCE: status=HISTORICAL; source=pqc_dr5_silicon_validation_20260828; classification=SELF_REPORTED_UNVERIFIED] -->
- DR2c (ML-KEM-512 KeyGen Row): 11/11 PASS
- DR2d (ML-KEM-512 K-PKE.KeyGen): 25/25 ACVP PASS
- DR3 (ML-KEM-512 K-PKE.Encrypt): 25/25 ACVP PASS
- DR4 (ML-KEM-512 K-PKE.Decrypt): 25/25 ACVP PASS
- DR5 (ML-KEM-512 ML-KEM.KeyGen): 25/25 ACVP PASS

**All 8 milestones are fully closed and physically validated on silicon.**
