# DR2 evidence set — 2026-08-18

**Status:** preserved escalation evidence for a blocked DR2d physical failure. This directory is not an executable test suite, not a production package, and not evidence of a DR2d pass.

## Stop / execution safety

- **Do not run hardware.** The completed production gate is `TOTAL 0/25 FAIL`; the one authorized W0 `tcId-01` capture has already been consumed.
- **retry0 through retry5 scripts are historical failed attempts and MUST NOT be executed.** This includes the original `PQC_DR2D_SIGMA_PRF_TAP_APPLY_COMPILE_ONLY_20260818.ps1`, retry1–retry4 apply scripts, and retry5 compile-only script.
- **Retry6 is the only completed sigma/PRF bundle.** Its evidence proves a compile-only/no-dispatch path (`COMPILE_EXIT=0`, `NPU_DISPATCH_ATTEMPTED=False`), not execution or cryptographic correctness. Do not treat it as an authorization to dispatch.
- Preserve the tree byte-for-byte. Verify it with `sha256sum -c SHA256SUMS` from this directory; the manifest intentionally excludes itself.

## Raw binary integrity

`PQC_DR2D_W0_token_tap_tcId01_raw_20260818.bin` is the retained raw W0 diagnostic output from the one completed capture. Its immutable recorded identity is:

```text
bytes:   2096
sha256:  b7e75f7b55f8f3d30757ca5b0c3c9d13626b40e08cb5c6972681103395c20c53
```

The binary is a diagnostic W0 token, not a key or a production result. Its parseable status/canonical ranges do not establish arithmetic correctness. Do not transform, redact in place, regenerate, or overwrite it; work from a separately named copy if an authorized review requires derived material.

## Preservation and privacy

The evidence contains Windows user/cache paths, toolchain paths, local build metadata, hashes, deterministic test material, and a raw intermediate token. Treat it as restricted engineering evidence: do not publish it broadly, upload it to an unapproved service, or infer that absence of an obvious secret string makes it public. Preserve line endings, binary contents, filenames, and relative paths. Record any derivative artifact separately with its source file, command, environment, time, and checksum.

## Top-level evidence classification

| File | Classification | Safe interpretation |
|---|---|---|
| `PQC_DR2D_W0_compile_invocation_and_intermediates_20260818.txt` | W0 compile provenance/intermediate inventory | Build-side evidence only; no payload-correctness claim. |
| `PQC_DR2D_W0_complete_IR_metadata_objects_20260818.txt` | W0 IR, metadata, object inventory | Static/compile artifact evidence; no dispatch claim. |
| `PQC_DR2D_W0_pair_pack_vs_passed_terminal_probe_20260818.txt` | W0 pair-pack versus terminal-probe analysis | Diagnostic comparison; read-only. |
| `PQC_DR2D_W0_relocations_and_final_link_20260818.txt` | W0 relocation and final-link record | Link/provenance evidence; read-only. |
| `PQC_DR2D_W0_token_tap_compile_only_evidence_20260818.txt` | W0 V2 compile-only/no-dispatch provenance | Compile-only evidence; not a native result. |
| `PQC_DR2D_W0_token_tap_tcId01_native_evidence_20260818.txt` | First W0 one-call provenance record | Incomplete first capture record ending at call start; preserve, do not rely on it as completed result. |
| `PQC_DR2D_W0_token_tap_tcId01_native_evidence_retry1_20260818.txt` | Completed W0 one-call provenance and token validation | The sole completed authorized native diagnostic capture; diagnostic-only, not production success. |
| `PQC_DR2D_W0_token_tap_tcId01_raw_20260818.bin` | Raw W0 diagnostic token | 2,096-byte immutable primary artifact; hash/size above. |
| `PQC_DR2D_derive_sigma_and_copy_words_20260818.txt` | W0 derive-sigma/copy-words analysis | Read-only semantic/dataflow evidence. |
| `PQC_DR2D_sigma_prf_tap_apply_compile_only_retry6_evidence_20260818.txt` | Final sigma/PRF compile-only provenance | The only completed sigma/PRF bundle; no dispatch, no runtime correctness claim. |

## `sigma_prf_retry_chain/` classification

Every artifact below is preserved to explain the chronology. **Only retry6 completed its compile-only bundle. Do not execute retry0–retry5 scripts.** “Local validation” files document construction checks in another environment and are not native runtime results.

| File | Classification | Execution status |
|---|---|---|
| `PQC_DR2D_SIGMA_PRF_TAP_DIAGNOSTIC_20260818.patch` | Original additive diagnostic patch (retry0 input) | Historical; do not apply/execute. |
| `PQC_DR2D_SIGMA_PRF_TAP_DIAGNOSTIC_20260818_HANDOFF.md` | Retry0 handoff/specification | Read-only. |
| `PQC_DR2D_SIGMA_PRF_TAP_APPLY_COMPILE_ONLY_20260818.ps1` | Retry0 script | **MUST NOT execute**; failed before specialization/compile. |
| `PQC_DR2D_SIGMA_PRF_TAP_BUILD_VALIDATION_20260818.txt` | Retry0 local construction validation | Read-only; no NPU call. |
| `PQC_DR2D_SIGMA_PRF_TAP_DIAGNOSTIC_RETRY1_FIX_20260818.patch` | Graph-only retry1 correction patch | Historical; do not apply/execute. |
| `PQC_DR2D_SIGMA_PRF_TAP_RETRY1_HANDOFF_20260818.md` | Retry1 handoff | Read-only. |
| `PQC_DR2D_SIGMA_PRF_TAP_APPLY_COMPILE_ONLY_RETRY1_20260818.ps1` | Retry1 script | **MUST NOT execute**; structural evidence-gate refusal. |
| `PQC_DR2D_SIGMA_PRF_TAP_RETRY1_BUILD_VALIDATION_20260818.txt` | Retry1 local validation | Read-only; no NPU call. |
| `PQC_DR2D_SIGMA_PRF_TAP_RETRY2_HANDOFF_20260818.md` | Retry2 handoff | Read-only. |
| `PQC_DR2D_SIGMA_PRF_TAP_APPLY_COMPILE_ONLY_RETRY2_20260818.ps1` | Retry2 script | **MUST NOT execute**; structural evidence-wrapper refusal. |
| `PQC_DR2D_SIGMA_PRF_TAP_RETRY2_BUILD_VALIDATION_20260818.txt` | Retry2 local validation | Read-only; no NPU call. |
| `PQC_DR2D_SIGMA_PRF_TAP_RETRY3_HANDOFF_20260818.md` | Retry3 handoff | Read-only. |
| `PQC_DR2D_SIGMA_PRF_TAP_APPLY_COMPILE_ONLY_RETRY3_20260818.ps1` | Retry3 script | **MUST NOT execute**; structural host failure. |
| `PQC_DR2D_SIGMA_PRF_TAP_RETRY3_BUILD_VALIDATION_20260818.txt` | Retry3 local validation | Read-only; no NPU call. |
| `PQC_DR2D_SIGMA_PRF_TAP_DIAGNOSTIC_RETRY4_FIX_20260818.patch` | One-line retry4 graph correction patch | Historical; do not apply/execute. |
| `PQC_DR2D_SIGMA_PRF_TAP_RETRY4_HANDOFF_20260818.md` | Retry4 handoff | Read-only. |
| `PQC_DR2D_SIGMA_PRF_TAP_APPLY_COMPILE_ONLY_RETRY4_20260818.ps1` | Retry4 script | **MUST NOT execute**; structural compile-helper failure. |
| `PQC_DR2D_SIGMA_PRF_TAP_RETRY4_BUILD_VALIDATION_20260818.txt` | Retry4 local validation | Read-only; no NPU call. |
| `PQC_DR2D_SIGMA_PRF_TAP_RETRY5_HANDOFF_20260818.md` | Retry5 handoff | Read-only. |
| `PQC_DR2D_SIGMA_PRF_TAP_COMPILE_ONLY_RETRY5_20260818.ps1` | Retry5 script | **MUST NOT execute**; structural precompile failure. |
| `PQC_DR2D_SIGMA_PRF_TAP_RETRY5_BUILD_VALIDATION_20260818.txt` | Retry5 local validation | Read-only; no NPU call. |
| `PQC_DR2D_SIGMA_PRF_TAP_RETRY6_HANDOFF_20260818.md` | Retry6 handoff | Read-only; describes the final compile-only continuation. |
| `PQC_DR2D_SIGMA_PRF_TAP_COMPILE_ONLY_RETRY6_20260818.ps1` | Retry6 compile-only script | Only completed bundle represented here; no dispatch occurred. Preserve; do not use it as a native-run authorization. |
| `PQC_DR2D_SIGMA_PRF_TAP_RETRY6_BUILD_VALIDATION_20260818.txt` | Retry6 local validation | Read-only construction validation; no NPU call. |

## Related documents

- Escalation handoff: [`../PQC_DR2_EXPERT_ESCALATION_20260818.md`](../PQC_DR2_EXPERT_ESCALATION_20260818.md)
- Integrated production audit: [`../PQC_DR2D_FULLWORD_PRODUCTION_ELF_AUDIT_20260818.md`](../PQC_DR2D_FULLWORD_PRODUCTION_ELF_AUDIT_20260818.md)
- W0 V2 diagnostic boundary: [`../PQC_DR2D_W0_TOKEN_TAP_DIAGNOSTIC_V2_20260818_HANDOFF.md`](../PQC_DR2D_W0_TOKEN_TAP_DIAGNOSTIC_V2_20260818_HANDOFF.md)
- Research roadmap: [`../PQC_DEVICE_RESIDENCY_ROADMAP.md`](../PQC_DEVICE_RESIDENCY_ROADMAP.md)

## References

- NIST FIPS 202, *SHA-3 Standard*: https://nvlpubs.nist.gov/nistpubs/FIPS/NIST.FIPS.202.pdf
- NIST FIPS 203, *Module-Lattice-Based Key-Encapsulation Mechanism Standard*: https://nvlpubs.nist.gov/nistpubs/fips/nist.fips.203.pdf
- NIST FIPS 204, *Module-Lattice-Based Digital Signature Standard*: https://nvlpubs.nist.gov/nistpubs/fips/nist.fips.204.pdf
- MLIR-AIE 1.4.1 documentation: https://xilinx.github.io/mlir-aie/1.4.1/
- Xilinx mlir-aie pinned commit: https://github.com/Xilinx/mlir-aie/commit/3ca0193cea9e2c39ec670a65f93e1dd43c969f22
- LLVM-AIE: https://github.com/Xilinx/llvm-aie
- XRT: https://github.com/Xilinx/XRT
- AMD XDNA kernel documentation: https://docs.kernel.org/accel/amdxdna/amdnpu.html
