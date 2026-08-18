# DR2d sigma-plus-PRF retry4

One-line graph-only correction: return `_specialized_program`, not `_specialized_program()`. Current graph hash required: `4b099799ac2c85ed8b0c3fa5129fd69f0c4e3a7352055ff4c6893f5bd55bbf30`; corrected graph hash: `f59df8bede5c924a7ae59878bf1100fffe890562a3bde9649e59369078108bf7`.

- Patch: `PQC_DR2D_SIGMA_PRF_TAP_DIAGNOSTIC_RETRY4_FIX_20260818.patch` — `3b8aa183be358080d86517007c63c659ecc5f2b9772fe4ad74beea363942d2e5`
- Script: `PQC_DR2D_SIGMA_PRF_TAP_APPLY_COMPILE_ONLY_RETRY4_20260818.ps1` — `634a703479cd5f75aa6d1d6b76d8c5f75597c2e9f45b3d32dbf18ceef4e857f6`
- Validation: `PQC_DR2D_SIGMA_PRF_TAP_RETRY4_BUILD_VALIDATION_20260818.txt` — `37e4b15b17dd20a47e4ae3356d175a19a5a47d31bc0817e6474e0a7b17de1e5e`

Retry4 preserves original through retry3 evidence, structurally gates retry3 pre-dispatch host failure, then performs the corrected full host/MLIR/compile-only/audit flow with distinct retry4 evidence. No native authorization or dispatch.

```powershell
$patch = ".\PQC_DR2D_SIGMA_PRF_TAP_DIAGNOSTIC_RETRY4_FIX_20260818.patch"
$script = ".\PQC_DR2D_SIGMA_PRF_TAP_APPLY_COMPILE_ONLY_RETRY4_20260818.ps1"
if ((Get-FileHash -Algorithm SHA256 -LiteralPath $patch).Hash -ne "3B8AA183BE358080D86517007C63C659ECC5F2B9772FE4AD74BEEA363942D2E5") { throw "patch hash mismatch" }
if ((Get-FileHash -Algorithm SHA256 -LiteralPath $script).Hash -ne "634A703479CD5F75AA6D1D6B76D8C5F75597C2E9F45B3D32DBF18CEEF4E857F6") { throw "script hash mismatch" }
$exe = [Diagnostics.Process]::GetCurrentProcess().MainModule.FileName
& $exe -NoProfile -ExecutionPolicy Bypass -File $script
if ($LASTEXITCODE -ne 0) { throw "retry4 failed" }
```
