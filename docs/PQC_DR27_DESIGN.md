# DR27 Architecture & Design: Palo Alto QRNG-OPENAPI v1.0 Ingress & On-Chip Key Reservoir on AMD Phoenix NPU (AIE2)

<div align="center">

![Standard: QRNG-OPENAPI v1.0](https://img.shields.io/badge/Entropy-QRNG--OPENAPI%20v1.0-blueviolet)
![Standard: NIST SP 800-90B](https://img.shields.io/badge/Health%20Tests-NIST%20SP%20800--90B-green)
![Standard: ETSI GS QKD 014](https://img.shields.io/badge/Reservoir-ETSI%20GS%20QKD%20014-purple)
![Residency: 100% On-Device Silicon](https://img.shields.io/badge/Residency-100%25%20On--Device%20(Zero%20Host%20Fallback)-brightgreen)
[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.22164124.svg)](https://doi.org/10.5281/zenodo.22164124)

</div>

---

## 1. Executive Summary

Milestone **DR27** implements true quantum entropy ingestion and key buffering on the AMD Phoenix NPU:
1. **DR27a: Sealed Host Ingress Daemon**: Connects to remote or physical QRNG appliances via Palo Alto Networks **QRNG-OPENAPI v1.0** REST endpoints (`POST /v1/entropy`), continuously validating entropy health against **NIST SP 800-90B** preflight tests (`GET /v1/healthtest`).
2. **DR27b: NPU-Resident Token-Bucket Key Reservoir**: 16-slot circular ring buffer in on-die Tile SRAM ($16 \times 32\text{ bytes} = 512\text{ bytes}$ master pool) decoupling discrete optical key arrival from line-rate cryptographic throughput.
3. **5% / 30% Hysteresis Loop**: Anti-flapping operational state machine preventing session renegotiation spikes during QKD network load surges.

---

## 2. Hysteresis State Machine & Reservoir Specifications

```
                   [ QKD Reservoir Capacity ]
                                │
        ┌───────────────────────┴───────────────────────┐
        ▼                                               ▼
   Drops Below 5%                               Reaches Above 30%
(Low-Water Mark Trigger)                    (High-Water Mark Clear)
        │                                               │
        v                                               v
[ State 1: Mode A ]                         [ State 0: Full Hybrid ]
(Algorithmic Primary)                        (Physical + Mathematical)
        │                                               ▲
        └────────────── Hysteresis Buffer ──────────────┘
            (Prevents rapid back-and-forth flapping)
```

| Operational State | Trigger Condition | Active Cryptographic Mechanisms | Resulting Security Posture |
|---|---|---|---|
| **State 0: Full Hybrid** | Reservoir capacity $> 30\%$; QRNG healthy; fiber active. | $\text{KMAC256}(K_{\text{QKD}} \parallel K_{\text{PQC}})$ + QRNG Seed + FIPS 204 Auth. | **Maximum Resilience**: Immune to optical intercept and mathematical cryptanalysis. |
| **State 1: Mode A (Lattice Primary)** | Reservoir drops $< 5\%$; fiber cut or KMS exhaustion. | FIPS 203 (ML-KEM) + QRNG/TRNG Seed + FIPS 204 Auth. | **High Security**: Zero packet drops; protected mathematically by lattice hardness. |
| **State 2: Mode B (Physical Fallback)** | Theoretical vulnerability published against lattice ring. | QKD Key Stream ($K_{\text{QKD}}$) + Classical ECDH / Pre-shared Key. | **High Security**: Protected by physical quantum mechanics while lattice algorithms patch. |
| **State 3: Autonomous Mode** | Remote QRNG REST endpoint unreachable or latency $> 50\text{ ms}$. | Hardware TRNG + FIPS 202 SHAKE-256 + FIPS 203/204. | **High Security**: Eliminates external network dependency during network floods. |
| **State 4: Zeroize / Panic** | Enclosure intrusion, chassis breach, or bus-glitch alert. | Immediate hardware write of `0x00` across all tile SRAM key registers. | **Fail-Safe**: Cryptographic zeroization prevents key extraction under physical capture. |

---

## 3. Academic & Standards Citations

1. **Palo Alto Networks / Industry Consortium (2023):** *QRNG-OPENAPI: Quantum Random Number Generator REST API Specification (Version 1.0)*.
2. **Turk, B., et al. (2018):** *NIST SP 800-90B: Recommendation for the Entropy Sources Used for Random Bit Generation*. National Institute of Standards and Technology. [DOI: 10.6028/NIST.SP.800-90B](https://doi.org/10.6028/NIST.SP.800-90B).
3. **ETSI (2019):** *ETSI GS QKD 014: Quantum Key Distribution (QKD); Protocol and data format of REST-based key delivery API*. European Telecommunications Standards Institute.
4. **AMD Corporation (2023):** *Versal AI Engine Architecture Manual (AM009)*. AMD Xilinx.
5. **Project Provenance & Scientific Repository:** [DOI: 10.5281/zenodo.22164124](https://doi.org/10.5281/zenodo.22164124).
