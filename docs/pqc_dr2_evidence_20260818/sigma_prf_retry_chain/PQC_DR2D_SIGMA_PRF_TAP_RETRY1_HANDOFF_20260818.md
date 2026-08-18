# DR2d sigma-plus-PRF tap retry1 — corrective compile-only handoff

**State required:** the original 3-file additive sigma-plus-PRF patch is already applied, and its original evidence file exists at `PQC_DR2D_sigma_prf_tap_apply_compile_only_evidence_20260818.txt`.  
**Native NPU:** **not authorized and not executed.**

## Deliverables

| File | SHA-256 |
|---|---|
| `PQC_DR2D_SIGMA_PRF_TAP_DIAGNOSTIC_RETRY1_FIX_20260818.patch` | `c1e09ebfd8b5a854547bb4b1be83c75a3c6ba2e59ab1c562ab4db541f08700dd` |
| `PQC_DR2D_SIGMA_PRF_TAP_APPLY_COMPILE_ONLY_RETRY1_20260818.ps1` | `c011747822cfc3d526ade11e862c0667c0f15161ef430aedc8fb07a51d1eb348` |
| `PQC_DR2D_SIGMA_PRF_TAP_RETRY1_BUILD_VALIDATION_20260818.txt` | `deb6e8f7c9a716d465df1ae4b17998ad78a020a2c40ac6d1e205f6d8f9b45e37` |

## Correction

The original direct `@iron.jit` decoration on `_program` compiled before specialization when the mandatory test called `tap._program()`, producing the reviewed `missing required keyword-only argument ... d_slots` failure.

The corrective patch changes **only** `phoenix_sdr_dsp/pqc/dr2d_mlkem512_kpke_sigma_prf_tap_graph.py`. `_program()` is now a plain outer factory which declares inner `@iron.jit _specialized_program(...)` and returns its unspecialized `CallableDesign`. The existing test and embedded compile API stay unchanged:

```python
design = tap._program()
specialized = design.specialize(
    d_slots=32, trace_slots=800, element_type=np.uint8
)
```

No C++ kernel, trace layout, contract test, production source, V2 token-tap source, ABI, serializer, or canonical runner is modified.

## Fail-closed retry gates

Before applying the correction, the retry script requires all three currently applied diagnostic files to have these exact hashes:

- C++ trace kernel: `e4bc1201e69842db5b2d33aabcde8195fced6a603a6630bdf641d3497f40a94d`;
- direct-JIT graph: `c324ece810d5fcbfe3363bd7db0eaae3f8515154b5fe08a41b12be7e79d6f6fb`;
- contract test: `d3dac863dd9cf5b48269e12a05f1f1e95028e04db481e2c6807908300ca6c315`.

It also hash-gates all protected production and accepted V2 inputs from the original bundle, including the retained W0 witness object. The corrected graph must become `4b099799ac2c85ed8b0c3fa5129fd69f0c4e3a7352055ff4c6893f5bd55bbf30`.

The original evidence is read but never deleted. It must contain both the missing-`d_slots` failure and `NPU_DISPATCH_ATTEMPTED=False`; it must not claim `COMPILE_ONLY_GATE=PASS`. The distinct retry output is `PQC_DR2D_sigma_prf_tap_apply_compile_only_retry1_evidence_20260818.txt`.

## Exact command

Place the corrective patch and retry script in `C:\phoenix-sdr-dsp`, then run:

```powershell
$patch = ".\PQC_DR2D_SIGMA_PRF_TAP_DIAGNOSTIC_RETRY1_FIX_20260818.patch"
$script = ".\PQC_DR2D_SIGMA_PRF_TAP_APPLY_COMPILE_ONLY_RETRY1_20260818.ps1"

if ((Get-FileHash -Algorithm SHA256 -LiteralPath $patch).Hash -ne
    "C1E09EBFD8B5A854547BB4B1BE83C75A3C6BA2E59AB1C562AB4DB541F08700DD") { throw "retry1 corrective patch hash mismatch" }
if ((Get-FileHash -Algorithm SHA256 -LiteralPath $script).Hash -ne
    "C011747822CFC3D526ADE11E862C0667C0F15161EF430AEDC8FB07A51D1EB348") { throw "retry1 script hash mismatch" }

$exe = [Diagnostics.Process]::GetCurrentProcess().MainModule.FileName
& $exe -NoProfile -ExecutionPolicy Bypass -File $script
if ($LASTEXITCODE -ne 0) { throw "retry1 compile-only bundle failed" }
```

The child-process bypass changes no machine-wide execution policy.

## What it does

1. Preserves and validates the original failure evidence.
2. Hash-checks protected production/V2 inputs and all three currently applied diagnostic files.
3. Applies the one-file corrective patch.
4. Runs Python syntax and the complete host/no-dispatch MLIR contracts.
5. Checks the outer-factory source shape, specializes, generates MLIR, and compiles without runtime tensors, callable invocation, or dispatch.
6. Audits generated text, object, ELF, symbol, relocation, and disassembly artifacts; W1–W4/serializer symbols fail closed.
7. Rehashes protected inputs and emits only the distinct retry1 evidence file with `COMPILE_ONLY_RETRY1_GATE=PASS`.

The script refuses native authorization variables, never sets one, never invokes a diagnostic runner, and records `NPU_DISPATCH_ATTEMPTED=False`. Do not run silicon, push, or package.
