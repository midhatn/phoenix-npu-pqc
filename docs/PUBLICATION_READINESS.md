# Publication Readiness

## Purpose and source identity

This maintained note is the release boundary for the private Phoenix NPU PQC
research repository. It does not authorize a physical run, revise protected
evidence, create a DOI, or claim that an immutable archive exists. Read it
with the [PQC reproducibility guide](PQC_REPRODUCIBILITY.md), the
[DR2 expert escalation](PQC_DR2_EXPERT_ESCALATION_20260818.md), and
[`docs/pqc_dr2_evidence_20260818/`](pqc_dr2_evidence_20260818/README.md).

The mathematical vocabulary and algorithm numbering are bounded by the
already cited primary standards: [NIST FIPS
202](https://nvlpubs.nist.gov/nistpubs/FIPS/NIST.FIPS.202.pdf), [NIST FIPS
203](https://nvlpubs.nist.gov/nistpubs/FIPS/NIST.FIPS.203.pdf), and [NIST
FIPS 204](https://nvlpubs.nist.gov/nistpubs/FIPS/NIST.FIPS.204.pdf). The
ML-KEM design uses the documented ring
$R_q = \mathbb{Z}_{3329}[x]/(x^{256}+1)$; neither the notation nor host
contracts establish FIPS conformance.

## Claim and evidence matrix

| Proposed claim | Supporting tracked evidence | Validated boundary | Not established |
| --- | --- | --- | --- |
| A current clone can run an explicit host-safe audit. | `scripts/validate_clean_clone.ps1`, `run_all_pqc_tests.py`, and CI host-safe tests. | Git/tool capture, Python compilation, allowlisted contract/reference checks, and manifest verification; no native toolchain or NPU is used. | Physical execution, AIE compilation, timing, or a new device result. |
| Protected DR2 forensic evidence is intact. | `docs/pqc_dr2_evidence_20260818/SHA256SUMS` plus Git status/diff checks. | Manifest-covered file bytes and absence of a protected working-tree diff. | A new physical experiment or an interpretation beyond the dated records. |
| DR2b is solved only for its narrow physical terminal-noise scope. | [DR2b physical record](PQC_DR2B_SILICON_VALIDATION_PENDING.md). | One ML-KEM-512 $\eta_1=3$ noise polynomial: SHAKE256 PRF, CBD3, then FIPS 203 NTT for the stated frozen requests. | Integrated K-PKE.KeyGen, full ML-KEM, residency beyond that terminal scope, or conformance. |
| DR2c is solved only for its narrow physical terminal-KeyGen-row scope. | [DR2c physical record](PQC_DR2C_SILICON_VALIDATION_PENDING.md) and handoff. | The recorded 11/11 first and 22/22 repeated terminal-row result. | Integrated K-PKE.KeyGen, complete matrix/noise/keygen residency, or full ML-KEM. |
| DR2d remains unresolved. | [DR2d status record](PQC_DR2D_SILICON_VALIDATION_PENDING.md), [design](PQC_DR2D_DESIGN.md), and protected evidence. | The integrated physical record is `TOTAL 0/25 FAIL`, exit 1. Host/compile-only/diagnostic observations remain diagnostic. | A passing physical DR2d result, integrated ML-KEM KeyGen correctness, or DR2 closure. |

## Exact validated and unvalidated boundaries

- **Host-safe evidence now:** default local and CI checks use the explicit
  allowlist in `run_all_pqc_tests.py`; retained `*_silicon.py` gates are
  excluded. Passing host output is not silicon evidence.
- **DR2b and DR2c:** each is a solved physical result only within the narrow
  terminal scope stated above. Neither one establishes integrated
  ML-KEM-512 K-PKE.KeyGen.
- **DR2d:** the physical result is 0/25 fail. It remains a release and
  publication blocker. Do not reclassify a compile-only result, an ELF
  inspection, terminal probe, or host oracle as a production pass.
- **Broader exclusions:** this repository does not establish complete ML-KEM
  or ML-DSA, FIPS conformance, constant-time behavior, side-channel
  resistance, secure zeroization as a certification claim, CMVP validation,
  or the research goal of 100% device residency.

## Clean-drive protocol

1. Clone the intended revision into a new directory and record remote URL,
   `git rev-parse HEAD`, and status.
2. In normal-user PowerShell 7 run
   `pwsh -File .\scripts\validate_clean_clone.ps1
   -InstallHostDependencies`. The explicit switch installs and verifies
   pinned `numpy==2.5.2`; it does not add a hardware-dispatch path.
3. The script records commit/status/tool versions, compiles maintained Python,
   lists and runs the repository's actual host-safe suite, confirms the
   protected evidence tree has no Git diff, and verifies every
   `SHA256SUMS` entry. It writes one timestamped text report under ignored
   `release-evidence/clean-clone/`.
4. Retain that report, the source revision, `toolchain.yaml`, and the
   manifest-verification result with the release record.
5. Do not add a hardware switch or use the clean-clone script to invoke a
   historical/native gate. Any future physical protocol requires separately
   reviewed operator, safety, toolchain, and evidence procedures.

## Artifact retention, citations, and reporting

Preserve protected evidence byte-for-byte, including its manifest; do not
rewrite logs, patches, historical scripts, or `SHA256SUMS`. Store new host
reports outside the ignored working directory in the approved retention
location along with commit, tool versions, commands, exit status, and raw
stdout/stderr. The ignored output directory is not an archive.

Cite [FIPS 202](https://nvlpubs.nist.gov/nistpubs/FIPS/NIST.FIPS.202.pdf),
[FIPS 203](https://nvlpubs.nist.gov/nistpubs/FIPS/NIST.FIPS.203.pdf), and
[FIPS 204](https://nvlpubs.nist.gov/nistpubs/FIPS/NIST.FIPS.204.pdf) at the
relevant cryptographic claims; cite [`CITATION.cff`](../CITATION.cff) for
repository metadata; and cite the dated DR2 record for every DR2 physical
count. A report must state backend, pass/fail/skip count, vector corpus,
repetitions, timing definition, and exact host/native boundary.

Negative results are first-class evidence. Retain the DR2d 0/25 physical fail
and all later diagnostic/compile-only material alongside any future claim;
do not filter a release narrative to passing subsystems.

## Remaining publication blockers

1. An independently reviewed physical DR2d protocol and a successful,
   reproducible native result; the existing 0/25 result remains blocking.
2. A controlled physical-evidence corpus with raw transcripts, generated
   artifact hashes, toolchain/driver identity, and independently reviewed
   oracle criteria.
3. A complete dependency and source-provenance closure appropriate to the
   intended claim, including release archive planning if one is later created.
4. Clear separation of narrow DR2b/DR2c results from integrated claims in all
   abstracts, tables, and release notes.

## Release and tag policy

### Clean-drive RC.1 result

The first independent Windows clean-drive execution of `v0.1.0-rc.1` on
2026-08-18 used PowerShell 7.6.5, Git 2.48.1.windows.1, and Python 3.13.15.
The protected-tree Git gate and all 35 protected evidence hashes passed, the
18-module plan was enumerated, and maintained Python compiled. The host-safe
suite then reported 15 import failures because system Python did not contain
NumPy; three modules passed, including the protected-manifest and
release-material contracts. No NPU access or native compilation occurred.
This is a prerequisite failure, not a host-suite pass. RC.2 adds an explicit
pinned-dependency installation switch rather than rewriting RC.1.

Create an annotated RC only after the host-safe report, protected-manifest
verification, reviewed diff, and explicit limitation statement are retained.
Its message must identify the exact commit and say that no new physical result
is implied. It must not claim a Zenodo DOI, immutable archive, DR2 closure, or
physical pass unless those items actually exist and are independently cited.

Do not tag a release that modifies `docs/pqc_dr2_evidence_20260818/` or its
`SHA256SUMS` as a continuation of this evidence line. A future physical release
must preserve this negative evidence and add separately reviewed new evidence
rather than rewriting history.
