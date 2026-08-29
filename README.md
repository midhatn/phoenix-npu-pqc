# 100% On-Device Post-Quantum Cryptography on AMD Phoenix NPU (AIE2 / XDNA1)

<div align="center">

![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)
![Target: AMD Phoenix NPU1](https://img.shields.io/badge/Target-AMD%20Ryzen%20AI%20NPU1%20(AIE2)-blue)
![Research: Post-Quantum Cryptography](https://img.shields.io/badge/Research-Post--Quantum%20Cryptography-8a2be2)
![Standards: FIPS 202/203/204](https://img.shields.io/badge/Standards-FIPS%20202%20%2F%20203%20%2F%20204-005ea8)
![Status: 100% PQC Silicon Certified (736/736 PASS across 19 Gates)](https://img.shields.io/badge/Status-100%25%20PQC%20Silicon%20Certified%20%C2%B7%20736%2F736%20PASS-brightgreen)
[![CI](https://github.com/midhatn/phoenix-npu-pqc/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/midhatn/phoenix-npu-pqc/actions/workflows/ci.yml)

**World's first 100% device-resident hardware implementation of the finalized NIST Post-Quantum Cryptography standards on the AMD Phoenix NPU (AIE2 / XDNA1 Architecture).**

</div>

---

## 1. Abstract & Executive Overview

Modern post-quantum cryptography (PQC) standards—such as **ML-KEM (FIPS 203)**, **ML-DSA (FIPS 204)**, and **SHA-3/SHAKE (FIPS 202)**—introduce substantial computational demands and memory footprints, requiring thousands of modular arithmetic operations, high-dimensional lattice matrix-vector multiplications, Number Theoretic Transforms (NTT), and continuous Keccak permutations.

This repository establishes the first complete, **100% device-resident** PQC engine running entirely on the **AMD Phoenix Neural Processing Unit (NPU)** powered by the **XDNA1 / AIE2 (AI Engine-ML)** tiled architecture. 

### Core Architectural Guarantees
- **Zero Host Cryptographic Fallback**: Every cryptographic transformation—including SHA-3/SHAKE hashing, Keccak-f[1600] permutations, Montgomery arithmetic, NTT/INTT butterfly networks, Centered Binomial Noise Sampling (CBD), rejection sampling loops, Hint generation/verification, and hardware CRC32 checksums—executes natively on physical AIE2 silicon without host CPU intervention or repair.
- **Complete Standards Coverage**: Fully implements all finalized NIST PQC standards across all security categories:
  - **NIST FIPS 202**: SHA3-224, SHA3-256, SHA3-384, SHA3-512, SHAKE128, SHAKE256 (Streaming arbitrary-length absorb/squeeze).
  - **NIST FIPS 203 (ML-KEM / Kyber)**: Security Categories 1, 3, 5 (**ML-KEM-512, ML-KEM-768, ML-KEM-1024**) across `KeyGen`, `Encaps`, and `Decaps` with constant-time implicit rejection.
  - **NIST FIPS 204 (ML-DSA / Dilithium)**: Security Categories 2, 3, 5 (**ML-DSA-44, ML-DSA-65, ML-DSA-87**) across `KeyGen`, `Sign` (deterministic & randomized), and `Verify`.
- **Strict Microarchitectural Compliance**:
  - Instruction `.text` memory budget: strictly **< 16 KiB** per AIE2 worker tile.
  - Local tile RAM budget: strictly **< 64 KiB** per worker tile.
  - Inter-tile communication: zero-copy point-to-point **ObjectFIFOs** mapped over hardware DMAs.

---

## 2. Universal Silicon Validation Evidence Matrix

The universal master silicon test suite ([`tests/pqc_device_resident/test_all_silicon_gates.py`](tests/pqc_device_resident/test_all_silicon_gates.py)) validates all 19 gates directly on physical AMD Phoenix AIE2 silicon (Ryzen 7 7840HS / Ryzen 9 7940HS):

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

## 3. Mathematical Foundations & Microarchitecture

### 3.1 Ring Polynomials & Moduli
All lattice operations are evaluated in the cyclotomic polynomial ring $\mathcal{R}_q = \mathbb{Z}_q[X]/(X^n + 1)$ with $n = 256$:
- **NIST FIPS 203 (ML-KEM)**: $q = 3329 = 13 \cdot 256 + 1$, primitive $256$-th root of unity $\zeta = 17$.
- **NIST FIPS 204 (ML-DSA)**: $q = 8380417 = 2^{23} - 2^{13} + 1$, primitive $512$-th root of unity $\zeta = 1753$.

### 3.2 Number Theoretic Transform (NTT) & Inverse NTT (INTT)
The NTT transforms polynomial convolution from $\mathcal{O}(n^2)$ into $\mathcal{O}(n \log n)$ pointwise multiplications:
$$\widehat{a}_j = \sum_{i=0}^{n-1} a_i \zeta^{(2 \cdot \text{bitrev}(j) + 1) \cdot i} \pmod q$$
Pointwise base multiplication in the NTT domain:
$$\widehat{c} = \widehat{a} \circ \widehat{b} \pmod q$$
The Inverse NTT (INTT) recovers standard polynomial coefficients:
$$a_i = n^{-1} \sum_{j=0}^{n-1} \widehat{a}_j \zeta^{-(2 \cdot \text{bitrev}(j) + 1) \cdot i} \pmod q$$

### 3.3 Centered Binomial Distribution (CBD)
For noise sampling in ML-KEM ($\ eta \in \{2, 3\}$):
$$\text{CBD}_\eta(b_0, \dots, b_{2\eta-1}) = \sum_{i=0}^{\eta-1} b_i - \sum_{i=0}^{\eta-1} b_{\eta+i}$$

### 3.4 NIST FIPS 202 Keccak-p[1600, 24] Permutation
The state array $\mathbf{A} \in \mathbb{F}_2^{5 \times 5 \times 64}$ is processed across 24 rounds:
1. $\theta$ (Column parity mixing): $A[x, y, z] \leftarrow A[x, y, z] \oplus \sum_{y'=0}^4 A[x-1, y', z] \oplus \sum_{y'=0}^4 A[x+1, y', z]$
2. $\rho$ (Bit lane rotation): $A[x, y, z] \leftarrow A[x, y, z - r[x, y]]$
3. $\pi$ (Lane permutation): $A[y, (2x + 3y) \bmod 5] \leftarrow A[x, y]$
4. $\chi$ (Non-linear row mapping): $A[x, y] \leftarrow A[x, y] \oplus (\neg A[x+1, y] \wedge A[x+2, y])$
5. $\iota$ (Round constant addition): $A[0, 0] \leftarrow A[0, 0] \oplus RC[i_r]$

---

## 4. Hardware Pipeline Topology & Memory Layout

Each cryptographic operation is mapped across a dedicated dataflow pipeline of AIE2 worker tiles:

```
                      AMD PHOENIX NPU AIE2 TILE ARRAY (XDNA1)
    ┌────────────────────────────────────────────────────────────────────────┐
    │                                                                        │
    │   [Worker 0: Ingress/Noise] ──Token 0──► [Worker 1: Matrix Rows 0-3]   │
    │              │                                        │                │
    │          (14 KiB RAM)                            (44 KiB RAM)          │
    │              │                                        │                │
    │              │                                     Token 1             │
    │              │                                        │                │
    │              ▼                                        ▼                │
    │   [Worker 3: Pack/Sealing]  ◄──Token 2── [Worker 2: Matrix Rows 4-7]   │
    │              │                                                         │
    │         (48 KiB RAM)                                                   │
    │              │                                                         │
    └──────────────┼─────────────────────────────────────────────────────────┘
                   ▼
         [Sealed Result Envelope] (Hardware CRC32 + Status Verified)
```

---

## 5. Formal Academic & Technical References

```bibtex
@standard{fips202_2024,
  title={{FIPS PUB 202: SHA-3 Standard: Permutation-Based Hash and Extendable-Output Functions}},
  institution={{National Institute of Standards and Technology (NIST)}},
  year={2015},
  doi={10.6028/NIST.FIPS.202}
}

@standard{fips203_2024,
  title={{FIPS PUB 203: Module-Lattice-Based Key-Encapsulation Mechanism Standard}},
  institution={{National Institute of Standards and Technology (NIST)}},
  year={2024},
  doi={10.6028/NIST.FIPS.203}
}

@standard{fips204_2024,
  title={{FIPS PUB 204: Module-Lattice-Based Digital Signature Standard}},
  institution={{National Institute of Standards and Technology (NIST)}},
  year={2024},
  doi={10.6028/NIST.FIPS.204}
}

@standard{fips205_2024,
  title={{FIPS PUB 205: Stateless Hash-Based Digital Signature Standard}},
  institution={{National Institute of Standards and Technology (NIST)}},
  year={2024},
  doi={10.6028/NIST.FIPS.205}
}

@article{kyber_crystals,
  title={{CRYSTALS-Kyber: A CCA-Secure Module-Lattice-Based KEM}},
  author={Bos, Joppe and Ducas, L{'e}o and Kiltz, Eike and Lepoint, Tancr{\`e}de and Lyubashevsky, Vadim and Schanck, John M. and Schwabe, Peter and Seiler, Gregor and Stehl{'e}, Damien},
  journal={IEEE European Symposium on Security and Privacy (EuroS\&P)},
  year={2018},
  doi={10.1109/EuroSP.2018.00032}
}

@article{dilithium_crystals,
  title={{CRYSTALS-Dilithium: A Lattice-Based Digital Signature Scheme}},
  author={Ducas, L{'e}o and Kiltz, Eike and Lepoint, Tancr{\`e}de and Lyubashevsky, Vadim and Schwabe, Peter and Seiler, Gregor and Stehl{'e}, Damien},
  journal={IACR Transactions on Cryptographic Hardware and Embedded Systems (TCHES)},
  year={2018},
  doi={10.13154/tches.v2018.i1.238-268}
}

@manual{amd_aie_ml_ug1603,
  title={{AI Engine-ML (AIE-ML) Architecture Manual (UG1603)}},
  author={{Advanced Micro Devices, Inc. (AMD)}},
  year={2023},
  url={https://docs.amd.com/r/en-US/ug1603-aie-ml-architecture}
}
```

---

## 6. How to Reproduce on Physical Hardware

### System Prerequisites
- **APU**: AMD Ryzen 7 7840HS, Ryzen 9 7940HS, Ryzen 7 8845HS, or Ryzen 9 8945HS with XDNA1 NPU.
- **Operating System**: Windows 11 (build 22621+) with AMD NPU driver `10.1109.8.100`+.
- **Software Toolchain**: MLIR-AIE 1.4.1, Peano LLVM-AIE Compiler, XRT 2.20.0+.

### Execution Commands
```powershell
# 1. Clean clone and one-command native setup
git clone https://github.com/midhatn/phoenix-npu-pqc.git
cd phoenix-npu-pqc
py .\install

# 2. Run the Universal Master Silicon Validation Suite (All 19 Gates)
& "C:\phoenix-sdr-dsp\third_party\mlir-aie\ironenv\Scripts\python.exe" tests/pqc_device_resident/test_all_silicon_gates.py

# 3. Alternatively, execute the canonical regression suite
& "C:\phoenix-sdr-dsp\third_party\mlir-aie\ironenv\Scripts\python.exe" run_all_silicon_tests.py
```

---

## 7. License

Licensed under the Apache License, Version 2.0. See [LICENSE](LICENSE) for details.
