$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$python = ".\third_party\mlir-aie\ironenv\Scripts\python.exe"
$runner = ".\tests\pqc_device_resident\diagnose_dr2d_mlkem512_kpke_w0_token_tap.py"
$graph = ".\phoenix_sdr_dsp\pqc\dr2d_mlkem512_kpke_keygen_w0_token_tap_graph.py"
$rawToken = ".\PQC_DR2D_W0_token_tap_tcId01_raw_20260818.bin"
$evidence = ".\PQC_DR2D_W0_token_tap_tcId01_native_evidence_retry1_20260818.txt"
$compileCache = "$HOME\.npu\cache\320b9680889452b524538534"
$retainedObject = "$HOME\.npu\cache\04f147d54cb01d160974a6e6\dr2d_kpke_keygen_seed_noise.o"
$authorizationName = "PQC_DR2D_W0_TAP_NATIVE_AUTHORIZATION"
$authorizationValue = "AUTHORIZED_AFTER_W0_TAP_COMPILE_ONLY_REVIEW"

$protectedExpected = [ordered]@{
  ".\run_all_silicon_tests.py" = "742591321AC5DC3069A51DED4E198905367F8DC6261DF8C3EBAE20B5E333FBAD"
  ".\phoenix_sdr_dsp\pqc\dr2d_mlkem512_kpke_keygen_abi.py" = "A6F44C68787905F6B4819598BAACAC59BF5BCC4A3125C8151B7863345E9FF4F4"
  ".\phoenix_sdr_dsp\pqc\dr2d_mlkem512_kpke_keygen_graph.py" = "E17E17B8481BC1FA8492A7E2BC9184FBAE095B55C5E175B015AA19A2BC999694"
  ".\phoenix_sdr_dsp\pqc\kernels\dr2d_mlkem512_kpke_keygen_internal.hpp" = "16D61E6ADA4D7DE384B3981CC76D3DE8319CE2BEC999727D4847567E7E1F3519"
  ".\phoenix_sdr_dsp\pqc\kernels\dr2d_mlkem512_kpke_keygen_seed.cc" = "2F94E2995706AC5636F35C66167E5DD8F54AC54B618C200BF4EE45B8B754CEAF"
  $retainedObject = "7EA27CC5F6BB905253A161ACD98988C62AFC54855BCFD1C4530A55C441E28B70"
  "$compileCache\dr2d_kpke_keygen_seed_noise.o" = "7EA27CC5F6BB905253A161ACD98988C62AFC54855BCFD1C4530A55C441E28B70"
  "$compileCache\elfs_main_core_0_2\elfs_main_core_0_2.elf" = "A9416BCE0FE7C7C041EE403CBEFCDFFA87967EA06973D67C538CCE946487E260"
  "$compileCache\final.xclbin" = "AB758041A31DE83C7A44A9BD70347567D98E09C750A4EE2EC0689DDDB1B6C8A6"
  "$compileCache\insts.bin" = "BD335C32CF5C9ACA6E5D08ECF853FB54004CACB4ADD196ADF450C5941A649BD5"
  "$compileCache\main.pdi" = "14FC528704389884AE457C71D02B3B116CA96A3F2E4F24E258BA74F2E0835E4C"
}

if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
  throw "Pinned IRON Python is missing: $python"
}
if (-not (Test-Path -LiteralPath $runner -PathType Leaf)) {
  throw "Diagnostic runner is missing: $runner"
}
if (-not (Test-Path -LiteralPath $graph -PathType Leaf)) {
  throw "Diagnostic graph is missing: $graph"
}
if (Test-Path -LiteralPath $rawToken) {
  throw "Raw output already exists; refusing overwrite: $rawToken"
}
if (Test-Path -LiteralPath $evidence) {
  throw "Evidence output already exists; refusing overwrite: $evidence"
}

Remove-Item "Env:$authorizationName" -ErrorAction SilentlyContinue
if (Test-Path "Env:$authorizationName") {
  throw "Native authorization was already present before the guarded block"
}

$pre = [ordered]@{}
foreach ($item in $protectedExpected.GetEnumerator()) {
  if (-not (Test-Path -LiteralPath $item.Key -PathType Leaf)) {
    throw "Protected input is missing: $($item.Key)"
  }
  $digest = (Get-FileHash -Algorithm SHA256 -LiteralPath $item.Key).Hash
  if ($digest -ne $item.Value) {
    throw "Protected hash mismatch: $($item.Key) observed=$digest"
  }
  $pre[$item.Key] = $digest
}

$diagnosticPre = [ordered]@{}
foreach ($path in @($graph, $runner)) {
  $diagnosticPre[$path] = (Get-FileHash -Algorithm SHA256 -LiteralPath $path).Hash
}

$hadPythonPath = Test-Path Env:PYTHONPATH
$oldPythonPath = $env:PYTHONPATH
$repoRoot = (Resolve-Path ".").Path
$env:PYTHONPATH = if ([string]::IsNullOrWhiteSpace($oldPythonPath)) {
  $repoRoot
} else {
  "$repoRoot$([IO.Path]::PathSeparator)$oldPythonPath"
}
$env:PQC_DR2D_W0_RETAINED_OBJECT = $retainedObject

try {
  & {
    "===== W0 TOKEN-TAP ONE-NATIVE-CALL PROVENANCE ====="
    "UTC_START=$([DateTime]::UtcNow.ToString('o'))"
    "REPO_ROOT=$repoRoot"
    "PYTHON=$([IO.Path]::GetFullPath($python))"
    "PYTHON_SHA256=$((Get-FileHash -Algorithm SHA256 -LiteralPath $python).Hash)"
    "RUNNER=$([IO.Path]::GetFullPath($runner))"
    "RUNNER_SHA256=$($diagnosticPre[$runner])"
    "GRAPH=$([IO.Path]::GetFullPath($graph))"
    "GRAPH_SHA256=$($diagnosticPre[$graph])"
    "COMPILE_CACHE=$compileCache"
    "RAW_TOKEN=$([IO.Path]::GetFullPath($rawToken))"
    "REQUESTED_NATIVE_CALLS=1"
    "W1_W4_OR_SERIALIZER_REQUESTED=False"

    "===== PINNED PRE-HASHES ====="
    foreach ($item in $pre.GetEnumerator()) {
      "PRE $($item.Key)=$($item.Value)"
    }

    $caseQuery = 'import json; from tests.pqc_device_resident.test_dr2d_mlkem512_kpke_keygen import PRE_SILICON_CORPUS; c = PRE_SILICON_CORPUS[0]; print(json.dumps({"label": c.label, "request_id": int(c.request_id), "d_hex": bytes(c.d).hex()}))'
    $caseJson = @(& $python -c $caseQuery 2>&1)
    $caseExit = $LASTEXITCODE
    if ($caseExit -ne 0) {
      $caseJson | ForEach-Object { [string]$_ }
      throw "Could not load tcId-01 from the pinned corpus"
    }

    $case = ($caseJson | Select-Object -Last 1) | ConvertFrom-Json
    if ([string]$case.label -notmatch "01$") {
      throw "First corpus case is not tcId-01: $($case.label)"
    }
    if ([string]$case.d_hex -notmatch "^[0-9a-fA-F]{64}$") {
      throw "tcId-01 D is not exactly 32 bytes"
    }

    "===== EXACT CASE ====="
    "CASE_LABEL=$($case.label)"
    "REQUEST_ID=$($case.request_id)"
    "D_HEX=$($case.d_hex)"

    [Environment]::SetEnvironmentVariable(
      $authorizationName,
      $authorizationValue,
      [EnvironmentVariableTarget]::Process
    )

    "===== EXACT NATIVE COMMAND ====="
    "COMMAND=& `"$([IO.Path]::GetFullPath($python))`" `"$([IO.Path]::GetFullPath($runner))`" --d-hex $($case.d_hex) --request-id $($case.request_id) --output `"$([IO.Path]::GetFullPath($rawToken))`""
    "NATIVE_CALL_BEGIN=True"

    $runOutput = @(
      & $python $runner `
        --d-hex ([string]$case.d_hex) `
        --request-id ([string]$case.request_id) `
        --output $rawToken 2>&1
    )
    $runExit = $LASTEXITCODE
    $runOutput | ForEach-Object { [string]$_ }

    "NATIVE_CALL_END=True"
    "NATIVE_CALL_EXIT=$runExit"
    "NATIVE_CALLS_ATTEMPTED=1"

    Remove-Item "Env:$authorizationName" -ErrorAction SilentlyContinue

    if ($runExit -ne 0) {
      throw "The single authorized token-tap invocation failed with exit code $runExit"
    }
    if (-not (Test-Path -LiteralPath $rawToken -PathType Leaf)) {
      throw "The diagnostic returned success but created no raw token"
    }

    $rawItem = Get-Item -LiteralPath $rawToken
    if ($rawItem.Length -ne 2096) {
      throw "Raw token has wrong length: $($rawItem.Length)"
    }

    "===== RAW TOKEN INTEGRITY ====="
    "RAW_TOKEN_BYTES=$($rawItem.Length)"
    "RAW_TOKEN_SHA256=$((Get-FileHash -Algorithm SHA256 -LiteralPath $rawToken).Hash)"

    & $python -c @'
import hashlib
from pathlib import Path

p = Path("PQC_DR2D_W0_token_tap_tcId01_raw_20260818.bin")
b = p.read_bytes()
if len(b) != 2096:
    raise SystemExit(f"wrong token size: {len(b)}")

regions = (
    ("header", 0, 16, False),
    ("rho", 16, 48, False),
    ("s_hat_0", 48, 560, True),
    ("s_hat_1", 560, 1072, True),
    ("e_hat_0", 1072, 1584, True),
    ("e_hat_1", 1584, 2096, True),
)

print("TOKEN_FULL_SHA256=" + hashlib.sha256(b).hexdigest())
print("TOKEN_REQUEST_ID=" + str(int.from_bytes(b[0:4], "little")))
print("TOKEN_STATUS=" + str(int.from_bytes(b[4:8], "little")))
print("TOKEN_RESERVED_HEX=" + b[8:16].hex())

for name, start, stop, polynomial in regions:
    data = b[start:stop]
    print(f"REGION {name} OFFSET={start} BYTES={len(data)} SHA256={hashlib.sha256(data).hexdigest()}")
    if polynomial:
        coeffs = [
            int.from_bytes(data[i:i + 2], "little")
            for i in range(0, len(data), 2)
        ]
        bad = [i for i, value in enumerate(coeffs) if value >= 3329]
        print(
            f"REGION {name} COEFFICIENTS={len(coeffs)} "
            f"NONCANONICAL={len(bad)} "
            f"FIRST_NONCANONICAL={bad[0] if bad else 'NONE'}"
        )
'@
    if ($LASTEXITCODE -ne 0) {
      throw "Host-only raw-token analysis failed"
    }

    "===== PINNED POST-HASHES ====="
    foreach ($item in $protectedExpected.GetEnumerator()) {
      $digest = (Get-FileHash -Algorithm SHA256 -LiteralPath $item.Key).Hash
      "POST $($item.Key)=$digest"
      if ($digest -ne $pre[$item.Key]) {
        throw "Protected input changed during diagnostic: $($item.Key)"
      }
    }
    foreach ($path in @($graph, $runner)) {
      $digest = (Get-FileHash -Algorithm SHA256 -LiteralPath $path).Hash
      "POST_DIAGNOSTIC $path=$digest"
      if ($digest -ne $diagnosticPre[$path]) {
        throw "Diagnostic file changed during invocation: $path"
      }
    }

    "===== FINAL ASSERTIONS ====="
    "NATIVE_AUTHORIZATION_PRESENT=$([bool](Test-Path "Env:$authorizationName"))"
    "NATIVE_CALLS_ATTEMPTED=1"
    "RAW_TOKEN_RETAINED=True"
    "PROTECTED_HASHES_UNCHANGED=True"
    "ONE_NATIVE_CAPTURE_GATE=PASS"
    "UTC_END=$([DateTime]::UtcNow.ToString('o'))"
  } 2>&1 | Tee-Object -FilePath $evidence
} finally {
  Remove-Item "Env:$authorizationName" -ErrorAction SilentlyContinue
  Remove-Item Env:PQC_DR2D_W0_RETAINED_OBJECT -ErrorAction SilentlyContinue
  if ($hadPythonPath) {
    $env:PYTHONPATH = $oldPythonPath
  } else {
    Remove-Item Env:PYTHONPATH -ErrorAction SilentlyContinue
  }
}
