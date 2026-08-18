# DR2d sigma-plus-PRF retry3

Retry3 reuses the unchanged graph-only outer-factory patch and replaces only evidence-wrapper assumptions. It requires the original, retry1, and retry2 logs and preserves all three; it writes only a distinct retry3 evidence file.

| File | SHA-256 |
|---|---|
| `PQC_DR2D_SIGMA_PRF_TAP_DIAGNOSTIC_RETRY1_FIX_20260818.patch` | `c1e09ebfd8b5a854547bb4b1be83c75a3c6ba2e59ab1c562ab4db541f08700dd` |
| `PQC_DR2D_SIGMA_PRF_TAP_APPLY_COMPILE_ONLY_RETRY3_20260818.ps1` | `95e6664e4b9a72d4612f0cbed7dc46f05a72bc8c84cfe074a57d1446f918d35d` |
| `PQC_DR2D_SIGMA_PRF_TAP_RETRY3_BUILD_VALIDATION_20260818.txt` | `bbd6fe2152d7f57e60a38901db396a0bd87772b840da9a4b05de7ea30f0b32dd` |

## Structural gates

- Original: exact missing-a-required-`d_slots` traceback, no dispatch, no pass.
- Retry1: RETRY1 non-dispatch provenance, original-gate heading, no dispatch, and no apply/pass/dispatch true.
- Retry2: RETRY2 non-dispatch provenance, original confirmed marker, retry1-gate heading, no dispatch, and no apply/pass/dispatch true.

The current graph/kernel/test hashes and `git apply --check` remain authoritative proof that correction has not applied. The script then applies the graph-only patch, runs full host/MLIR/compile-only/audit/post-hash flow, and emits `PQC_DR2D_sigma_prf_tap_apply_compile_only_retry3_evidence_20260818.txt`. It does not authorize or dispatch native work.

## Command

```powershell
$patch = ".\PQC_DR2D_SIGMA_PRF_TAP_DIAGNOSTIC_RETRY1_FIX_20260818.patch"
$script = ".\PQC_DR2D_SIGMA_PRF_TAP_APPLY_COMPILE_ONLY_RETRY3_20260818.ps1"
if ((Get-FileHash -Algorithm SHA256 -LiteralPath $patch).Hash -ne "C1E09EBFD8B5A854547BB4B1BE83C75A3C6BA2E59AB1C562AB4DB541F08700DD") { throw "patch hash mismatch" }
if ((Get-FileHash -Algorithm SHA256 -LiteralPath $script).Hash -ne "95E6664E4B9A72D4612F0CBED7DC46F05A72BC8C84CFE074A57D1446F918D35D") { throw "retry3 hash mismatch" }
$exe = [Diagnostics.Process]::GetCurrentProcess().MainModule.FileName
& $exe -NoProfile -ExecutionPolicy Bypass -File $script
if ($LASTEXITCODE -ne 0) { throw "retry3 failed" }
```
