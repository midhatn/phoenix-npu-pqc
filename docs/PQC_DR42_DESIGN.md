# DR42 Architecture & Design: ANSSI Composite & Dual-Signature Sovereign Standard Engine

<div align="center">

![Agency: ANSSI (France)](https://img.shields.io/badge/Agency-ANSSI%20(France)%20Hybrid%20Mandate-005ea8)
![Standard: BSI TR-02102-1](https://img.shields.io/badge/Standard-BSI%20TR--02102--1%20%2F%20IETF%20Composite-purple)
![Hardware: AMD Phoenix NPU (AIE2 / XDNA1)](https://img.shields.io/badge/Target-AMD%20Phoenix%20NPU%20(AIE2%20%2F%20XDNA1)-red)
[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.22164124.svg)](https://doi.org/10.5281/zenodo.22164124)

</div>

---

## 1. Executive Summary & Sovereign Mandate

Milestone **DR42** implements the **ANSSI Composite & Dual-Signature Sovereign Standard Engine** on the AMD Phoenix NPU (AIE2 / XDNA1 Architecture).

In accordance with official positions from **ANSSI (French National Cybersecurity Agency)**, **BSI (Federal Office for Information Security, Germany)**, and the **IETF `draft-ietf-lamps-pq-composite-sigs`**, DR42 enforces atomic dual-signature generation and verification combining pre-quantum algorithms (`Ed25519`, `ECDSA P-384`) with post-quantum lattice signatures (`ML-DSA-44`, `ML-DSA-65`, `ML-DSA-87`).

---

## 2. Composite Dual-Signature Microarchitecture

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│  DOCUMENT / ARTIFACT PAYLOAD M                                                         │
└───────────────────────────────────────────┬────────────────────────────────────────────┘
                                            │
               ┌────────────────────────────┴────────────────────────────┐
               ▼                                                         ▼
┌───────────────────────────────────────────┐ ┌──────────────────────────────────────────┐
│  CLASSICAL DIGITAL SIGNATURE ENGINE       │ │  POST-QUANTUM DIGITAL SIGNATURE ENGINE   │
│   • Ed25519 (RFC 8032) / ECDSA P-384      │ │   • ML-DSA-44 / ML-DSA-65 (FIPS 204)     │
│   • Generates Sig_trad (64B / 96B)        │ │   • Generates Sig_pqc (2,420B / 3,309B)  │
└─────────────────────┬─────────────────────┘ └────────────────────┬─────────────────────┘
                      │                                            │
                      \─────────────────────┬──────────────────────/
                                            ▼
┌────────────────────────────────────────────────────────────────────────────────────────┐
│  COMPOUND SERIALIZER: Sig_composite = [Len(Sig_trad) || Sig_trad || Len(Sig_pqc) || ..]│
└───────────────────────────────────────────┬────────────────────────────────────────────┘
                                            │
                                            ▼
┌────────────────────────────────────────────────────────────────────────────────────────┐
│  ATOMIC VERIFICATION CONJUNCTION (AIE2 Tile 3,2):                                      │
│                Valid_composite = Verify_trad(...) AND Verify_pqc(...)                  │
│   • True  ==> Document mathematically authentic under both classical and quantum math  │
│   • False ==> Fail-Closed Immediate Rejection & Zeroization                            │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Supported Composite Combinations

| Combination Name | Classical Component | Post-Quantum Component | Compound PK Size | Compound Signature Size | Security Level |
| :--- | :--- | :--- | :---: | :---: | :---: |
| **`Ed25519-ML-DSA-44`** | Ed25519 (32 B) | ML-DSA-44 (1,312 B) | 1,348 B | 2,488 B | NIST Level 2 / ANSSI Qual |
| **`ECDSA-P384-ML-DSA-65`**| ECDSA P-384 (97 B)| ML-DSA-65 (1,952 B) | 2,053 B | 3,409 B | NIST Level 3 / CNSA 2.0 |
| **`ECDSA-P521-ML-DSA-87`**| ECDSA P-521 (133 B)| ML-DSA-87 (2,592 B) | 2,729 B | 4,763 B | NIST Level 5 / CNSA 2.0 |

---

## 4. References & Standards Citations

1. **ANSSI (2022)**: *ANSSI Views on the Post-Quantum Cryptography Transition*.
2. **BSI TR-02102-1 (2024)**: *Cryptographic Mechanisms: Recommendations and Key Lengths*.
3. **IETF Draft `draft-ietf-lamps-pq-composite-sigs-02`**: *Composite Signatures For Use In Internet PKI*.
4. **Project Provenance & Scientific Repository:** [DOI: 10.5281/zenodo.22164124](https://doi.org/10.5281/zenodo.22164124).
