# PQC DR2 Local Source Forensic Recovery - 2026-08-18

**Disposition:** recovery and publication provenance only. No hardware
dispatch, compilation, source repair, cache deletion, reset, clean, or
production merge was performed during this recovery.

## Purpose

This record authenticates the Windows research checkout used for DR2a through
DR2d and resolves the earlier uncertainty around local-only commits and
uncommitted DR2d source. It preserves the repository's existing layout:
committed DR2b/DR2c source remains in its original `docs/`,
`phoenix_sdr_dsp/`, and `tests/` paths; uncommitted DR2d source and root-level
evidence retain their original relative paths.

## Transport authentication

| Item | Recorded identity |
|---|---|
| uploaded archive | `phoenix-sdr-dsp_DR2_forensic_export_20260818T113718Z_retry2.zip` |
| archive bytes | `16,834,093` |
| archive SHA-256 | `068e94f869aa9038dfc33b324b498ca79d96feb67e2fa94a89ea8ad8253cf6ed` |
| internal manifest | 11 entries, all verified |
| DR2-named working files | 159, all recovered byte-for-byte |
| staged-index capture | absent as an expected empty pipeline output; porcelain-v2 status showed no staged or unmerged entries |
| capture safety markers | `HARDWARE_DISPATCH=False`, `COMPILATION=False`, `PATCH_APPLY=False`, `GIT_RESET_OR_CLEAN=False`, `SOURCE_MODIFICATION=False` |

The archive contained an all-refs Git bundle, complete `.git` ZIP, refs,
reflogs, unreachable-object inventory, tracked worktree patch, repository
status, and a ZIP of all matched DR2 working files. No file from the archive
was executed.

## Recovered Git lineage

The all-refs bundle authenticated this ordered branch from PR #8 baseline
`7b38973789fafb950a26551bc947f4fcaa91ec25`:

| Stage | Commit | Tree | Subject |
|---|---|---|---|
| DR2a | `99c80ac34e78c39f66280c64b2109db5d25c0dd9` | `fcc5b85d20ef339bc9051a67d4c32bff9de75e6f` | `feat(pqc): add device-resident ML-KEM SampleNTT` |
| DR2b | `8b1bff209b691f013420648dff3f2a022380a918` | `131aa54d43705f1ed465d6aff8bb9156fd197dc3` | `feat(pqc): add device-resident ML-KEM noise-to-NTT` |
| lineage | `c0a739090ba73ec700074c8ba6876abbb14bb0a4` | `78e8fd16c3deb0dba09ee7ef3fa2c3c9d7540d39` | `docs(pqc): record ordered DR2 validation lineage` |
| DR2c | `74c735b089b1e66ee5ff1a49b8abf1222cce8057` | `91134a06597f8197bc0766aaa904764b0bf87f7c` | `feat(pqc): add device-resident ML-KEM KeyGen row` |
| roadmap | `48b5e25e42ec63d5b8b79e67791c02d3420e8353` | `cdfca290ee0490ac2c5ed129beca8590134b93c8` | `docs(pqc): add accepted NPU implementation roadmap` |

Two safety refs were also recovered:

- `d033a8d5165bdea0ab3ab1cceaed99c42b856544`:
  pre-integration DR2b commit.
- `53e7b0e5c827bd015ccf5055c69ded2dc2e6c5bc`:
  local DR0/DR1/DR2a integration-state snapshot.

The withdrawn DR2a PR commit `60e63ea` and reconstructed local commit
`99c80ac...` contain byte-identical versions of all ten DR2a milestone files.
The research branch therefore keeps its existing DR2a base and replays the
authenticated DR2b, lineage, DR2c, and roadmap changes on top.

## Supported milestone conclusions

| Stage | Supported conclusion | Explicit boundary |
|---|---|---|
| DR2b | Solved for the narrow ML-KEM-512 SHAKE256 to CBD3 to NTT noise operation: 13/13 physical pass and 26/26 same-process aggregate. | Not complete K-PKE.KeyGen or ML-KEM. |
| DR2c | Solved for the narrow terminal ML-KEM-512 `t_hat` row operation: 11/11 physical pass and 22/22 same-process aggregate. | Excludes complete `G(d || k)`, both-row orchestration, final serialization, and full KeyGen closure. |
| DR2d | Compile-only audit passed, but integrated physical execution failed all 25 ACVP cases with parsed, systematically incorrect payloads. | Blocked research snapshot; not solved, releasable, or merge-ready. |

This distinction is critical: DR2b and DR2c are physically solved within their
documented sub-operation boundaries, while the integrated DR2 milestone
remains open because DR2d fails.

## Published and excluded material

Published on the research branch:

- authenticated DR2b and DR2c milestone source, tests, and documentation;
- recovered DR2d production source, host tests, diagnostic source, patches,
  scripts, logs, disassemblies, and compile/native evidence;
- DR2a/DR2b/DR2c physical logs and combined zero-skip host logs;
- exact checksum manifest
  [`pqc_dr2_evidence_20260818/RECOVERED_LOCAL_SOURCE_SHA256SUMS`](pqc_dr2_evidence_20260818/RECOVERED_LOCAL_SOURCE_SHA256SUMS).

Intentionally excluded:

- the complete `.git` ZIP and all-refs bundle, because the research branch now
  records the required DR2 commit and tree identities and the archives contain
  unrelated repository history;
- the outer transport ZIP, because it duplicates the published files and
  carries the complete Git capture;
- build caches, xclbins, PDIs, and toolchain installations not present in the
  159-file working snapshot.

## Publication validation

The recovery workspace performed host-only validation and did not load IRON,
XRT, or a native runner:

| Check | Result |
|---|---|
| uploaded archive SHA-256 | PASS |
| 11-entry transport manifest | 11/11 PASS |
| recovered working-file equivalence | 159/159 PASS |
| recovered-file publication manifest | 159/159 PASS |
| Python syntax (`compileall`) | PASS |
| DR2a/DR2b/DR2c/DR2d stage-specific host/reference suites | 43/43 PASS |
| updated-document local links | PASS, zero broken links |
| credential-pattern scan | PASS; matches were cryptographic variable names only |
| native execution | NOT RUN |
| historical sigma/PRF scripts | NOT RUN |

The combined historical static-contract invocation ran 32 tests and retained
four failures. All four are the same over-broad source scan: DR2a, DR2b,
DR2c, and DR2d contracts recursively scan every later `phoenix_sdr_dsp/pqc`
file for the substring `tests.`, while the recovered W0 and sigma/PRF
diagnostic graphs deliberately name the protected
`run_all_silicon_tests.py` file. This is recorded rather than hidden by
rewriting historical milestone tests or diagnostic provenance guards.

The DR2d contract also required two ignored upstream ACVP provenance files that
the laptop exporter did not select because their filenames lack `DR2`. They
were retrieved from `usnistgov/ACVP-Server` at immutable commit
`975de31eb83d87039ec88934fdc47d8c312b892d` and accepted only after matching
the hashes pinned by the recovered contract:

- `prompt.json`:
  `3f9ce34f6c836c77958bad2729e837c3b213f44ac36c3065976e7acca6389523`
- `expectedResults.json`:
  `a253d0ad91c95ebea5b409673defef0aa49d65d4ed72286399e2e798ddf073a4`

## Expert continuation boundary

1. Read
   [`PQC_DR2_EXPERT_ESCALATION_20260818.md`](PQC_DR2_EXPERT_ESCALATION_20260818.md)
   and
   [`PQC_DR2D_FULLWORD_PRODUCTION_ELF_AUDIT_20260818.md`](PQC_DR2D_FULLWORD_PRODUCTION_ELF_AUDIT_20260818.md)
   before inspecting scripts.
2. Verify recovered artifacts with
   [`pqc_dr2_evidence_20260818/RECOVERED_LOCAL_SOURCE_SHA256SUMS`](pqc_dr2_evidence_20260818/RECOVERED_LOCAL_SOURCE_SHA256SUMS).
3. Treat every historical PowerShell script as read-only evidence unless a new
   review explicitly authorizes a bounded action.
4. Do not rerun DR2d, apply historical patches, update the driver as an
   experiment, or dispatch a diagnostic from this publication alone.
5. Keep DR3 blocked until integrated DR2 satisfies the accepted roadmap gate.

## References

- NIST FIPS 202, *SHA-3 Standard*: https://nvlpubs.nist.gov/nistpubs/FIPS/NIST.FIPS.202.pdf
- NIST FIPS 203, *Module-Lattice-Based Key-Encapsulation Mechanism Standard*: https://nvlpubs.nist.gov/nistpubs/fips/nist.fips.203.pdf
- NIST ACVP-Server ML-KEM KeyGen corpus at recovered commit: https://github.com/usnistgov/ACVP-Server/tree/975de31eb83d87039ec88934fdc47d8c312b892d/gen-val/json-files/ML-KEM-keyGen-FIPS203
- MLIR-AIE 1.4.1 documentation: https://xilinx.github.io/mlir-aie/1.4.1/
- Xilinx mlir-aie pinned commit: https://github.com/Xilinx/mlir-aie/commit/3ca0193cea9e2c39ec670a65f93e1dd43c969f22
- LLVM-AIE: https://github.com/Xilinx/llvm-aie
- XRT: https://github.com/Xilinx/XRT
- AMD XDNA kernel documentation: https://docs.kernel.org/accel/amdxdna/amdnpu.html
