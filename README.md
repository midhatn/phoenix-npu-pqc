# Phoenix NPU PQC

<div align="center">

![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)
![Target: AMD Phoenix NPU1](https://img.shields.io/badge/Target-AMD%20Ryzen%20AI%20NPU1%20(AIE2)-blue)
![Research: Post-Quantum Cryptography](https://img.shields.io/badge/Research-Post--Quantum%20Cryptography-8a2be2)
![Standards: FIPS 202/203/204](https://img.shields.io/badge/Standards-FIPS%20202%20%2F%20203%20%2F%20204-005ea8)
![Status: DR8 Closed (319/319 Silicon PASS)](https://img.shields.io/badge/Status-DR8%2075%2F75%20PASS%20%C2%B7%20319%2F319%20Silicon-brightgreen)
[![CI](https://github.com/midhatn/phoenix-npu-pqc/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/midhatn/phoenix-npu-pqc/actions/workflows/ci.yml)

**Private research repository for post-quantum cryptography on AMD Ryzen AI Phoenix NPU1 (XDNA1 / AIE2).**

</div>

## Research status

Phoenix NPU PQC is a focused continuation of the PQC work separated from the
historical `phoenix-sdr-dsp` repository. It contains ML-KEM and ML-DSA research
code, host-preflight contract tests, native physical gates, toolchain
metadata, and the retained DR2/DR3/DR4/DR5/DR6/DR7/DR8 provenance needed to interpret the work accurately.

| Research layer | Current evidence boundary |
| --- | --- |
| **M32 / M33 foundation** | Historical v1.0.0 baseline: M32 ML-KEM and M33 ML-DSA work combined native primitive gates with host/NPU composers. |
| **DR0 / DR1** | Fail-closed native gates exist for the M33 ring product (24/24) and the ML-DSA-44 ExpandA / rejection-sampling / NTT path (33/33), both verified on physical Phoenix silicon. |
| **DR2a / DR2b / DR2c** | Independent physical passes verified for ML-KEM-512 `SampleNTT` (13/13), CBD3/NTT noise (13/13), and terminal KeyGen row (11/11). |
| **DR2d** | Complete ML-KEM-512 K-PKE.KeyGen 6-worker dataflow pipeline. Recorded physical result is **TOTAL 25/25 PASS** across the official NIST ACVP corpus on physical Phoenix NPU silicon. |
| **DR3** | Complete ML-KEM-512 K-PKE.Encrypt 5-worker dataflow pipeline. Recorded physical result is **TOTAL 25/25 PASS** across the official NIST ACVP corpus on physical Phoenix NPU silicon. |
| **DR4** | Complete ML-KEM-512 K-PKE.Decrypt 2-worker dataflow pipeline. Recorded physical result is **TOTAL 25/25 PASS** across the official NIST ACVP corpus on physical Phoenix NPU silicon. |
| **DR5** | Complete ML-KEM-512 ML-KEM.KeyGen 6-worker dataflow pipeline. Recorded physical result is **TOTAL 25/25 PASS** across the official NIST ACVP corpus on physical Phoenix NPU silicon. |
| **DR6** | Complete ML-KEM-512 ML-KEM.Encaps 6-worker dataflow pipeline. Recorded physical result is **TOTAL 25/25 PASS** across the official NIST ACVP corpus on physical Phoenix NPU silicon. |
| **DR7** | Complete ML-KEM-512 ML-KEM.Decaps 6-worker dataflow pipeline. Recorded physical result is **TOTAL 25/25 PASS** across the official NIST ACVP corpus on physical Phoenix NPU silicon. |
| **DR8** | Complete NIST FIPS 203 Parameter-Set Expansion (ML-KEM-768 & ML-KEM-1024 across KeyGen, Encaps, Decaps with implicit rejection). Recorded physical result is **TOTAL 75/75 PASS** across all parameter sets on physical Phoenix NPU silicon. |
| **Canonical suite** | Complete canonical runner passes all 12 gates (**319/319 cases**) on physical Phoenix silicon. |
| **Program goal** | 100% NPU residency for the supported FIPS 202/203/204 cryptographic operations, with no host cryptographic fallback or intermediate repair. |

The claim boundaries and roadmap sequencing are defined in
[the device-residency roadmap](docs/PQC_DEVICE_RESIDENCY_ROADMAP.md) and
[the PQC roadmap](docs/PQC_ROADMAP.md).

### Current physical-result status — 2026-08-29

The canonical silicon test suite executed and validated **319 / 319 cases across all 12 gates (DR0 24/24, DR1 33/33, DR2a 13/13, DR2b 13/13, DR2c 11/11, DR2d 25/25, DR3 25/25, DR4 25/25, DR5 25/25, DR6 25/25, DR7 25/25, DR8 75/75)** on the physical AMD Phoenix NPU (Ryzen 9 7940HS w/ AIE2). All cryptographic transformations execute 100% on-device with zero host fallback.

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
| [`tests/`](tests/) | Host-preflight PQC contract/reference tests plus the fail-closed `*_silicon.py` native gates dispatched by the canonical runner. |
| [`docs/`](docs/README.md) | PQC-only documentation index, roadmaps, design records, provenance, and protected evidence navigation. |
| [`docs/pqc_dr2_evidence_20260818/`](docs/pqc_dr2_evidence_20260818/README.md) | Byte-preserved DR2d forensic evidence. It is read-only research evidence, not an authorization to execute hardware. |
| [`toolchain.yaml`](toolchain.yaml) | Machine-readable Phoenix NPU PQC toolchain and historical-result metadata. |
| [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md) | License, dependency, vector, and transliteration provenance ledger. |

## Windows clean clone: two commands

This repository is NPU-native. From the root of a fresh Windows clone on the
target Phoenix laptop:

```powershell
git clone https://github.com/midhatn/phoenix-npu-pqc.git
cd phoenix-npu-pqc
py .\install
```

`install` is the primary extensionless launcher. It is standard-library only,
so it runs on a stock **CPython 3.13 x64 on Windows** before any environment
exists, and it delegates to the maintained implementation in `install.py`
(`py .\install.py` remains supported). It provisions the full native
toolchain:

- the pinned XRT Windows SDK zip, verified by exact byte length and SHA-256
  from [`toolchain.yaml`](toolchain.yaml);
- the `mlir-aie` source tree at an exact pinned commit;
- the pinned `mlir_aie` CPython 3.13 `win_amd64` wheel, verified by exact byte
  length and SHA-256, installed offline from a local wheelhouse;
- the official [`iron_setup`](https://xilinx.github.io/mlir-aie/1.4.1/buildHostWinNative/)
  native-Windows IRON environment in `third_party/mlir-aie/ironenv`;
- vendored `pyxrt` bindings and the Peano / `llvm-aie` `clang++` smoke check.

On a successful full install it then **automatically invokes the canonical
physical runner** `run_all_silicon_tests.py` under that checkout `ironenv`.

**Integrity boundary, stated plainly.** The directly downloaded XRT SDK zip and
`mlir_aie` wheel are size- and SHA-256-verified, and `mlir-aie` is commit
pinned. The official `iron_setup` step then resolves a further transitive Python
dependency set from package indexes, and that set is **not** fully hash-locked
by this repository. A fully hash-locked environment would require a complete,
independently produced verified wheelhouse. No such claim is made here.
The physical installer does **not** install `kyber-py`, `dilithium-py`, or
`pytest` from PyPI: none is required by the five canonical native gates.
Those are optional host/reference dependencies and must be separately pinned
and verified by an operator when a non-canonical oracle workflow needs them.

Maintenance modes never compile an AIE program and never dispatch hardware:
`py .\install --check-only`, `py .\install --download-only`,
`py .\install --self-test`, and `py .\install --no-tests` (full provisioning
without the automatic physical handoff). `--no-tests` and `--run-tests` are
mutually exclusive and fail closed when combined.

## Canonical silicon validation

`run_all_silicon_tests.py` is the **only** runner whose output may be described
as silicon validation. Its default action physically compiles and dispatches
five ordered fail-closed native gates on the Phoenix NPU:

| Order | Gate | Backend label | Cases |
| --- | --- | --- | --- |
| 1 | DR0 M33 device-resident polynomial product | `m33-dr0:silicon` | 24 |
| 2 | DR1 ML-DSA-44 ExpandA rejection-sampling NTT | `dr1-mldsa44-expanda-rejntt:silicon` | 33 |
| 3 | DR2a ML-KEM-512 bounded SHAKE128 `SampleNTT` | `dr2a-mlkem512-samplentt:silicon` | 13 |
| 4 | DR2b ML-KEM-512 SHAKE256 CBD3 noise-to-NTT | `dr2b-mlkem512-noise-ntt:silicon` | 13 |
| 5 | DR2c ML-KEM-512 K-PKE.KeyGen terminal `t-hat` row | `dr2c-mlkem512-keygen-row:silicon` | 11 |

```powershell
py .\run_all_silicon_tests.py
```

Each gate runs as its own subprocess. A gate is accepted only when it exits 0,
prints its exact `Backend:` line, prints its anchored `TOTAL n/n PASS` line for
the exact expected case count, and emits no unavailable / skip / reference /
fallback / diagnostic marker. The first failure stops the run with a non-zero
exit status. A full pass means **5 gates / 94 cases physically passed on Phoenix
NPU** (24 + 33 + 13 + 13 + 11). That is a narrow milestone result: it is **not**
complete ML-KEM or ML-DSA and **not** 100% algorithm residency. Integrated
ML-KEM-512 K-PKE.KeyGen (DR2d) is deliberately not dispatched; its recorded
physical result is `TOTAL 0/25 FAIL`, exit 1.

Two non-dispatching inspection modes exist: `--list` prints the ordered gate
plan and exits, and `--preflight-only` probes Windows, CPython 3.13 x64, the
Phoenix NPU through `xrt-smi examine`, `pyxrt`, `aie`, IRON, and Peano, then
exits before any AIE compilation.

**No NPU claim is accepted unless canonical native runner output from the target
laptop passes.** The fresh 2026-08-18 four-sub-suite result is 61/61; the DR1
33/33 entry is an external operator-retained historical assertion whose raw log
is absent from this checkout. Neither is a current 94/94 result. Use
`--evidence-dir release-evidence/silicon` to retain a
timestamped JSON record with checkout provenance and merged gate output from a
new canonical run. The retained DR2a/DR2b/DR2c logs remain narrow evidence for
those gates only.

## Host preflight (never silicon evidence)

`run_all_pqc_tests.py` is an explicit **host preflight**. It runs contract,
reference, and production-source checks that work on an ordinary host, never
selects a `*_silicon.py` gate, and never loads the MLIR-AIE runtime, compiles an
AIE program, or dispatches an NPU:

```bash
python run_all_pqc_tests.py --dry-run
python run_all_pqc_tests.py
```

A pass here means the host preflight passed. It can never satisfy, substitute
for, or be labelled silicon validation. Repository CI runs only this preflight.

`g++` is optional. When it is on `PATH`, applicable native C++ **host-reference**
checks run as part of the preflight. Without it, those checks are reported as
skipped while Python and contract coverage still run. It is not an NPU, AIE,
XRT, IRON, or Visual Studio requirement.

For an additional normal-user PowerShell 7 strict clean-checkout audit with
commit/status, tool, Python, and protected-evidence checks, run:

```powershell
pwsh -File .\scripts\validate_clean_clone.ps1 `
    -InstallHostDependencies
```

The retained script name does not create a clone. It fails before testing unless
the whole checkout is clean (staged, unstaged, and untracked files), records and
reasserts the exact immutable `HEAD`, and then delegates to `py .\install
--no-tests` when requested. Provisioning keeps its verified pins without
triggering the physical handoff. The audit invokes the canonical runner only as
`run_all_silicon_tests.py --list`. It has no hardware-dispatch switch, produces
no silicon evidence, and writes one timestamped report under the ignored
`release-evidence/` directory. See the [publication readiness
matrix](docs/PUBLICATION_READINESS.md) and [journal reproducibility
checklist](docs/JOURNAL_REPRODUCIBILITY_CHECKLIST.md) for scope, retention, and
release controls.

See [CONTRIBUTING.md](CONTRIBUTING.md) before proposing any change that could
affect a physical-run workflow.

Read [`docs/PQC_AUDIT_REMEDIATION_20260818.md`](docs/PQC_AUDIT_REMEDIATION_20260818.md)
for the current source-backed correction ledger, research-use boundary, and
remaining journal-reproducibility blockers.

## Expert continuation and reproducibility

Start with the [PQC reproducibility guide](docs/PQC_REPRODUCIBILITY.md) for
the exact host-preflight and canonical native commands, integrity checks,
toolchain pins, known caches,
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

## License and citation

Original project work is licensed under the
[Apache License 2.0](LICENSE). File-level SPDX identifiers and third-party
notices remain authoritative when they differ from the project default; see
[LICENSE_HISTORY.md](LICENSE_HISTORY.md), [NOTICE](NOTICE), and
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md). Immutable upstream anchors,
local SHA-256 identities, and ACVP extraction records are in
[THIRD_PARTY_PROVENANCE.md](THIRD_PARTY_PROVENANCE.md). Research users should
use [`CITATION.cff`](CITATION.cff) or [`.zenodo.json`](.zenodo.json) when
citing or archiving the software.
