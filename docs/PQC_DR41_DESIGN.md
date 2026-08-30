# DR41 Architecture & Design: ETSI GS QKD 004 / 015 Quantum Key Management System (Q-KMS) REST Lifecycle Engine

<div align="center">

![Standard: ETSI GS QKD 004](https://img.shields.io/badge/Standard-ETSI%20GS%20QKD%20004%20(V2.1.1)-005ea8)
![Standard: ETSI GS QKD 015](https://img.shields.io/badge/Standard-ETSI%20GS%20QKD%20015%20(Inter--KME)-purple)
![Hardware: AMD Phoenix NPU (AIE2 / XDNA1)](https://img.shields.io/badge/Target-AMD%20Phoenix%20NPU%20(AIE2%20%2F%20XDNA1)-red)
[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.22164124.svg)](https://doi.org/10.5281/zenodo.22164124)

</div>

---

## 1. Executive Summary & Quantum Lifecycle Mandate

Milestone **DR41** implements the **ETSI GS QKD 004 / 015 Quantum Key Management System (Q-KMS) REST Lifecycle Engine** on the AMD Phoenix NPU (AIE2 / XDNA1 Architecture).

It provides full compliance with the ETSI GS QKD 004 application interface (`OPEN_CONNECT`, `GET_KEY`, `GET_KEY_WITH_KEY_IDS`, `CLOSE`), enables multi-hop inter-KME quantum key relay (ETSI GS QKD 015), and enforces hardware-isolated multi-tenant key lifecycle transitions inside AIE2 MemTile SRAM.

---

## 2. ETSI Q-KMS Multi-Tenant Architecture & State Machine

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│  SECURE APPLICATION ENTITY (SAE A)           SECURE APPLICATION ENTITY (SAE B)         │
└───────────────────────┬───────────────────────────────────────┬────────────────────────┘
                        │ ETSI 004: OPEN_CONNECT / GET_KEY      │ ETSI 004: GET_KEY_WITH_IDS
                        ▼                                       ▼
┌────────────────────────────────────────────────────────────────────────────────────────┐
│  AIE2 ON-CHIP Q-KMS REST / JSON ROUTER (Tile 0,1 DMA Shim)                             │
└───────────────────────────────────────────┬────────────────────────────────────────────┘
                                            │
               ┌────────────────────────────┴────────────────────────────┐
               ▼                                                         ▼
┌───────────────────────────────────────────┐ ┌──────────────────────────────────────────┐
│  TENANT DOMAIN ALPHA (Row 1 MemTile 1,0)  │ │  TENANT DOMAIN BETA (Row 1 MemTile 1,1)   │
│   • 256-bit Quantum Keys (UUIDv4 Key IDs) │ │   • 512-bit Quantum Keys                 │
│   • Hardware ACL & Policy Engine          │ │   • Hardware ACL & Policy Engine         │
└─────────────────────┬─────────────────────┘ └────────────────────┬─────────────────────┘
                      │                                            │
                      \─────────────────────┬──────────────────────/
                                            ▼
┌────────────────────────────────────────────────────────────────────────────────────────┐
│  KEY LIFECYCLE FINITE STATE MACHINE (FSM):                                             │
│    RESERVOIR_INGRESS ──► ALLOCATED_ACTIVE ──► SUSPENDED ──► EXPIRED ──► ZEROIZED (0x00)│
└───────────────────────────────────────────┬────────────────────────────────────────────┘
                                            │
                                            ▼
┌────────────────────────────────────────────────────────────────────────────────────────┐
│  ETSI GS QKD 015 INTER-KME RELAY ENGINE: Hop-by-Hop ML-KEM-768 + OTP Quantum Key Relay │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Supported ETSI Interfaces

1. **ETSI GS QKD 004 (V2.1.1)**:
   - `OPEN_CONNECT(source_sae_id, destination_sae_id, qos)` $\rightarrow$ `status, key_stream_id`
   - `GET_KEY(key_stream_id, num_keys, key_size)` $\rightarrow$ `keys: [key_id, key_material]`
   - `GET_KEY_WITH_KEY_IDS(key_stream_id, key_ids)` $\rightarrow$ `keys: [key_id, key_material]`
   - `CLOSE(key_stream_id)` $\rightarrow$ `status` (Triggers hardware zeroization)

2. **ETSI GS QKD 015 (V2.1.1)**:
   - `RELAY_ENVELOPE`: Encapsulates a relayed target key $K_{AB}$ across node $C$ using $C_{\text{PQC}} = \text{ML-KEM-768.Encaps}(pk_C)$ and $C_{\text{OTP}} = K_{AB} \oplus K_{\text{relay}}$.

---

## 4. References & Standards Citations

1. **ETSI GS QKD 004 V2.1.1 (2020-08)**: *Quantum Key Distribution (QKD); Application Interface*.
2. **ETSI GS QKD 015 V2.1.1 (2022-04)**: *Quantum Key Distribution (QKD); Control Interface for Orchestration / Inter-KME*.
3. **Project Provenance & Scientific Repository:** [DOI: 10.5281/zenodo.22164124](https://doi.org/10.5281/zenodo.22164124).
