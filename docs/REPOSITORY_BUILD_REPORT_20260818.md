# Phoenix NPU PQC repository build report — 2026-08-18

## Result

The active repository identity is **Phoenix NPU PQC** (`phoenix-npu-pqc`).
Current-facing documentation, metadata, issue forms, installation text, and CI
now describe only PQC research. The source-compatible Python import remains
`phoenix_sdr_dsp`; this is an explicit compatibility decision, not the
repository name.

The historical claim boundary is unchanged:

- M32/M33 is a hybrid native and host/NPU foundation.
- DR0/DR1 and DR2a/DR2b/DR2c are narrow physical-result records.
- Integrated DR2d ML-KEM-512 K-PKE.KeyGen remains an unresolved physical
  `TOTAL 0/25 FAIL`, exit 1.
- 100% NPU residency remains a research goal, not a completed capability.

## Implemented changes

- Replaced the root README and `docs/README.md` with PQC-only navigation and
  explicit physical-versus-compile-only evidence boundaries.
- Added [the split record](REPOSITORY_SPLIT_20260818.md) with the preserved
  M33e `v1.0.0` / `9c592a4c077c73f2ebf910aca0b6575664b0726f`, native M33
  `e77e7ed2783d88b5451394866d7ddfccd9db4f69`, and DR0/DR1
  `7b38973789fafb950a26551bc947f4fcaa91ec25` anchors.
- Added [the reproducibility guide](PQC_REPRODUCIBILITY.md), including
  host-safe commands, canonical NIST and AMD/Xilinx references, exact known
  DR2 cache/hash anchors, failure chronology, and continuation questions.
- Rewrote current metadata and contributor-facing configuration for
  `phoenix-npu-pqc`: `CITATION.cff`, `CONTRIBUTING.md`, `SECURITY.md`,
  `toolchain.yaml`, the then-current native `install.py`, issue forms, pull-request template,
  Dependabot comment, Markdown-link configuration, and CI.
- Added `run_all_pqc_tests.py`, an explicit eight-module host-safe allowlist
  with `--help`, `--list`, and `--dry-run`. `run_all_silicon_tests.py` is now
  a compatibility forwarder to that host-safe runner and does not dispatch
  hardware.
- Updated the current PQC roadmaps and repaired two retained local
  documentation references that pointed to files excluded by the repository
  split. The historical claims themselves were not changed.

## Evidence recovery and integrity

The raw W0 capture
`PQC_DR2D_W0_token_tap_tcId01_raw_20260818.bin` was restored from an existing
root-level byte-identical copy. The seven protected
`sigma_prf_retry_chain/*.ps1` files were restored from the corresponding
root-level copies after Git line-ending conversion caused their initial
checksum mismatch. The `SHA256SUMS` manifest was not modified.

`.gitattributes` now marks the protected PowerShell evidence files binary and
unsets their EOL attribute, preventing future line-ending conversion from
changing the preserved bytes. The raw capture is explicitly exempted from the
generic binary ignore rule so it remains visible to Git. No evidence gap
remains in the checked-out manifest.

## Checks performed

All commands below were host-only. No NPU toolchain was loaded, no AIE program
was compiled, and no physical hardware command was invoked.

| Check | Result |
| --- | --- |
| `python run_all_pqc_tests.py --help` | PASS |
| `python run_all_pqc_tests.py --dry-run` | PASS; eight explicit host-safe modules listed |
| `python run_all_silicon_tests.py --dry-run` | PASS; forwards to the same host-safe plan |
| `python run_all_pqc_tests.py` | PASS; 8/8 modules passed; 78 tests ran with one documented Windows-IRON-environment skip and no failures |
| `python -m compileall -q phoenix_sdr_dsp tests run_all_pqc_tests.py run_all_silicon_tests.py install install.py` | PASS |
| Python AST, YAML, JSON, citation-field, toolchain, CI host-only, and import-compatibility checks | PASS |
| Local Markdown-link check over all retained Markdown files | PASS |
| `(cd docs/pqc_dr2_evidence_20260818 && sha256sum -c SHA256SUMS)` | PASS; every manifest entry verified |
| `git diff --check` | PASS |
| Placeholder scan of current docs/configuration | PASS; no unfinished-work marker found |

## Publication and deliberate non-actions

- The history-preserving repository split was committed and pushed to the
  private `midhatn/phoenix-npu-pqc` GitHub repository. No release or new tag
  was created.
- No hardware authorization, native dispatch, cache deletion, driver update,
  or historical-script execution occurred.
- The checksum manifest and retained evidence contents were not rewritten.
- No result in this report changes the DR2d physical outcome or expands a
  residency, correctness, conformance, security, or production claim.
