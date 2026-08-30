# DR25 Architecture & Design: Higher-Order Masked Polynomial Arithmetic & On-Chip Local PRNG Entropy Expansion on AMD Phoenix AIE2 Silicon

<div align="center">

![Security: Side-Channel Defense (DPA/CPA)](https://img.shields.io/badge/Security-Side--Channel%20Defense%20(DPA%2FCPA)-005ea8)
![Entropy: On-Chip SHAKE PRNG Stream](https://img.shields.io/badge/Entropy-On--Chip%20SHAKE%20PRNG%20Stream-purple)
![Target: AMD Phoenix NPU (AIE2 / XDNA1)](https://img.shields.io/badge/Hardware-AMD%20Phoenix%20AIE2%20(512--bit%20SIMD)-red)
![Residency: 100% On-Device Silicon](https://img.shields.io/badge/Residency-100%25%20On--Device%20(Zero%20Host%20Fallback)-brightgreen)
[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.22164124.svg)](https://doi.org/10.5281/zenodo.22164124)

</div>

---

## 1. Executive Summary & Physical Threat Model

Milestone **DR25** implements **Higher-Order Arithmetic Polynomial Masking (Blinding)** and an **Autonomous On-Chip PRNG Stream Engine** on the AMD Phoenix NPU (AIE2 / XDNA1 Architecture).

### Physical Side-Channel Threat Models Addressed:
1. **Differential Power Analysis (DPA) & Correlation Power Analysis (CPA)**:
   * Measuring APU core rail voltage during NTT or polynomial multiplication reveals secret key coefficients ($\mathbf{s}, \mathbf{e}$).
   * **Mitigation**: Secret polynomials in ring $\mathcal{R}_q = \mathbb{Z}_q[X]/(X^{256} + 1)$ are split into $d+1$ statistically independent random shares ($s = \sum_{i=0}^d s^{(i)} \pmod q$). Every intermediate register value is uniformly distributed in $\mathbb{Z}_q$, achieving $d$-th order probing security (Ishai-Sahai-Wagner model).
2. **Bus Starvation & Mask Refresh Bottleneck**:
   * Continuously fetching random masking shares from host PCIe during continuous line-rate encryption exhausts bus bandwidth and causes compute stalls.
   * **Mitigation**: An on-chip **FIPS 202 SHAKE-128 PRNG stream generator** executes directly inside Tile (3,2) microcode, expanding 32-byte QRNG seeds (from DR27) into multi-gigabit mask streams in local SRAM.
3. **Laser & Clock Fault Injection (Glitch Attacks)**:
   * Attackers injecting precise voltage or clock glitches to skip loops or zeroize polynomials.
   * **Mitigation**: Dual-rail redundant vector pipelines cross-verify accumulators; any mismatch triggers the **DR10 Hardware Zeroizer** and locks execution.

---

## 2. Mathematical Masking Formulations

### 2.1 Order-1 Arithmetic Masking (2 Shares)
For secret polynomial $s(X) \in \mathcal{R}_q$ and uniform random mask $m(X) \leftarrow_{\$} \mathcal{R}_q$:
$$s^{(0)}(X) = (s(X) - m(X)) \pmod q, \quad s^{(1)}(X) = m(X)$$
Reconstruction:
$$s(X) = (s^{(0)}(X) + s^{(1)}(X)) \pmod q$$

### 2.2 Order-2 Arithmetic Masking (3 Shares)
For uniform random masks $m_1(X), m_2(X) \leftarrow_{\$} \mathcal{R}_q$:
$$s^{(0)}(X) = (s(X) - m_1(X) - m_2(X)) \pmod q, \quad s^{(1)}(X) = m_1(X), \quad s^{(2)}(X) = m_2(X)$$
Reconstruction:
$$s(X) = (s^{(0)}(X) + s^{(1)}(X) + s^{(2)}(X)) \pmod q$$

### 2.3 Linear & Non-Linear Masked Operations
* **Masked Addition ($c = a + b$)**:
  $$c^{(i)}(X) = (a^{(i)}(X) + b^{(i)}(X)) \pmod q \quad \forall i \in \{0, \dots, d\}$$
* **Masked Ring Multiplication ($c = a \cdot s$) with Public $a$**:
  $$c^{(i)}(X) = (a(X) \cdot s^{(i)}(X)) \pmod{X^{256} + 1, q} \quad \forall i \in \{0, \dots, d\}$$
* **Constant-Time Share Refreshing**:
  Given fresh random polynomial $r(X) \leftarrow_{\$} \mathcal{R}_q$:
  $$s^{(0)}(X) \leftarrow (s^{(0)}(X) + r(X)) \pmod q, \quad s^{(1)}(X) \leftarrow (s^{(1)}(X) - r(X)) \pmod q$$

---

## 3. Microarchitectural Tile Mapping on AMD Phoenix AIE2

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                 XRT OBJECTFIFO INGRESS INTERFACE                                 │
│         ObjectFIFOs: dr25_seed_in, dr25_poly_in, dr25_shares_out, dr25_status_out                │
└────────────────────────────────────────────┬─────────────────────────────────────────────────────┘
                                             │ Zero-Copy DMA
═════════════════════════════════════════════╪═════════════════════════════════════════════════════
                                             │ PHYSICAL AIE2 TILE ARRAY
┌────────────────────────────────────────────▼─────────────────────────────────────────────────────┐
│  TILE (3,2): On-Chip FIPS 202 SHAKE-128 Local PRNG Stream Generator                             │
│   • Absorbs 32-byte QRNG seed from DR27 reservoir                                                │
│   • Squeezes high-throughput 256-element random mask polynomials directly into local SRAM        │
├──────────────────────────────────────────────────────────────────────────────────────────────────┤
│  TILE (1,0): Share Branch 0 (Primary Vector Pipeline)                                            │
│   • Evaluates arithmetic operations on Share 0: s^(0)(X)                                         │
│   • Branchless Barrett modular arithmetic mod 3329 (ML-KEM) and mod 8380417 (ML-DSA)             │
├──────────────────────────────────────────────────────────────────────────────────────────────────┤
│  TILE (1,2): Share Branch 1 & Dual-Rail Redundant Cross-Checker                                  │
│   • Evaluates arithmetic operations on Share 1: s^(1)(X) in parallel                             │
│   • Executes redundant parity check to detect laser/clock glitch fault injection                 │
├──────────────────────────────────────────────────────────────────────────────────────────────────┤
│  TILE (3,3): DR10 Sealed Zeroizer & Fault Execution Gate                                         │
│   • If Dual-Rail Path A == Path B: Output verified masked shares to egress DMA                   │
│   • If Dual-Rail Path A != Path B (Glitch Detected): Hard-fault and overwrite SRAM with 0x00      │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 4. References & Standards Citations

1. **Ishai, Y., Sahai, A., & Wagner, D. (2003):** *Private Circuits: Securing Hardware against Probing Attacks*. CRYPTO 2003.
2. **NIST FIPS PUB 203 (August 2024):** *Module-Lattice-Based Key-Encapsulation Mechanism Standard (ML-KEM)*.
3. **NIST FIPS PUB 204 (August 2024):** *Module-Lattice-Based Digital Signature Standard (ML-DSA)*.
4. **NIST FIPS PUB 202 (August 2015):** *SHA-3 Standard: Permutation-Based Hash and Extendable-Output Functions*.
5. **Project Provenance & Scientific Repository:** [DOI: 10.5281/zenodo.22164124](https://doi.org/10.5281/zenodo.22164124).
