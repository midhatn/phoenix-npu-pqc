# DR2d sigma-plus-PRF retry2 — evidence-gate correction

**Required current state:** original three additive files are unchanged, the graph-only corrective patch is not applied, and both original/retry1 evidence files exist.  
**Native status:** no authorization and no dispatch.

| File | SHA-256 |
|---|---|
| `PQC_DR2D_SIGMA_PRF_TAP_DIAGNOSTIC_RETRY1_FIX_20260818.patch` | `c1e09ebfd8b5a854547bb4b1be83c75a3c6ba2e59ab1c562ab4db541f08700dd` |
| `PQC_DR2D_SIGMA_PRF_TAP_APPLY_COMPILE_ONLY_RETRY2_20260818.ps1` | `44dba1b1cdf2117b4fb587274b5bff307767f3131f1593eb4b64c44aa6fe10c4` |
| `PQC_DR2D_SIGMA_PRF_TAP_RETRY2_BUILD_VALIDATION_20260818.txt` | `67fe17ed8f4a028683bda53c6d2d166d223b3e729e1942e2e324be4ff8b5ead9` |

Retry2 reuses the unchanged graph-only outer-factory correction. It fixes only the retry wrapper’s original-evidence matcher and preserves both previous logs.

## Evidence gates

- `PQC_DR2D_sigma_prf_tap_apply_compile_only_evidence_20260818.txt` must contain the exact reviewed form `missing a required keyword-only argument: 'd_slots'` (the regex also accepts an optional `a`), plus `NPU_DISPATCH_ATTEMPTED=False`; it must not contain `COMPILE_ONLY_GATE=PASS` or dispatch true.
- `PQC_DR2D_sigma_prf_tap_apply_compile_only_retry1_evidence_20260818.txt` must contain `REFUSED: original evidence does not contain the reviewed missing-d_slots failure`, plus no-dispatch proof; it must not claim corrective apply or retry1 pass.
- Neither prior log is deleted, truncated, or overwritten. Retry2 writes only `PQC_DR2D_sigma_prf_tap_apply_compile_only_retry2_evidence_20260818.txt`.

The script then runs the same production/V2/current-diagnostic hash gates, graph-only correction, host tests, outer-factory validation, MLIR generation, compile-only build, artifact audit, and post-hashes as retry1.

## Exact command

From `C:\phoenix-sdr-dsp`:

```powershell
$patch = ".\PQC_DR2D_SIGMA_PRF_TAP_DIAGNOSTIC_RETRY1_FIX_20260818.patch"
$script = ".\PQC_DR2D_SIGMA_PRF_TAP_APPLY_COMPILE_ONLY_RETRY2_20260818.ps1"
if ((Get-FileHash -Algorithm SHA256 -LiteralPath $patch).Hash -ne "C1E09EBFD8B5A854547BB4B1BE83C75A3C6BA2E59AB1C562AB4DB541F08700DD") { throw "patch hash mismatch" }
if ((Get-FileHash -Algorithm SHA256 -LiteralPath $script).Hash -ne "44DBA1B1CDF2117B4FB587274B5BFF307767F3131F1593EB4B64C44AA6FE10C4") { throw "retry2 script hash mismatch" }
$exe = [Diagnostics.Process]::GetCurrentProcess().MainModule.FileName
& $exe -NoProfile -ExecutionPolicy Bypass -File $script
if ($LASTEXITCODE -ne 0) { throw "retry2 compile-only bundle failed" }
```

No native environment variable is set or accepted. Do not run silicon, push, or package.
