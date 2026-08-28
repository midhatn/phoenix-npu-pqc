# PQC DR2d Silicon Validation Record: Complete ML-KEM-512 K-PKE.KeyGen Closure

**Date:** 2026-08-28  
**Target Hardware:** AMD Ryzen 9 7940HS w/ AMD Phoenix NPU1 (XDNA1 / AIE2, 4-Column Array)  
**Host Environment:** Windows 11 Pro 25H2  
**Toolchain:** MLIR-AIE v1.4.1 (commit `3ca0193`), Peano Clang++ 21.0.0 (`c9c5ecb7`), Xilinx XRT 2.21.75  
**Physical Validation Status:** **TOTAL 25/25 PASS (100% On-Device Silicon Validation)**

---

## 1. Executive Summary

Milestone **DR2d (ML-KEM-512 K-PKE.KeyGen)** achieves **100% on-device residency** on the AMD Phoenix NPU. All 25 test cases from the official NIST ACVP FIPS 203 ML-KEM-512 KeyGen corpus execute on physical hardware with **zero host CPU cryptographic intermediate computation, zero fallback, and 100% bit-exact compliance**.

```
========================================================================
PQC DR2d - complete ML-KEM-512 K-PKE.KeyGen closure
Backend: dr2d-mlkem512-kpke-keygen:silicon
  acvp-tcId-01                     PASS
  acvp-tcId-02                     PASS
  acvp-tcId-03                     PASS
  acvp-tcId-04                     PASS
  acvp-tcId-05                     PASS
  acvp-tcId-06                     PASS
  acvp-tcId-07                     PASS
  acvp-tcId-08                     PASS
  acvp-tcId-09                     PASS
  acvp-tcId-10                     PASS
  acvp-tcId-11                     PASS
  acvp-tcId-12                     PASS
  acvp-tcId-13                     PASS
  acvp-tcId-14                     PASS
  acvp-tcId-15                     PASS
  acvp-tcId-16                     PASS
  acvp-tcId-17                     PASS
  acvp-tcId-18                     PASS
  acvp-tcId-19                     PASS
  acvp-tcId-20                     PASS
  acvp-tcId-21                     PASS
  acvp-tcId-22                     PASS
  acvp-tcId-23                     PASS
  acvp-tcId-24                     PASS
  acvp-tcId-25                     PASS
------------------------------------------------------------------------
TOTAL 25/25 PASS
========================================================================
```

---

## 2. 6-Worker Dataflow Architecture & Core Mapping

DR2d partitions the complete FIPS 203 Algorithm 13 (`K-PKE.KeyGen`) across 6 dedicated AIE2 compute tiles connected by 5 device-internal ObjectFIFOs.

```
       Host DMA Ingress
     (d[32] + descriptor[16])
              │
              ▼
   ┌─────────────────────┐
   │ Worker W0 (Tile 0,2)│  dr2d_kpke_keygen_seed_noise
   │  - Validate ingress │  - Derive G(d || 2) -> (rho, sigma)
   │  - SHAKE256 PRF     │  - Derive s_hat[0..1], e_hat[0..1] via CBD3 + NTT
   └──────────┬──────────┘
              │ dr2d_secret_token (2,096 B)
              ▼
   ┌─────────────────────┐
   │ Worker W1 (Tile 0,3)│  dr2d_kpke_keygen_row0_expand
   │  - Matrix expansion │  - Expand A[0,0] & A[0,1] via SampleNTT
   └──────────┬──────────┘
              │ dr2d_row0_matrix (3,120 B)
              ▼
   ┌─────────────────────┐
   │ Worker W2 (Tile 1,2)│  dr2d_kpke_keygen_row0_accumulate
   │  - Row-0 product    │  - t_hat[0] = e_hat[0] + A[0,0]*s_hat[0] + A[0,1]*s_hat[1]
   └──────────┬──────────┘
              │ dr2d_row_state (2,096 B)
              ▼
   ┌─────────────────────┐
   │ Worker W3 (Tile 1,3)│  dr2d_kpke_keygen_row1_expand
   │  - Matrix expansion │  - Expand A[1,0] & A[1,1] via SampleNTT
   └──────────┬──────────┘
              │ dr2d_row1_matrix (3,120 B)
              ▼
   ┌─────────────────────┐
   │ Worker W4 (Tile 2,2)│  dr2d_kpke_keygen_row1_accumulate
   │  - Row-1 product    │  - t_hat[1] = e_hat[1] + A[1,0]*s_hat[0] + A[1,1]*s_hat[1]
   └──────────┬──────────┘
              │ dr2d_final_token (2,112 B)
              ▼
   ┌─────────────────────┐
   │ Worker W5 (Tile 2,3)│  dr2d_kpke_keygen_serialize
   │  - Serialization    │  - ByteEncode12(t_hat), ByteEncode12(s_hat), append rho
   │  - Terminal commit  │  - Commit CRC32, lengths, status, and magic
   └──────────┬──────────┘
              │
              ▼
       Host DMA Egress
    (result[1588] = header[20] || ekPKE[800] || dkPKE[768])
```

---

## 3. Investigation, Root Cause, and Resolution

### 3.1 Initial Symptom
When DR2d was compiled and dispatched to the Phoenix NPU, the suffix `rho` matched 100% bit-exact, while `ekPKE` and `dkPKE` diverged from byte zero.

### 3.2 Subroutine-Level Silicon Isolation
To find the exact source of divergence:
1. **Mathematical Validation**: Every individual function (`keccak_f1600`, `derive_g`, `shake256_prf_192`, `cbd3`, `ntt`) was isolated on physical hardware and proved 100% bit-exact against FIPS 203.
2. **Memory Map & Stack Frame Interaction**:
   - In AIE2 architecture, Tile (0, 2) local memory consists of 4 16KB banks (`0x70000..0x7FFFF`).
   - The original monolithic Worker W0 declared large local buffers across multiple nonces (`state[200]`, `prf[192]`, `coefficients[256]` $\times 2$), swelling the stack frame to `0xa20` (2,592 bytes).
   - Peano compiler register allocation under this stack pressure emitted post-increment pointer adjustments on `p2` during byte-level memory operations, mutating the base token pointer across nonces and causing misaligned 32-bit word stores.

### 3.3 The Permanent Fix
1. **Modular Sub-Pipeline (`sample_one_nonce`)**: Refactored noise polynomial sampling into a cleanly scoped helper function that reuses a single, small stack frame (`<512B`).
2. **Deterministic 32-Bit Word Alignment**: Replaced all byte-clearing loops on token headers with direct 32-bit little-endian word stores (`store_le32` and `store_pair_word`).

```cpp
static void sample_one_nonce(const uint8_t sigma[32], uint8_t nonce, uint8_t *out) {
  uint8_t prf[192];
  uint32_t coeff[kN];
  shake256_prf_192(sigma, nonce, prf);
  cbd3(prf, coeff);
  ntt(coeff);
  for (uint32_t pair = 0; pair < kN / 2; ++pair) {
    store_pair_word(out, pair, coeff[2 * pair], coeff[2 * pair + 1]);
  }
}
```

---

## 4. Full Physical Silicon Verification Record

### 4.1 ACVP Corpus Validation (25/25)
Running `python tests/pqc_device_resident/test_dr2d_mlkem512_kpke_keygen_silicon.py`:
- All 25 vectors verified against NIST ACVP expected outputs.
- EK SHA-256 and DK SHA-256 match 100% bit-exact on physical hardware.

### 4.2 DR Milestone Summary
- **DR0 (ML-DSA Ring Product)**: 100% Silicon PASS
- **DR1 (ML-DSA-44 ExpandA / RejNTT)**: 100% Silicon PASS
- **DR2a (ML-KEM-512 SampleNTT)**: 100% Silicon PASS (13/13)
- **DR2b (ML-KEM-512 Noise CBD3 + NTT)**: 100% Silicon PASS (13/13)
- **DR2c (ML-KEM-512 KeyGen Row Accumulate)**: 100% Silicon PASS (11/11)
- **DR2d (Complete ML-KEM-512 K-PKE.KeyGen)**: 100% Silicon PASS (25/25)
- **Master Regression Suite (`run_all_silicon_tests.py`)**: 34/34 Milestones PASS (100%)
