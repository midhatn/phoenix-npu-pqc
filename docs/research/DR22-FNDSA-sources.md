# Research Ledger: DR22 FN-DSA (FALCON) Parameter Sizing, Ring Arithmetic, and Silicon Architecture

## Metadata
- **Task ID**: `DR22-FNDSA-PIPELINE`
- **Deliverable**: DR22 (FN-DSA KeyGen, Sign, Verify)
- **Author**: Autonomous Engineering Agent (Gemini)
- **Date**: 2026-09-01T06:14:00Z
- **Status**: IMPLEMENTATION (Milestone DR22)

---

## 1. Governing Standards & Normative References

### Primary Specification
- **Title**: FIPS 206 (Draft / Initial Public Draft): Fast-Fourier Lattice-Based Digital Signature Standard (FN-DSA)
- **Issuing Organization**: National Institute of Standards and Technology (NIST)
- **Official Specification Baseline**: Falcon: Fast-Fourier Lattice-based Compact Signatures over NTRU (NIST Post-Quantum Cryptography Standardization Project)
- **Official URL**: https://csrc.nist.gov/pubs/fips/206/ipd / https://falcon-sign.info/falcon.pdf
- **Relevant Parameters**:
  - Degree: $n = 512$ (`FN-DSA-512`), $n = 1024$ (`FN-DSA-1024`).
  - Ring Modulus: $q = 12289$.
  - Polynomial quotient ring: $\mathcal{R}_q = \mathbb{Z}_q[x] / (x^n + 1)$.
  - Salt length: $r \in \{0, 1\}^{320}$ (40 bytes).
  - Public Key: $h \in \mathcal{R}_q$ encoded with 14-bit coefficients:
    - `FN-DSA-512`: $896\text{ bytes}$ ($512 \times 14 / 8$). Header byte + payload = $897\text{ bytes}$.
    - `FN-DSA-1024`: $1792\text{ bytes}$ ($1024 \times 14 / 8$). Header byte + payload = $1793\text{ bytes}$.
  - Signature Format:
    - 1-byte header: `0x30 + log_n` (`0x39` for $n=512$, `0x3a` for $n=1024$).
    - 40-byte salt $r$.
    - Variable-length compressed encoding of polynomial $s_2$.
    - Bound $\beta^2$: $\beta_{512}^2 = 34034726$, $\beta_{1024}^2 = 70265242$.

---

## 2. Microarchitecture & Algorithmic Design for AMD Phoenix AIE2

1. **HashToPoint via SHAKE-256**:
   - `HashToPoint(r || msg, n, q)`:
     - Squeeze SHAKE-256 stream initialized with $r \parallel \text{msg}$.
     - Squeeze 2 bytes at a time, interpret as 16-bit integer $w = b_0 | (b_1 \ll 8)$.
     - Rejection sampling: if $w < 61445$ (where $61445 = 5 \times 12289$), $c_i = w \pmod{12289}$.
     - Squeeze until all $n$ coefficients of $c(x)$ are sampled.
2. **NTT and Polynomial Multiplication over $\mathbb{Z}_{12289}[x] / (x^n + 1)$**:
   - Modulus $q = 12289$ is prime, with $q \equiv 1 \pmod{2048}$.
   - Primitive 2048-th root of unity modulo 12289 is $\omega = 7$.
   - AIE2 vector units natively support fast Montgomery modular multiplication mod 12289 using 32-bit registers.
3. **Signature Verification**:
   - Decode signature $s_2 \in \mathcal{R}$.
   - Compute $s_1 = c - s_2 \cdot h \pmod q$, centered into $[-q/2, q/2]$.
   - Compute squared Euclidean norm:
     $$\|(s_1, s_2)\|^2 = \sum_{i=0}^{n-1} s_{1,i}^2 + \sum_{i=0}^{n-1} s_{2,i}^2$$
   - Verification accepts if and only if $\|(s_1, s_2)\|^2 \le \beta^2$ and all decoding/rejection bounds hold.

---

## 3. Evidence & Provenance Classification

- **Test Harness**: `tests/pqc_device_resident/test_dr22_fndsa_silicon.py`
- **Execution Boundary**: `[ON-TILE SILICON]`
- **Evidence Class**: `BIT_EXACT_PHYSICAL_SILICON`
