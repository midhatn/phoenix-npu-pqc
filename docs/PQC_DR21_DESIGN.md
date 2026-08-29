# DR21 Architecture & Design: NIST FIPS 205 (SLH-DSA / SPHINCS+) On-Device Stateless Hash-Based Signatures on AMD Phoenix AIE2 Silicon

<div align="center">

![Standard: NIST FIPS PUB 205](https://img.shields.io/badge/Standard-NIST%20FIPS%20PUB%20205%20(2024)-005ea8)
![Target: AMD Phoenix NPU (AIE2 / XDNA1)](https://img.shields.io/badge/Hardware-AMD%20Phoenix%20AIE2%20(512--bit%20SIMD)-red)
![Residency: 100% On-Device Silicon](https://img.shields.io/badge/Residency-100%25%20On--Device%20(Zero%20Host%20Fallback)-brightgreen)
[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.22164124.svg)](https://doi.org/10.5281/zenodo.22164124)

</div>

---

## 1. Executive Summary & Cryptographic Rationale

Milestone **DR21** implements **NIST FIPS PUB 205 (Stateless Hash-Based Digital Signature Standard — SLH-DSA / SPHINCS+)** on the AMD Phoenix NPU (AIE2 / XDNA1 Architecture).

While ML-KEM (FIPS 203) and ML-DSA (FIPS 204) rely on the hardness of Module Learning With Errors (M-LWE) and Module Short Integer Solution (M-SIS) over algebraic lattices, **FIPS 205 relies exclusively on the security of cryptographic hash functions (SHAKE-256 / SHA-3 / Keccak-f[1600])**.

### The Ultimate Mathematical Hedge:
If future advances in quantum sieve algorithms or algebraic geometry weaken lattice assumptions, **FIPS 205 remains mathematically secure**, providing a conservative, non-lattice sovereign fallback.

---

## 2. Mathematical Specification & Standard Parameters

### 2.1 Parameter Sets Implemented
In accordance with NIST FIPS 205 Table 1:

| Parameter Set | Security Category | $n$ (bytes) | $h$ | $d$ | $h' = h/d$ | $a$ | $k$ | $w$ | PK Size | SK Size | Sig Size |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **SLH-DSA-SHAKE-128s** | Category 1 | 16 | 63 | 7 | 9 | 12 | 14 | 16 | 32 B | 64 B | 7,856 B |
| **SLH-DSA-SHAKE-128f** | Category 1 (Fast) | 16 | 66 | 22 | 3 | 6 | 33 | 16 | 32 B | 64 B | 17,088 B |
| **SLH-DSA-SHAKE-256s** | Category 5 | 32 | 64 | 8 | 8 | 14 | 17 | 16 | 64 B | 128 B | 29,792 B |
| **SLH-DSA-SHAKE-256f** | Category 5 (Fast) | 32 | 68 | 17 | 4 | 8 | 35 | 16 | 64 B | 128 B | 49,856 B |

### 2.2 32-Byte ADRS (Address Structure) Domain Separation
To prevent multi-target and cross-tree hash collision attacks, every hash evaluation utilizes a 32-byte `ADRS` descriptor formatted according to FIPS 205 Section 4.2:
- `Layer Address` (4 bytes, offset 0)
- `Tree Address` (12 bytes, offset 4)
- `Type` (4 bytes, offset 16): `WOTS_HASH(0)`, `WOTS_PK(1)`, `TREE(2)`, `FORS_TREE(3)`, `FORS_ROOTS(4)`, `WOTS_PRF(5)`, `FORS_PRF(6)`
- `Word 1` (4 bytes, offset 20): `KeyPair Address`
- `Word 2` (4 bytes, offset 24): `Chain Address` / `Tree Height`
- `Word 3` (4 bytes, offset 28): `Hash Address` / `Tree Index`

---

## 3. Hardware Silicon Architecture & Invariants

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                 XRT OBJECTFIFO INGRESS INTERFACE                                 │
│             ObjectFIFOs: dr21_msg_in, dr21_adrs_in, dr21_key_in, dr21_sig_out                │
└────────────────────────────────────────────┬─────────────────────────────────────────────────────┘
                                             │ 2 Input DMA Channels (Universal Invariant)
═════════════════════════════════════════════╪═════════════════════════════════════════════════════
                                             │ PHYSICAL AIE2 TILE ARRAY
┌────────────────────────────────────────────▼─────────────────────────────────────────────────────┐
│  TILE (3,2): 512-bit SIMD Keccak-f[1600] Core (DR9 Fused Pipeline)                               │
│   • 24-round Keccak permutations running in constant-time vector microcode                       │
│   • Evaluates PRF, PRF_msg, H_msg, F, and T_l domain hash functions                              │
├──────────────────────────────────────────────────────────────────────────────────────────────────┤
│  TILE (3,0) & (3,1): W-OTS+ & FORS Multi-Tree Co-Processor                                       │
│   • Winternitz Chaining Function: c^i(X, ADRS) computed in parallel across SIMD lanes            │
│   • FORS (Forest of Random Subsets) leaf generation and authentication paths                     │
│   • Hypertree Merkle path verification across d layers of sub-trees                              │
├──────────────────────────────────────────────────────────────────────────────────────────────────┤
│  TILE (3,3): DR10 Sealed Zeroization & Memory Scrubber                                           │
│   • Overwrites private seed buffers with 0x00 upon signature completion                          │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 4. Academic & Standards Citations

1. **NIST FIPS PUB 205 (August 2024):** *Stateless Hash-Based Digital Signature Standard (SLH-DSA)*. National Institute of Standards and Technology. [DOI: 10.6028/NIST.FIPS.205](https://doi.org/10.6028/NIST.FIPS.205).
2. **NIST FIPS PUB 202 (August 2015):** *SHA-3 Standard: Permutation-Based Hash and Extendable-Output Functions*. National Institute of Standards and Technology. [DOI: 10.6028/NIST.FIPS.202](https://doi.org/10.6028/NIST.FIPS.202).
3. **Bernstein, D. J., et al. (2019):** *SPHINCS+ — Submission to the NIST Post-Quantum Cryptography Standardization Process*.
4. **AMD Corporation (2023):** *Versal AI Engine Architecture Manual (AM009)*. AMD Xilinx.
5. **Project Provenance & Scientific Repository:** [DOI: 10.5281/zenodo.22164124](https://doi.org/10.5281/zenodo.22164124).
