# Comprehensive PQC Citation and Mathematical Provenance Audit

> [!NOTE]
> <!-- [CLAIM-PROVENANCE: status=HISTORICAL; source=pqc_citation_audit_v1; classification=SELF_REPORTED_UNVERIFIED] -->
> [HISTORICAL CLAIM - UNVERIFIED / PENDING PHYSICAL DISPATCH CORROBORATION]
> Legacy metrics reflect pre-refactor self-reported baseline scope across 19 gates and 736 test cases.

**Historical Scope**: 19 Gates Evaluated across 736 Test Cases
**Date**: August 29, 2026
**Target Hardware**: AMD Phoenix APU (Ryzen 7 7840HS / Ryzen 9 7940HS w/ XDNA1 NPU / AIE2 Architecture)

---

## 1. Executive Summary

This document establishes the publication-grade scientific, algorithmic, and microarchitectural citation ledger for the **Phoenix NPU PQC** repository (`phoenix-npu-pqc`). Every implemented mathematical formula, number-theoretic primitive, modular reduction technique, cryptographic standard, microarchitectural constraint, and test vector corpus is bound to its formal specification and primary-source literature.

---

## 2. Standards & Specification Citations

| Identifier | Full Title | Organization / Year | Canonical DOI / URL | Role in Repository |
| :--- | :--- | :--- | :--- | :--- |
| **FIPS 202** | *SHA-3 Standard: Permutation-Based Hash and Extendable-Output Functions* | NIST (2015) | [DOI: 10.6028/NIST.FIPS.202](https://doi.org/10.6028/NIST.FIPS.202) | Keccak-f[1600], SHA3-224/256/384/512, SHAKE128/256 |
| **FIPS 203** | *Module-Lattice-Based Key-Encapsulation Mechanism Standard (ML-KEM)* | NIST (2024) | [DOI: 10.6028/NIST.FIPS.203](https://doi.org/10.6028/NIST.FIPS.203) | ML-KEM-512, ML-KEM-768, ML-KEM-1024 parameter sets, KeyGen, Encaps, Decaps |
| **FIPS 204** | *Module-Lattice-Based Digital Signature Standard (ML-DSA)* | NIST (2024) | [DOI: 10.6028/NIST.FIPS.204](https://doi.org/10.6028/NIST.FIPS.204) | ML-DSA-44, ML-DSA-65, ML-DSA-87 parameter sets, KeyGen, Sign, Verify |
| **NIST SP 800-185** | *SHA-3 Derived Functions: cSHAKE, KMAC, TupleHash, ParallelHash* | NIST (2016) | [DOI: 10.6028/NIST.SP.800-185](https://doi.org/10.6028/NIST.SP.800-185) | Domain separation and customizable extendable output functions |

---

## 3. Mathematical Foundations & Microarchitecture

### 3.1 Ring Polynomials & Moduli
The lattice operations operate in the quotient ring $\mathcal{R}_q = \mathbb{Z}_q[X]/(X^n + 1)$ with $n = 256$:
- **ML-KEM (FIPS 203)**:
  - Modulus: $q = 3329 = 13 \cdot 256 + 1$.
  - Twiddle factors: $\zeta = 17$ (primitive 256-th root of unity).
  - Matrix dimensions $k \in \{2, 3, 4\}$ corresponding to ML-KEM-512, 768, 1024.
- **ML-DSA (FIPS 204)**:
  - Modulus: $q = 8380417 = 2^{23} - 2^{13} + 1$.
  - Twiddle factors: $\zeta = 1753$ (primitive 512-th root of unity).
  - Matrix dimensions $(k, l) \in \{(4, 4), (6, 5), (8, 7)\}$ corresponding to ML-DSA-44, 65, 87.

### 3.2 Number-Theoretic Transforms (NTT / INTT)
* **Cooley-Tukey Radix-2 Forward NTT**:

$$
\widehat{a}_j = \sum_{i=0}^{n-1} a_i \zeta^{(2 \cdot \text{bitrev}(j) + 1) \cdot i} \pmod q
$$

  * *Citation*: Cooley, J. W., & Tukey, J. W. (1965). *An algorithm for the machine calculation of complex Fourier series*. *Mathematics of Computation*, 19(90), 297–301. [DOI: 10.1090/S0025-5718-1965-0178586-1](https://doi.org/10.1090/S0025-5718-1965-0178586-1).
* **Gentleman-Sande Inverse NTT (INTT)**:

$$
a_i = n^{-1} \sum_{j=0}^{n-1} \widehat{a}_j \zeta^{-(2 \cdot \text{bitrev}(j) + 1) \cdot i} \pmod q
$$

  * *Citation*: Gentleman, W. M., & Sande, G. (1966). *Fast Fourier Transforms—for fun and profit*. *AFIPS '66*, pp. 563–578. [DOI: 10.1145/1464291.1464352](https://doi.org/10.1145/1464291.1464352).

### 3.3 Montgomery Modular Arithmetic
All modular arithmetic on AIE2 uses Montgomery reduction ($R = 2^{32} \pmod q$ for 32-bit operations, $R = 2^{16} \pmod q$ for 16-bit operations):

$$
\text{MontReduce}(T) = (T - (T \cdot q^{-1} \bmod R) \cdot q) / R
$$

where $q^{-1} \equiv 62209 \pmod{2^{16}}$ for 16-bit ML-KEM arithmetic ($q^{-1} \equiv 1806234369 \pmod{2^{32}}$ for 32-bit representation) and $q^{-1} \equiv 58728449 \pmod{2^{32}}$ for ML-DSA ($q \cdot q^{-1} \equiv 1 \pmod R$).
* *Citation*: Montgomery, P. L. (1985). *Modular multiplication without trial division*. *Mathematics of Computation*, 44(170), 519–521. [DOI: 10.1090/S0025-5718-1985-0777282-X](https://doi.org/10.1090/S0025-5718-1985-0777282-X).

### 3.4 Barrett Compression & Polynomial Reductions

* *Citation*: Barrett, P. (1986). *Implementing the Rivest Shamir and Adleman Public Key Encryption Algorithm on a Standard Digital Signal Processor*. *CRYPTO '86*, LNCS 263, pp. 311–323. [DOI: 10.1007/3-540-47721-7_24](https://doi.org/10.1007/3-540-47721-7_24).
* **Exact Linear Closed-Form Compressions (AIE2 Invariant)**:

$$
\text{Compress}_4(x) = \left\lfloor \frac{x \cdot 315 + 32701}{2^{16}} \right\rfloor \land \text{0x0F} \equiv \left\lfloor \frac{x \cdot 16 + 1664}{3329} \right\rfloor \bmod 16
$$

$$
\text{Compress}_{10}(x) = \left\lfloor \frac{x \cdot 161271 + 261911}{2^{19}} \right\rfloor \land \text{0x3FF} \equiv \left\lfloor \frac{x \cdot 1024 + 1664}{3329} \right\rfloor \bmod 1024
$$

---

## 4. Hardware Platform & Toolchain Provenance

| Component | Entity / Model | Version / Commit | Specification URL |
| :--- | :--- | :--- | :--- |
| **AMD Phoenix APU** | AMD Ryzen 7 7840HS / Ryzen 9 7940HS | Family 19h Model 74h | [AMD Ryzen AI](https://www.amd.com/en/products/processors/laptop/ryzen/7000-series.html) |
| **NPU Tile Array** | AMD XDNA1 / AIE2 (4 rows $\times$ 5 cols) | IPU 1.0 | [Linux Kernel amdxdna](https://docs.kernel.org/accel/amdxdna/amdnpu.html) |
| **MLIR-AIE** | AMD / Xilinx open-source compiler | Release 1.4.1 / Commit `3ca0193` | [GitHub: Xilinx/mlir-aie](https://github.com/Xilinx/mlir-aie) |
| **Peano LLVM-AIE** | AMD AIE2 Clang/LLVM backend | Clang 18.0.0 (`aie2-none-unknown-elf`) | [GitHub: Xilinx/llvm-aie](https://github.com/Xilinx/llvm-aie) |
| **AMD XRT** | Xilinx Runtime driver & library | Version 2.20.0 / 2.21.75 | [GitHub: Xilinx/XRT](https://github.com/Xilinx/XRT) |

---

## 5. Physical Silicon Evidence Summary (Historical Baseline Scope)

> [!NOTE]
> [HISTORICAL CLAIM - UNVERIFIED / PENDING PHYSICAL DISPATCH CORROBORATION]
> Legacy test totals below represent pre-refactor self-reported metrics. Under current Phase A zero-speculation policy, all 19 active gates are tracked with 0 independently physically verified gates pending driver-level dispatch trace corroboration.

1. **NIST FIPS 202 (DR9)**: 122 test cases (SHA3-224/256/384/512, SHAKE128/256) tracked.
2. **NIST FIPS 203 (DR2d, DR3–DR8)**: 225 test cases (ML-KEM-512, 768, 1024 KeyGen/Encaps/Decaps) tracked.
3. **NIST FIPS 204 (DR11–DR15)**: 255 test cases (ML-DSA-44, 65, 87 KeyGen/Sign/Verify) tracked.
4. **Hardware Primitives & Lifecycle (DR0–DR2c, DR10)**: 134 test cases tracked.
5. **Universal Silicon Total**: 736 test cases tracked across legacy core gate set (122 + 225 + 255 + 134 = 736).
