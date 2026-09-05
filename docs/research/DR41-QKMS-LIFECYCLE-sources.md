# DR41 Research and Provenance: Q-KMS Integration & Hybrid Key Lifecycle Management Engine

## Milestone Deliverable Context
- Deliverable: **DR41 (Quantum Key Management System - Q-KMS - Integration & Hybrid Key Lifecycle Engine on AMD Phoenix NPU)**
- Standards: ETSI GS QKD 014, ETSI GS QKD 015, OASIS KMIP v2.1/v3.0, NIST SP 800-57 Part 1 Rev. 5, NIST SP 800-56C Rev. 2
- Target Architecture: AMD Phoenix AIE2 / XDNA1 (AIE2 Vector Compute Tiles + Tile Local SRAM)
- Classification & Integrity Rules:
  - Kernel Execution: **[ON-TILE SILICON]** for AIE2 hardware execution of tile SRAM key vault slot management, SP 800-56C extract-and-expand dual key derivation, atomic slot zeroization, and on-chip lifecycle status enforcement.
  - Host Harness & Orchestration: **[HOST RUNTIME]** for Q-KMS key container marshaling (ETSI QKD 014/015 REST/KMIP interfaces), slot leasing, policy enforcement, and independent parent oracle verification.
  - Anti-Fabrication Invariant: No mock key stores, hardcoded session keys, fake zeroization, or unverified transitions. Key derivations and state transitions must match independent cryptographic oracles bit-for-bit.

## Citation Ledger

### Citation 1: ETSI GS QKD 014 / 015: Key Delivery API & Key Management System Architecture
- Source Title: ETSI GS QKD 014 v1.3.1: Quantum Key Distribution (QKD); Protocol and data format of REST-based key delivery API
- Author / Organization: European Telecommunications Standards Institute (ETSI)
- Source Type: Normative standard
- Full URL: https://www.etsi.org/deliver/etsi_gs/QKD/001_099/014/01.03.01_60/gs_QKD014v010301p.pdf
- Publication Date: 2022-09-01
- Access Date: 2026-09-05T19:20:00Z
- Relevant Section: Clause 5 (Key Container Data Formats) & Clause 6 (Key Delivery Protocol)
- Exact Technical Claim:
  - QKD Key Management Systems deliver discrete optical symmetric keys encapsulated in standard JSON containers identified by UUIDs, key size attributes, and synchronization epochs.
  - Symmetric key buffers must be securely ingested into cryptographic endpoints without persistent intermediate caching.
- How Claim Was Independently Verified: Verified against ETSI GS QKD 014 schemas and implemented in `phoenix_sdr_dsp/pqc/dr41_qkms_abi.py`.
- Affected Files: `phoenix_sdr_dsp/pqc/dr41_qkms_abi.py`, `tests/test_pqc_dr41_contract.py`.
- Confidence Level: PRIMARY

### Citation 2: OASIS KMIP & NIST SP 800-57: Key Lifecycle Management States
- Source Title: NIST SP 800-57 Part 1 Rev. 5: Recommendation for Key Management: Part 1 - General
- Author / Organization: National Institute of Standards and Technology (NIST), U.S. Department of Commerce
- Source Type: Normative standard
- Full URL: https://csrc.nist.gov/pubs/sp/800/57/pt1/r5/final
- Publication Date: 2020-05-01
- Access Date: 2026-09-05T19:20:00Z
- Relevant Section: Section 8.1: Key States and Transitions (Pre-Activation, Active, Deactivated, Compromised, Destroyed)
- Exact Technical Claim:
  - Cryptographic keys progress through defined lifecycle states: Pre-Active (registered but not authorized for use), Active (authorized for protection and processing), Deactivated (expired or superseded), Compromised, and Destroyed.
  - State transitions must be one-way for terminal states (Destroyed cannot transition to Active) and require explicit security controls.
- How Claim Was Independently Verified: Implemented formal state transition matrix inside `phoenix_sdr_dsp/pqc/kernels/dr41_qkms_internal.hpp` and verified against NIST SP 800-57 state graph.
- Affected Files: `phoenix_sdr_dsp/pqc/kernels/dr41_qkms_internal.hpp`, `phoenix_sdr_dsp/pqc/dr41_qkms_abi.py`, `tests/test_pqc_dr41_contract.py`.
- Confidence Level: PRIMARY

### Citation 3: NIST SP 800-56C Rev. 2: Two-Step Key Derivation (Extract-and-Expand)
- Source Title: NIST SP 800-56C Rev. 2: Recommendation for Key-Derivation Methods in Key-Establishment Schemes
- Author / Organization: National Institute of Standards and Technology (NIST), U.S. Department of Commerce
- Source Type: Normative standard
- Full URL: https://csrc.nist.gov/pubs/sp/800/56/c/r2/final
- Publication Date: 2020-08-01
- Access Date: 2026-09-05T19:20:00Z
- Relevant Section: Section 4: Two-Step Key Derivation Procedure (Randomness Extraction and Key Expansion)
- Exact Technical Claim:
  - Hybrid classical/quantum-safe key establishment combines multiple shared secrets ($ss_{\text{PQC}}$ and $K_{\text{QKD}}$) by extracting a master pseudorandom key (PRK) and expanding it with context info to generate symmetric keys.
  - The security of the derived key holds as long as at least one input key material remains uncompromised.
- How Claim Was Independently Verified: Built SP 800-56C dual key extraction and expansion into `phoenix_sdr_dsp/pqc/kernels/dr41_qkms_internal.hpp`.
- Affected Files: `phoenix_sdr_dsp/pqc/kernels/dr41_qkms_internal.hpp`, `phoenix_sdr_dsp/pqc/dr41_qkms_abi.py`, `tests/pqc_device_resident/test_dr41_qkms_silicon.py`.
- Confidence Level: PRIMARY

### Citation 4: Repository Hardware Security and State Integrity Policy
- Source Title: Repository Anti-Fabrication and Ground Truth Engineering Rules
- Author / Organization: Project Security Governance
- Source Type: Policy specification (`AGENTS.md` and `.agents/rules/zero-speculation-policy.md`)
- Full URL: https://github.com/midhatn/phoenix-npu-pqc/blob/main/AGENTS.md
- Publication Date: 2026-08-01
- Access Date: 2026-09-05T19:20:00Z
- Relevant Section: Ground Truth and Hardware Isolation
- Exact Technical Claim:
  - Prohibit claiming that the Phoenix NPU generated external QKD keys or quantum entropy. External optical keys are inputs to the NPU.
  - Prohibit mock key storage or fake hardware zeroization.
  - Enforce complete 100% buffer comparison against independent test oracles.
- How Claim Was Independently Verified: Enforced via fail-closed architecture in `phoenix_sdr_dsp/pqc/dr41_qkms_abi.py`.
- Affected Files: `phoenix_sdr_dsp/pqc/dr41_qkms_abi.py`, `tests/pqc_device_resident/test_dr41_qkms_silicon.py`.
- Confidence Level: PRIMARY
