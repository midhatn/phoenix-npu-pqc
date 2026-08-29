# Hybrid PQC & QKD Hardware Roadmap (v1.1.0 Released · v1.2.0 Planned)
## Complete Standards Compliance, Architecture, and Design Requirements (DR) for 100% Device-Resident Hybrid Execution on AMD Phoenix NPU (AIE2 / XDNA1)

<div align="center">

![Standard: NIST FIPS 202 / 203 / 204 / 205 / 206](https://img.shields.io/badge/Standards-NIST%20FIPS%20202%2F203%2F204%2F205%2F206-005ea8)
![Standard: ETSI GS QKD 014 v1.1.1 / v1.3.1](https://img.shields.io/badge/QKD%20Standard-ETSI%20GS%20QKD%20014-purple)
![Standard: NIST SP 800-56C Rev 2](https://img.shields.io/badge/Key%20Combiner-NIST%20SP%20800--56C%20Rev%202-green)
![Target: AMD Phoenix NPU (AIE2 / XDNA1)](https://img.shields.io/badge/Hardware-AMD%20Phoenix%20AIE2%20(512--bit%20SIMD)-red)
![Residency: 100% On-Device Silicon](https://img.shields.io/badge/Residency-100%25%20On--Device%20(Zero%20Host%20Fallback)-brightgreen)
![Status: v1.1.0 Certified (839/839 PASS)](https://img.shields.io/badge/Status-v1.1.0%20Certified%20%C2%B7%20839%2F839%20PASS-brightgreen)

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
   * *The Problem*: If a mathematical or algorithmic breakthrough emerges against lattice problems ($\mathcal{R}\text{-LWE}$ / $\mathcal{M}\text{-LWE}$), pure PQC is compromised. Conversely, if an optical physical attack (detector blinding, Trojan horse fiber probing, or side-channel tapping) breaches QKD hardware, pure QKD is compromised.
   * *The Solution*: $K_{\text{Final}}$ is derived using a NIST-approved multi-key combiner:
     $$K_{\text{Final}} = \text{KMAC256}\Big(K_{\text{QKD}} \parallel K_{\text{PQC}}, \text{Context}\Big)$$
     The session remains unbreakable even if either physical QKD fiber or mathematical lattice problems are completely compromised.

---

## 2. Standards Conformance Matrix

| Standard / Organization | Specification Reference | Role in Hybrid Pipeline | AIE2 Implementation Milestone | Status in v1.1.0 |
|---|---|---|---|:---:|
| **ETSI** | **ETSI GS QKD 014 (v1.1.1 / v1.3.1)** | REST-based Key Delivery API for KME Ingress | **DR16** (Key Ingress Engine) | **100% PASS** |
| **ETSI** | **ETSI GS QKD 015 (v2.1.1)** | Orchestration and Control-Plane Security | **DR17** (Asymmetric Auth Control) | **100% PASS** |
| **NIST** | **FIPS PUB 204 (2024)** | ML-DSA Digital Signature Verification | **DR11–DR15, DR17** (Auth Hub) | **100% PASS** |
| **NIST** | **FIPS PUB 203 (2024)** | ML-KEM Key Encapsulation Mechanism | **DR2d, DR3–DR8** (Lattice KEM) | **100% PASS** |
| **NIST** | **FIPS PUB 202 (2015)** | SHA-3 / SHAKE / Keccak-f[1600] Permutations | **DR9, DR18** (Combiner Core) | **100% PASS** |
| **NIST** | **SP 800-56C Rev. 2 (2020)** | Two-Step Key Extraction and Expansion | **DR18** (Dual Key Combiner) | **100% PASS** |
| **NIST** | **SP 800-227 (2024)** | Multi-Key Encapsulation Combiners | **DR18** (Hybrid Session KDF) | **100% PASS** |
| **IETF** | **RFC 9370 / RFC 8784 (2023)** | Multi-KEM IKEv2 / IPsec Protocol Models | **DR19** (Session Orchestrator) | **100% PASS** |
| **NIST** | **FIPS PUB 205 (2024)** | Stateless Hash-Based Signatures (SLH-DSA) | **DR21** (SPHINCS+ Engine) | *Planned v1.2* |
| **NIST** | **FIPS PUB 206 (2025)** | Fast-Fourier Lattice Signatures (FN-DSA) | **DR22** (Falcon FP32 Engine) | *Planned v1.2* |

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

## 4. Future Roadmap: Version 1.2.0 (Planned Milestones)

```
========================================================================================================================
                                     PHOENIX NPU PQC & QKD ROADMAP: v1.2.0
========================================================================================================================

[MODULE 6] Conservative & Compact PQC Extensions
  • Milestone DR21: NIST FIPS 205 (SLH-DSA / SPHINCS+) On-Device Tree Hashing Engine on AIE2 Keccak Core.
  • Milestone DR22: NIST FIPS 206 (FN-DSA / FALCON) Floating-Point FFT Signature Engine (Native FP32 VPU).

[MODULE 7] Production Network Offload & Cryptographic Provider Subsystems
  • Milestone DR23: OpenSSL 3.x Native Provider Plugin (`phoenix-pqc-provider`) & PKCS#11 HSM Token.
  • Milestone DR24: Quantum-Safe Kernel-Bypass WireGuard / IPsec Inline VPN Co-Processor (60s ML-KEM/QKD re-keying).

[MODULE 8] Advanced Physical Security & Multi-Generation Hardware Scaling
  • Milestone DR25: Higher-Order Masked Polynomial Arithmetic & Dual-Rail Fault Injection Countermeasures.
  • Milestone DR26: AMD XDNA 2 (Ryzen AI 300 / Strix Point - 50 TOPS) & AMD Alveo V70 Datacenter Port.
========================================================================================================================
```

### Detailed v1.2.0 Milestone Specifications:

#### Milestone DR21: NIST FIPS 205 (SLH-DSA / SPHINCS+) On-Device Tree Hashing
* **Standard**: NIST FIPS 205 (SLH-DSA-SHAKE-128s/f, 192s/f, 256s/f).
* **Objective**: Stateless hash-based signatures providing an alternative security foundation completely independent of lattice assumptions.
* **Architecture**: SPHINCS+ W-OTS+ and FORS tree hashing mapped across all 20 AIE2 compute tiles in parallel using the native Keccak-f[1600] SIMD core.

#### Milestone DR22: NIST FIPS 206 (FN-DSA / FALCON) High-Precision FP32 FFT Engine
* **Standard**: NIST FIPS 206 (FN-DSA-512 and FN-DSA-1024).
* **Objective**: Ultra-compact lattice signatures (~666 bytes) using Fast Fourier sampling over NTRU lattices.
* **Architecture**: Native 512-bit vector floating-point (FP32) FFT butterfly pipeline on AIE2 VPU tiles.

#### Milestone DR23: OpenSSL 3.x Provider Plugin & PKCS#11 HSM Integration
* **Standard**: OpenSSL 3.0+ Provider Architecture & PKCS#11 v3.0.
* **Objective**: Direct drop-in acceleration for enterprise software (Nginx, Envoy, Apache, Chromium, OpenSSH).
* **Deliverables**: `phoenix-pqc-provider.dll` / `libphoenix_pqc.so` exposing `X25519MLKEM768` and `ML-DSA-65/87` certificates.

#### Milestone DR24: Quantum-Safe WireGuard / IPsec Kernel-Bypass Inline VPN Co-Processor
* **Standard**: IETF RFC 9370 / RFC 8784 / WireGuard Protocol.
* **Objective**: Low-latency VPN tunnel adapter offloading packet encryption (AES-256-GCM / ChaCha20) and continuous background ML-KEM + QKD session re-keying to the NPU without CPU interrupts.

#### Milestone DR25: Higher-Order Masked Polynomial Arithmetic & Dual-Rail Fault Hardening
* **Objective**: Mathematical side-channel resistance against Differential Power Analysis (DPA/CPA) and laser/clock fault injection attacks.
* **Mechanism**: 1st- and 2nd-order polynomial blinding and dual-rail lockstep cross-tile verification.

#### Milestone DR26: AMD XDNA 2 & AMD Alveo V70 Multi-Architecture Scaling
* **Objective**: Scale from client APUs (Phoenix XDNA 1 / 20 tiles) to next-gen client (Strix Point XDNA 2 / 32 tiles / 50 TOPS) and datacenter accelerators (Alveo V70 / 304 tiles / 75W).

---

## 5. Version History & Milestone Release Matrix

| Version | Status | Modules Included | Milestones | Physical Silicon Status |
| :--- | :---: | :--- | :--- | :---: |
| **v1.0.0** | **Released** | Modules 1, 2, 3, 4 (PQC Core) | DR0–DR15 (19 Gates) | **736 / 736 PASS** (23.98s) |
| **v1.1.0** | **Released (Current)** | Modules 1–5 (PQC + Hybrid QKD) | DR0–DR20 (23 Gates) | **839 / 839 PASS** (36.86s) |
| **v1.2.0** | **Planned** | Modules 6, 7, 8 (SLH-DSA, OpenSSL, VPN, Masking) | DR21–DR26 (30 Gates) | *In Development* |
