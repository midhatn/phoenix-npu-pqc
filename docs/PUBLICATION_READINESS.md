# Publication Readiness

## Release boundary

This note distinguishes source/host checks, dated physical evidence, and a new
canonical physical run. It does not authorize a hardware run, modify protected
evidence, create a tag, or convert a host result into a silicon claim.

The only accepted NPU result is a physical pass of
`py .\run_all_silicon_tests.py` on the target Phoenix laptop. The runner
compiles and dispatches five ordered native gates: DR0, DR1, DR2a, DR2b, and
DR2c. A complete current result would be 94/94, but **no current 94/94 claim is
made here**.

## Claim and evidence matrix

| Proposed claim | Supporting record | Validated boundary | Not established |
| --- | --- | --- | --- |
| Current working-tree native release flow is fail-closed. | `install`, `install.py`, `run_all_silicon_tests.py`, and host contract tests. | Full install uses the native pins and hands off to the canonical runner; exact backend/total parsing rejects nonphysical output. | A physical pass without running it on the target laptop, or release of files not included in a reviewed commit. |
| Fresh four-sub-suite result exists. | Operator verification on 2026-08-18. | DR0 24/24, DR2a 13/13, DR2b 13/13, and DR2c 11/11, totaling 61/61, against retained current-source hashes. | DR1 in the current checkout or a current 94/94 canonical pass. |
| External historical DR1 assertion exists. | [DR1 validation record](PQC_DR1_SILICON_VALIDATION_PENDING.md). | Operator-supplied log SHA-256 `85B373B1E3B8A1BD883DA6BBDE73F874EE5C331B4AE419E5D161758A64EB4A7E`, reported backend `dr1-mldsa44-expanda-rejntt:silicon`, reported `TOTAL 33/33 PASS`; raw log absent from this repository. | Independent reproduction of that log, a current DR1 rerun, or a current five-gate result. |
| DR2b is solved only for its narrow physical terminal-noise scope. | [DR2b physical record](PQC_DR2B_SILICON_VALIDATION_PENDING.md). | One SHAKE256/CBD3/NTT terminal polynomial under its stated corpus. | Integrated K-PKE.KeyGen or full ML-KEM. |
| DR2c is solved only for its narrow physical terminal-KeyGen-row scope. | [DR2c physical record](PQC_DR2C_SILICON_VALIDATION_PENDING.md). | One terminal t-hat row under its stated corpus. | Integrated K-PKE.KeyGen, complete ML-KEM, or complete residency. |
| DR2d remains unresolved. | [DR2d status record](PQC_DR2D_SILICON_VALIDATION_PENDING.md) and protected evidence. | `TOTAL 0/25 FAIL`, exit 1. | DR2 closure, integrated KeyGen correctness, or a pass inferred from diagnostics. |

## Installation and verification controls

`py .\install` is the primary Windows entry point. It delegates to `install.py`
and, after a successful full native installation, invokes the canonical runner
under checkout-local ironenv. The direct XRT SDK and `mlir_aie` wheel are
size- and SHA-256-verified; the source checkout is commit-pinned. The official
`iron_setup.py` transitive dependency set is **not fully hash-locked**. Do not
claim all packages are locked. `kyber-py`, `dilithium-py`, and `pytest` are
optional host/reference packages, not default physical-installer dependencies.
The XRT SDK direct-download **archive release** is `2.21.75`; its separately
recorded **runtime-reported version** is `2.21.0`. The two fields are explicit
in `toolchain.yaml` and are not interchangeable artifact pins.

The following modes never compile or dispatch: `install --check-only`,
`--download-only`, `--self-test`, and `--no-tests`; canonical `--list` and
`--preflight-only` are also non-dispatching. `run_all_pqc_tests.py` and CI are
host preflight only.

For a new physical record, preserve raw runner output and optional timestamped
JSON provenance emitted by:

```powershell
py .\run_all_silicon_tests.py --evidence-dir release-evidence\silicon
```

The evidence directory is outside the protected DR2d bundle. Never edit
`docs/pqc_dr2_evidence_20260818/**` or `SHA256SUMS`; verify it with the existing
manifest instead.

## Remaining blockers and release rule

1. Include the following required native-release artifacts in the reviewed,
   tracked release commit: `tests/pqc_device_resident/test_dr1_mldsa44_rejntt_silicon.py`,
   `tests/test_canonical_silicon_runner_behavior.py`, and
   `tests/test_canonical_silicon_runner_contract.py`. A clean `HEAD` without
   these files is not the reviewed release candidate.
2. Run the strict `validate_clean_clone.ps1` clean-checkout host audit only
   after that commit, from a checkout with no staged, unstaged, or untracked
   files; retain the reported immutable `HEAD`.
3. Rerun the complete current canonical suite on the target laptop before
   claiming 94/94 or a current five-gate silicon pass.
4. Preserve the DR2d `0/25` failure and distinguish it from all compile-only,
   diagnostic, host, and narrow sub-gate evidence.
5. Do not claim complete ML-KEM/ML-DSA, FIPS conformance, constant-time
   behavior, secure zeroization, side-channel resistance, certification, or
   100% residency.
6. Retain source revision, toolchain/driver identity, commands, exact backend
   lines, exact totals, raw output, and manifest verification with any release
   evidence.
