# Phoenix NPU PQC documentation

This index contains only documentation relevant to the Phoenix NPU PQC
research repository. Historical records retain their original dates, evidence
claims, and filenames; they are not rewritten to imply a broader result.

## Start here

- [Repository overview](../README.md) — scope, research status, host-safe validation, and compatibility policy.
- [Repository split record](REPOSITORY_SPLIT_20260818.md) — history-preserving migration from `phoenix-sdr-dsp`.
- [Repository build report](REPOSITORY_BUILD_REPORT_20260818.md) — implementation scope, restored evidence integrity, and host-only verification results.
- [PQC roadmap](PQC_ROADMAP.md) — program-level status and claim boundaries.
- [PQC device-residency roadmap](PQC_DEVICE_RESIDENCY_ROADMAP.md) — DR0 through the blocked integrated DR2 decision.
- [PQC reproducibility guide](PQC_REPRODUCIBILITY.md) — host-safe commands, toolchain pins, integrity checks, and evidence interpretation.

## Historical foundation

- [M32 FIPS 203 ML-KEM](M32_FIPS203_MLKEM.md) and its component designs: [M32b](M32b_DESIGN.md), [M32c](M32c_DESIGN.md), [M32d](M32d_DESIGN.md), and [M32e](M32e_DESIGN.md).
- [M33 ML-DSA NTT](M33a_DESIGN.md), [rounding/hint](M33b_DESIGN.md), [KeyGen](M33d_DESIGN.md), and [Sign/Verify](M33e_DESIGN.md).
- [M33 silicon provenance](M33_SILICON_PROVENANCE.md) and [historical validation record](M33_SILICON_VALIDATION_20260817.md).
- [PQC v1 historical scope](PQC_COMPLETE_V1.md) — hybrid M32/M33 foundation; not a complete residency claim.

## Device-residency research

- [DR0 design](PQC_DR0_DESIGN.md), [provenance](PQC_DR0_PROVENANCE.md), and [physical validation record](PQC_DR0_SILICON_VALIDATION_20260817.md).
- [DR1 design](PQC_DR1_DESIGN.md) and [validation record](PQC_DR1_SILICON_VALIDATION_PENDING.md).
- [DR2a design](PQC_DR2A_DESIGN.md) and [validation record](PQC_DR2A_SILICON_VALIDATION_PENDING.md).
- [DR2b design](PQC_DR2B_DESIGN.md) and [validation record](PQC_DR2B_SILICON_VALIDATION_PENDING.md).
- [DR2c design](PQC_DR2C_DESIGN.md), [handoff](PQC_DR2C_MLKEM512_KEYGEN_ROW_HANDOFF_20260817.md), and [physical validation record](PQC_DR2C_SILICON_VALIDATION_PENDING.md).
- [DR2d design](PQC_DR2D_DESIGN.md), [physical-status record](PQC_DR2D_SILICON_VALIDATION_PENDING.md), and [ELF audit](PQC_DR2D_FULLWORD_PRODUCTION_ELF_AUDIT_20260818.md).

## DR2d provenance and protected evidence

- [DR2 expert escalation](PQC_DR2_EXPERT_ESCALATION_20260818.md) — records the integrated physical `0/25` result and stop state.
- [Local forensic recovery](PQC_DR2_LOCAL_FORENSIC_RECOVERY_20260818.md) — provenance of recovered DR2 material.
- [W0 token-tap diagnostic handoff](PQC_DR2D_W0_TOKEN_TAP_DIAGNOSTIC_V2_20260818_HANDOFF.md).
- [Protected DR2 evidence inventory](pqc_dr2_evidence_20260818/README.md) — includes `SHA256SUMS`; do not edit the evidence or manifest.

## Environment, maintenance, and citations

- [Windows setup](SETUP_WINDOWS.md) and [toolchain pin rationale](M2_TOOLCHAIN_PIN.md).
- [Citation audit](CITATION_AUDIT.md).

The source-compatible Python package remains `phoenix_sdr_dsp`; see the root
README for the compatibility rationale.
