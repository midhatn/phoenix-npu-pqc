# Journal Reproducibility Checklist

Use this checklist before a manuscript, release candidate, or statement about
physical evidence. A checked item means the cited material was retained.

## Source and native environment

- [ ] Record clone URL, branch, `git rev-parse HEAD`, working-tree status,
  Windows version, CPython 3.13 x64, XRT, driver, firmware, MLIR-AIE/IRON,
  `pyxrt`, and Peano identity.
- [ ] Retain `toolchain.yaml`, direct artifact byte lengths/SHA-256 values, and
  the explicit limitation that official `iron_setup.py` transitive dependencies
  are not fully hash-locked.
- [ ] Use `py .\install` only on the target Phoenix laptop when a physical run
  is intended. It delegates to `install.py` and, after successful full native
  provisioning, invokes the canonical runner under checkout-local ironenv.
- [ ] Treat `--check-only`, `--download-only`, `--self-test`, `--no-tests`,
  canonical `--list`, and canonical `--preflight-only` as non-dispatching.

## Canonical physical evidence

- [ ] Use only `py .\run_all_silicon_tests.py` for a silicon claim; do not use
  `run_all_pqc_tests.py`, CI, clean-checkout audit output, compile-only output, or
  a diagnostic as a substitute.
- [ ] Retain the exact order DR0, DR1, DR2a, DR2b, DR2c and exact totals
  24/24, 33/33, 13/13, 13/13, 11/11. Reject unavailable, skipped, fallback,
  reference, generic-only, malformed, and wrong-total output.
- [ ] Record the exact silicon backend for every gate and the fail-fast exit
  status. Confirm DR2d was never dispatched by the canonical suite.
- [ ] Before claiming current 94/94, retain a complete current canonical pass
  from the target laptop. The 2026-08-18 fresh four-sub-suite result is 61/61
  (DR0, DR2a, DR2b, DR2c), not 94/94.
- [ ] State the DR1 historical record separately: SHA-256
  `85B373B1E3B8A1BD883DA6BBDE73F874EE5C331B4AE419E5D161758A64EB4A7E`,
  reported backend `dr1-mldsa44-expanda-rejntt:silicon`, and reported
  `TOTAL 33/33 PASS`. Mark it as an external operator-retained assertion: the
  raw log is absent from this repository and is not independently reproducible.
- [ ] Retain raw stdout/stderr and, when requested, the timestamped
  `--evidence-dir` JSON provenance record.

## Host preflight and protected evidence

- [ ] Run `python run_all_pqc_tests.py` only as host preflight and label it
  clearly as not silicon validation.
- [ ] Run
  `pwsh -File .\scripts\validate_clean_clone.ps1 -InstallHostDependencies`
  only for the strict clean-checkout host audit. Despite its retained filename,
  it creates no clone: it rejects staged, unstaged, and untracked changes and
  records/reasserts immutable `HEAD`. The audit has no hardware-dispatch switch;
  retain its host report separately from a physical record.
- [ ] Confirm every existing entry in
  `docs/pqc_dr2_evidence_20260818/SHA256SUMS` verifies and that the protected
  tree has no Git diff. Do not modify the bundle or either manifest.

## Scope and negative-result controls

- [ ] State DR2b and DR2c only within their narrow terminal scopes; neither is
  integrated K-PKE.KeyGen evidence.
- [ ] State DR2d as `TOTAL 0/25 FAIL`, exit 1. Retain failed, unavailable, and
  contradictory outcomes with equal provenance.
- [ ] Do not claim complete ML-KEM/ML-DSA, FIPS conformance, constant-time
  behavior, side-channel resistance, zeroization, certification, or 100% NPU
  residency without separate evidence.
- [ ] Cite the relevant primary standard: [FIPS 202](https://nvlpubs.nist.gov/nistpubs/FIPS/NIST.FIPS.202.pdf),
  [FIPS 203](https://nvlpubs.nist.gov/nistpubs/FIPS/NIST.FIPS.203.pdf), or
  [FIPS 204](https://nvlpubs.nist.gov/nistpubs/FIPS/NIST.FIPS.204.pdf).
