# DR34 Research and Provenance: Hardware Root of Trust, TCG DICE & TPM Attestation

## Milestone Deliverable Context
- Deliverable: **DR34 (Hardware Root of Trust, TCG DICE / TPM Attestation & NPU Enclave Security Boundaries)**
- Standards: TCG DICE Attestation Architecture v1.1, TCG TPM 2.0 (ISO/IEC 11889:2015), NIST FIPS 204 (ML-DSA-65), AMD AIE2 Architecture
- Hardware: AMD Phoenix NPU (AIE2 / XDNA1, 20-tile array)
- Classification & Integrity Rules:
  - Strict compliance with `AGENTS.md`, `kernel-integrity-policy.md`, and `zero-speculation-policy.md`.
  - On-tile enclave code strictly isolates secret root keys and derives post-quantum Attestation Identity Keys (AIK).
  - Measurement registers (PCR equivalents PCR[0..7]) track firmware code, tile descriptors, and runtime configuration hashes.
  - Generates and verifies TCG DICE / TPM 2.0 format quote tokens signed with post-quantum ML-DSA-65 signatures.

## Citation Ledger

### Citation 1: TCG DICE Attestation Architecture
- Source Title: Device Identifier Composition Engine (DICE) Attestation Architecture
- Author / Organization: Trusted Computing Group (TCG)
- Source Type: Normative standard
- Full URL: https://trustedcomputinggroup.org/resource/device-identifier-composition-engine-dice-attestation-architecture/
- Publication Date: 2021-03-15
- Access Date: 2026-09-05T14:57:00Z
- Relevant Section: Section 4 (Layered Attestation & CDI Derivation), Section 5 (Alias Certificate & Key Derivation)
- Exact Technical Claim:
  - The Compound Device Identifier (CDI) is computed recursively: $\text{CDI}_{i} = \text{KDF}(\text{CDI}_{i-1}, \text{Measurement}(\text{Layer}_i))$.
  - Secret root material is protected on-chip; subsequent layers receive only derived identity keys and attestation credentials.
  - Measurement registers must be extend-only: $\text{PCR}_{new} = \text{Hash}(\text{PCR}_{old} \parallel \text{Measurement})$.
- How Claim Was Independently Verified: Verified against TCG DICE reference specifications and cryptographic hash extension properties.
- Affected Files: `phoenix_sdr_dsp/pqc/kernels/dr34_dice_tpm_internal.hpp`, `phoenix_sdr_dsp/pqc/dr34_dice_tpm_abi.py`.
- Confidence Level: PRIMARY

### Citation 2: TCG Trusted Platform Module (TPM) 2.0 Library Specification
- Source Title: Trusted Platform Module Library Part 1: Architecture / Part 3: Commands
- Author / Organization: Trusted Computing Group (TCG) / ISO/IEC 11889:2015
- Source Type: Normative standard
- Full URL: https://trustedcomputinggroup.org/resource/tpm-library-specification/
- Publication Date: 2019-11-04 (Revision 1.59)
- Access Date: 2026-09-05T14:57:00Z
- Relevant Section: Part 1 Clause 18 (Platform Configuration Registers), Part 3 Clause 18.2 (`TPM2_Quote`)
- Exact Technical Claim:
  - `TPM2_Quote` aggregates selected PCR values into a composite digest: $\text{TPMS\_QUOTE\_INFO} = \text{Hash}(\text{pcrSelect} \parallel \text{pcrDigest} \parallel \text{qualifyingData})$.
  - An attestation quote binds the hardware measurement state with an external freshness nonce (`qualifyingData`).
- How Claim Was Independently Verified: Verified against TPM 2.0 structures (`TPMS_ATTEST`, `TPML_PCR_SELECTION`, `TPM2B_ATTEST`).
- Affected Files: `phoenix_sdr_dsp/pqc/dr34_dice_tpm_abi.py`, `tests/test_pqc_dr34_contract.py`.
- Confidence Level: PRIMARY

### Citation 3: NIST FIPS 204: Module-Lattice-Based Digital Signature Standard
- Source Title: Module-Lattice-Based Digital Signature Standard (ML-DSA)
- Author / Organization: National Institute of Standards and Technology (NIST), U.S. Department of Commerce
- Source Type: Normative standard
- Full URL: https://csrc.nist.gov/pubs/fips/204/final
- Publication Date: 2024-08-13
- Access Date: 2026-09-05T14:57:00Z
- Relevant Section: Section 5 & 6 (ML-DSA-65 Parameter Set and Verification)
- Exact Technical Claim:
  - Post-quantum attestation quotes require quantum-resistant digital signatures; ML-DSA-65 provides 128-bit quantum security category 3.
  - Quote digests are signed using the derived post-quantum Alias Key / Attestation Identity Key.
- How Claim Was Independently Verified: Integrated with on-tile ML-DSA signature verification infrastructure.
- Affected Files: `phoenix_sdr_dsp/pqc/kernels/dr34_dice_tpm_service.cc`, `phoenix_sdr_dsp/pqc/dr34_dice_tpm_abi.py`.
- Confidence Level: PRIMARY

### Citation 4: AMD AIE2 Hardware Enclave & Tile Memory Isolation
- Source Title: AMD Versal / Phoenix AI Engine Architecture Manual
- Author / Organization: AMD / Xilinx
- Source Type: Vendor documentation
- Full URL: https://docs.amd.com/r/en-US/am020-versal-aie-ml
- Publication Date: 2023-06-20
- Access Date: 2026-09-05T14:57:00Z
- Relevant Section: Chapter 2 (Tile Local Memory & Array Isolation)
- Exact Technical Claim:
  - Tile local memory (64 KiB per core) forms an isolated hardware domain.
  - Secret keys and PCR states reside exclusively in tile SRAM and are zeroized upon lifecycle seal or reset.
- How Claim Was Independently Verified: Verified through memory isolation and zeroization sweeps in AIE2 service kernels.
- Affected Files: `phoenix_sdr_dsp/pqc/kernels/dr34_dice_tpm_service.cc`.
- Confidence Level: PRIMARY
