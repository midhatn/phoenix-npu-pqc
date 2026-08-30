# DR32 Architecture & Design: Automated NIST ACVP Server Test Vector Harness & Cryptographic Boundary Ingestion Engine

<div align="center">

![Compliance: NIST FIPS 140-3 / SP 800-140Br1](https://img.shields.io/badge/Compliance-NIST%20FIPS%20140--3%20%2F%20SP%20800--140Br1-005ea8)
![Protocol: Automated Cryptographic Validation Protocol (ACVP)](https://img.shields.io/badge/Protocol-Automated%20Crypto%20Validation%20(ACVP)-purple)
![Target: AMD Phoenix NPU (AIE2 / XDNA1)](https://img.shields.io/badge/Hardware-AMD%20Phoenix%20AIE2%20(512--bit%20SIMD)-red)
![Residency: 100% On-Device Silicon](https://img.shields.io/badge/Residency-100%25%20On--Device%20(Zero%20Host%20Fallback)-brightgreen)
[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.22164124.svg)](https://doi.org/10.5281/zenodo.22164124)

</div>

---

## 1. Executive Summary & FIPS 140-3 Validation Mandate

Milestone **DR32** implements the **Automated NIST ACVP (Automated Cryptographic Validation Protocol) Server Test Vector Harness & Cryptographic Boundary Ingestion Engine** on the AMD Phoenix NPU (AIE2 / XDNA1 Architecture).

Under **NIST FIPS 140-3** and the **Cryptographic Module Validation Program (CMVP)**, all cryptographic hardware boundary algorithms must undergo automated algorithmic testing via the NIST ACVP specification:
* **NIST FIPS 203 (ML-KEM)**: `keyGen`, `encapDecap` (AFT, VAL).
* **NIST FIPS 204 (ML-DSA)**: `keyGen`, `sigGen`, `sigVer` (AFT, VAL, Known Answer Tests).
* **NIST FIPS 205 (SLH-DSA)**: `keyGen`, `sigGen`, `sigVer`.
* **NIST SP 800-208 (LMS)**: `sigVer` (Stateless Firmware Verifier).

---

## 2. NIST ACVP Protocol & JSON Schema Pipeline

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                             NIST ACVP SERVER / ACVTOOL PROMPT JSON                               │
│      { "acvVersion": "1.0", "vsId": 12345, "testGroups": [ { "tgId": 1, "testType": "AFT"... } ]}│
└────────────────────────────────────────────┬─────────────────────────────────────────────────────┘
                                             │ Zero-Copy Ingestion
═════════════════════════════════════════════╪═════════════════════════════════════════════════════
                                             │ PHYSICAL AIE2 CRYPTOGRAPHIC BOUNDARY
┌────────────────────────────────────────────▼─────────────────────────────────────────────────────┐
│  TILE (3,2): Ingestion & Hardware Packet Demultiplexer                                           │
│   • Parses ACVP test cases into hardware DMA buffers (REQ_BYTES / DESCRIPTOR_BYTES)              │
│   • Ingests externalMu, context nonces, seed tokens, and ciphertext inputs                       │
├──────────────────────────────────────────────────────────────────────────────────────────────────┤
│  AIE2 ARRAY COMPUTE TILES (Tiles 0..3, Rows 2..5): Algorithm Execution Core                      │
│   • Dispatches to dedicated hardware graphs (DR2-DR8 ML-KEM, DR11-DR15 ML-DSA, DR21, DR28)       │
│   • 100% On-Device execution with zero host mathematical intervention                            │
├──────────────────────────────────────────────────────────────────────────────────────────────────┤
│  TILE (3,3): Hardware Response Assembler & Boundary CRC32 Checksum                               │
│   • Formats NIST ACVP response vectors ({ "tcId": 1, "pk": "...", "c": "...", "k": "..." })      │
│   • Verifies hardware CRC32 integrity across all output buffers                                  │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Cryptographic Boundary Definition (NIST SP 800-140Br1)

* **Physical Boundary**: AMD Phoenix APU package containing the AIE2 NPU silicon tile array.
* **Logical Boundary**: The AIE2 microcode execution core isolated by XRT ObjectFIFO streaming interfaces and DR10 hardware zeroizers.
* **Approved Security Functions**:
  * ML-KEM-512/768/1024 (FIPS 203)
  * ML-DSA-44/65/87 (FIPS 204)
  * SLH-DSA-SHAKE-128s (FIPS 205)
  * LMS/HSS (NIST SP 800-208)
  * SHA-3 / SHAKE / Keccak-f[1600] (FIPS 202)
  * SP 800-56C Rev. 2 Dual Key Combiner

---

## 4. References & Standards Citations

1. **NIST SP 800-140Br1 (2020):** *CMVP Security Policy Requirements for Cryptographic Modules*.
2. **NIST ACVP Protocol Specification (2024):** *Automated Cryptographic Validation Protocol Specification (RFC 8446 Appendix / NIST CAVP)*.
3. **NIST FIPS PUB 203 / 204 / 205 (August 2024):** *Final Post-Quantum Cryptography Standards*.
4. **Project Provenance & Scientific Repository:** [DOI: 10.5281/zenodo.22164124](https://doi.org/10.5281/zenodo.22164124).
