# DR34 Architecture & Design: On-Device Firmware Remote Attestation & TPM 2.0 / TCG DICE Engine

<div align="center">

![Standard: TCG DICE Architecture](https://img.shields.io/badge/Standard-TCG%20DICE%20Architecture-005ea8)
![Protocol: TPM 2.0 PCR & Remote Attestation](https://img.shields.io/badge/Protocol-TPM%202.0%20%2F%20IETF%20RATS%20(RFC%209334)-purple)
![Key: ML-DSA & LMS Attestation Identity Keys](https://img.shields.io/badge/Signatures-ML--DSA%20%26%20LMS%20AIKs-brightgreen)
![Hardware: AMD Phoenix NPU (AIE2 / XDNA1)](https://img.shields.io/badge/Target-AMD%20Phoenix%20NPU%20(AIE2%20%2F%20XDNA1)-red)
[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.22164124.svg)](https://doi.org/10.5281/zenodo.22164124)

</div>

---

## 1. Executive Summary & Attestation Mandate

Milestone **DR34** implements the **On-Device Firmware Remote Attestation & TPM 2.0 / TCG DICE Engine** on the AMD Phoenix NPU (AIE2 / XDNA1 Architecture).

It provides hardware-rooted measurement of AIE2 bitstreams (`.xclbin`), microcode binaries, and security patch levels into simulated/hardware TPM 2.0 PCR registers and generates cryptographic Quotes and TCG DICE Compound Device Identifier (CDI) certificate chains using on-device **NIST FIPS 204 ML-DSA** and **NIST SP 800-208 LMS** Attestation Identity Keys (AIKs).

---

## 2. TCG DICE Layered Derivation Model

```
┌────────────────────────────────────────────────────────────────────────┐
│  LAYER 0: Unique Device Secret (UDS) [Sealed DR10 Tile 0,1 SRAM]       │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
               KMAC256(UDS, Bitstream Hash || Security Version)
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│  LAYER 1: Compound Device Identifier (CDI) [Tile 3,2 Keccak Engine]    │
│   • Generates Layer 1 Device ID Keypair (ML-DSA-44 or LMS)             │
│   • Issues Self-Signed / CA-Bound Device ID Certificate               │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
               KMAC256(CDI, Runtime Config || Security Patch Level)
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│  LAYER 2: Attestation Identity Key (AIK / Alias Key)                   │
│   • Generates TPM 2.0 Cryptographic Quotes for Remote Verifiers        │
│   • Signs PCR Digest (PCR[12] Bitstream || PCR[14] Patch Level)        │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 3. TPM 2.0 PCR Measurement Allocation

* **PCR[12]**: AIE2 Bitstream (`.xclbin` bitstream hash and partition metadata).
* **PCR[14]**: Microcode Security Patch Level and Monotonic Security Version.
* **PCR[15]**: Dynamic Column Power & Multi-Tile Clustering Topology Configuration.

---

## 4. References & Standards Citations

1. **TCG DICE Architecture Specification (Version 1.1)**: *Device Identifier Composition Engine*.
2. **Trusted Platform Module (TPM) 2.0 Library Specification (ISO/IEC 11889)**.
3. **IETF RFC 9334 (January 2023)**: *Remote ATtestation ProcedureS (RATS) Architecture*.
4. **Project Provenance & Scientific Repository:** [DOI: 10.5281/zenodo.22164124](https://doi.org/10.5281/zenodo.22164124).
