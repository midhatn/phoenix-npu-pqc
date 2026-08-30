# DR29 Architecture & Design: NSA CNSA 2.0 Level 5 Multi-Tile Distributed Memory Engine on AMD Phoenix AIE2 Silicon

<div align="center">

![Mandate: NSA CNSA 2.0 Level 5](https://img.shields.io/badge/Mandate-NSA%20CNSA%202.0%20Level%205%20(Category%205)-005ea8)
![Algorithms: ML-KEM-1024 / ML-DSA-87](https://img.shields.io/badge/Algorithms-ML--KEM--1024%20%2F%20ML--DSA--87-purple)
![Target: AMD Phoenix NPU (AIE2 / XDNA1)](https://img.shields.io/badge/Hardware-AMD%20Phoenix%20AIE2%20(512--bit%20SIMD)-red)
![Residency: 100% On-Device Silicon](https://img.shields.io/badge/Residency-100%25%20On--Device%20(Zero%20Host%20Fallback)-brightgreen)
[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.22164124.svg)](https://doi.org/10.5281/zenodo.22164124)

</div>

---

## 1. Executive Summary & Problem Formulation

Milestone **DR29** implements the **NSA CNSA 2.0 Level 5 Multi-Tile Distributed Memory Engine** on the AMD Phoenix NPU (AIE2 / XDNA1 Architecture).

### The SRAM Boundary Challenge in Category 5 PQC:
Under the **NSA Commercial National Security Algorithm Suite 2.0 (CNSA 2.0)**, sovereign and high-assurance defense systems mandate the highest parameter sets:
* **NIST FIPS 203 ML-KEM-1024 ($k=4$)**: Matrix $\mathbf{A} \in \mathcal{R}_q^{4 \times 4}$ (16 polynomials in $\mathcal{R}_q$).
* **NIST FIPS 204 ML-DSA-87 ($k=8, l=7$)**: Matrix $\mathbf{A} \in \mathcal{R}_q^{8 \times 7}$ consisting of **56 polynomials in $\mathcal{R}_q$**.

For ML-DSA-87:
$$\text{Matrix Size} = 56 \times 256 \times 4\text{ bytes} = 57,344\text{ bytes} = 56\text{ KiB}$$
Combined with secret vector $\mathbf{s}_1 \in \mathcal{R}_q^7$ (7 KiB), secret vector $\mathbf{s}_2 \in \mathcal{R}_q^8$ (8 KiB), masking vector $\mathbf{y} \in \mathcal{R}_q^7$ (7 KiB), commitment $\mathbf{w}_1 \in \mathcal{R}_q^8$ (8 KiB), and hint tables (8 KiB), the active memory footprint reaches **$\approx 94\text{ KiB}$**.

Because each physical AIE2 compute tile contains exactly **64 KiB local SRAM**, monolithic single-tile execution causes an **immediate SRAM overflow**.

---

## 2. Spatial 4-Tile Cluster & MemTile Architecture

To execute 100% on silicon with zero host fallback, DR29 partitions the matrix into a **4-Tile Spatial Cluster ($2 \times 2$ Grid across Columns 1..4)** backed by **Shared MemTiles (Row 1, 512 KiB each)**:

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                            SHARED MEMTILES (Row 1: 2,048 KiB Total SRAM)                         │
│   MemTile (1,0): 512 KiB    MemTile (1,1): 512 KiB    MemTile (1,2): 512 KiB    MemTile (1,3)    │
│   • Ping-Pong Double Buffering: Holds 56-Poly Matrix A (56 KiB) & streams chunks via AXI crossbar │
└────────────────────────────────────┬─────────────────────────────┬───────────────────────────────┘
                                     │ Direct Stream Interconnect  │
═════════════════════════════════════╪═════════════════════════════╪═══════════════════════════════
                                     │ PHYSICAL AIE2 COMPUTE TILES │
┌────────────────────────────────────▼─────────────────────────────▼───────────────────────────────┐
│  TILE (2,0): Cluster Node 0 (Upper Left)       │  TILE (2,1): Cluster Node 1 (Upper Right)       │
│   • Sub-Matrix A[0..3, 0..3] (16 Polys = 16KB) │   • Sub-Matrix A[0..3, 4..6] (12 Polys = 12KB)  │
│   • Partial accum: A[0..3, 0..3] * s[0..3]     │   • Partial accum: A[0..3, 4..6] * s[4..6]      │
│   • Working SRAM: 24.5 KiB (< 64 KiB Limit)    │   • Working SRAM: 20.5 KiB (< 64 KiB Limit)     │
├────────────────────────────────────────────────┼─────────────────────────────────────────────────┤
│  TILE (2,2): Cluster Node 2 (Lower Left)       │  TILE (2,3): Cluster Node 3 (Lower Right)       │
│   • Sub-Matrix A[4..7, 0..3] (16 Polys = 16KB) │   • Sub-Matrix A[4..7, 4..6] (12 Polys = 12KB)  │
│   • Partial accum: A[4..7, 0..3] * s[0..3]     │   • Partial accum: A[4..7, 4..6] * s[4..6]      │
│   • Working SRAM: 24.5 KiB (< 64 KiB Limit)    │   • Working SRAM: 20.5 KiB (< 64 KiB Limit)     │
└────────────────────────────────────────────────┴─────────────────────────────────────────────────┘
                                     │ Horizontal Reduction via Direct Neighbor Crossbar
                                     ▼
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│  Row Accumulation: Result Vector w = (Node 0 + Node 1, Node 2 + Node 3) in Constant Time         │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Mathematical Sub-Matrix Decomposition

### 3.1 ML-DSA-87 ($8 \times 7$ Matrix Decomposition)
$$\mathbf{A} = \begin{pmatrix} \mathbf{A}_{00} & \mathbf{A}_{01} \\ \mathbf{A}_{10} & \mathbf{A}_{11} \end{pmatrix}, \quad \mathbf{s}_1 = \begin{pmatrix} \mathbf{s}_{1,\text{top}} \\ \mathbf{s}_{1,\text{bot}} \end{pmatrix}$$
Where:
* $\mathbf{A}_{00} \in \mathcal{R}_q^{4 \times 4}$ (Tile 2,0), $\mathbf{s}_{1,\text{top}} \in \mathcal{R}_q^4$
* $\mathbf{A}_{01} \in \mathcal{R}_q^{4 \times 3}$ (Tile 2,1), $\mathbf{s}_{1,\text{bot}} \in \mathcal{R}_q^3$
* $\mathbf{A}_{10} \in \mathcal{R}_q^{4 \times 4}$ (Tile 2,2), $\mathbf{s}_{1,\text{top}} \in \mathcal{R}_q^4$
* $\mathbf{A}_{11} \in \mathcal{R}_q^{4 \times 3}$ (Tile 2,3), $\mathbf{s}_{1,\text{bot}} \in \mathcal{R}_q^3$

$$\mathbf{w}_{\text{top}} = \mathbf{A}_{00} \cdot \mathbf{s}_{1,\text{top}} + \mathbf{A}_{01} \cdot \mathbf{s}_{1,\text{bot}} \pmod q$$
$$\mathbf{w}_{\text{bot}} = \mathbf{A}_{10} \cdot \mathbf{s}_{1,\text{top}} + \mathbf{A}_{11} \cdot \mathbf{s}_{1,\text{bot}} \pmod q$$

### 3.2 Memory Ceiling Proof ($\le 24.5\text{ KiB}$)
For Tile (2,0):
* Sub-Matrix $\mathbf{A}_{00}$: $16 \times 256 \times 4\text{ bytes} = 16,384\text{ bytes} = 16.0\text{ KiB}$
* Vector chunk $\mathbf{s}_{1,\text{top}}$: $4 \times 256 \times 4\text{ bytes} = 4,096\text{ bytes} = 4.0\text{ KiB}$
* Partial accumulator $\mathbf{w}_{\text{partial}}$: $4 \times 256 \times 4\text{ bytes} = 4,096\text{ bytes} = 4.0\text{ KiB}$
* Ping-Pong stream buffer overhead: $512\text{ bytes} = 0.5\text{ KiB}$
* **Total Peak SRAM**: $16.0 + 4.0 + 4.0 + 0.5 = \mathbf{24.5\text{ KiB}} \ll \mathbf{64\text{ KiB}}$ (**61.7% Safety Margin**).

---

## 4. References & Standards Citations

1. **NSA Cybersecurity Advisory (September 2022 / 2024):** *Commercial National Security Algorithm Suite 2.0 (CNSA 2.0)*. National Security Agency.
2. **NIST FIPS PUB 203 (August 2024):** *Module-Lattice-Based Key-Encapsulation Mechanism Standard (ML-KEM)*.
3. **NIST FIPS PUB 204 (August 2024):** *Module-Lattice-Based Digital Signature Standard (ML-DSA)*.
4. **AMD Corporation (2023):** *Versal AI Engine Architecture Manual (AM009)*. AMD Xilinx.
5. **Project Provenance & Scientific Repository:** [DOI: 10.5281/zenodo.22164124](https://doi.org/10.5281/zenodo.22164124).
