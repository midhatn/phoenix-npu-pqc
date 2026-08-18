$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

# This script is intentionally non-administrative and contains no NPU invocation.
$patch = ".\PQC_DR2D_SIGMA_PRF_TAP_DIAGNOSTIC_RETRY4_FIX_20260818.patch"
$evidence = ".\PQC_DR2D_sigma_prf_tap_apply_compile_only_retry4_evidence_20260818.txt"
$retry3Evidence = ".\PQC_DR2D_sigma_prf_tap_apply_compile_only_retry3_evidence_20260818.txt"
$retry2Evidence = ".\PQC_DR2D_sigma_prf_tap_apply_compile_only_retry2_evidence_20260818.txt"
$originalEvidence = ".\PQC_DR2D_sigma_prf_tap_apply_compile_only_evidence_20260818.txt"
$retry1Evidence = ".\PQC_DR2D_sigma_prf_tap_apply_compile_only_retry1_evidence_20260818.txt"
$python = ".\third_party\mlir-aie\ironenv\Scripts\python.exe"
$llvmBin = ".\third_party\mlir-aie\ironenv\Lib\site-packages\llvm-aie\bin"
$readobj = Join-Path $llvmBin "llvm-readobj.exe"
$objdump = Join-Path $llvmBin "llvm-objdump.exe"
$repoRoot = (Resolve-Path ".").Path
$expectedPatchHash = "3B8AA183BE358080D86517007C63C659ECC5F2B9772FE4AD74BEEA363942D2E5"
$retainedObject = "$HOME\.npu\cache\04f147d54cb01d160974a6e6\dr2d_kpke_keygen_seed_noise.o"

$productionExpected = [ordered]@{
  ".\run_all_silicon_tests.py" = "742591321AC5DC3069A51DED4E198905367F8DC6261DF8C3EBAE20B5E333FBAD"
  ".\phoenix_sdr_dsp\pqc\dr2d_mlkem512_kpke_keygen_abi.py" = "A6F44C68787905F6B4819598BAACAC59BF5BCC4A3125C8151B7863345E9FF4F4"
  ".\phoenix_sdr_dsp\pqc\dr2d_mlkem512_kpke_keygen_graph.py" = "E17E17B8481BC1FA8492A7E2BC9184FBAE095B55C5E175B015AA19A2BC999694"
  ".\phoenix_sdr_dsp\pqc\kernels\dr2d_mlkem512_kpke_keygen_internal.hpp" = "16D61E6ADA4D7DE384B3981CC76D3DE8319CE2BEC999727D4847567E7E1F3519"
  ".\phoenix_sdr_dsp\pqc\kernels\dr1_keccak_f1600.hpp" = "0470FB39277478A368004A49E551A3411D8F9185B492AC01F85D2297BCEA3C1F"
  ".\phoenix_sdr_dsp\pqc\kernels\dr2d_mlkem512_kpke_keygen_seed.cc" = "2F94E2995706AC5636F35C66167E5DD8F54AC54B618C200BF4EE45B8B754CEAF"
  $retainedObject = "7EA27CC5F6BB905253A161ACD98988C62AFC54855BCFD1C4530A55C441E28B70"
}
$acceptedV2DiagnosticExpected = [ordered]@{
  ".\phoenix_sdr_dsp\pqc\dr2d_mlkem512_kpke_keygen_w0_token_tap_graph.py" = "6B3D29AADA8CC7C4BE288899D55DA20B3C286E0AA415101106BBA4E86295F124"
  ".\tests\pqc_device_resident\diagnose_dr2d_mlkem512_kpke_w0_token_tap.py" = "B96E1D60981121FEAC33644DDCDA38CC490D2EE8866300509941266383575DA0"
}
$currentlyAppliedDiagnosticExpected = [ordered]@{
  ".\phoenix_sdr_dsp\pqc\kernels\dr2d_mlkem512_kpke_sigma_prf_tap.cc" = "E4BC1201E69842DB5B2D33AABCDE8195FCED6A603A6630BDF641D3497F40A94D"
  ".\phoenix_sdr_dsp\pqc\dr2d_mlkem512_kpke_sigma_prf_tap_graph.py" = "4B099799AC2C85ED8B0C3FA5129FD69F0C4E3A7352055FF4C6893F5BD55BBF30"
  ".\tests\pqc_device_resident\test_dr2d_mlkem512_kpke_sigma_prf_tap_contract.py" = "D3DAC863DD9CF5B48269E12A05F1F1E95028E04DB481E2C6807908300CA6C315"
}
$correctedDiagnosticExpected = [ordered]@{
  ".\phoenix_sdr_dsp\pqc\kernels\dr2d_mlkem512_kpke_sigma_prf_tap.cc" = "E4BC1201E69842DB5B2D33AABCDE8195FCED6A603A6630BDF641D3497F40A94D"
  ".\phoenix_sdr_dsp\pqc\dr2d_mlkem512_kpke_sigma_prf_tap_graph.py" = "F59DF8BEDE5C924A7AE59878BF1100FFFE890562A3BDE9649E59369078108BF7"
  ".\tests\pqc_device_resident\test_dr2d_mlkem512_kpke_sigma_prf_tap_contract.py" = "D3DAC863DD9CF5B48269E12A05F1F1E95028E04DB481E2C6807908300CA6C315"
}
$correctiveGraph = ".\phoenix_sdr_dsp\pqc\dr2d_mlkem512_kpke_sigma_prf_tap_graph.py"
$nativeAuthorizationVariables = @(
  "PQC_DR2D_W0_TAP_NATIVE_AUTHORIZATION",
  "PQC_DR2D_SIGMA_PRF_TAP_NATIVE_AUTHORIZATION"
)
$forbiddenSymbols = @(
  "dr2d_kpke_keygen_seed_noise",
  "dr2d_kpke_keygen_row0_expand",
  "dr2d_kpke_keygen_row0_accumulate",
  "dr2d_kpke_keygen_row1_expand",
  "dr2d_kpke_keygen_row1_accumulate",
  "dr2d_kpke_keygen_serialize"
)

function Assert-ExactHash([string]$Path, [string]$Expected) {
  if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
    throw "REFUSED: required file is missing: $Path"
  }
  $actual = (Get-FileHash -Algorithm SHA256 -LiteralPath $Path).Hash
  if ($actual -ne $Expected) {
    throw "REFUSED: hash mismatch: path=$Path expected=$Expected observed=$actual"
  }
  return $actual
}

function Assert-HashManifest([System.Collections.IDictionary]$Manifest, [string]$Label) {
  $results = [ordered]@{}
  foreach ($entry in $Manifest.GetEnumerator()) {
    $results[$entry.Key] = Assert-ExactHash $entry.Key $entry.Value
  }
  return $results
}

if (Test-Path -LiteralPath $evidence) {
  throw "REFUSED: evidence already exists; preserving it: $evidence"
}
if (-not (Test-Path -LiteralPath $patch -PathType Leaf)) { throw "REFUSED: patch missing: $patch" }
if ((Get-FileHash -Algorithm SHA256 -LiteralPath $patch).Hash -ne $expectedPatchHash) {
  throw "REFUSED: diagnostic patch hash mismatch"
}
foreach ($path in @($python, $readobj, $objdump)) {
  if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
    throw "REFUSED: required tool is missing: $path"
  }
}
foreach ($name in $nativeAuthorizationVariables) {
  if (Test-Path "Env:$name") {
    throw "REFUSED: native authorization environment variable is present: $name"
  }
}

$hadPythonPath = Test-Path Env:PYTHONPATH
$oldPythonPath = $env:PYTHONPATH
$env:PYTHONPATH = if ([string]::IsNullOrWhiteSpace($oldPythonPath)) {
  $repoRoot
} else {
  "$repoRoot$([IO.Path]::PathSeparator)$oldPythonPath"
}
$env:PQC_DR2D_W0_RETAINED_OBJECT = $retainedObject

try {
  & {
    "===== DR2D SIGMA-PLUS-PRF TAP RETRY4: NON-DISPATCH PROVENANCE ====="
    "UTC_START=$([DateTime]::UtcNow.ToString('o'))"
    "REPO_ROOT=$repoRoot"
    "PATCH=$([IO.Path]::GetFullPath($patch))"
    "PATCH_SHA256=$((Get-FileHash -Algorithm SHA256 -LiteralPath $patch).Hash)"
    "PYTHON=$([IO.Path]::GetFullPath($python))"
    "PYTHON_SHA256=$((Get-FileHash -Algorithm SHA256 -LiteralPath $python).Hash)"
    "RETAINED_W0_OBJECT=$retainedObject"
    "RETAINED_W0_OBJECT_SHA256=$((Get-FileHash -Algorithm SHA256 -LiteralPath $retainedObject).Hash)"
    "NPU_DISPATCH_AUTHORIZED=False"
    "NPU_DISPATCH_ATTEMPTED=False"
    "NATIVE_RUNNER_INVOKED=False"
    "W1_W4_OR_SERIALIZER_REQUESTED=False"
    "TRACE_LAYOUT=sigma:32;prf_nonce_0:192;prf_nonce_1:192;prf_nonce_2:192;prf_nonce_3:192;total:800"
    "ORIGINAL_EVIDENCE=$([IO.Path]::GetFullPath($originalEvidence))"
    "RETRY1_EVIDENCE=$([IO.Path]::GetFullPath($retry1Evidence))"
    "RETRY2_EVIDENCE=$([IO.Path]::GetFullPath($retry2Evidence))"
    "RETRY3_EVIDENCE=$([IO.Path]::GetFullPath($evidence))"

    "===== ORIGINAL FAILED EVIDENCE GATE ====="
    if (-not (Test-Path -LiteralPath $originalEvidence -PathType Leaf)) {
      throw "REFUSED: original failed evidence is missing: $originalEvidence"
    }
    $originalEvidenceText = Get-Content -LiteralPath $originalEvidence -Raw
    $missingSlotsPattern = '(?s-i)missing\s+(?:a\s+)?required\s+keyword-only\s+argument\s*:?\s*[''\"]?d_slots[''\"]?'
    if (-not [regex]::IsMatch($originalEvidenceText, $missingSlotsPattern)) {
      throw "REFUSED: original evidence does not contain the reviewed missing-d_slots failure"
    }
    if ($originalEvidenceText -notmatch "NPU_DISPATCH_ATTEMPTED=False") {
      throw "REFUSED: original evidence does not prove no dispatch"
    }
    if ($originalEvidenceText -match "COMPILE_ONLY_GATE=PASS" -or
        $originalEvidenceText -match "NPU_DISPATCH_ATTEMPTED=True") {
      throw "REFUSED: original evidence is not the expected pre-dispatch host/MLIR failure"
    }
    "ORIGINAL_MISSING_D_SLOTS_FAILURE=CONFIRMED"
    "ORIGINAL_NPU_DISPATCH_ATTEMPTED=False"
    "ORIGINAL_EVIDENCE_PRESERVED=True"

    "===== RETRY1 STRUCTURAL EVIDENCE GATE ====="
    if (-not (Test-Path -LiteralPath $retry1Evidence -PathType Leaf)) {
      throw "REFUSED: retry1 evidence is missing: $retry1Evidence"
    }
    $retry1EvidenceText = Get-Content -LiteralPath $retry1Evidence -Raw
    foreach ($required in @(
      "DR2D SIGMA-PLUS-PRF TAP RETRY1: NON-DISPATCH PROVENANCE",
      "===== ORIGINAL FAILED EVIDENCE GATE =====",
      "NPU_DISPATCH_ATTEMPTED=False"
    )) {
      if (-not $retry1EvidenceText.Contains($required)) {
        throw "REFUSED: retry1 evidence lacks required structural marker: $required"
      }
    }
    if ($retry1EvidenceText -match "(?i)\b(PATCH_APPLIED|CORRECTIVE_PATCH_APPLIED|PASS)\b" -or
        $retry1EvidenceText -match "NPU_DISPATCH_ATTEMPTED=True") {
      throw "REFUSED: retry1 evidence is not a pre-apply, non-dispatch refusal"
    }
    "RETRY1_STRUCTURAL_REFUSAL=CONFIRMED"
    "RETRY1_NPU_DISPATCH_ATTEMPTED=False"
    "RETRY1_EVIDENCE_PRESERVED=True"

    "===== RETRY2 STRUCTURAL EVIDENCE GATE ====="
    if (-not (Test-Path -LiteralPath $retry2Evidence -PathType Leaf)) {
      throw "REFUSED: retry2 evidence is missing: $retry2Evidence"
    }
    $retry2EvidenceText = Get-Content -LiteralPath $retry2Evidence -Raw
    foreach ($required in @(
      "DR2D SIGMA-PLUS-PRF TAP RETRY2: NON-DISPATCH PROVENANCE",
      "ORIGINAL_MISSING_D_SLOTS_FAILURE=CONFIRMED",
      "===== RETRY1 WRAPPER-REFUSAL EVIDENCE GATE =====",
      "NPU_DISPATCH_ATTEMPTED=False"
    )) {
      if (-not $retry2EvidenceText.Contains($required)) {
        throw "REFUSED: retry2 evidence lacks required structural marker: $required"
      }
    }
    if ($retry2EvidenceText -match "(?i)\b(PATCH_APPLIED|CORRECTIVE_PATCH_APPLIED|PASS)\b" -or
        $retry2EvidenceText -match "NPU_DISPATCH_ATTEMPTED=True") {
      throw "REFUSED: retry2 evidence is not a pre-apply, non-dispatch refusal"
    }
    "RETRY2_STRUCTURAL_REFUSAL=CONFIRMED"
    "RETRY2_NPU_DISPATCH_ATTEMPTED=False"
    "RETRY2_EVIDENCE_PRESERVED=True"

    "===== RETRY3 STRUCTURAL EVIDENCE GATE ====="
    if (-not (Test-Path -LiteralPath $retry3Evidence -PathType Leaf)) { throw "REFUSED: retry3 evidence is missing: $retry3Evidence" }
    $retry3EvidenceText = Get-Content -LiteralPath $retry3Evidence -Raw
    foreach ($required in @("DR2D SIGMA-PLUS-PRF TAP RETRY3: NON-DISPATCH PROVENANCE", "CORRECTIVE_PATCH_APPLIED=True", "PYTHON_SYNTAX=PASS", "===== HOST AND NO-DISPATCH MLIR CONTRACTS =====", "NPU_DISPATCH_ATTEMPTED=False")) { if (-not $retry3EvidenceText.Contains($required)) { throw "REFUSED: retry3 evidence lacks required marker: $required" } }
    if ($retry3EvidenceText -match "COMPILE_ONLY_RETRY3_GATE=PASS" -or $retry3EvidenceText -match "NPU_DISPATCH_ATTEMPTED=True") { throw "REFUSED: retry3 evidence is not the expected pre-dispatch host failure" }
    "RETRY3_STRUCTURAL_HOST_FAILURE=CONFIRMED"
    "RETRY3_EVIDENCE_PRESERVED=True"

    "===== PROTECTED PRODUCTION PRE-HASHES ====="
    $productionPre = Assert-HashManifest $productionExpected "PRODUCTION_PRE"
    foreach ($entry in $productionPre.GetEnumerator()) {
      "PRODUCTION_PRE $($entry.Key)=$($entry.Value)"
    }
    "===== ACCEPTED V2 DIAGNOSTIC PRE-HASHES ====="
    $v2Pre = Assert-HashManifest $acceptedV2DiagnosticExpected "V2_DIAGNOSTIC_PRE"
    foreach ($entry in $v2Pre.GetEnumerator()) {
      "V2_DIAGNOSTIC_PRE $($entry.Key)=$($entry.Value)"
    }
    "===== CURRENT APPLIED DIAGNOSTIC PRE-HASHES ====="
    $currentDiagnosticPre = Assert-HashManifest $currentlyAppliedDiagnosticExpected "CURRENT_DIAGNOSTIC_PRE"
    foreach ($entry in $currentDiagnosticPre.GetEnumerator()) {
      "CURRENT_DIAGNOSTIC_PRE $($entry.Key)=$($entry.Value)"
    }

    "===== CORRECTIVE PATCH PREVIEW AND APPLY ====="
    & git apply --check --verbose $patch
    if ($LASTEXITCODE -ne 0) { throw "REFUSED: patch does not apply cleanly" }
    & git apply --stat $patch
    if ($LASTEXITCODE -ne 0) { throw "REFUSED: could not render patch stat" }
    & git apply $patch
    if ($LASTEXITCODE -ne 0) { throw "REFUSED: patch application failed" }
    "CORRECTIVE_PATCH_APPLIED=True"
    & git diff --no-ext-diff -- $correctiveGraph
    if ($LASTEXITCODE -ne 0) { throw "REFUSED: could not render additive diff" }

    "===== PYTHON SYNTAX ====="
    & $python -m py_compile `
      .\phoenix_sdr_dsp\pqc\dr2d_mlkem512_kpke_sigma_prf_tap_graph.py `
      .\tests\pqc_device_resident\test_dr2d_mlkem512_kpke_sigma_prf_tap_contract.py
    if ($LASTEXITCODE -ne 0) { throw "REFUSED: Python syntax validation failed" }
    "PYTHON_SYNTAX=PASS"

    "===== HOST AND NO-DISPATCH MLIR CONTRACTS ====="
    $env:PQC_DR2D_REQUIRE_IRON_MLIR_CONTRACT = "1"
    try {
      & $python -m unittest `
        tests.pqc_device_resident.test_dr2d_mlkem512_kpke_sigma_prf_tap_contract -v
      if ($LASTEXITCODE -ne 0) { throw "REFUSED: host/MLIR contracts failed" }
    } finally {
      Remove-Item Env:PQC_DR2D_REQUIRE_IRON_MLIR_CONTRACT -ErrorAction SilentlyContinue
    }
    "HOST_AND_NO_DISPATCH_MLIR_CONTRACTS=PASS"

    $compileScript = Join-Path $env:TEMP "compile_dr2d_sigma_prf_tap_no_dispatch_20260818.py"
    $pythonSource = @'
import hashlib
import inspect
import os
from pathlib import Path

import numpy as np

from phoenix_sdr_dsp.pqc import dr2d_mlkem512_kpke_sigma_prf_tap_graph as tap

AUTH_VARS = (
    "PQC_DR2D_W0_TAP_NATIVE_AUTHORIZATION",
    "PQC_DR2D_SIGMA_PRF_TAP_NATIVE_AUTHORIZATION",
)
for auth_var in AUTH_VARS:
    if os.environ.get(auth_var):
        raise SystemExit(f"REFUSED: native authorization is present during compile-only gate: {auth_var}")

before = tap.verify_production_hashes()
print("HASH_GATE_BEFORE=PASS")
for name, digest in sorted(before.items()):
    print(f"PINNED_BEFORE {name}={digest}")

factory_source = inspect.getsource(tap._program)
for required in (
    "def _program():",
    "@iron.jit",
    "def _specialized_program(",
    "return _specialized_program()",
):
    if required not in factory_source:
        raise SystemExit(f"REFUSED: outer-factory correction is incomplete: missing {required}")
print(
    "OUTER_FACTORY_SOURCE_SHA256="
    + hashlib.sha256(factory_source.encode("utf-8")).hexdigest()
)

design = tap._program()
expected_compile_params = {"d_slots", "trace_slots", "element_type"}
actual_compile_params = set(design.compilable.compile_params)
if actual_compile_params != expected_compile_params:
    raise SystemExit(
        "REFUSED: CompileTime parameter set mismatch: "
        f"expected={sorted(expected_compile_params)} observed={sorted(actual_compile_params)}"
    )

specialized = design.specialize(
    d_slots=tap.D_BYTES,
    trace_slots=tap.TRACE_BYTES,
    element_type=np.uint8,
)
if set(specialized.compilable.compile_kwargs) != expected_compile_params:
    raise SystemExit("REFUSED: specialization keys do not exactly match CompileTime parameters")

callable_compile_source = inspect.getsource(type(specialized).compile)
compilable_compile_source = inspect.getsource(type(specialized.compilable).compile)
if "self.compilable.compile(" not in callable_compile_source:
    raise SystemExit("REFUSED: CallableDesign.compile delegation changed")
for label, source in (
    ("CallableDesign.compile", callable_compile_source),
    ("CompilableDesign.compile", compilable_compile_source),
):
    for forbidden in ("NPUKernel", "DefaultNPURuntime", "pyxrt"):
        if forbidden in source:
            raise SystemExit(f"REFUSED: compile surface references {forbidden}: {label}")

mlir_text = specialized.as_mlir()
for required in (
    "dr2d_kpke_sigma_prf_tap",
    "dr2d_sigma_prf_tap_d",
    "dr2d_sigma_prf_tap_trace",
    "memref<32xui8>",
    "memref<800xui8>",
):
    if required not in mlir_text:
        raise SystemExit(f"REFUSED: generated MLIR missing {required}")
for forbidden in (
    "dr2d_kpke_keygen_seed_noise",
    "dr2d_kpke_keygen_row0_expand",
    "dr2d_kpke_keygen_row0_accumulate",
    "dr2d_kpke_keygen_row1_expand",
    "dr2d_kpke_keygen_row1_accumulate",
    "dr2d_kpke_keygen_serialize",
):
    if forbidden in mlir_text:
        raise SystemExit(f"REFUSED: generated MLIR contains forbidden symbol {forbidden}")
print("NO_DISPATCH_MLIR_GENERATION=PASS")
print("GENERATED_MLIR_SHA256=" + hashlib.sha256(mlir_text.encode("utf-8")).hexdigest())
print("===== GENERATED MLIR BEGIN =====")
print(mlir_text)
print("===== GENERATED MLIR END =====")
print("CALLABLE_COMPILE_SOURCE_SHA256=" + hashlib.sha256(callable_compile_source.encode()).hexdigest())
print("COMPILABLE_COMPILE_SOURCE_SHA256=" + hashlib.sha256(compilable_compile_source.encode()).hexdigest())
print("NO_RUNTIME_TENSORS_CREATED=True")
print("NO_CALLABLE_DESIGN_INVOCATION=True")
print("COMPILE_ONLY_BEGIN=True")

xclbin_path, inst_path = specialized.compile()
xclbin = Path(xclbin_path).resolve()
if inst_path is None:
    raise SystemExit("REFUSED: compile-only build returned no instruction artifact")
insts = Path(inst_path).resolve()
if not xclbin.is_file() or not insts.is_file():
    raise SystemExit("REFUSED: compile-only artifacts are missing")
cache_path = xclbin.parent.resolve()
if not cache_path.is_dir():
    raise SystemExit("REFUSED: compile-only cache directory is missing")
pdis = [Path(path).resolve() for path in specialized.get_pdi_paths()]
if not pdis or any(not path.is_file() for path in pdis):
    raise SystemExit("REFUSED: compile-only build did not retain a PDI")

after = tap.verify_production_hashes()
if after != before:
    raise SystemExit("REFUSED: protected production hashes changed during compilation")
print("HASH_GATE_AFTER=PASS")
for name, digest in sorted(after.items()):
    print(f"PINNED_AFTER {name}={digest}")
print(f"XCLBIN_PATH={xclbin}")
print(f"INST_PATH={insts}")
print(f"CACHE_PATH={cache_path}")
for pdi in pdis:
    print(f"PDI_PATH={pdi}")
print("COMPILE_ONLY_COMPLETE=True")
print("NPU_DISPATCH_ATTEMPTED=False")
'@
    [IO.File]::WriteAllText($compileScript, $pythonSource, [Text.UTF8Encoding]::new($false))
    "===== COMPILE-ONLY SCRIPT ====="
    "COMPILE_SCRIPT=$compileScript"
    "COMPILE_SCRIPT_SHA256=$((Get-FileHash -Algorithm SHA256 -LiteralPath $compileScript).Hash)"
    "EXACT_COMPILE_COMMAND=& `"$([IO.Path]::GetFullPath($python))`" `"$compileScript`""
    $compileOutput = @(& $python $compileScript 2>&1)
    $compileExit = $LASTEXITCODE
    $compileOutput | ForEach-Object { [string]$_ }
    "COMPILE_EXIT=$compileExit"
    if ($compileExit -ne 0) { throw "REFUSED: compile-only Python failed with exit $compileExit" }

    $cacheLine = $compileOutput | ForEach-Object { [string]$_ } |
      Where-Object { $_ -like "CACHE_PATH=*" } | Select-Object -Last 1
    if (-not $cacheLine) { throw "REFUSED: compile-only output did not report CACHE_PATH" }
    $tapCache = [IO.Path]::GetFullPath($cacheLine.Substring("CACHE_PATH=".Length))
    $productionCache = [IO.Path]::GetFullPath("$HOME\.npu\cache\04f147d54cb01d160974a6e6")
    $cacheRoot = [IO.Path]::GetFullPath("$HOME\.npu\cache")
    if ($tapCache -eq $productionCache) { throw "REFUSED: diagnostic compilation reused production cache" }
    if (-not $tapCache.StartsWith($cacheRoot, [StringComparison]::OrdinalIgnoreCase)) {
      throw "REFUSED: cache lies outside the NPU cache root: $tapCache"
    }
    if (-not (Test-Path -LiteralPath $tapCache -PathType Container)) {
      throw "REFUSED: reported diagnostic cache is missing: $tapCache"
    }
    foreach ($name in $nativeAuthorizationVariables) {
      if (Test-Path "Env:$name") { throw "REFUSED: native authorization appeared: $name" }
    }

    "===== GENERATED TEXT ARTIFACTS ====="
    $textArtifacts = Get-ChildItem -LiteralPath $tapCache -Recurse -File |
      Where-Object { $_.Extension -in @( ".mlir", ".ll", ".json", ".cc", ".cpp", ".h", ".hpp") } |
      Sort-Object FullName
    if (-not $textArtifacts) { throw "REFUSED: compile cache contains no text artifacts" }
    foreach ($artifact in $textArtifacts) {
      $raw = Get-Content -LiteralPath $artifact.FullName -Raw
      foreach ($symbol in $forbiddenSymbols) {
        if ($raw.Contains($symbol)) {
          throw "REFUSED: forbidden downstream/serializer symbol in $($artifact.FullName): $symbol"
        }
      }
      "TEXT_ARTIFACT=$($artifact.FullName) BYTES=$($artifact.Length) SHA256=$((Get-FileHash -Algorithm SHA256 -LiteralPath $artifact.FullName).Hash)"
      "===== TEXT BEGIN: $($artifact.FullName) ====="
      $raw
      "===== TEXT END: $($artifact.FullName) ====="
    }

    "===== OBJECT AND ELF AUDIT ====="
    $binaryArtifacts = Get-ChildItem -LiteralPath $tapCache -Recurse -File |
      Where-Object { $_.Extension -in @( ".o", ".elf") } | Sort-Object FullName
    if (-not $binaryArtifacts) { throw "REFUSED: compile cache contains no object or ELF artifacts" }
    $tapBinaryFound = $false
    foreach ($artifact in $binaryArtifacts) {
      "===== BINARY BEGIN: $($artifact.FullName) ====="
      "SHA256=$((Get-FileHash -Algorithm SHA256 -LiteralPath $artifact.FullName).Hash)"
      $readobjOutput = @(& $readobj --sections --symbols --relocations $artifact.FullName 2>&1)
      if ($LASTEXITCODE -ne 0) { throw "REFUSED: llvm-readobj failed: $($artifact.FullName)" }
      $readobjOutput | ForEach-Object { [string]$_ }
      $objdumpOutput = @(& $objdump -d --triple=aie2 --disassemble-zeroes $artifact.FullName 2>&1)
      if ($LASTEXITCODE -ne 0) { throw "REFUSED: llvm-objdump failed: $($artifact.FullName)" }
      $objdumpOutput | ForEach-Object { [string]$_ }
      $combinedAudit = ($readobjOutput + $objdumpOutput) -join "`n"
      foreach ($symbol in $forbiddenSymbols) {
        if ($combinedAudit.Contains($symbol)) {
          throw "REFUSED: forbidden downstream/serializer symbol in binary audit: $symbol"
        }
      }
      if ($combinedAudit -match "dr2d_kpke_sigma_prf_tap") {
        $tapBinaryFound = $true
      }
      "===== BINARY END: $($artifact.FullName) ====="
    }
    if (-not $tapBinaryFound) {
      throw "REFUSED: sigma-plus-PRF tap entrypoint is absent from all binary audits"
    }

    "===== PROTECTED PRODUCTION POST-HASHES ====="
    $productionPost = Assert-HashManifest $productionExpected "PRODUCTION_POST"
    foreach ($entry in $productionPost.GetEnumerator()) {
      "PRODUCTION_POST $($entry.Key)=$($entry.Value)"
    }
    foreach ($entry in $productionPre.GetEnumerator()) {
      if ($productionPost[$entry.Key] -ne $entry.Value) {
        throw "REFUSED: production input changed during diagnostic: $($entry.Key)"
      }
    }
    "===== CORRECTED DIAGNOSTIC POST-HASHES ====="
    $correctedDiagnosticPost = Assert-HashManifest $correctedDiagnosticExpected "CORRECTED_DIAGNOSTIC_POST"
    foreach ($entry in $correctedDiagnosticPost.GetEnumerator()) {
      "CORRECTED_DIAGNOSTIC_POST $($entry.Key)=$($entry.Value)"
    }
    "CORRECTIVE_GRAPH_OUTER_FACTORY=PASS"

    "===== ACCEPTED V2 DIAGNOSTIC POST-HASHES ====="
    $v2Post = Assert-HashManifest $acceptedV2DiagnosticExpected "V2_DIAGNOSTIC_POST"
    foreach ($entry in $v2Post.GetEnumerator()) {
      "V2_DIAGNOSTIC_POST $($entry.Key)=$($entry.Value)"
    }
    foreach ($entry in $v2Pre.GetEnumerator()) {
      if ($v2Post[$entry.Key] -ne $entry.Value) {
        throw "REFUSED: accepted V2 diagnostic changed during this bundle: $($entry.Key)"
      }
    }

    "===== FINAL SAFETY ASSERTIONS ====="
    "NATIVE_AUTHORIZATION_PRESENT=False"
    "NATIVE_RUNNER_INVOKED=False"
    "XRT_TENSOR_CREATED=False"
    "NPU_DISPATCH_ATTEMPTED=False"
    "W1_W4_OR_SERIALIZER_REQUESTED=False"
    "PROTECTED_HASHES_UNCHANGED=True"
    "SIGMA_PRF_TRACE_BYTES=800"
    "SIGMA_BYTES=32"
    "RAW_PRF_BYTES_PER_NONCE=192"
    "RAW_PRF_NONCES=0,1,2,3"
    "COMPILE_ONLY_RETRY4_GATE=PASS"
    "UTC_END=$([DateTime]::UtcNow.ToString('o'))"
  } 2>&1 | Tee-Object -FilePath $evidence
} finally {
  Remove-Item Env:PQC_DR2D_REQUIRE_IRON_MLIR_CONTRACT -ErrorAction SilentlyContinue
  Remove-Item Env:PQC_DR2D_W0_RETAINED_OBJECT -ErrorAction SilentlyContinue
  foreach ($name in $nativeAuthorizationVariables) {
    if (Test-Path "Env:$name") { throw "REFUSED: native authorization variable appeared: $name" }
  }
  if ($hadPythonPath) {
    $env:PYTHONPATH = $oldPythonPath
  } else {
    Remove-Item Env:PYTHONPATH -ErrorAction SilentlyContinue
  }
}
