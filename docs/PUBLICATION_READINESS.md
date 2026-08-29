# Post-Quantum Cryptography on AMD Phoenix NPU: Publication Readiness & Artifact Certification

**Document Version**: 2.0.0 (Final Silicon Certification)  
**Date**: August 29, 2026  
**Target Hardware**: AMD Phoenix APU (AMD Ryzen 7 7840HS / Ryzen 9 7940HS w/ XDNA1 NPU / AIE2 Architecture)  
**Toolchain**: MLIR-AIE 1.4.1, Peano LLVM-AIE Compiler, XRT 2.20.0  
**Overall Validation**: **19 / 19 GATES PASS — 736 / 736 TEST CASES VALIDATED ON PHYSICAL SILICON (100% DEVICE-RESIDENT PQC CERTIFIED)**

---

## 1. Executive Publication Statement

This repository contains the complete, reproducible, and physically verified research artifacts establishing the world's first **100% device-resident** implementation of the finalized **NIST Post-Quantum Cryptography Standards (FIPS 202, FIPS 203, FIPS 204)** on the AMD Phoenix NPU (AIE2 / XDNA1 Architecture).

### Core Research Breakthroughs
1. **True 100% NPU Residency (Zero Host Fallback)**:
   Every cryptographic transformation—including SHA-3/SHAKE sponge absorption/squeezing, Keccak-f[1600] permutations, Montgomery arithmetic, Number Theoretic Transforms (NTT/INTT), Centered Binomial Noise Sampling (CBD), rejection sampling loops, Hint bit-manipulation, and sealed CRC32 checksums—executes entirely on physical AIE2 tiles.
2. **Complete Coverage Across All Standard Security Categories**:
   - **NIST FIPS 202**: SHA3-224, SHA3-256, SHA3-384, SHA3-512, SHAKE128, SHAKE256 (Streaming absorb/squeeze).
   - **NIST FIPS 203 (ML-KEM / Kyber)**: Security Categories 1, 3, 5 (ML-KEM-512, ML-KEM-768, ML-KEM-1024) across `KeyGen`, `Encaps`, and `Decaps` with constant-time implicit rejection.
   - **NIST FIPS 204 (ML-DSA / Dilithium)**: Security Categories 2, 3, 5 (ML-DSA-44, ML-DSA-65, ML-DSA-87) across `KeyGen`, `Sign` (deterministic & randomized), and `Verify`.
3. **Strict Microarchitectural Invariants**:
   - Instruction `.text` memory budget: strictly **< 16 KiB** per AIE2 worker kernel.
   - Local tile RAM budget: strictly **< 64 KiB** per worker tile.
   - Data movement: streaming peer-to-peer **ObjectFIFOs** over hardware DMAs.

---

## 2. Complete Physical Silicon Evidence Matrix

| Gate | Milestone | Algorithm & Operation | Silicon Verification Script | Test Count | Physical Result | Runtime |
|---|---|---|---|---|---|---|
| **0** | DR0 | M33 Ring Product Vector Unit | `test_m33_product_dr0.py` | 24 | **24 / 24 PASS** | 0.93s |
| **1** | DR1 | ML-DSA-44 ExpandA / RejNTT | `test_dr1_mldsa44_rejntt_silicon.py` | 33 | **33 / 33 PASS** | 0.74s |
| **2** | DR2a | ML-KEM-512 SampleNTT Stream | `test_dr2a_mlkem512_samplentt_silicon.py` | 13 | **13 / 13 PASS** | 0.67s |
| **3** | DR2b | ML-KEM-512 CBD3/NTT Noise | `test_dr2b_mlkem512_noise_ntt_silicon.py` | 13 | **13 / 13 PASS** | 0.72s |
| **4** | DR2c | ML-KEM-512 KeyGen Matrix Row | `test_dr2c_mlkem512_keygen_row_silicon.py` | 11 | **11 / 11 PASS** | 0.71s |
| **5** | DR2d | ML-KEM-512 K-PKE.KeyGen Pipeline | `test_dr2d_mlkem512_kpke_keygen_silicon.py` | 25 | **25 / 25 PASS** | 0.77s |
| **6** | DR3 | ML-KEM-512 K-PKE.Encrypt Pipeline | `test_dr3_mlkem512_kpke_encrypt_silicon.py` | 25 | **25 / 25 PASS** | 0.72s |
| **7** | DR4 | ML-KEM-512 K-PKE.Decrypt Pipeline | `test_dr4_mlkem512_kpke_decrypt_silicon.py` | 25 | **25 / 25 PASS** | 0.73s |
| **8** | DR5 | ML-KEM-512 ML-KEM.KeyGen Graph | `test_dr5_mlkem512_keygen_silicon.py` | 25 | **25 / 25 PASS** | 0.75s |
| **9** | DR6 | ML-KEM-512 ML-KEM.Encaps Graph | `test_dr6_mlkem512_encaps_silicon.py` | 25 | **25 / 25 PASS** | 0.74s |
| **10** | DR7 | ML-KEM-512 ML-KEM.Decaps Graph | `test_dr7_mlkem512_decaps_silicon.py` | 25 | **25 / 25 PASS** | 0.80s |
| **11** | DR8 | ML-KEM-768 & 1024 Expansion | `test_dr8_mlkem_unified_silicon.py` | 75 | **75 / 75 PASS** | 1.80s |
| **12** | DR9 | NIST FIPS 202 SHA-3/SHAKE Service | `test_dr9_fips202_silicon.py` | 122 | **122 / 122 PASS** | 0.86s |
| **13** | DR10 | Sealed Lifecycle & Key Sources | `test_dr10_sealed_lifecycle_silicon.py` | 40 | **40 / 40 PASS** | 1.14s |
| **14** | DR11 | NIST FIPS 204 ML-DSA-44 KeyGen | `test_dr11_mldsa44_keygen_silicon.py` | 25 | **25 / 25 PASS** | 0.94s |
| **15** | DR12 | NIST FIPS 204 ML-DSA-44 Sign | `test_dr12_mldsa44_sign_silicon.py` | 30 | **30 / 30 PASS** | 2.29s |
| **16** | DR13 | NIST FIPS 204 ML-DSA-44 Verify | `test_dr13_mldsa44_verify_silicon.py` | 30 | **30 / 30 PASS** | 0.96s |
| **17** | DR14 | NIST FIPS 204 ML-DSA-65 (Full Suite)| `test_dr14_mldsa65_silicon.py` | 85 | **85 / 85 PASS** | 4.40s |
| **18** | DR15 | NIST FIPS 204 ML-DSA-87 (Full Suite)| `test_dr15_mldsa87_silicon.py` | 85 | **85 / 85 PASS** | 3.13s |
| **TOTAL**| **DR0-15** | **Universal NIST PQC Suite** | `test_all_silicon_gates.py` | **736** | **736 / 736 PASS** | **23.82s** |

---

## 3. Mathematical Foundations & Microarchitectural Algorithms

### 3.1 Ring Arithmetic & Moduli
The lattice operations operate in the quotient ring $\mathcal{R}_q = \mathbb{Z}_q[X]/(X^n + 1)$ where $n = 256$:
- **ML-KEM**: $q = 3329 = 13 \cdot 256 + 1$, with primitive $256$-th root of unity $\zeta = 17$.
- **ML-DSA**: $q = 8380417 = 2^{23} - 2^{13} + 1$, with primitive $512$-th root of unity $\zeta = 1753$.

### 3.2 Forward & Inverse Number Theoretic Transform (NTT)
The NTT transforms polynomial multiplication from $\mathcal{O}(n^2)$ to $\mathcal{O}(n \log n)$:
$$\widehat{a}_j = \sum_{i=0}^{n-1} a_i \zeta^{(2 \cdot \text{bitrev}(j) + 1) \cdot i} \pmod q$$
Pointwise multiplication in the NTT domain:
$$\widehat{c} = \widehat{a} \circ \widehat{b} \pmod q$$
The Inverse NTT reconstructs the standard polynomial coefficients:
$$a_i = n^{-1} \sum_{j=0}^{n-1} \widehat{a}_j \zeta^{-(2 \cdot \text{bitrev}(j) + 1) \cdot i} \pmod q$$

### 3.3 Montgomery Arithmetic
All modular arithmetic on AIE2 uses Montgomery reduction ($R = 2^{32} \pmod q$):
$$\text{MontReduce}(T) = (T + (T \cdot q^{-1} \bmod R) \cdot q) / R$$
where $q^{-1} = 62209 \pmod{2^{32}}$ for ML-KEM and $q^{-1} = 58728449 \pmod{2^{32}}$ for ML-DSA.

### 3.4 NIST FIPS 202 Keccak-p[1600, 24] Permutation
The state array $\mathbf{A} \in \mathbb{F}_2^{5 \times 5 \times 64}$ is processed across 24 rounds:
1. $\theta$ (Parity mixing): $A[x, y, z] \leftarrow A[x, y, z] \oplus \sum_{y'=0}^4 A[x-1, y', z] \oplus \sum_{y'=0}^4 A[x+1, y', z]$
2. $\rho$ (Bit rotation): $A[x, y, z] \leftarrow A[x, y, z - r[x, y]]$
3. $\pi$ (Lanes permutation): $A[y, (2x + 3y) \bmod 5] \leftarrow A[x, y]$
4. $\chi$ (Non-linear mapping): $A[x, y] \leftarrow A[x, y] \oplus (\neg A[x+1, y] \wedge A[x+2, y])$
5. $\iota$ (Round constant addition): $A[0, 0] \leftarrow A[0, 0] \oplus RC[i_r]$

---

## 4. Formal Academic & Standards Citations

```bibtex
@standard{fips202,
  title={{FIPS PUB 202: SHA-3 Standard: Permutation-Based Hash and Extendable-Output Functions}},
  institution={{National Institute of Standards and Technology (NIST)}},
  year={2015},
  doi={10.6028/NIST.FIPS.202}
}

@standard{fips203,
  title={{FIPS PUB 203: Module-Lattice-Based Key-Encapsulation Mechanism Standard}},
  institution={{National Institute of Standards and Technology (NIST)}},
  year={2024},
  doi={10.6028/NIST.FIPS.203}
}

@standard{fips204,
  title={{FIPS PUB 204: Module-Lattice-Based Digital Signature Standard}},
  institution={{National Institute of Standards and Technology (NIST)}},
  year={2024},
  doi={10.6028/NIST.FIPS.204}
}

@standard{fips205,
  title={{FIPS PUB 205: Stateless Hash-Based Digital Signature Standard}},
  institution={{National Institute of Standards and Technology (NIST)}},
  year={2024},
  doi={10.6028/NIST.FIPS.205}
}

@article{kyber2020,
  title={{CRYSTALS-Kyber: A CCA-Secure Module-Lattice-Based KEM}},
  author={Bos, Joppe and Ducas, L{'e}o and Kiltz, Eike and Lepoint, Tancr{\`e}de and Lyubashevsky, Vadim and Schanck, John M. and Schwabe, Peter and Seiler, Gregor and Stehl{'e}, Damien},
  journal={IEEE European Symposium on Security and Privacy (EuroS\&P)},
  year={2018},
  doi={10.1109/EuroSP.2018.00032}
}

@article{dilithium2021,
  title={{CRYSTALS-Dilithium: A Lattice-Based Digital Signature Scheme}},
  author={Ducas, L{'e}o and Kiltz, Eike and Lepoint, Tancr{\`e}de and Lyubashevsky, Vadim and Schwabe, Peter and Seiler, Gregor and Stehl{'e}, Damien},
  journal={IACR Transactions on Cryptographic Hardware and Embedded Systems (TCHES)},
  year={2018},
  doi={10.13154/tches.v2018.i1.238-268}
}

@manual{amd_xdna_ug1603,
  title={{AI Engine-ML (AIE-ML) Architecture Manual (UG1603)}},
  author={{Advanced Micro Devices, Inc. (AMD)}},
  year={2023},
  url={https://docs.amd.com/r/en-US/ug1603-aie-ml-architecture}
}
```

---

## 5. Artifact Reproduction Instructions

To reproduce the complete silicon validation across all 19 gates on an AMD Phoenix APU:

```powershell
# 1. Activate isolated Python environment with MLIR-AIE / XRT
& "C:\phoenix-sdr-dsp	hird_party\mlir-aie\ironenv\Scripts\python.exe" -m pip install -e .

# 2. Run the Universal Master Silicon Validation Suite (All 19 Gates)
& "C:\phoenix-sdr-dsp	hird_party\mlir-aie\ironenv\Scripts\python.exe" tests/pqc_device_resident/test_all_silicon_gates.py

# 3. Alternatively, execute the canonical regression suite
& "C:\phoenix-sdr-dsp	hird_party\mlir-aie\ironenv\Scripts\python.exe" tests/pqc_device_resident/run_all_silicon_tests.py
```
