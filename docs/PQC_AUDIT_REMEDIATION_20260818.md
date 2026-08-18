# Phoenix NPU PQC audit and remediation record — 2026-08-18

> **Superseding release-flow note.** This dated record describes the earlier
> host-forwarder state. Current `main` has a native-only five-gate canonical
> runner; see the root README and `PQC_REPRODUCIBILITY.md` for the current
> release boundary.

## Purpose, scope, and non-claims

This document records host-safe remediation of the research/document and
engineering audits completed on 2026-08-18. It identifies what was corrected
on current `main`, what remains historical evidence, and what requires a new
authorized native experiment or independent provenance review.

It does not report a new physical result. In particular, the integrated DR2d
ML-KEM-512 K-PKE.KeyGen physical record remains `TOTAL 0/25 FAIL`, exit 1.
Nothing in this document establishes complete ML-KEM, complete ML-DSA, FIPS or
CMVP conformance, constant-time behavior, side-channel resistance, secure
zeroization, or production readiness.

The protected [`pqc_dr2_evidence_20260818/`](pqc_dr2_evidence_20260818/README.md)
bundle and its `SHA256SUMS` manifest are immutable. They were verified, not
rewritten.

## Corrected normative references and mathematics

| Topic | Corrected statement | Authoritative source |
| --- | --- | --- |
| FIPS 202 | SHA3-* and SHAKE* are defined by equations in FIPS 202 §§6.1–6.3; use section references for those functions. KECCAK-p and its step mappings have algorithm identifiers. | https://nvlpubs.nist.gov/nistpubs/FIPS/NIST.FIPS.202.pdf |
| ML-KEM transforms | FIPS 203 NTT and NTT⁻¹ are Algorithms 9 and 10; `MultiplyNTTs` and `BaseCaseMultiply` are Algorithms 11 and 12. | https://nvlpubs.nist.gov/nistpubs/FIPS/NIST.FIPS.203.pdf |
| SampleNTT | FIPS 203 `SampleNTT` is Algorithm 7. A three-byte group yields two 12-bit candidates. With $p=3329/4096$, the expected number of groups to accept 256 coefficients is $256/(2p)\approx157.49$, or about 472.47 bytes. | https://nvlpubs.nist.gov/nistpubs/FIPS/NIST.FIPS.203.pdf |
| 840-byte model | 840 bytes provide 280 groups / 560 candidates. Under the independent-candidate binomial model, $\Pr[\mathrm{Bin}(560,3329/4096)<256]\approx2^{-261.24}$. This describes a fixed implementation cap; it is not an unbounded-sampler or conformance claim. | https://nvlpubs.nist.gov/nistpubs/FIPS/NIST.FIPS.203.pdf |
| ML-KEM layers | K-PKE.KeyGen/Encrypt/Decrypt are Algorithms 13–15; ML-KEM internal interfaces are Algorithms 16–18; external ML-KEM operations are Algorithms 19–21. | https://nvlpubs.nist.gov/nistpubs/FIPS/NIST.FIPS.203.pdf |
| ML-DSA interfaces | ML-DSA.KeyGen/Sign/Verify are Algorithms 1–3; internal interfaces are Algorithms 6–8; NTT/NTT⁻¹/BitRev8 are Algorithms 41–43. | https://nvlpubs.nist.gov/nistpubs/FIPS/NIST.FIPS.204.pdf |
| Phoenix topology | Phoenix/Hawk Point has five columns by four compute-tile rows (a 4×5 topology) and six concurrent workload contexts. The text uses “five columns × four rows” to prevent orientation ambiguity. | https://docs.kernel.org/accel/amdxdna/amdnpu.html |

The historical M32c kernel has a fixed 840-byte DMA-oriented SampleNTT
implementation and no limit-status field. Its deterministic zero-padding
exhaustion path is therefore explicitly outside any FIPS-conformance claim.
Future work must use a protocol that signals the bounded limit rather than
accepting an incomplete polynomial.

## Current corrections

1. **Historical setup/identity.** This dated record described a host-safe
   forwarder. The current `SETUP_WINDOWS.md` documents the native-only
   canonical runner and its separate host-preflight path.
2. **DR2 topology.** Current DR2d records use one definition: five computation
   workers W0–W4 plus serializer W5, six worker cores total. Evidence that maps
   only W0–W4 is labelled as such and is not treated as an integrated pass.
3. **DR2 status.** DR2c is described as a narrow recorded terminal-row
   physical `11/11` pass (repeated `22/22`), not integrated KeyGen. DR2d has
   no passing integrated physical result; its `0/25` failure remains blocking.
4. **Historical runner pin.** The W0 diagnostic preserves the historical
   `run_all_silicon_tests.py` SHA-256 `742591321ac5dc3069a51ded4e198905367f8dc6261df8c3ebae20b5e333fbad`.
   Current `main` intentionally has a different host-safe wrapper, so the
   diagnostic now rejects it with an explicit historical-baseline message
   instead of silently changing the evidence pin.
5. **Host-safe test coverage.** The default runner and CI include the repaired
   DR1/DR2 contract modules, DR2d W0 pin behavior, M33 native-runner contracts,
   DR0 host contracts, and installer pin-parser regression test. Native
   `*_silicon.py` files remain excluded.
6. **Historical toolchain parsing.** The former native `install.py` read nested
   `toolchain.xrt.sdk_*`, `toolchain.mlir_aie.*`, driver, and Python fields
   rather than silently relying on duplicated fallback values. This does not
   make the package installation hash-locked; that remains a release blocker.
7. **Research security boundary.** `SECURITY.md` now states the research-use,
   evidence-class, protected-evidence, and publication-risk boundaries.
8. **Licensing/provenance.** At the time of this audit,
   `THIRD_PARTY_NOTICES.md` and `LICENSES/Apache-2.0.txt` distinguished the
   then-current root MIT license from file-level Apache-2.0 SPDX declarations
   and recorded unresolved pq-crystals/vector provenance for formal review.
   The later project-wide Apache-2.0 transition preserves file-specific
   exceptions and the former MIT text under `LICENSES/MIT.txt`.
9. **Duplicate evidence.** Exactly 20 root-level files that were byte-identical
   to SHA-256-manifested protected copies were removed. The complete list,
   canonical replacements, and hashes are in
   [`PQC_EVIDENCE_DEDUPLICATION_20260818.md`](PQC_EVIDENCE_DEDUPLICATION_20260818.md).
   Unique artifacts, including PII-bearing historical captures, were retained
   and classified as access/publication risks.
10. **GitHub math rendering.** Maintained Markdown outside the immutable
    evidence bundle now uses GitHub-supported `$...$` inline delimiters and
    standalone `$$...$$` display delimiters instead of `\(...\)` and
    `\[...\]`. The normalization excludes fenced and inline code examples.
    GitHub's supported syntax is documented at
    https://docs.github.com/en/get-started/writing-on-github/working-with-advanced-formatting/writing-mathematical-expressions.
11. **Release dependency pins.** CI now pins third-party Actions to reviewed
    immutable commit SHAs with their release versions in comments:
    `actions/checkout` v7.0.1, `actions/setup-python` v7.0.0, and
    `github-action-markdown-link-check` v1.0.17. CI package installs are pinned
    to `ruff==0.16.3`, `cffconvert==2.0.0`, `PyYAML==6.0.3`, and
    `numpy==2.5.2`; the historical installer specified `pytest==9.1.1`.
    These are version pins, not hash-locked dependency resolution. Hash locks,
    transitive dependency capture, and platform-specific wheel provenance
    remain deferred release work.
12. **Production/test dependency guard.** DR1 and DR2 contract tests now share
    an AST-based guard over production Python sources. It rejects direct
    `import tests` / `import tests.*`, `from tests... import ...`, and literal
    `importlib.import_module('tests...')` or `__import__('tests...')` calls,
    including multi-name import statements. The DR1 contract includes a
    synthetic self-test for direct and dynamic cases; CI format checks include
    every maintained DR contract test and the guard helper.

## Evidence interpretation and reproducibility

NIST ACVP JSON specifications are validation-protocol drafts, not a substitute
for a FIPS conformance claim. The ML-KEM specification states that FIPS 203
§3.3 requirements such as zeroization, DRBG strength, and wrong-length inputs
are not fully covered by the ACVP vector process:
https://pages.nist.gov/ACVP/draft-celi-acvp-ml-kem.html

For journal-grade reproduction, a future release needs:

- a fixed source commit/archive or DOI;
- an SBOM plus platform-specific dependency locks and package hashes;
- imported ACVP source commit and vector-file hashes;
- source tree and dirty-diff identity for each physical result;
- full native command/transcript, host/device/driver/firmware records, and
  xclbin/PDI/ELF hashes; and
- a separately reviewed physical corpus and oracle before any DR2d pass claim.

Relevant provenance authorities:

- FIPS 202: https://csrc.nist.gov/pubs/fips/202/final
- FIPS 203: https://csrc.nist.gov/pubs/fips/203/final
- FIPS 204: https://csrc.nist.gov/pubs/fips/204/final
- NIST PQC project: https://csrc.nist.gov/projects/post-quantum-cryptography
- ACVP-Server: https://github.com/usnistgov/ACVP-Server
- MLIR-AIE: https://github.com/Xilinx/mlir-aie
- XRT: https://github.com/Xilinx/XRT
- SPDX license-information guidance: https://spdx.dev/learn/handling-license-info/
- Citation File Format: https://citation-file-format.github.io/

## Validation required for this remediation

The intended non-hardware validation set is:

```bash
python run_all_pqc_tests.py --dry-run
python run_all_pqc_tests.py
python -m compileall -q phoenix_sdr_dsp tests tools install install.py run_all_pqc_tests.py run_all_silicon_tests.py
ruff check .
ruff format --check .
cffconvert --validate
(cd docs/pqc_dr2_evidence_20260818 && sha256sum -c SHA256SUMS)
git diff --check
```

No command above authorizes a physical NPU run or historical PowerShell
evidence-script execution.

## Host-safe verification result

At the remediation revision, the expanded `run_all_pqc_tests.py` allowlist ran
17 modules and completed 141 `unittest` cases successfully, with two expected
skips for unavailable checkout-local IRON no-dispatch contracts. It executed no
hardware path. Python syntax compilation, `ruff check .`, scoped maintained-file
format checks, CFF validation, tracked JSON/YAML parsing, local Markdown-link
validation, protected-manifest verification, and `git diff --check` also passed.

An all-file `ruff format --check .` is intentionally not a required gate: it
would propose reformatting pre-existing historical and checksum-protected
evidence files. The CI format gate is scoped to maintained entrypoints and
newly formatted host-safe code; lint still covers the entire tree.
