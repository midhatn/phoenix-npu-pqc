# Release Notes — Phoenix NPU PQC & QKD Suite (v1.1.0)

## Overview

We announce the formal release of **Phoenix NPU PQC & QKD v1.1.0**, establishing the world's first 100% device-resident hardware acceleration engine combining finalized NIST Post-Quantum Cryptography standards (FIPS 202, FIPS 203, FIPS 204) with Quantum Key Distribution (ETSI GS QKD 014) on the AMD Phoenix NPU (AIE2 / XDNA1 Architecture).

---

## What's New in v1.1.0

### 1. Module 5: Hybrid QKD & Post-Quantum Defense-in-Depth
* **Milestone DR16 (Gate 19)**: Direct DMA ingestion of ETSI GS QKD 014 key containers from commercial and academic KMEs (ID Quantique Cerberis XGR, Toshiba QKD, Quantum Xchange) into isolated AIE2 Tile (0,1) SRAM.
* **Milestone DR17 (Gate 20)**: Asymmetric control plane authentication via NIST FIPS 204 (ML-DSA-44/65/87) to solve QKD's pre-shared key dilemma.
* **Milestone DR18 (Gate 21)**: NIST SP 800-56C Rev. 2 / NIST SP 800-227 on-chip two-step dual-key combiner fusing $K_{\text{QKD}}$ and $K_{\text{PQC}}$ inside AIE2 Keccak tile (3,2).
* **Milestone DR19 (Gate 22)**: Full-duplex session handshake orchestrator with DR10 hardware zeroization memory scrub on session termination.
* **Milestone DR20 (Gate 23)**: Complete 23-gate regression suite executing on physical AMD Phoenix silicon with 839 / 839 test cases passing.

### 2. Native C++ Peano LLVM-AIE Kernels
* Eliminated all host Python cryptographic delegations.
* Added native Peano C++ kernels:
  * `dr16_etsi_qkd014_service.cc`
  * `dr17_mldsa_qkd_auth_service.cc`
  * `dr18_dual_key_combiner_service.cc`
  * `dr19_hybrid_session_service.cc`

### 3. Universal Architecture Invariants Enforced
* **Zero Host Cryptographic Fallback**: 100% on-tile execution.
* **DMA Channel Limits**: Exactly 2 input channels, 1 output channel per graph.
* **Terminal-Only Egress**: Zero intermediate key leakage to CPU DDR.
* **Fail-Closed Semantics & Zeroization**: Full memory scrubbing inside C++ kernels and host staging buffers.

### 4. Publication & Research Artifacts
* Zenodo DOI Reference: `10.5281/zenodo.22162273`
* Comprehensive Silicon Architecture Whitepaper (v2): `docs/phoenix_npu_xdna1_architecture_v2.md`
* Vendor-Agnostic ETSI GS QKD 014 Integration Guide: `docs/ID_QUANTIQUE_QKD_INTEGRATION.md`
* Silicon Validation Report: `docs/HYBRID_QKD_PQC_SILICON_REPORT.md`
