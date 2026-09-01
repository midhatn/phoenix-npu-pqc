---
trigger: always_on
---

# Autonomous DR0–DR42 Engineering Handover and Execution Constitution

This directive establishes the autonomous supervisory and coding rules for the `phoenix-npu-pqc` repository across Milestone Deliverables DR0 through DR42 inclusive.

## 0. Standing Autonomous Authority

The agent operates with standing supervisory and coding authority to:
- Inspect and modify authorized repository files within the active milestone boundary.
- Create milestone branches and isolated worktrees.
- Run host tests and mathematical transliteration checks.
- Generate MLIR and compile AIE2 kernels.
- Execute AMD Phoenix NPU physical tests under the Windows watchdog supervisor.
- Create structured, fail-closed evidence bundles.
- Commit, push, open pull requests, inspect CI, and merge passing milestone PRs automatically.
- Update authorized machine-readable milestone state (`.agent/state.json`, `.agent/task_queue.json`, `.agent/current_task.md`, `.agent/blockers.json`, `.agent/handoff.md`, `.agent/session_log.jsonl`).
- Advance to the next dependency-safe milestone.
- Quarantine a milestone after three consecutive evidence-valid strikes.
- Proceed without human operational prompts or interactive confirmation.

## 1. Authoritative Roadmap Scope (DR0 through DR42)

- The authorized roadmap covers **DR0 through DR42 inclusive**.
- **DR43 is explicitly excluded**. No agent may activate, edit, compile, or execute DR43.
- FIPS 205 (SLH-DSA) and FIPS 206 (FN-DSA) follow their assigned DR numbers (including DR21 for FIPS 205).
- Every DR must be classified dynamically from live evidence into one of:
  - `PHYSICAL_VERIFIED`
  - `HOST_VERIFIED_ONLY`
  - `COMPILE_VERIFIED_ONLY`
  - `HISTORICAL_UNVERIFIED`
  - `FUNCTIONAL_MISMATCH`
  - `HOST_FALLBACK_PRESENT`
  - `STUB_OR_TRIVIAL_IMPLEMENTATION`
  - `PLANNED`
  - `BLOCKED_THREE_STRIKES`
  - `DEPENDENCY_BLOCKED`

## 2. Protected Verification Infrastructure and Immutability

Following bootstrap, the following infrastructure paths are strictly read-only and immutable during ordinary milestone work:
- `AGENTS.md`
- `.agent/decisions.md` (except appending validated architectural records)
- `.agents/rules/`
- `schemas/evidence.schema.json`
- `tools/agent_integrity.py`
- `tools/verify_agent_change.py`
- `tools/verify_evidence_manifest.py`
- `tools/promote_dr_status.py`
- `tests/policy/`
- `.github/workflows/`
- Core XRT and MLIR-AIE/IRON runtime bridges
- Official ACVP/NIST vector JSON files
- Existing host reference oracles
- Protected passing milestone baselines

No milestone repair may modify verification infrastructure or policy scanners to achieve a passing state.

## 3. Active Milestone Boundary and File Allowlist

Edits during milestone work are strictly confined to the active DR's authorized boundary:
- Active milestone kernel source files (`phoenix_sdr_dsp/pqc/kernels/dr<N>_*`)
- Active milestone graph or composer files (`phoenix_sdr_dsp/pqc/dr<N>_*_graph.py`, `tests/m<XX>_*/<name>_composer.py`)
- Active milestone test files (`tests/pqc_device_resident/test_dr<N>_*`, `tests/m<XX>_*/test_*`)
- Active milestone ABI files (`phoenix_sdr_dsp/pqc/dr<N>_*_abi.py`) only when required
- Active milestone research ledger (`docs/research/<TASK-ID>-sources.md`)
- Machine-readable `.agent/` state files updated after every diagnostic or implementation step

## 4. Hardware Constraints (AIE2 / XDNA1)

- Maximum two inbound ObjectFifo DMA streams per tile.
- Polynomial tile layout uses exactly 256 coefficients.
- DMA-visible records and vector buffers use 32-byte alignment.
- Token offsets and total buffer lengths must be statically verified.
- Canonical coefficients: $[0, q)$.
- Centered coefficients: $(-q/2, q/2]$.
- Conversions between canonical, centered, NTT, and Montgomery representations must be explicit.
- No implicit reinterpretation between byte, 16-bit, and 32-bit storage.
- ObjectFifo producer/consumer element types and transfer sizes must match exactly.
- ObjectFifo acquire and release operations must balance.
- Private cryptographic FIFOs must not have shim endpoints.
- Host-visible DMA contains only public inputs, final outputs, and explicit status headers.
- Secret intermediates must remain exclusively in tile SRAM.

## 5. Device-Residency and Zero-Fallback Policy

- No host CPU fallback, Python reference fallback, or simulated execution inside physical test paths.
- No expected-output injection, test-vector pattern matching, or request-ID answer dispatch.
- Physical device failure, driver timeout, or buffer mismatch must fail closed with a non-zero exit code.
- Host role is limited to input marshaling, zero-copy buffer dispatch, status verification, and independent oracle comparison of final output buffers.

## 6. Fast Transliteration Pre-Silicon Gate

Before any kernel compilation or silicon dispatch, the applicable mathematical transliteration check must pass:
- `tools/m32e_kernel_transliteration_check.py` for ML-KEM
- `tools/m33a_kernel_transliteration_check.py` through `m33e` for ML-DSA
- Equivalent parameter-set transliteration checks where applicable.

Transliteration checks test kernel-equivalent arithmetic against the mathematical model across boundary values, random ranges, canonical/centered conversions, NTT/INTT round trips, and modular reduction.

## 7. Windows NPU Watchdog Supervisor

All physical executions must run under a PowerShell watchdog supervisor:
- Polls `Get-PnpDevice -FriendlyName "*NPU*"` every 5 seconds.
- Verifies device status is `OK` (Problem 0, ConfigManagerErrorCode 0).
- Enforces per-stage timeout (maximum 900 seconds per execution).
- Preserves pre- and post-run device status, child PID, stdout, stderr, and exit code.
- On watchdog trigger, preserves diagnostic records without altering system/driver state.

## 8. Three-Strike Quarantine Rule

A strike is defined as one provenance-linked implementation iteration that changed active milestone code, passed pre-silicon checks, compiled, executed, and failed the predicted functional boundary.
- After **three consecutive valid strikes** on a microarchitectural boundary:
  1. Halt edits on that milestone immediately.
  2. Preserve all branches, worktrees, caches, logs, and artifacts.
  3. Mark the milestone `BLOCKED_THREE_STRIKES` in `.agent/state.json`.
  4. Record root-cause hypotheses, exact failure logs, and evidence in `.agent/blockers.json`.
  5. Push the quarantine branch and open a draft PR marked `[BLOCKED - DO NOT MERGE]`.
  6. Automatically advance to the next dependency-safe milestone.

## 9. Autonomous Micro-Loop

For each active milestone:
1. Verify Git baseline and evidence state.
2. Formulate one earliest-divergence hypothesis.
3. Declare an exact file allowlist.
4. Make the minimal bounded edit.
5. Run mathematical and transliteration checks.
6. Run host contract tests.
7. Run static topology, alignment, and memory fit checks.
8. Generate MLIR and perform fresh cold compilation in a UUID cache directory.
9. Verify source-to-artifact hash provenance.
10. Execute physical test under the watchdog supervisor.
11. Verify zero cache drift and output bit-exactness against the independent oracle.
12. Run full regression suite and policy scanner.
13. Commit, push, open PR, verify CI, and merge when all gates pass.
14. Protect the passing baseline and advance to the next milestone.

## 10. DR2d Pinned Disposition

- DR2d is resolved (25/25 official ML-KEM-512 K-PKE KeyGen cases passing, merged in PR #10).
- Complete and verify its fail-closed evidence archive at:
  `C:\Projects\phoenix-validation-evidence\dr2d-a0405851-20260901`
- Refuse to overwrite an existing evidence destination.
- Include the standard non-claim statement:
  "Zero cache-tree mutation was observed and is consistent with reuse of the pinned artifacts; it does not independently prove that no compiler process ran."
- Protect DR2d as a verified baseline.
