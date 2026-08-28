# DR11: Complete NIST FIPS 204 ML-DSA-44 Key Generation Design Document

## 1. Executive Summary & Architectural Scope

**Milestone Identifier**: `DR11`  
**Standard**: NIST FIPS 204 (Module-Lattice-Based Digital Signature Standard, ML-DSA)  
**Security Level**: NIST Category 2 (ML-DSA-44, k=4, l=4, eta=2)  
**Target Silicon**: AMD Phoenix NPU (Ryzen 7040/8040 Series, XDNA1 / AIE2 VLIW Matrix Processor)  
**Toolchain**: MLIR-AIE 1.4.1 / IRON Python JIT / Peano Clang 21 / XRT Runtime  
**Residency Guarantee**: **100% On-Device Device-Resident Silicon Execution**. Zero host CPU cryptographic helper routines, zero host modular arithmetic fallback, zero host key exposure.

DR11 realizes the complete end-to-end device-resident Key Generation algorithm (ML-DSA.KeyGen) of FIPS 204 directly inside AMD Phoenix AIE2 tiles. Ingesting a 32-byte master seed xi, the 6-worker AIE2 dataflow pipeline generates the complete FIPS 204 public key pk (1312 B) and private key sk (2560 B) in sealed on-device memory, verifies structural validity, seals output with hardware-computed CRC32, and clears all intermediate sensitive states.

---

## 2. Mathematical Formalization & FIPS 204 Specifications

For ML-DSA-44:
- Ring: R_q = Z_q[X] / (X^256 + 1) with modulus q = 8380417 = 2^23 - 2^13 + 1.
- Matrix dimension: k x l = 4 x 4.
- Secret noise parameter: eta = 2.
- Power-of-two rounding divisor: 2^d = 2^13 = 8192.
- Twiddle factors: omega = 1756 (primitive 512-th root of unity modulo q).

### Algorithm Flow (FIPS 204, Algorithm 6: ML-DSA.KeyGen):
1. **Seed Expansion**:
   rho || sigma || K = SHAKE256(xi || bytes([4, 4]), 128)
   - rho: 32 bytes (public seed for matrix A)
   - sigma: 64 bytes (private seed for noise vectors s1, s2)
   - K: 32 bytes (private seed for deterministic signing)

2. **Secret Vector Sampling**:
   s1 <- SampleBounded(sigma, 0..3)
   s2 <- SampleBounded(sigma, 4..7)
   where SampleBounded(sigma, idx) = RejBoundedPoly(SHAKE256(sigma || idx, 136)) with eta=2.

3. **Forward Number Theoretic Transform**:
   s1_ntt = NTT(s1) in R_q^4

4. **Matrix Expansion & Vector-Matrix Inner Product**:
   For i = 0..3:
     A[i, j] = ExpandA(rho, j, i) in R_q (j = 0..3)
     w[i] = sum(A[i, j] * s1_ntt[j])
     w[i] = INTT(w[i])
     t[i] = w[i] + s2[i] mod q
     (t1[i], t0[i]) = Power2Round(t[i], 13)

5. **Public Key Assembly & Hashing**:
   pk = rho || pkEncode(t1) (1312 bytes)
   tr = SHAKE256(pk, 64) (64 bytes)

6. **Private Key Assembly**:
   sk = rho || K || tr || skEncode(s1, s2) || skEncode(t0) (2560 bytes)

---

## 3. Microarchitectural Dataflow & Pipeline Topography

```
                                      +---------------------------------------------+
                                      |            Host Ingress Ring                |
                                      |        (32-B Seed xi, 16-B Desc)            |
                                      +---------------------------------------------+
                                                             |
                                                             v (DMA Channel 0)
+---------------------------------------------------------------------------------------------------------------------------+
| Worker 0: dr11_mldsa44_keygen_noise                                                                                       |
|   - SHAKE256(xi || 0x04 || 0x04) -> rho (32B), sigma (64B), K (32B)                                                     |
|   - Sample s1[0..3] & s2[0..3] via SampleBounded(sigma, idx)                                                             |
|   - Forward Montgomery NTT on s1[0..3] -> s1_ntt[4][256]                                                                  |
|   - Bit-pack skEncode(s1, s2) -> 768 Bytes                                                                                |
|   - Emits Token 0 (9028 Bytes)                                                                                            |
+---------------------------------------------------------------------------------------------------------------------------+
                                                             | ObjectFIFO (Token 0: 9028 B)
                                                             v
+---------------------------------------------------------------------------------------------------------------------------+
| Worker 1: dr11_mldsa44_keygen_row0                                                                                        |
|   - Expand A[0, 0..3] via SHAKE128(rho || j || 0)                                                                         |
|   - Pointwise Montgomery Product: w0_ntt = sum(A[0, j] * s1_ntt[j])                                                       |
|   - Inverse Montgomery NTT: w0 = INTT(w0_ntt)                                                                             |
|   - Add noise: t0_poly = w0 + s2[0]                                                                                       |
|   - Power2Round(t0_poly) -> t1[0] (320 B), t0[0] (416 B)                                                                  |
|   - Emits Token 1 (8740 Bytes)                                                                                            |
+---------------------------------------------------------------------------------------------------------------------------+
                                                             | ObjectFIFO (Token 1: 8740 B)
                                                             v
+---------------------------------------------------------------------------------------------------------------------------+
| Worker 2: dr11_mldsa44_keygen_row1                                                                                        |
|   - Expand A[1, 0..3] via SHAKE128(rho || j || 1)                                                                         |
|   - w1_ntt = sum(A[1, j] * s1_ntt[j]) -> INTT -> w1 + s2[1] -> Power2Round -> t1[1], t0[1]                                |
|   - Emits Token 2 (8452 Bytes)                                                                                            |
+---------------------------------------------------------------------------------------------------------------------------+
                                                             | ObjectFIFO (Token 2: 8452 B)
                                                             v
+---------------------------------------------------------------------------------------------------------------------------+
| Worker 3: dr11_mldsa44_keygen_row2                                                                                        |
|   - Expand A[2, 0..3] via SHAKE128(rho || j || 2)                                                                         |
|   - w2_ntt = sum(A[2, j] * s1_ntt[j]) -> INTT -> w2 + s2[2] -> Power2Round -> t1[2], t0[2]                                |
|   - Emits Token 3 (8164 Bytes)                                                                                            |
+---------------------------------------------------------------------------------------------------------------------------+
                                                             | ObjectFIFO (Token 3: 8164 B)
                                                             v
+---------------------------------------------------------------------------------------------------------------------------+
| Worker 4: dr11_mldsa44_keygen_row3                                                                                        |
|   - Expand A[3, 0..3] via SHAKE128(rho || j || 3)                                                                         |
|   - w3_ntt = sum(A[3, j] * s1_ntt[j]) -> INTT -> w3 + s2[3] -> Power2Round -> t1[3], t0[3]                                |
|   - Drops s1_ntt & s2 (no longer required)                                                                                |
|   - Emits Token 4 (3780 Bytes)                                                                                            |
+---------------------------------------------------------------------------------------------------------------------------+
                                                             | ObjectFIFO (Token 4: 3780 B)
                                                             v
+---------------------------------------------------------------------------------------------------------------------------+
| Worker 5: dr11_mldsa44_keygen_finalize                                                                                    |
|   - Assemble pk = rho || t1[0..3] (1312 Bytes)                                                                            |
|   - Compute tr = SHAKE256(pk, 64 Bytes) using streaming sponge absorbing 1312 B                                          |
|   - Assemble sk = rho || K || tr || s_encoded || t0_encoded (2560 Bytes)                                                  |
|   - Append Sealed Header & Hardware-Computed CRC32                                                                        |
|   - Zeroizes all intermediate registers                                                                                   |
|   - Emits Sealed Result Record (3892 Bytes)                                                                               |
+---------------------------------------------------------------------------------------------------------------------------+
                                                             |
                                                             v (DMA Channel 1)
                                      +---------------------------------------------+
                                      |            Host Egress Ring                 |
                                      |       (3892-B Sealed Record)                |
                                      +---------------------------------------------+
```

---

## 4. Arithmetic & Instruction Engineering

### 4.1 Division-Free Montgomery Reduction
AIE2 lacks a 64-bit integer hardware divider. To prevent LLVM from emitting calls to __moddi3 / __udivmoddi4:
mont_reduce(a) = (a - (a * QINV mod 2^32) * Q) >> 32
with:
- Q = 8380417
- QINV = 58728449

### 4.2 Legalizer-Safe NTT Butterfly Loops
To prevent Peano Clang GlobalISel from crashing on unsupported G_CTTZ_ZERO_UNDEF instructions, the NTT and INTT loops utilize fixed stage bounds stage < 8 with bit-shift strides (128u >> stage and 1u << stage) and explicit #pragma clang loop unroll(disable).

---

## 5. Security & Zeroization Verification

1. **Host Boundary Isolation**: The host CPU only transmits the 32-byte seed xi. The secret noise polynomials s1, s2, the secret matrix products, the secret vector t0, and private keys never touch host memory until sealed output extraction.
2. **Intermediate Zeroization**: All scratchpad buffers (state, sigma, poly, tr) are unconditionally scrubbed using clear_bytes prior to worker function return.
3. **Dataflow Integrity**: Hardware-calculated CRC32 protects the (pk, sk) payload against transmission corruption.
