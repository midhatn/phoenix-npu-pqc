# Hybrid PQC & QKD Hardware Roadmap (v1.1.0 Released · v1.2.0 Planned)
## Complete Standards Compliance, Architecture, and Design Requirements (DR) for Hybrid Execution on AMD Phoenix NPU (AIE2 / XDNA1)

<div align="center">

![Standard: NIST FIPS 202 / 203 / 204 / 205 / 206](https://img.shields.io/badge/Standards-NIST%20FIPS%20202%2F203%2F204%2F205%2F206-005ea8)
![Standard: ETSI GS QKD 014 / 015](https://img.shields.io/badge/QKD%20Standard-ETSI%20GS%20QKD%20014%20%2F%20015-purple)
![Standard: NIST SP 800-56C Rev 2 · SP 800-227](https://img.shields.io/badge/Key%20Combiner-NIST%20SP%20800--56C%20Rev%202%20%C2%B7%20SP%20800--227-green)
![Entropy: QRNG-OPENAPI v1.0](https://img.shields.io/badge/Entropy-QRNG--OPENAPI%20v1.0-blueviolet)
![Target: AMD Phoenix NPU (AIE2 / XDNA1)](https://img.shields.io/badge/Hardware-AMD%20Phoenix%20AIE2%20(512--bit%20SIMD)-red)
![Residency: 100% On-Device Silicon](https://img.shields.io/badge/Residency-100%25%20On--Device%20(Zero%20Host%20Fallback)-brightgreen)
![Status: v1.1.0 Certified (839/839 PASS)](https://img.shields.io/badge/Status-v1.1.0%20Certified%20%C2%B7%20839%2F839%20PASS-brightgreen)
[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.22162273.svg)](https://doi.org/10.5281/zenodo.22162273)

</div>

---

## 1. Executive Summary & Defense-in-Depth Rationale

Post-Quantum Cryptography (PQC) and Quantum Key Distribution (QKD) are frequently mischaracterized as competing paradigms. Combining **FIPS 203 (ML-KEM)**, **FIPS 204 (ML-DSA)**, **QKD (ETSI GS QKD 014)**, and **QRNG-OPENAPI entropy ingestion** into a unified hardware pipeline provides the highest achievable assurance tier in modern cryptology: **Defense-in-Depth Quantum Resilience**.

### Execution Domain Separation (Audit-Safe Boundary)

To maintain rigorous compliance with accelerator design models, the architecture maintains a strict boundary between transport I/O and cryptographic computation:

* **Sealed Host Ingress Layer (Network & Transport I/O)**: Handles TCP/IP network transport, HTTP/REST endpoints, mTLS handshakes, and JSON parsing for external appliances (QRNG-OPENAPI and ETSI GS QKD 014 KMS). Keys and entropy blocks are transferred directly to locked device memory via XRT ObjectFifos and immediately zeroized on the host.
* **Device-Resident Silicon Layer (AIE2 Compute Array)**: All polynomial vector arithmetic, Keccak permutations, rejection sampling, lattice NTT transforms, signature verification, and hybrid key derivation execute 100% on silicon with zero host computation or memory spilling.

```
+───────────────────────────────────────────────────────────────────────────────────────────+
│                               SEALED HOST INGRESS LAYER                                   │
│  [ QRNG-OPENAPI Ingress Daemon ]                   [ ETSI GS QKD 014 KMS Client ]         │
│   - TLS 1.3 / mTLS REST Ingestion                   - REST / JSON Ingress Engine          │
│   - SP 800-90B Preflight Health                     - Key_ID Metadata & Routing           │
+───────────────────────────┬───────────────────────────────────────────┬───────────────────+
                            │ Zero-Copy XRT ObjectFifo DMA              │
════════════════════════════╪═══════════════════════════════════════════╪═══════════════════
                            │ SILICON BOUNDARY (AIE2 TILE ARRAY)        │
+───────────────────────────▼───────────────────────────────────────────▼───────────────────+
│                                 FIPS 204 (ML-DSA-44/65/87)                                │
│                     Authenticates Control Plane, Nodes, & QKD Key_IDs                     │
+─────────────────────────────────────────────┬─────────────────────────────────────────────+
                                              │
                      +-----------------------+-----------------------+
                      │                                               │
                      v                                               v
+───────────────────────────────────────────+   +───────────────────────────────────────────+
│         DR27b Key Reservoir Pool          │   │          NIST FIPS 203 (ML-KEM)           │
│   (On-Device Token-Bucket Ring Buffer)    │   │         (Module Lattice Exchange)         │
│       K_QKD (Physical Layer Secrecy)      │   │    K_PQC (Algorithmic Network Defense)    │
+---------------------+---------------------+   +---------------------+---------------------+
                      │                                               │
                      │ K_QKD (32 Bytes)                              │ K_PQC (32 Bytes)
                      \                       /───────────────────────/
                       \                     /
                        v                   v
+───────────────────────────────────────────────────────────────────────────────────────────+
│                             DR18 SP 800-56C Rev. 2 Dual KDF                              │
│                    K_Final = KMAC256(K_QKD || K_PQC, Context_String)                      │
+─────────────────────────────────────────────┬─────────────────────────────────────────────+
                                              │
                                              v
+───────────────────────────────────────────────────────────────────────────────────────────+
│                              DR10 Sealed Zeroization Core                                 │
│                Hardware Register Zeroization (0x00 Overwrite on Session Close)            │
+───────────────────────────────────────────────────────────────────────────────────────────+
```

### The Architectural Mandate (The "WHY")

This architecture ensures full physical and mathematical resilience: if the physical optical fiber fails, FIPS 203 protects the channel; if lattice mathematics develops a theoretical vulnerability, QKD and QRNG entropy protect the payload.

#### Fundamental Cryptographic Vulnerabilities Solved:

1. **Solving QKD's Authentication Dilemma (MitM Prevention)**:
   * **The Problem**: Quantum mechanics guarantees eavesdropper detection on optical links, but QKD cannot authenticate channel endpoints natively. Pre-shared symmetric Wegman-Carter MACs create an unscalable distribution loop.
   * **The Solution**: NIST FIPS 204 (ML-DSA) runs on AIE2 hardware to digitally sign session establishment requests, endpoint certificates, and ETSI 014 `key_ID` manifests. This establishes quantum-safe asymmetric authentication with zero pre-shared keys.

2. **Solving Entropy Starvation & PRNG State Degradation**:
   * **The Problem**: Host OS PRNGs are susceptible to virtual-machine cloning, low initial entropy, or state recovery attacks.
   * **The Solution**: Seeding is driven by true quantum randomness via QRNG-OPENAPI (validated against NIST SP 800-90B health metrics). Conditioning via FIPS 202 (SHAKE-256) provides full-entropy private keys and nonces to the lattice engines.

3. **Dual-Layer Physical & Mathematical Secrecy**:
   * **The Problem**: Physical attacks (detector blinding, fiber backscatter, side-channel probing) threaten optical QKD nodes, while algebraic advances threaten mathematical lattices.
   * **The Solution**: $K_{\text{Final}}$ is derived using a NIST SP 800-56C Rev. 2 / SP 800-227 compliant combiner:
     $$K_{\text{Final}} = \text{KMAC256}\Big(K_{\text{QKD}} \parallel K_{\text{PQC}}, \text{Context}\Big)$$
     Confidentiality remains intact even if either physical optical fiber or mathematical lattice problems are completely compromised.

---

## 2. Standards Conformance Matrix

| Standard / Organization | Specification Reference | Role in Hybrid Pipeline | AIE2 Implementation Milestone | Status |
|---|---|---|---|:---:|
| **Palo Alto / Consortium** | **QRNG-OPENAPI (v1.0)** | REST Entropy Ingestion (`/v1/entropy`, `/v1/healthtest`) | **DR27a** (Host Ingress Daemon) | *Planned v1.2* |
| **ETSI** | **ETSI GS QKD 014 (v1.1.1 / v1.3.1)** | REST Key Delivery API for KME Ingress | **DR16** (Sealed Key Ingress) | **100% PASS** |
| **ETSI** | **ETSI GS QKD 015 (v2.1.1)** | Orchestration and Control-Plane Security | **DR17** (Asymmetric Auth Control) | **100% PASS** |
| **NIST** | **FIPS PUB 204 (2024)** | ML-DSA Digital Signature Verification | **DR11–DR15, DR17** (Auth Hub) | **100% PASS** |
| **NIST** | **FIPS PUB 203 (2024)** | ML-KEM Key Encapsulation Mechanism | **DR2d, DR3–DR8** (Lattice KEM) | **100% PASS** |
| **NIST** | **FIPS PUB 202 (2015)** | SHA-3 / SHAKE / Keccak-f[1600] Permutations | **DR9, DR18, DR25** (Hashing/Expansion) | **100% PASS** |
| **NIST** | **SP 800-56C Rev. 2 (2020)** | Two-Step Key Extraction and Expansion | **DR18** (Dual Key Combiner) | **100% PASS** |
| **NIST** | **SP 800-227 (2024)** | Multi-Key Encapsulation Combiners | **DR18** (Hybrid Session KDF) | **100% PASS** |
| **NIST** | **SP 800-208 / RFC 8554** | Stateful Hash Signatures (LMS Verification Only) | **DR28** (Immutable Root of Trust) | *Planned v1.2* |
| **NSA** | **CNSA 2.0 (2022/2024)** | Category 5 Mandate (ML-KEM-1024, ML-DSA-87) | **DR29** (Distributed Memory Engine) | *Planned v1.2* |
| **IETF** | **RFC 9370 / RFC 8784 (2023)** | Multi-KEM IKEv2 / IPsec Protocol Models | **DR19, DR24** (Session Orchestrator) | **100% PASS** |
| **3GPP** | **TS 33.501 (Rel-18/19)** | 5G/6G Core Network SUCI Post-Quantum Security | **DR30** (Telecom Interconnect) | *Planned v1.2* |
| **NIST** | **FIPS PUB 205 (2024)** | Stateless Hash-Based Signatures (SLH-DSA) | **DR21** (SPHINCS+ Engine) | *Planned v1.2* |
| **NIST** | **FIPS PUB 206 (2025)** | Fast-Fourier Lattice Signatures (FN-DSA) | **DR22** (Falcon Verification Core) | *Planned v1.2* |

---

## 3. Five Core Modules in v1.1.0 (23 Silicon Gates · 839 Test Cases)

### Module 1: NIST FIPS 202 (SHA-3 / SHAKE — Milestone DR9)
* **Status**: 100% Silicon Certified (**122 / 122 PASS**).

### Module 2: NIST FIPS 203 (ML-KEM — Milestones DR2d, DR3–DR8)
* **Status**: 100% Silicon Certified (**210 / 210 PASS**).

### Module 3: NIST FIPS 204 (ML-DSA — Milestones DR11–DR15)
* **Status**: 100% Silicon Certified (**255 / 255 PASS**).

### Module 4: Hardware Lifecycle & Foundation (Milestones DR0, DR1, DR2a–DR2c, DR10)
* **Status**: 100% Silicon Certified (**149 / 149 PASS**).

### Module 5: Hybrid QKD & Post-Quantum Defense-in-Depth (Milestones DR16–DR20)
* **Milestone DR16 (Gate 19)**: ETSI GS QKD 014 Sealed Ingress Kernel (`dr16_etsi_qkd014_service.cc`) — **25 / 25 PASS**.
* **Milestone DR17 (Gate 20)**: ML-DSA Asymmetric QKD Control Authenticator (`dr17_mldsa_qkd_auth_service.cc`) — **25 / 25 PASS**.
* **Milestone DR18 (Gate 21)**: NIST SP 800-56C Dual Combiner (`dr18_dual_key_combiner_service.cc`) — **30 / 30 PASS**.
* **Milestone DR19 (Gate 22)**: Full-Duplex Session Orchestrator (`dr19_hybrid_session_service.cc`) — **20 / 20 PASS**.
* **Milestone DR20 (Gate 23)**: Universal Master Silicon Suite (`run_all_silicon_tests.py`) — **839 / 839 PASS in 36.86s**.

---

## 4. Operational Resilience & Hysteresis Control Loop

To prevent session re-negotiation spikes ("state flapping") when QKD key arrival rates fluctuate under high wire-speed network loads, the state machine incorporates a strict hysteresis loop tied to the **DR27b Key Reservoir**:

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
| **State 1: Degraded Mode A (Algorithmic Primary)** | Reservoir capacity drops $< 5\%$; fiber cut or KMS exhaustion. | FIPS 203 (ML-KEM) + QRNG/TRNG Seed + FIPS 204 Auth. | **High Security**: Zero packet drops; protected mathematically by lattice hardness. |
| **State 2: Degraded Mode B (Physical Fallback)** | Theoretical vulnerability published against Module Lattice ring. | QKD Key Stream ($K_{\text{QKD}}$) + Classical ECDH / Pre-shared Key. | **High Security**: Protected by physical quantum mechanics while lattice algorithms patch. |
| **State 3: Autonomous Mode** | Remote QRNG REST endpoint unreachable or latency $> 50\text{ ms}$. | Hardware TRNG + FIPS 202 SHAKE-256 + FIPS 203/204. | **High Security**: Eliminates external network dependency during network floods. |
| **State 4: Zeroize / Panic** | Enclosure intrusion, chassis breach, or bus-glitch alert. | Immediate hardware write of `0x00` across all tile SRAM key registers. | **Fail-Safe**: Cryptographic zeroization prevents key extraction under physical capture. |

---

## 5. Future Roadmap: Version 1.2.0 (Planned Milestones)

```
========================================================================================================================
                                     PHOENIX NPU PQC & QKD ROADMAP: v1.2.0
========================================================================================================================

[MODULE 6] Conservative & Compact PQC Extensions
  • Milestone DR21: NIST FIPS 205 (SLH-DSA / SPHINCS+) On-Device Tree Hashing Engine on AIE2 Keccak Core.
  • Milestone DR22: NIST FIPS 206 (FN-DSA / FALCON) Precision-Safe Verification Engine & Constant-Time Signing.

[MODULE 7] Production Network Offload & Cryptographic Provider Subsystems
  • Milestone DR23: OpenSSL 3.x Native Provider Plugin (`phoenix-pqc-provider`) & PKCS#11 HSM Token.
  • Milestone DR24: Quantum-Safe Kernel-Bypass WireGuard / IPsec Inline VPN Co-Processor (RFC 9370 Multi-KEM).

[MODULE 8] Advanced Physical Security & Multi-Generation Hardware Scaling
  • Milestone DR25: Higher-Order Masked Polynomial Arithmetic & On-Chip Local SHAKE PRNG Entropy Expansion.
  • Milestone DR26: AMD XDNA 2 (Ryzen AI 300 / Strix Point - 50 TOPS) & AMD Alveo V70 Datacenter Port.

[MODULE 9] True Quantum Entropy, Root-of-Trust, & Government Standards
  • Milestone DR27a: QRNG-OPENAPI Sealed Host Ingress Daemon (REST, mTLS, & SP 800-90B Health Tests).
  • Milestone DR27b: NPU-Resident Token-Bucket Key Reservoir with Hysteresis & Anti-Flapping Logic.
  • Milestone DR28: NIST SP 800-208 (LMS) Stateless Firmware & Bitstream Verification Engine (Secure Boot).
  • Milestone DR29: NSA CNSA 2.0 Level 5 Multi-Tile Distributed Memory Engine (ML-KEM-1024, ML-DSA-87).
  • Milestone DR30: 3GPP TS 33.501 5G/6G Core Network SUCI De-Concealment Co-Processor.
========================================================================================================================
```

### Detailed v1.2.0 Milestone Specifications:

#### Milestone DR21: NIST FIPS 205 (SLH-DSA / SPHINCS+) On-Device Tree Hashing
* **Standard**: NIST FIPS 205 (SLH-DSA-SHAKE-128s/f, 192s/f, 256s/f).
* **Objective**: Stateless hash-based signatures providing a conservative security foundation independent of lattice assumptions.
* **Architecture**: SPHINCS+ W-OTS+ and FORS tree hashing mapped across all 20 AIE2 compute tiles in parallel using the native Keccak-f[1600] SIMD core.

#### Milestone DR22: NIST FIPS 206 (FN-DSA / FALCON) Precision-Safe Verification Engine
* **Standard**: NIST FIPS 206 (FN-DSA-512 and FN-DSA-1024).
* **Objective**: Ultra-compact lattice signatures (~666 bytes) using Fast Fourier sampling over NTRU lattices.
* **Architecture & Precision Hardening**: Native 512-bit vector floating-point (FP32) butterfly pipelines are utilized strictly for signature verification. Signature generation utilizes emulated 53-bit double precision (FP64) / fixed-point routines with constant-time cycle enforcement to prevent timing side channels on denormalized floats.

#### Milestone DR23: OpenSSL 3.x Provider Plugin & PKCS#11 HSM Integration
* **Standard**: OpenSSL 3.0+ Provider Architecture & PKCS#11 v3.0.
* **Objective**: Direct drop-in acceleration for enterprise software (Nginx, Envoy, Apache, Chromium, OpenSSH).
* **Deliverables**: `phoenix-pqc-provider.dll` / `libphoenix_pqc.so` exposing `X25519MLKEM768` and `ML-DSA-65/87` certificates.

#### Milestone DR24: Quantum-Safe WireGuard / IPsec Kernel-Bypass Inline VPN Co-Processor
* **Standard**: IETF RFC 9370 / RFC 8784 / WireGuard Protocol.
* **Objective**: Low-latency VPN tunnel adapter offloading packet encryption (AES-256-GCM / ChaCha20) and continuous background ML-KEM + QKD session re-keying to the NPU without CPU interrupts.

#### Milestone DR25: Higher-Order Masking & On-Chip Local PRNG Entropy Expansion
* **Objective**: Mathematical side-channel resistance against Differential Power Analysis (DPA/CPA) and laser/clock fault injection attacks without exhausting entropy.
* **Architecture**: Implements 1st- and 2nd-order polynomial blinding. To prevent bus starvation during continuous share refreshes, external QRNG seeds are expanded locally across tiles using dedicated FIPS 202 SHAKE-128 PRNG stream generators executing directly in tile microcode.

#### Milestone DR26: AMD XDNA 2 & AMD Alveo V70 Multi-Architecture Scaling
* **Objective**: Scale from client APUs (Phoenix XDNA 1 / 20 tiles) to next-gen client (Strix Point XDNA 2 / 32 tiles / 50 TOPS) and datacenter accelerators (Alveo V70 / 304 tiles / 75W).

#### Milestone DR27a: QRNG-OPENAPI Sealed Host Ingress Daemon
* **Standards**: Palo Alto Networks QRNG-OPENAPI v1.0 & NIST SP 800-90B.
* **Objective**: Host-side background service handling HTTPS/mTLS connections to external QRNG appliances.
* **Deliverables**: Ingests entropy blocks via `POST /v1/entropy`, runs continuous NIST SP 800-90B health evaluations via `GET /v1/healthtest`, and streams conditioned seeds to the NPU via XRT ObjectFifos with zero host memory persistence.

#### Milestone DR27b: NPU-Resident Token-Bucket Key Reservoir
* **Standard**: ETSI GS QKD 014 (Key Buffer Management).
* **Objective**: In-memory, tile-accessible key pool decoupling discrete optical key arrival from line-rate encryption throughput.
* **Architecture**: Implements the 5% / 30% hysteresis state loop, tracks key lifetimes, and manages atomic memory zeroization upon hardware tamper alerts.

#### Milestone DR28: NIST SP 800-208 (LMS) Stateless Verification Engine
* **Standards**: NIST SP 800-208 / RFC 8554 (Leighton-Micali Signatures) & IETF RATS (RFC 9334).
* **Objective**: Immutable secure boot and AIE2 kernel bitstream authentication.
* **Scope Boundary**: Strictly scoped as a Signature Verifier. Eliminates non-volatile leaf-state tracking hazards by enforcing that stateful signature generation occurs offline in air-gapped HSMs.

#### Milestone DR29: NSA CNSA 2.0 Level 5 Multi-Tile Distributed Memory Engine
* **Standard**: NSA Commercial National Security Algorithm Suite 2.0 (Category 5).
* **Objective**: Full support for ML-KEM-1024 and ML-DSA-87 without overflowing 64 KB tile SRAM limits.
* **Architecture**: Partitions the 56-polynomial matrix ($A \in R_q^{8 \times 7}$) across a 4-tile compute cluster using memory-mapped AXI interconnects, guaranteeing that per-tile working sets remain under 44 KB.

#### Milestone DR30: 3GPP TS 33.501 5G/6G Core Network SUCI Co-Processor
* **Standard**: 3GPP TS 33.501 (Release 18/19 Security Architecture).
* **Objective**: Hardware acceleration for Subscription Concealed Identifier (SUCI) de-concealment using ML-KEM-768/1024 within 5G core network functions (UDM/AUSF).
* **Deliverables**: Microsecond-latency subscriber profile decapsulation pipeline for telecom edge gateways.

---

## 6. Version History & Milestone Release Matrix

| Version | Status | Modules Included | Milestones | Physical Silicon Status |
|---|---|---|---|:---:|
| **v1.0.0** | **Released** | Modules 1, 2, 3, 4 (PQC Core) | **DR0–DR15** (19 Gates) | **736 / 736 PASS** (23.98s) |
| **v1.1.0** | **Released (Current)** | Modules 1–5 (PQC + Hybrid QKD) | **DR0–DR20** (23 Gates) | **839 / 839 PASS** (36.86s) |
| **v1.2.0** | **Planned** | Modules 6–9 (Extensions, Providers, Entropy, CNSA 2.0) | **DR21–DR30** (36 Gates) | *In Development* |
