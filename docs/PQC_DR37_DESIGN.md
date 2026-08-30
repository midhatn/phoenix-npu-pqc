# DR37 Architecture & Design: ETSI TS 103 744 & BSI TR-02102-1 Dual-Scheme Hybrid KEM Engine

<div align="center">

![Standard: ETSI TS 103 744](https://img.shields.io/badge/Standard-ETSI%20TS%20103%20744-005ea8)
![Standard: BSI TR-02102-1](https://img.shields.io/badge/Standard-BSI%20TR--02102--1%20(2025%2F2026)-darkblue)
![Draft: IETF RFC 9954](https://img.shields.io/badge/IETF-RFC%209954%20(X25519MLKEM768)-purple)
![Hardware: AMD Phoenix NPU (AIE2 / XDNA1)](https://img.shields.io/badge/Target-AMD%20Phoenix%20NPU%20(AIE2%20%2F%20XDNA1)-red)
[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.22164124.svg)](https://doi.org/10.5281/zenodo.22164124)

</div>

---

## 1. Executive Summary & Regulatory Context

Milestone **DR37** implements the **ETSI TS 103 744 & BSI TR-02102-1 Dual-Scheme Hybrid Key Encapsulation Mechanism (Hybrid KEM) Engine** on the AMD Phoenix NPU (AIE2 / XDNA1 Architecture).

Sovereign European guidelines (BSI Germany TR-02102-1, ANSSI France Scientific Recommendations) mandate that post-quantum migrations must utilize **hybrid key exchange** combining classical Diffie-Hellman with post-quantum lattice cryptography to ensure complete defense-in-depth against both Store-Now-Decrypt-Later (SNDL) attacks and theoretical lattice cryptanalysis.

---

## 2. Mathematical Architecture & Hybrid Flow

```
                                  SENDER / CLIENT (AIE2 Silicon)
┌────────────────────────────────────────────────────────────────────────────────────────┐
│  PUBLIC KEY: PK_Hybrid = (PK_Classical [X25519] || PK_PQC [ML-KEM-768])                │
└───────────────────────────────────────────┬────────────────────────────────────────────┘
                                            │
               ┌────────────────────────────┴────────────────────────────┐
               ▼                                                         ▼
┌──────────────────────────────┐                         ┌──────────────────────────────┐
│  CLASSICAL ENCAPSULATION     │                         │  POST-QUANTUM ENCAPSULATION  │
│   • Generate ephemeral (e_sk)│                         │   • FIPS 203 ML-KEM-768 Enc  │
│   • CT_c = X25519_base(e_sk) │                         │   • (CT_pqc, SS_pqc) =       │
│   • SS_c = X25519(e_sk, PK_c)│                         │     ML-KEM-Encaps(PK_pqc)    │
└──────────────┬───────────────┘                         └──────────────┬───────────────┘
               │                                                        │
               │ SS_c (32 Bytes)                                        │ SS_pqc (32 Bytes)
               \────────────────────────────┬───────────────────────────/
                                            ▼
┌────────────────────────────────────────────────────────────────────────────────────────┐
│  AIE2 ON-CHIP DUAL KEY COMBINER (Tile 3,2)                                             │
│   • IKM = SS_c || SS_pqc || CT_c || CT_pqc                                            │
│   • SS_Final = HKDF-Extract(salt="", IKM) -> HKDF-Expand(info="ETSI_HYBRID_KEM", 32)  │
└───────────────────────────────────────────┬────────────────────────────────────────────┘
                                            ▼
                        Final Quantum-Safe Session Key (32 Bytes)
```

---

## 3. Supported Hybrid Profiles

1. **`X25519MLKEM768` (Standard BSI / TLS 1.3 Profile)**:
   - Classical: Montgomery Curve25519 ($X25519$, 32-byte public key / ciphertext).
   - Post-Quantum: NIST FIPS 203 ML-KEM-768 (1,184-byte public key, 1,088-byte ciphertext).
   - Total Hybrid PK: 1,216 bytes · Total Hybrid CT: 1,120 bytes.
2. **`SecP384R1MLKEM1024` (CNSA 2.0 / Sovereign High-Assurance Profile)**:
   - Classical: NIST Curve P-384 ECDH (49/97-byte public key, 48-byte shared secret).
   - Post-Quantum: NIST FIPS 203 ML-KEM-1024 (1,568-byte public key, 1,568-byte ciphertext).
   - Total Hybrid PK: 1,617 bytes · Total Hybrid CT: 1,616 bytes.

---

## 4. References & Standards Citations

1. **ETSI TS 103 744 (2024)**: *Quantum-Safe Hybrid Key Exchanges*.
2. **BSI Technical Guideline TR-02102-1 (2025/2026)**: *Cryptographic Mechanisms for TLS 1.3*.
3. **IETF RFC 9954 (2025)**: *Hybrid Key Encapsulation Mechanisms for TLS 1.3*.
4. **Project Provenance & Scientific Repository:** [DOI: 10.5281/zenodo.22164124](https://doi.org/10.5281/zenodo.22164124).
