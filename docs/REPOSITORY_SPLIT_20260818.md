# Repository split record — 2026-08-18

## Purpose

Phoenix NPU PQC (`phoenix-npu-pqc`) is a dedicated private research repository
created by history-preserving separation of the post-quantum cryptography
material from `phoenix-sdr-dsp`. The split narrows the repository's active
scope to FIPS 202/203/204 research on AMD Phoenix NPU1; it does not alter,
renumber, or upgrade the meaning of the retained experimental records.

## Preserved lineage

| Lineage point | Preserved reference | Meaning in this repository |
| --- | --- | --- |
| M33e baseline | Tag `v1.0.0` at commit `9c592a4c077c73f2ebf910aca0b6575664b0726f` | Historical M32/M33 hybrid foundation. It includes host/NPU compositions and must not be represented as complete NPU residency. |
| Native M33 runners | Commit `e77e7ed2783d88b5451394866d7ddfccd9db4f69` | Later addition of native M33 ML-DSA runner infrastructure. |
| DR0 and DR1 | Commit `7b38973789fafb950a26551bc947f4fcaa91ec25` | Device-resident DR0/DR1 graph research and their narrow validation lineage. |
| DR2 research | Retained DR2 source, documents, logs, forensic material, and `docs/pqc_dr2_evidence_20260818/` | DR2a/DR2b/DR2c have narrow physical-result records; the integrated DR2d candidate has a recorded `0/25` physical failure and remains unresolved. |

## Migration policy

1. Retained evidence directories and checksum-protected material are
   byte-preserved. Their original content is evidence, not current repository
   copywriting.
2. Current-facing files — the root README, documentation index, contribution
   guidance, security policy, CI, issue forms, citation metadata, toolchain
   metadata, installer text, and test entrypoints — identify this repository
   as Phoenix NPU PQC.
3. The Python import path remains `phoenix_sdr_dsp` for compatibility with
   retained research code and callers. This is an import-API compatibility
   decision, not a repository-identity claim.
4. The default runner and CI execute only host-safe PQC checks. Native-only
   physical gates remain retained research artifacts and are not authorized or
   invoked by these entrypoints.

## Current claim boundary

The migration does not claim completion of integrated ML-KEM KeyGen, complete
ML-KEM, complete ML-DSA, FIPS conformance, or 100% NPU residency. The
long-term target remains full residency without host cryptographic fallback;
the DR2d result blocks the integrated DR2 closure required to advance that
goal.
