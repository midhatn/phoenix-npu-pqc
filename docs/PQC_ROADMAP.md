# Phoenix NPU PQC roadmap

**Status date:** 2026-08-18

**Repository:** `phoenix-npu-pqc`

**Purpose:** claim-safe research sequencing for FIPS 202/203/204 work on AMD
Phoenix NPU1. This is not a delivery schedule, production claim, certification
plan, or authorization to run hardware.

## Objective

The program goal is **100% NPU-resident execution** for the supported
cryptographic operations: the required FIPS 202 SHA-3/SHAKE work; FIPS 203
ML-KEM parameter sets and operations; and FIPS 204 ML-DSA parameter sets and
operations.

For this roadmap, “100% NPU-resident” means the NPU graph performs the
cryptographic computation, intermediate-state handling, sampling, transforms,
encoding, comparison, rejection/control flow, and final validation. The host
may submit public inputs and receive the final API result, but it may not
provide cryptographic fallback, compute an intermediate, or repair a device
result.

## Status ledger

| Area | State | Claim boundary |
| --- | --- | --- |
| M32 / M33 historical baseline | Retained | `v1.0.0` at `9c592a4` is a hybrid foundation: native primitive gates and host/NPU compositions coexist. |
| Native M33 runners | Retained | The later `e77e7ed` lineage adds native M33 runner infrastructure; it does not make the whole FIPS 204 flow resident. |
| DR0 | Narrow physical result retained | One M33 device-resident polynomial product. |
| DR1 | Narrow physical result retained | ML-DSA-44 ExpandA / rejection-sampling / NTT path. |
| DR2a | Narrow physical result retained | ML-KEM-512 `SampleNTT` path. |
| DR2b | Narrow physical result retained | ML-KEM-512 CBD3/NTT noise path. |
| DR2c | Narrow physical result retained | One terminal ML-KEM-512 KeyGen row. |
| DR2d | **Unresolved** | Integrated ML-KEM-512 K-PKE.KeyGen recorded `TOTAL 0/25 FAIL`, exit 1. |
| Integrated DR2 | **Blocked** | DR2a/DR2b/DR2c do not close integrated DR2d. |

## Decision rule

DR2 can close only after an independently checked integrated physical corpus,
reproducible build/provenance, fail-closed behavior, exact-output validation,
and an explicit closure decision. The current DR2d `0/25` outcome means those
conditions are not met. DR3 and later work are not started by this repository
state.

## Evidence and governance

- [Device-residency roadmap](PQC_DEVICE_RESIDENCY_ROADMAP.md) is the detailed
  DR decision sequence and stop-state record.
- [DR2 expert escalation](PQC_DR2_EXPERT_ESCALATION_20260818.md) records the
  integrated failure and diagnostic boundary.
- [Protected evidence inventory](pqc_dr2_evidence_20260818/README.md) and
  `SHA256SUMS` preserve the DR2 forensic material.
- [Repository split record](REPOSITORY_SPLIT_20260818.md) records the
  history-preserving transition to Phoenix NPU PQC.

## Exclusions

This roadmap does not claim FIPS conformance, constant-time execution,
side-channel resistance, secure zeroization, performance, CMVP validation,
certification, production readiness, or a driver/toolchain root cause.

## Normative references

- [FIPS 202: SHA-3 Standard](https://nvlpubs.nist.gov/nistpubs/FIPS/NIST.FIPS.202.pdf)
- [FIPS 203: ML-KEM](https://nvlpubs.nist.gov/nistpubs/FIPS/NIST.FIPS.203.pdf)
- [FIPS 204: ML-DSA](https://nvlpubs.nist.gov/nistpubs/FIPS/NIST.FIPS.204.pdf)
