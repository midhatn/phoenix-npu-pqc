# DR28 Architecture & Design: NIST SP 800-208 / RFC 8554 (LMS / HSS) Stateless Bitstream & Firmware Verification Engine on AMD Phoenix AIE2 Silicon

<div align="center">

![Standard: NIST SP 800-208 / RFC 8554](https://img.shields.io/badge/Standard-NIST%20SP%20800--208%20%2F%20RFC%208554-005ea8)
![Standard: NSA CNSA 2.0](https://img.shields.io/badge/Mandate-NSA%20CNSA%202.0%20(Stateful%20Hash)-purple)
![Target: AMD Phoenix NPU (AIE2 / XDNA1)](https://img.shields.io/badge/Hardware-AMD%20Phoenix%20AIE2%20(512--bit%20SIMD)-red)
![Residency: 100% On-Device Silicon](https://img.shields.io/badge/Residency-100%25%20On--Device%20(Zero%20Host%20Fallback)-brightgreen)
[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.22164124.svg)](https://doi.org/10.5281/zenodo.22164124)

</div>

---

## 1. Executive Summary & Hardware Attestation Rationale

Milestone **DR28** implements **NIST SP 800-208 (Recommendation for Stateful Hash-Based Signature Schemes)** and **IETF RFC 8554 (Leighton-Micali Hash-Based Signatures — LMS / HSS)** on the AMD Phoenix NPU (AIE2 / XDNA1 Architecture).

In mission-critical quantum-resilient systems, executing post-quantum algorithms is meaningless if the **underlying hardware bitstream (`.xclbin`, `.bin`, `.elf`) or microcode can be tampered with or replaced by malicious code**.

### The Core Security Properties of DR28:
1. **Stateless On-Device Verifier**: In accordance with **NIST SP 800-208 Section 4**, client accelerators operate strictly as stateless verifiers to eliminate catastrophic stateful private-key reuse hazards.
2. **Immutable Root of Trust**: Verifies bitstream authenticity on physical silicon *before* releasing AIE2 tile execution locks.
3. **NSA CNSA 2.0 Mandate Compliance**: Meets the official U.S. National Security Agency mandate for stateful hash-based firmware update verification.

---

## 2. Mathematical Specification & Standard Parameters

### 2.1 Standard Parameter Sets (RFC 8554 & NIST SP 800-208)

#### LM-OTS Parameters (One-Time Signatures):
| LM-OTS Type Code | Name | Hash ($H$) | $n$ (bytes) | $w$ (Winternitz) | $p$ (chains) | $ls$ (checksum shift) | Sig Size |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| `0x00000001` | `LMOTS_SHA256_N32_W1` | SHA-256 | 32 | 1 | 265 | 7 | 8,516 B |
| `0x00000002` | `LMOTS_SHA256_N32_W2` | SHA-256 | 32 | 2 | 133 | 6 | 4,292 B |
| `0x00000003` | `LMOTS_SHA256_N32_W4` | SHA-256 | 32 | 4 | 67 | 4 | 2,180 B |
| `0x00000004` | `LMOTS_SHA256_N32_W8` | SHA-256 | 32 | 8 | 34 | 0 | 1,124 B |
| `0x00000008` | `LMOTS_SHAKE256_N32_W8`| SHAKE-256 | 32 | 8 | 34 | 0 | 1,124 B |

#### LMS Parameters (Merkle Trees):
| LMS Type Code | Name | Hash ($H$) | $m$ (bytes) | $h$ (height) | Max Signatures ($2^h$) | Public Key Size |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: |
| `0x00000005` | `LMS_SHA256_M32_H5` | SHA-256 | 32 | 5 | 32 | 56 B |
| `0x00000006` | `LMS_SHA256_M32_H10`| SHA-256 | 32 | 10 | 1,024 | 56 B |
| `0x00000007` | `LMS_SHA256_M32_H15`| SHA-256 | 32 | 15 | 32,768 | 56 B |
| `0x00000008` | `LMS_SHA256_M32_H20`| SHA-256 | 32 | 20 | 1,048,576 | 56 B |

---

## 3. Microarchitectural Verification Flow on AIE2

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                 XRT OBJECTFIFO INGRESS INTERFACE                                 │
│          ObjectFIFOs: dr28_pk_in, dr28_bitstream_in, dr28_sig_in, dr28_verdict_out               │
└────────────────────────────────────────────┬─────────────────────────────────────────────────────┘
                                             │ 2 Input DMA Channels (Zero-Copy)
═════════════════════════════════════════════╪═════════════════════════════════════════════════════
                                             │ PHYSICAL AIE2 TILE ARRAY
┌────────────────────────────────────────────▼─────────────────────────────────────────────────────┐
│  TILE (3,2): SHA-256 / Keccak-f[1600] Vector Core (DR9 Ingress Engine)                          │
│   1. Compute Message Digest:                                                                     │
│      d = H( I || u32(q) || u16(0xDADA) || C || bitstream_data )                                  │
├──────────────────────────────────────────────────────────────────────────────────────────────────┤
│  TILE (3,1): Winternitz LM-OTS Candidate Public Key Recovery Core                                │
│   2. Decompose digest d into Winternitz base-2^w digits: a = coef(d || checksum, w)              │
│   3. Compute Winternitz Hash Chains from a[i] to (2^w - 1):                                      │
│      z[i] = H( I || u32(q) || u16(i) || u8(j) || y[i] )                                          │
│   4. Recover candidate OTS Public Key:                                                           │
│      K_c = H( I || u32(q) || u16(0xDADA) || z[0] || z[1] || ... || z[p-1] )                       │
├──────────────────────────────────────────────────────────────────────────────────────────────────┤
│  TILE (3,0): Merkle Tree Authentication Path Traverser                                           │
│   5. Compute leaf node hash: T_c[2^h + q] = H( I || u32(2^h + q) || u16(0xDADA) || K_c )          │
│   6. Hash up the Merkle authentication path to root:                                             │
│      T_c[node/2] = H( I || u32(node/2) || u16(0xDADA) || left_child || right_child )             │
├──────────────────────────────────────────────────────────────────────────────────────────────────┤
│  TILE (3,3): Constant-Time Equality Verifier & DR10 Execution Gate                               │
│   7. Compare reconstructed root T_c[1] == Public Key T[1]                                        │
│      • If Equal: Return 0x00000000 (AUTHENTIC) -> Unlock AIE2 Microcode Execution                │
│      • If Non-Equal: Return 0x00000001 (TAMPERED) -> Fail-Closed Hard Fault & Zeroize            │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 4. References & Standards Citations

1. **NIST SP 800-208 (October 2020):** *Recommendation for Stateful Hash-Based Signature Schemes*. National Institute of Standards and Technology. [DOI: 10.6028/NIST.SP.800-208](https://doi.org/10.6028/NIST.SP.800-208).
2. **IETF RFC 8554 (April 2019):** *Leighton-Micali Hash-Based Signatures (LMS)*. Internet Engineering Task Force.
3. **NSA CNSA 2.0 (September 2022 / 2024):** *Commercial National Security Algorithm Suite 2.0 Cybersecurity Advisory*. National Security Agency.
4. **IETF RFC 9334 (January 2023):** *Remote ATtestation ProcedureS (RATS) Architecture*. Internet Engineering Task Force.
5. **Project Provenance & Scientific Repository:** [DOI: 10.5281/zenodo.22164124](https://doi.org/10.5281/zenodo.22164124).
