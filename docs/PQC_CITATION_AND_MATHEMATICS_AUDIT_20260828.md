# Comprehensive PQC Citation and Mathematical Provenance Audit (2026-08-28)

## 1. Executive Summary

This document establishes the publication-grade scientific, algorithmic, and microarchitectural citation ledger for the **Phoenix NPU PQC** repository (`phoenix-npu-pqc`). Every implemented mathematical formula, number-theoretic primitive, modular reduction technique, cryptographic standard, microarchitectural constraint, and test vector corpus is bound to its formal specification and primary-source literature.

---

## 2. Standards & Specification Citations

| Identifier | Full Title | Organization / Year | Canonical DOI / URL | Role in Repository |
| :--- | :--- | :--- | :--- | :--- |
| **FIPS 202** | *SHA-3 Standard: Permutation-Based Hash and Extendable-Output Functions* | NIST (2015) | [DOI: 10.6028/NIST.FIPS.202](https://doi.org/10.6028/NIST.FIPS.202) | Keccak-$f[1600]$, SHA3-256, SHA3-512, SHAKE128, SHAKE256 |
| **FIPS 203** | *Module-Lattice-Based Key-Encapsulation Mechanism Standard (ML-KEM)* | NIST (2024) | [DOI: 10.6028/NIST.FIPS.203](https://doi.org/10.6028/NIST.FIPS.203) | ML-KEM-512 parameter set, K-PKE.KeyGen, K-PKE.Encrypt, K-PKE.Decrypt |
| **FIPS 204** | *Module-Lattice-Based Digital Signature Standard (ML-DSA)* | NIST (2024) | [DOI: 10.6028/NIST.FIPS.204](https://doi.org/10.6028/NIST.FIPS.204) | ML-DSA-44 parameter set, ExpandA rejection sampling, NTT multiplication |
| **NIST SP 800-185** | *SHA-3 Derived Functions: cSHAKE, KMAC, TupleHash, ParallelHash* | NIST (2016) | [DOI: 10.6028/NIST.SP.800-185](https://doi.org/10.6028/NIST.SP.800-185) | Domain separation and customizable extendable output functions |

---

## 3. Foundational Algorithms & Primary Academic Literature

### 3.1 Number-Theoretic Transforms (NTT / INTT)
* **Cooley-Tukey Radix-2 Forward NTT**:
  $$X_k = \sum_{j=0}^{N-1} x_j \zeta^{j k} \pmod q$$
  * *Citation*: Cooley, J. W., & Tukey, J. W. (1965). *An algorithm for the machine calculation of complex Fourier series*. *Mathematics of Computation*, 19(90), 297–301. [DOI: 10.1090/S0025-5718-1965-0178586-1](https://doi.org/10.1090/S0025-5718-1965-0178586-1).
  * *Implementation*: 7 statically unrolled radix-2 butterfly stages on AIE2 vector/scalar registers with bit-reversed twiddle factors $\zeta \in \mathbb{Z}_{3329}$.
* **Gentleman-Sande Inverse NTT (INTT)**:
  $$x_j = N^{-1} \sum_{k=0}^{N-1} X_k \zeta^{-j k} \pmod q$$
  * *Citation*: Gentleman, W. M., & Sande, G. (1966). *Fast Fourier Transforms—for fun and profit*. *Proceedings of the November 7-10, 1966, Fall Joint Computer Conference (AFIPS '66)*, pp. 563–578. [DOI: 10.1145/1464291.1464352](https://doi.org/10.1145/1464291.1464352).
  * *Implementation*: In-place decimation-in-frequency structure scaled by $N^{-1} \equiv 3303 \pmod{3329}$.

### 3.2 Modular Reduction & Barrett Compression
* **Barrett Modular Reduction**:
  * *Citation*: Barrett, P. (1986). *Implementing the Rivest Shamir and Adleman Public Key Encryption Algorithm on a Standard Digital Signal Processor*. *Advances in Cryptology — CRYPTO '86*, LNCS 263, pp. 311–323. [DOI: 10.1007/3-540-47721-7_24](https://doi.org/10.1007/3-540-47721-7_24).
  * *Mathematical Derivation*: For modulus $q = 3329$ and product $P = a \cdot b < q^2$:
    $$P = \text{hi} \cdot 2^{16} + \text{lo}$$
    $$Y = \text{hi} \cdot 2285 + \text{lo} \equiv P \pmod{3329}$$
    $$q_{\text{est}} = \lfloor (Y \cdot 314) / 2^{20} \rfloor, \quad r = Y - q_{\text{est}} \cdot 3329$$
* **Exact 32-Bit Linear Closed-Form Compression (DR3 Microarchitectural Invariant)**:
  * *Problem*: Elimination of compiler TableGen immediate masking hazards (`0xfe81`) on AIE2.
  * *Formulae*:
    $$\text{Compress}_4(x) = \left\lfloor \frac{x \cdot 315 + 32701}{2^{16}} \right\rfloor \land \text{0x0F} \equiv \left\lfloor \frac{x \cdot 16 + 1664}{3329} \right\rfloor \bmod 16$$
    $$\text{Compress}_{10}(x) = \left\lfloor \frac{x \cdot 161271 + 261911}{2^{19}} \right\rfloor \land \text{0x3FF} \equiv \left\lfloor \frac{x \cdot 1024 + 1664}{3329} \right\rfloor \bmod 1024$$
  * *Exhaustive Proof*: Verified bit-exact for all $x \in [0, 3328]$ ($0$ mismatches across the entire domain).

### 3.3 Cryptographic Primitives & Schemes
* **CRYSTALS-Kyber / ML-KEM**:
  * *Citation*: Bos, J., Ducas, L., Kiltz, E., Lepoint, T., Lyubashevsky, V., Schanck, J. M., Schwabe, P., Seiler, G., & Stehlé, D. (2018). *CRYSTALS -- Kyber: A CCA-Secure Module-Lattice-Based KEM*. *IEEE European Symposium on Security and Privacy (EuroS&P 2018)*. [DOI: 10.1109/EuroSP.2018.00032](https://doi.org/10.1109/EuroSP.2018.00032).
* **CRYSTALS-Dilithium / ML-DSA**:
  * *Citation*: Ducas, L., Kiltz, E., Lepoint, T., Lyubashevsky, V., Schwabe, P., Seiler, G., & Stehlé, D. (2018). *CRYSTALS-Dilithium: A Lattice-Based Digital Signature Scheme*. *IACR Transactions on Cryptographic Hardware and Embedded Systems (TCHES)*, 2018(1), 238–268. [DOI: 10.13154/tches.v2018.i1.238-268](https://doi.org/10.13154/tches.v2018.i1.238-268).
* **Keccak Permutation Family**:
  * *Citation*: Bertoni, G., Daemen, J., Peeters, M., & Van Assche, G. (2011). *The Keccak Reference*. Submission to NIST SHA-3 Competition. [URL: https://keccak.team/files/Keccak-reference-3.0.pdf](https://keccak.team/files/Keccak-reference-3.0.pdf).

---

## 4. Hardware Platform & Toolchain Provenance

| Component | Entity / Repository | Version / Commit | Specification URL |
| :--- | :--- | :--- | :--- |
| **AMD Phoenix SoC** | AMD Ryzen 9 7940HS w/ Radeon 780M | Family 19h Model 74h | [AMD Ryzen AI](https://www.amd.com/en/products/processors/laptop/ryzen/7000-series.html) |
| **NPU Architecture** | AMD XDNA1 / AIE2 (4 rows $\times$ 5 cols) | IPU 1.0 | [Linux Kernel amdxdna Documentation](https://docs.kernel.org/accel/amdxdna/amdnpu.html) |
| **MLIR-AIE** | Xilinx / AMD open-source compiler | Commit `3ca0193` / Release 1.4.1 | [GitHub: Xilinx/mlir-aie](https://github.com/Xilinx/mlir-aie) |
| **LLVM-AIE (Peano)** | AMD AIE2 Clang/LLVM backend | Clang 18.0.0 (`aie2-none-unknown-elf`) | [GitHub: Xilinx/llvm-aie](https://github.com/Xilinx/llvm-aie) |
| **AMD XRT** | Xilinx Runtime driver & library | Version 2.21.75 | [GitHub: Xilinx/XRT](https://github.com/Xilinx/XRT) |

---

## 5. Physical Silicon Test Corpus & Vector Provenance

* **NIST ACVP ML-KEM-512 Test Vectors**:
  - Extracted from official NIST CAVP / ACVP JSON test vectors for FIPS 203.
  - Test suites:
    - `dr2d_nist_acvp_mlkem512_kpke_keygen_25.json`: 25 keygen vectors (Seed $\to$ Public Key, Private Key).
    - `dr3_nist_acvp_mlkem512_kpke_encrypt_25.json`: 25 encryption vectors ($ek, m, r \to c$).
* **Physical Exact-Output Validation Summary**:
  - 100% bit-exact across all 144 silicon test cases (DR0: 24, DR1: 33, DR2a: 13, DR2b: 13, DR2c: 11, DR2d: 25, DR3: 25).
