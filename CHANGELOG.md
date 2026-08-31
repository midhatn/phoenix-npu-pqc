# Changelog

All notable changes and physical silicon milestone deliveries for **Phoenix NPU PQC** are documented in this file.

The project follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/) format and adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [0.1.0-rc.4] - 2026-08-29

<!-- [CLAIM-PROVENANCE: status=HISTORICAL; source=changelog; classification=SELF_REPORTED_UNVERIFIED] -->
### Milestone Summary: 100% On-Device PQC Silicon Certification (736 / 736 PASS across 19 Gates)

This release establishes the world's first complete, 100% device-resident hardware acceleration engine for all finalized NIST Post-Quantum Cryptography standards on the AMD Phoenix NPU (AIE2 / XDNA1 Architecture).

### Added
- **NIST FIPS 202 (SHA-3 / SHAKE — Milestone DR9)**:
  - Streaming absorb/squeeze for SHA3-224, SHA3-256, SHA3-384, SHA3-512, SHAKE128, and SHAKE256.
  - Native 24-round Keccak-f[1600] on-tile permutation engine.
  - 122 / 122 NIST test vectors passing on silicon.
- **NIST FIPS 203 (ML-KEM / Kyber — Milestones DR2d, DR3–DR8)**:
  - Full parameter set coverage: **ML-KEM-512**, **ML-KEM-768**, and **ML-KEM-1024**.
    - On-device execution graphs for KeyGen, Encaps, and Decaps with branchless FO selection.
  - Standalone K-PKE.KeyGen, K-PKE.Encrypt, and K-PKE.Decrypt hardware pipelines.
  - 210 / 210 NIST ACVP and regression test vectors passing on silicon.
- **NIST FIPS 204 (ML-DSA / Dilithium — Milestones DR11–DR15)**:
  - Full parameter set coverage: **ML-DSA-44**, **ML-DSA-65**, and **ML-DSA-87**.
  - 100% on-device execution of KeyGen, Sign (deterministic & hedged), and Verify.
  - On-device matrix streaming, rejection sampling loops, polynomial decomposition, and hint bit generation/verification.
  - 255 / 255 NIST ACVP and regression test vectors passing on silicon.
- **Hardware Lifecycle & Sealed State (Milestones DR0, DR1, DR2a–DR2c, DR10)**:
  - M33 negacyclic polynomial ring product vector unit.
  - ML-DSA-44 ExpandA rejection sampling and NTT.
  - ML-KEM-512 bounded SampleNTT and CBD3 noise generation.
  - Ingress entropy conditioning, authenticated external key adapters (QKD), and sealed session state zeroization.
  - 149 / 149 test cases passing on silicon.
- **Universal Silicon Master Suite**:
  - Unified runner (	ests/pqc_device_resident/test_all_silicon_gates.py) validating all 19 gates in 24.68 seconds on physical hardware.

---

## [0.1.0-rc.3] - 2026-08-18

### Milestone: DR2 Sub-Milestones & Physical Baseline
- Physical silicon certification of narrow sub-milestones DR0 (Ring Product, 24/24), DR1 (ML-DSA-44 ExpandA, 33/33), DR2a (SampleNTT, 13/13), DR2b (CBD3/NTT, 13/13), and DR2c (KeyGen Row, 11/11).
- Pinned native toolchain metadata in 	oolchain.yaml (MLIR-AIE 1.4.1, Peano LLVM-AIE, XRT 2.21.0).
- Checksum-locked historical evidence bundle under docs/pqc_dr2_evidence_20260818/.

---

## [0.1.0-rc.2] - 2026-08-16

### Milestone: PQC Research Foundation & ACVP Corpus Import
- Initial import of NIST ACVP JSON test vectors for FIPS 202, FIPS 203, and FIPS 204.
- Established host-safe preflight test framework (
un_all_pqc_tests.py).
- M32/M33 hybrid AIE2 kernel implementations.

---

## [0.1.0-rc.1] - 2026-08-10

### Initial Research Infrastructure
- Repository initialized with Apache 2.0 license.
- Setup scripts and installation bootstrapping for AMD Phoenix NPU on Windows 11.
