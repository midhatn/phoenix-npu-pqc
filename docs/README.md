# Phoenix NPU PQC Research Documentation Index

This index organizes mathematical specifications, architectural designs, microarchitectural invariants, and historical validation records across post-quantum cryptography research modules on the AMD Phoenix NPU (AIE2 / XDNA1).

---

## 1. Primary Research Standards Modules

### Module 1: NIST FIPS 202 (SHA-3 / SHAKE — Milestone DR9)
* [DR9 Design Specification](PQC_DR9_DESIGN.md) — Reusable streaming Keccak-f[1600] engine for SHA3-224/256/384/512 and SHAKE128/256.
* [DR9 Historical Silicon Validation Record](PQC_DR9_SILICON_VALIDATION_20260829.md) — Historical test vector record.

### Module 2: NIST FIPS 203 (ML-KEM / Kyber — Milestones DR2d, DR3–DR8)
* [DR2d ML-KEM-512 K-PKE.KeyGen Design](PQC_DR2D_DESIGN.md) & [Silicon Validation Record](PQC_DR2D_SILICON_VALIDATION_20260828.md)
* [DR3 ML-KEM-512 K-PKE.Encrypt Design](PQC_DR3_DESIGN.md) & [Silicon Validation Record](PQC_DR3_SILICON_VALIDATION_20260828.md)
* [DR4 ML-KEM-512 K-PKE.Decrypt Design](PQC_DR4_DESIGN.md) & [Silicon Validation Record](PQC_DR4_SILICON_VALIDATION_20260828.md)
* [DR5 ML-KEM-512 ML-KEM.KeyGen Design](PQC_DR5_DESIGN.md) & [Silicon Validation Record](PQC_DR5_SILICON_VALIDATION_20260828.md)
* [DR6 ML-KEM-512 ML-KEM.Encaps Design](PQC_DR6_DESIGN.md) & [Silicon Validation Record](PQC_DR6_SILICON_VALIDATION_20260828.md)
* [DR7 ML-KEM-512 ML-KEM.Decaps Design](PQC_DR7_DESIGN.md) & [Silicon Validation Record](PQC_DR7_SILICON_VALIDATION_20260828.md)
* [DR8 ML-KEM-768 & 1024 Expansion Design](PQC_DR8_DESIGN.md) & [Silicon Validation Record](PQC_DR8_SILICON_VALIDATION_20260829.md)

### Module 3: NIST FIPS 204 (ML-DSA / Dilithium — Milestones DR11–DR15)
* [DR11 ML-DSA-44 KeyGen Design](PQC_DR11_DESIGN.md) & [Silicon Validation Record](PQC_DR11_SILICON_VALIDATION_20260829.md)
* [DR12 ML-DSA-44 Signing Design](PQC_DR12_DESIGN.md) & [Silicon Validation Record](PQC_DR12_SILICON_VALIDATION_20260829.md)
* [DR13 ML-DSA-44 Verification Design](PQC_DR13_DESIGN.md) & [Silicon Validation Record](PQC_DR13_SILICON_VALIDATION_20260829.md)
* [DR14 ML-DSA-65 Suite Design](PQC_DR14_DESIGN.md) & [Silicon Validation Record](PQC_DR14_SILICON_VALIDATION_20260829.md)
* [DR15 ML-DSA-87 Suite & Primary Closure Design](PQC_DR15_DESIGN.md) & [Silicon Validation Record](PQC_DR15_SILICON_VALIDATION_20260829.md)

### Module 4: Hardware Lifecycle & Foundation (Milestones DR0, DR1, DR2a–DR2c, DR10)
* [DR0 M33 Ring Product Design](PQC_DR0_DESIGN.md), [Provenance](PQC_DR0_PROVENANCE.md), and [Validation Record](PQC_DR0_SILICON_VALIDATION_20260817.md)
* [DR1 ML-DSA-44 ExpandA / RejNTT Design](PQC_DR1_DESIGN.md) & [Validation Record](PQC_DR1_SILICON_VALIDATION_PENDING.md)
* [DR2a ML-KEM-512 SampleNTT Design](PQC_DR2A_DESIGN.md) & [Validation Record](PQC_DR2A_SILICON_VALIDATION_PENDING.md)
* [DR2b ML-KEM-512 CBD3 Noise-to-NTT Design](PQC_DR2B_DESIGN.md) & [Validation Record](PQC_DR2B_SILICON_VALIDATION_PENDING.md)
* [DR2c ML-KEM-512 KeyGen Row Design](PQC_DR2C_DESIGN.md) & [Validation Record](PQC_DR2C_SILICON_VALIDATION_PENDING.md)
* [DR10 Sealed Lifecycle, Entropy & Key Sources Design](PQC_DR10_DESIGN.md) & [Silicon Validation Record](PQC_DR10_SILICON_VALIDATION_20260829.md)

---

## 2. Universal Architecture Invariants Enforced

* **Zero Host Cryptographic Fallback**: All sampling, polynomial arithmetic, transforms, hashing, KDFs, re-encryptions, and comparisons execute strictly on AIE2 hardware tiles.
* **DMA Channel Limits & Ingress**: Max 2 input DMA channels per core boundary; exactly 2 host fills per public operation.
* **Terminal-Only Egress**: Only final public records transfer to the CPU after dispatch.
* **Fail-Closed Semantics & Zeroization**: Intermediate state and scratchpads are explicitly zeroized before release.

---

## 3. Governance, Environment & Audits

* [Performance & Microarchitectural Benchmarks](BENCHMARKS.md) — Empirical execution latency, memory footprint, and tile budgets across all 19 silicon gates.
* [Changelog](../CHANGELOG.md) — Version release history and milestone progression from DR0 to DR15.
* [PQC Device-Residency Roadmap](PQC_DEVICE_RESIDENCY_ROADMAP.md) — Milestone tracking status across DR0 through DR15.
* [Comprehensive PQC Citation & Mathematics Audit](PQC_CITATION_AND_MATHEMATICS_AUDIT_20260828.md) — Scientific citation ledger, mathematical derivations, algorithmic proofs, and ACVP vector provenance.
* [Windows Setup Guide](SETUP_WINDOWS.md) — Native `py .\install` clean-clone instructions, toolchain pins, and canonical gate verification.
* [Journal Reproducibility Checklist](JOURNAL_REPRODUCIBILITY_CHECKLIST.md) — Manuscript-ready clean-checkout, evidence verification, and citation controls.
* [Publication Readiness Report](PUBLICATION_READINESS.md) — Evidence matrix, 19-gate validation summary, and release policy.
