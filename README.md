# Phoenix NPU PQC

<div align="center">

![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)
![Target: AMD Phoenix NPU1](https://img.shields.io/badge/Target-AMD%20Ryzen%20AI%20NPU1%20(AIE2)-blue)
![Research: Post-Quantum Cryptography](https://img.shields.io/badge/Research-Post--Quantum%20Cryptography-8a2be2)
![Standards: FIPS 202/203/204](https://img.shields.io/badge/Standards-FIPS%20202%20%2F%20203%20%2F%20204-005ea8)
![Status: DR2d unresolved](https://img.shields.io/badge/Status-DR2d%200%2F25%20physical%20result-critical)
[![CI](https://github.com/midhatn/phoenix-npu-pqc/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/midhatn/phoenix-npu-pqc/actions/workflows/ci.yml)

**Private research repository for post-quantum cryptography on AMD Ryzen AI Phoenix NPU1 (XDNA1 / AIE2).**

</div>

## Research status

Phoenix NPU PQC is a focused continuation of the PQC work separated from the
historical `phoenix-sdr-dsp` repository. It contains ML-KEM and ML-DSA research
code, host-safe contract tests, toolchain metadata, and the retained DR2
provenance needed to interpret the work accurately.

| Research layer | Current evidence boundary |
| --- | --- |
| **M32 / M33 foundation** | Historical v1.0.0 baseline: M32 ML-KEM and M33 ML-DSA work combined native primitive gates with host/NPU composers. This is a hybrid foundation, not a claim of complete device residency. |
| **DR0 / DR1** | Narrow, fail-closed physical results are retained for the M33 product and ML-DSA-44 ExpandA / rejection-sampling / NTT paths. |
| **DR2a / DR2b / DR2c** | Narrow, independent physical results are retained for ML-KEM-512 `SampleNTT`, CBD3/NTT noise, and one terminal KeyGen row respectively. They do not establish integrated ML-KEM KeyGen. |
| **DR2d** | The integrated ML-KEM-512 K-PKE.KeyGen candidate uses five computation workers (W0–W4) plus serializer W5 (six worker cores total). Its recorded physical result is **0/25**, exit 1. Compile-only and diagnostic material do not convert that outcome into a pass. |
| **Program goal** | 100% NPU residency for the supported FIPS 202/203/204 cryptographic operations, with no host cryptographic fallback or intermediate repair. This is a research goal, not a completed capability. |

The claim boundaries and the stop condition are defined in
[the device-residency roadmap](docs/PQC_DEVICE_RESIDENCY_ROADMAP.md). The
integrated DR2d result blocks DR2 closure and later DR research.

## Scope

- FIPS 202 SHA-3/SHAKE building blocks.
- FIPS 203 ML-KEM research, including ML-KEM-512 device-residency work.
- FIPS 204 ML-DSA research, including the historical M33 foundation and DR0/DR1.
- Native MLIR-AIE / IRON / XRT integration for AMD Phoenix NPU1.
- Reproducible host-side contract, reference, and provenance checks.

This repository is not a claim of FIPS conformance, constant-time behavior,
side-channel resistance, secure zeroization, CMVP validation, certification,
or production readiness.

## Repository guide

| Location | Purpose |
| --- | --- |
| [`phoenix_sdr_dsp/`](phoenix_sdr_dsp/) | Compatibility package path retained for existing PQC imports. New repository identity does **not** rename this import path. |
| [`tests/`](tests/) | Host-safe PQC contract/reference tests plus native-only physical gates that are retained as research artifacts. |
| [`docs/`](docs/README.md) | PQC-only documentation index, roadmaps, design records, provenance, and protected evidence navigation. |
| [`docs/pqc_dr2_evidence_20260818/`](docs/pqc_dr2_evidence_20260818/README.md) | Byte-preserved DR2d forensic evidence. It is read-only research evidence, not an authorization to execute hardware. |
| [`toolchain.yaml`](toolchain.yaml) | Machine-readable Phoenix NPU PQC toolchain and historical-result metadata. |
| [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md) | License, dependency, vector, and transliteration provenance ledger. |

## Host-safe validation

The repository CI and default local validation are host-only. They do not
authorize, compile for, or dispatch to an NPU:

```bash
python run_all_pqc_tests.py --dry-run
python run_all_pqc_tests.py
```

`run_all_silicon_tests.py` remains only as a compatibility entrypoint and
forwards to the same host-safe suite. It never starts a hardware test.

For a normal-user PowerShell 7 clean-clone audit with commit/status, tool,
Python, and protected-evidence checks, run:

```powershell
pwsh -File .\scripts\validate_clean_clone.ps1
```

The script has no hardware switch and writes one timestamped report under the
ignored `release-evidence/` directory. See the [publication readiness
matrix](docs/PUBLICATION_READINESS.md) and [journal reproducibility
checklist](docs/JOURNAL_REPRODUCIBILITY_CHECKLIST.md) for scope, retention,
and release controls.

Native-only physical gates and captured results are documented as evidence
boundaries; they are not invoked by CI. See
[CONTRIBUTING.md](CONTRIBUTING.md) before proposing any change that could
affect a physical-run workflow.

Read [`docs/PQC_AUDIT_REMEDIATION_20260818.md`](docs/PQC_AUDIT_REMEDIATION_20260818.md)
for the current source-backed correction ledger, research-use boundary, and
remaining journal-reproducibility blockers.

## Expert continuation and reproducibility

Start with the [PQC reproducibility guide](docs/PQC_REPRODUCIBILITY.md) for
the exact host-safe commands, integrity check, toolchain pins, known caches,
and source boundaries. The mathematical and implementation entry points are
the M32/M33 design records and the DR0–DR2d design records in the
[documentation index](docs/README.md).

For DR2d continuation, read the [expert escalation
record](docs/PQC_DR2_EXPERT_ESCALATION_20260818.md) before interpreting or
changing the integrated graph. It distinguishes the physical `0/25` outcome,
compile-only evidence, diagnostic captures, and rejected explanations. The
forensic evidence manifest can be checked without hardware:

```bash
(cd docs/pqc_dr2_evidence_20260818 && sha256sum -c SHA256SUMS)
```

## Compatibility

The Python package remains importable as `phoenix_sdr_dsp` so existing research
scripts and retained test material continue to resolve:

```python
from phoenix_sdr_dsp.pqc import dr2d_mlkem512_kpke_keygen_graph
```

This compatibility name reflects the repository's lineage. The repository
name, documentation, metadata, issue forms, and CI identity are
**Phoenix NPU PQC** (`phoenix-npu-pqc`).

## Provenance and migration

The split preserves Git history rather than recasting earlier results. See
[the repository split record](docs/REPOSITORY_SPLIT_20260818.md) for the
M33e `v1.0.0` baseline at `9c592a4`, the later native M33 runner at
`e77e7ed`, DR0/DR1 at `7b38973`, and the DR2 research provenance.

## Standards and toolchain

- [FIPS 202: SHA-3 Standard](https://nvlpubs.nist.gov/nistpubs/FIPS/NIST.FIPS.202.pdf)
- [FIPS 203: ML-KEM](https://nvlpubs.nist.gov/nistpubs/FIPS/NIST.FIPS.203.pdf)
- [FIPS 204: ML-DSA](https://nvlpubs.nist.gov/nistpubs/FIPS/NIST.FIPS.204.pdf)
- [MLIR-AIE](https://github.com/Xilinx/mlir-aie), [LLVM-AIE / Peano](https://github.com/Xilinx/llvm-aie), and [XRT](https://github.com/Xilinx/XRT)

The pinned environment and its evidence boundaries are recorded in
[`toolchain.yaml`](toolchain.yaml) and
[the Windows setup guide](docs/SETUP_WINDOWS.md).
