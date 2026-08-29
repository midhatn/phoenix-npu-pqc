# Hybrid PQC & QKD Hardware Roadmap (v1.1.0)
## Complete Standards Compliance, Architecture, and Design Requirements (DR) for 100% Device-Resident Hybrid Execution on AMD Phoenix NPU (AIE2 / XDNA1)

<div align="center">

![Standard: NIST FIPS 202 / 203 / 204](https://img.shields.io/badge/Standards-NIST%20FIPS%20202%20%2F%20203%20%2F%20204-005ea8)
![Standard: ETSI GS QKD 014 v1.1.1 / v1.3.1](https://img.shields.io/badge/QKD%20Standard-ETSI%20GS%20QKD%20014-purple)
![Standard: NIST SP 800-56C Rev 2](https://img.shields.io/badge/Key%20Combiner-NIST%20SP%20800--56C%20Rev%202-green)
![Target: AMD Phoenix NPU (AIE2 / XDNA1)](https://img.shields.io/badge/Hardware-AMD%20Phoenix%20AIE2%20(512--bit%20SIMD)-red)
![Residency: 100% On-Device Silicon](https://img.shields.io/badge/Residency-100%25%20On--Device%20(Zero%20Host%20Fallback)-brightgreen)

</div>

---

## 1. Executive Summary & Defense-in-Depth Rationale

Post-Quantum Cryptography (PQC) and Quantum Key Distribution (QKD) are often erroneously positioned as competing technologies. In reality, combining **FIPS 203 (ML-KEM)**, **FIPS 204 (ML-DSA)**, and **QKD (ETSI GS QKD 014)** into a unified, device-resident hardware pipeline provides the highest achievable security tier in modern cryptology: **Defense-in-Depth Quantum Resilience**.

```
                  +-------------------------------------------------------------+
                  |               FIPS 204 (ML-DSA-44/65/87)                    |
                  |     Authenticates Control Plane, Nodes, & QKD Key_IDs       |
                  +------------------------------+------------------------------+
                                                 |
                     +---------------------------+---------------------------+
                     |                                                       |
                     v                                                       v
     +-------------------------------+                       +-------------------------------+
     |   ETSI GS QKD 014 Ingress     |                       |    NIST FIPS 203 (ML-KEM)     |
     |   (Optical QKD Key Stream)    |                       |    (Lattice Key Exchange)     |
     |   K_QKD (Information-Theoretic|                       |    K_PQC (Algorithmic Defense |
     |   Physical Layer Secrecy)     |                       |    over Classical IP Network) |
     +---------------+---------------+                       +---------------+---------------+
                     |                                                       |
                     |  K_QKD (32 Bytes)                     K_PQC (32 Bytes)|
                     +----------------------->[ AIE2 Tile ]<-----------------+
                                              [ DR9 Keccak]
                                              [ Fusing Hub]
                                                    |
                                                    v  NIST SP 800-56C Rev. 2 Two-Step KDF
                                         +---------------------+
                                         |       K_Final       |
                                         |  (256-bit AES Key)  |
                                         +----------+----------+
                                                    |
                                                    v
                                         [ DR10 Sealed Zeroize ]
                                         (SRAM Wiped on Close)
```

### The Two Fundamental Cryptographic Vulnerabilities Solved:

1. **Solving QKD's Authentication Dilemma (MitM Prevention)**:
   * *The Problem*: Quantum mechanics guarantees that an eavesdropper cannot intercept photons without detection, but QKD **cannot authenticate who is at the other end of the fiber**. Historically, QKD used symmetric Wegman-Carter MACs, requiring pre-shared keys and creating a distribution chicken-and-egg dilemma.
   * *The Solution*: **NIST FIPS 204 (ML-DSA)** runs on AIE2 hardware to digitally sign session establishment requests, endpoint certificates, and ETSI 014 `key_ID` manifests. This enables quantum-safe asymmetric authentication with zero pre-shared symmetric keys.

2. **Dual-Layer Confidentiality (Eliminating Single Points of Failure)**:
   * *The Problem*: If a mathematical or algorithmic breakthrough emerges against lattice problems ($R	ext{-LWE}$ / $M	ext{-LWE}$), pure PQC is compromised. Conversely, if an optical physical attack (detector blinding, Trojan horse fiber probing, or side-channel tapping) breaches QKD hardware, pure QKD is compromised.
   * *The Solution*: $K_{	ext{Final}}$ is derived using a NIST-approved multi-key combiner:
     $$K_{	ext{Final}} = 	ext{KMAC256}(K_{	ext{QKD}} \parallel K_{	ext{PQC}}, 	ext{Context}=	ext{key\_ID} \parallel 	ext{Epoch}, S=	ext{"ETSI-QKD-PQC-COMBINER"})$$
     If *either* physical QKD or mathematical ML-KEM remains secure, $K_{	ext{Final}}$ remains provably secure.

---

## 2. Complete Standards & Compliance Matrix

This roadmap commits to strict compliance with all finalized international standards across PQC, QKD, Key Combiners, and Microarchitectural Isolation:

| Standard / Body | Scope & Title | Role in Hybrid Pipeline |
| :--- | :--- | :--- |
| **NIST FIPS 202** | SHA-3 Standard: Permutation-Based Hash and Extendable-Output Functions | Hardware Keccak-f[1600] 24-round core, KMAC256, and SHAKE-128/256 engine on AIE2. |
| **NIST FIPS 203** | Module-Lattice-Based Key-Encapsulation Mechanism (ML-KEM) | ML-KEM-512, 768, 1024 on-device encapsulation and decapsulation with IND-CCA2 implicit rejection. |
| **NIST FIPS 204** | Module-Lattice-Based Digital Signature Algorithm (ML-DSA) | ML-DSA-44, 65, 87 on-device signing and verification for QKD node and channel authentication. |
| **ETSI GS QKD 014** (v1.1.1 & v1.3.1) | Quantum Key Distribution (QKD); Protocol and data format of REST-based key delivery API | Standard interface for Key Management Entity (KME) key requests (`/enc_keys`, `/dec_keys`) and UUID key container parsing. |
| **ETSI GS QKD 004** | Quantum Key Distribution (QKD); Application Interface | Standard application-layer primitives for QKD buffer queries and synchronization. |
| **ETSI GS QKD 015** | Quantum Key Distribution (QKD); Security Framework | Threat models, key lifecycle management, and boundary isolation for QKD nodes. |
| **ITU-T Y.3800–Y.3804** | Quantum Key Distribution Networks (QKDN) Architecture & Key Management | Architectural layering of Quantum Layer, Key Management Layer, and Application Layer. |
| **NIST SP 800-56C Rev. 2** | Recommendation for Key-Derivation Methods in Key-Establishment Schemes | Two-step extraction-then-expansion multi-key combiner specifications (KMAC256 / SHAKE256). |
| **NIST SP 800-227 / BSI TR-02102** | Recommendations for Hybrid Key Encapsulation Mechanisms | Dual-PRF IND-CCA2 combiner security proofs ensuring non-degradation of component entropy. |
| **IETF RFC 9370 / RFC 8784** | Multiple Key Encapsulation Mechanisms & Mixing Pre-Shared Keys in IKEv2 | Standardized multi-key payload layouts and cryptographic binding contexts. |
| **ISO/IEC 23837-1 / 23837-2** | Quantum key distribution — Security requirements, test and evaluation methods | Physical and logical testing bounds for quantum entropy validation. |

---

## 3. Microarchitectural Mapping to AMD Phoenix NPU (AIE2 / XDNA1)

To prevent side-channel leakage, cold-boot attacks, and CPU cache snooping, **zero bytes of raw quantum keys ($K_{	ext{QKD}}$), lattice secrets ($K_{	ext{PQC}}$), or combined keys ($K_{	ext{Final}}$) ever touch the host CPU cache or DDR RAM in plaintext**.

```
+---------------------------------------------------------------------------------------------------+
|                            AMD PHOENIX AIE2 4x4 TILE MATRIX (XDNA1)                               |
+---------------------------------------------------------------------------------------------------+
| Row 0: SHIM NOC INGRESS & EGRESS                                                                  |
|   Tile (0,0): Host PCIe Ingress DMA      Tile (0,1): ETSI 014 QKD Stream Ingress                   |
|   Tile (0,2): ML-KEM / ML-DSA ObjectFIFO Tile (0,3): Authenticated Result Egress                  |
+---------------------------------------------------------------------------------------------------+
| Row 1: RING ARITHMETIC & LATTICE EXPANSION                                                        |
|   Tile (1,0): DR0 M33 Ring Product       Tile (1,1): DR1 ExpandA Matrix Engine                    |
|   Tile (1,2): DR2a SampleNTT Engine      Tile (1,3): DR2b Centered Binomial Noise (CBD3)          |
+---------------------------------------------------------------------------------------------------+
| Row 2: POST-QUANTUM KEY ENCAPSULATION (FIPS 203)                                                  |
|   Tile (2,0): DR5 ML-KEM-512 KeyGen      Tile (2,1): DR6 ML-KEM-512 Encaps                        |
|   Tile (2,2): DR7 ML-KEM-512 Decaps      Tile (2,3): DR8 Unified ML-KEM-768/1024 CCA Engine       |
+---------------------------------------------------------------------------------------------------+
| Row 3: HYBRID AUTHENTICATION, FUSING & SEALED LIFECYCLE                                           |
|   Tile (3,0): DR11/DR12 ML-DSA-44 Sign   Tile (3,1): DR14/DR15 ML-DSA-65/87 Verify                |
|   Tile (3,2): DR9/DR18 Keccak SP 800-56C Tile (3,3): DR10/DR19 Sealed Lifecycle & Zeroizer        |
|               (Dual-Key Fusing Hub)                  (Hardware Memory Scrubber)                   |
+---------------------------------------------------------------------------------------------------+
```

---

## 4. Design Requirements (DR) Roadmap to 100% NPU Residency

### Completed & Certified Baseline (Milestones DR0–DR15)
* [x] **DR0**: AIE2 M33 Polynomial Ring Product Acceleration ($R_q$ modular multiplication).
* [x] **DR1**: ML-DSA-44 ExpandA Matrix Expansion & RejNTT Sampler on AIE2 SIMD.
* [x] **DR2a–DR2d**: ML-KEM-512 SampleNTT, Centered Binomial Noise (CBD), KeyGen Row, and K-PKE KeyGen.
* [x] **DR3–DR4**: K-PKE Vector Encrypt & Decrypt graphs on physical silicon.
* [x] **DR5–DR7**: Complete NIST FIPS 203 ML-KEM-512 KeyGen, Encaps, and Decaps with implicit rejection.
* [x] **DR8**: Unified Parameter Scaling for ML-KEM-768 and ML-KEM-1024.
* [x] **DR9**: NIST FIPS 202 SHA-3 (224/256/384/512) and SHAKE-128/256 Service Graph on AIE2.
* [x] **DR10**: Sealed Lifecycle, Memory Zeroization Scrubber, and Hardware CRC32 Validation.
* [x] **DR11–DR13**: NIST FIPS 204 ML-DSA-44 KeyGen, Fiat-Shamir with Aborts Sign, and Constant-Time Verify.
* [x] **DR14–DR15**: Full NIST FIPS 204 ML-DSA-65 and ML-DSA-87 Physical Silicon Validation.

---

### New Milestones for Hybrid QKD + PQC Pipeline (Milestones DR16–DR20)

#### Milestone DR16: ETSI GS QKD 014 Key Container Parser & Sealed Ingress Graph
* **Standard**: ETSI GS QKD 014 v1.1.1 / v1.3.1.
* **Objective**: Ingest standard ETSI 014 Key Containers (`key_ID`, `key`, `metadata`) into AIE2 tile SRAM via ObjectFIFO without host CPU memory exposure.
* **Deliverables**:
  * `phoenix_sdr_dsp/pqc/dr16_etsi_qkd014_abi.py`: Binary & JSON packet layouts for ETSI 014 key descriptors.
  * `phoenix_sdr_dsp/pqc/dr16_etsi_qkd014_graph.py`: AIE2 DMA ingress graph parsing UUIDs, validating epoch counters, and isolating key material in Tile (0,1).
  * `tests/pqc_device_resident/test_dr16_etsi_qkd014_silicon.py`: Silicon validation test suite.

#### Milestone DR17: ML-DSA Asymmetric QKD Control Plane Authenticator Graph
* **Standard**: NIST FIPS 204 (ML-DSA) & ETSI GS QKD 015.
* **Objective**: Eliminate QKD's pre-shared key dilemma by signing and verifying QKD session negotiation nonces, node certificates, and `key_ID` transmissions on AIE2 vector tiles.
* **Deliverables**:
  * `phoenix_sdr_dsp/pqc/dr17_mldsa_qkd_auth_abi.py`: Authentication header format binding QKD `key_ID` to node identity.
  * `phoenix_sdr_dsp/pqc/dr17_mldsa_qkd_auth_graph.py`: AIE2 graph executing ML-DSA-44/65/87 verification on incoming QKD metadata.
  * `tests/pqc_device_resident/test_dr17_mldsa_qkd_auth_silicon.py`: Anti-MitM silicon validation tests.

#### Milestone DR18: NIST SP 800-56C Rev. 2 / SP 800-227 On-Device Dual-Key Combiner Graph
* **Standard**: NIST SP 800-56C Rev. 2 (Section 4.1 / 4.2), NIST SP 800-227, BSI TR-02102.
* **Objective**: On-tile fusion of $K_{	ext{QKD}}$ (from DR16) and $K_{	ext{PQC}}$ (from DR7/DR8) inside Tile (3,2) using the DR9 Keccak engine with strict domain separation and session context binding.
* **Formula**:
  $$K_{	ext{Final}} = 	ext{KMAC256}\Big(K_{	ext{QKD}} \parallel K_{	ext{PQC}}, 	ext{Context}=	ext{key\_ID} \parallel 	ext{Epoch} \parallel 	ext{SAE\_Master} \parallel 	ext{SAE\_Slave}, S=	ext{"ETSI-QKD-PQC-COMBINER"}\Big)$$
* **Deliverables**:
  * `phoenix_sdr_dsp/pqc/dr18_dual_key_combiner_abi.py`: Combiner input/output staging layout.
  * `phoenix_sdr_dsp/pqc/dr18_dual_key_combiner_graph.py`: Multi-stream AIE2 fusing graph.
  * `tests/pqc_device_resident/test_dr18_dual_key_combiner_silicon.py`: Dual-PRF and entropy-retention silicon test suite.

#### Milestone DR19: Full-Duplex Hybrid QKD-PQC Session Orchestrator & Zero-Leakage Teardown
* **Standard**: IETF RFC 9370 / RFC 8784, ETSI GS QKD 014.
* **Objective**: End-to-end orchestration of the complete defense-in-depth pipeline (Ingress $ightarrow$ Auth $ightarrow$ KEM $ightarrow$ Combine $ightarrow$ AES-GCM Ingress $ightarrow$ DR10 Zeroize).
* **Deliverables**:
  * `phoenix_sdr_dsp/pqc/dr19_hybrid_session_orchestrator.py`: High-level session manager driving AIE2 runtime.
  * `tests/pqc_device_resident/test_dr19_hybrid_session_silicon.py`: End-to-end dual-node session simulation on physical hardware.

#### Milestone DR20: QKDN Interoperability Test Suite & Master Silicon Certification
* **Standard**: ISO/IEC 23837-1/2, ITU-T Y.3800, NIST ACVP.
* **Objective**: Comprehensive certification against mock ETSI 014 KME servers, active optical tampering injections, and side-channel leakage tests.
* **Deliverables**:
  * `run_all_hybrid_qkd_pqc_tests.py`: Master test harness for all 24 hardware gates (DR0–DR20).
  * `docs/HYBRID_QKD_PQC_SILICON_REPORT.md`: Comprehensive academic reproducibility report.

---

## 5. Verification & Mathematical Soundness Proofs

1. **Dual-PRF Security Guarantee**:
   Let $\mathcal{A}$ be an adversary with polynomial resources. If ML-KEM is IND-CCA2 secure AND/OR QKD is Information-Theoretically Secure, the advantage of $\mathcal{A}$ distinguishing $K_{	ext{Final}}$ from a random string is bounded by:
   $$\mathbf{Adv}_{	ext{Hybrid}}(\mathcal{A}) \le \min\Big(\mathbf{Adv}_{	ext{ML-KEM}}^{	ext{IND-CCA2}}(\mathcal{A}),\; \mathbf{Adv}_{	ext{QKD}}^{	ext{ITS}}(\mathcal{A})\Big) + \epsilon_{	ext{KMAC}}$$

2. **Memory Remanence Elimination**:
   Upon session teardown, invocation of the DR10 Hardware Zeroization graph unconditionally clears:
   * 16 worker tile data SRAMs ($16 	imes 64	ext{ KiB} = 1	ext{ MiB}$).
   * All ObjectFIFO ping-pong descriptors and stream switch registers.
   * Execution verified by on-device hardware CRC32 computation returning expected clean state checksum (`0xE533F258`).

---

## 6. Implementation Timeline & Versioning

* **v1.0.0 (Current)**: 100% PQC Silicon Certified (NIST FIPS 202, 203, 204 across 19 Gates, Milestones DR0–DR15).
* **v1.1.0 (Target)**: Hybrid QKD + PQC Defense-in-Depth Integration (ETSI GS QKD 014 Ingress, ML-DSA QKD Authentication, NIST SP 800-56C Combiner, Milestones DR16–DR20).
