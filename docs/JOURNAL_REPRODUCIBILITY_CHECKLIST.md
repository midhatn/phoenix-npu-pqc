# Journal Reproducibility Checklist

Use this checklist before a manuscript, release candidate, or any statement
about physical evidence. A checked item means the cited material was retained.

## Environment and source identity

- [ ] Record clone URL, branch, `git rev-parse HEAD`, status, OS, PowerShell
  7, Python, and all tools used by the host-safe audit.
- [ ] For any future physical work, separately record MLIR-AIE/IRON, XRT,
  driver, firmware, NPU identity, compiler, command line, and operator
  authorization.
- [ ] Retain `toolchain.yaml`, package pins, and unresolved dependency-hash
  limitations.
- [ ] Cite the applicable primary standard with URL: [FIPS
  202](https://nvlpubs.nist.gov/nistpubs/FIPS/NIST.FIPS.202.pdf), [FIPS
  203](https://nvlpubs.nist.gov/nistpubs/FIPS/NIST.FIPS.203.pdf), or [FIPS
  204](https://nvlpubs.nist.gov/nistpubs/FIPS/NIST.FIPS.204.pdf).

## Hashes, protected evidence, and clean clone

- [ ] Run
  `pwsh -File .\scripts\validate_clean_clone.ps1 -InstallHostDependencies`
  from a clean-drive clone and retain its one timestamped report. The switch
  explicitly installs and verifies pinned `numpy==2.5.2`. Without it, a
  missing or mismatched NumPy installation must stop with an actionable
  refusal before the host-safe suite.
- [ ] Confirm the report verifies every entry in
  `docs/pqc_dr2_evidence_20260818/SHA256SUMS` and records no protected-tree
  Git diff.
- [ ] Preserve `docs/pqc_dr2_evidence_20260818/**` and its `SHA256SUMS`
  byte-for-byte; never overwrite a historical log or script to “refresh” it.
- [ ] State that the default audit is host-safe and has no hardware-dispatch
  switch.

## Host checks and physical-run safety

- [ ] Retain the explicit host-safe suite plan, suite output, Python
  compilation result, manifest check, and local link/lint checks used for the
  release.
- [ ] Do not invoke retained native or historical scripts through the
  clean-clone path.
- [ ] Before any separately approved physical experiment, freeze source and
  vector inputs, define stop conditions, document safety/rollback procedure,
  and retain unfiltered raw stdout/stderr.
- [ ] Label host, compile-only, diagnostic, terminal-probe, and physical
  results distinctly.

## Evidence, statistics, and negative results

- [ ] Report vector count, pass/fail/skip count, backend label, exit status,
  repetitions, seed policy, timing method, summary statistic, dispersion,
  and outlier policy.
- [ ] State the oracle and comparison criterion (bit-exact or the named
  numerical tolerance) and retain the raw comparisons.
- [ ] State DR2b and DR2c only within their narrow terminal scopes; neither
  is integrated K-PKE.KeyGen evidence.
- [ ] State DR2d as `TOTAL 0/25 FAIL`, exit 1, unless independently retained
  future physical evidence supports a different dated claim.
- [ ] Retain negative, failed, unavailable, and contradictory outcomes with
  equal provenance. Do not omit them from release comparisons.

## Citation and archive checklist

- [ ] Cite repository metadata from [`CITATION.cff`](../CITATION.cff), the
  relevant FIPS URL, and the precise dated DR2 status record at each claim.
- [ ] Include a source revision and evidence path for every manuscript
  figure/table.
- [ ] Do not claim a DOI, immutable archive, FIPS conformance, certification,
  complete ML-KEM/ML-DSA, constant-time behavior, or 100% NPU residency unless
  separately established and cited.
- [ ] Release only with a limitation statement preserving the DR2d negative
  result and the narrow DR2b/DR2c boundaries.
