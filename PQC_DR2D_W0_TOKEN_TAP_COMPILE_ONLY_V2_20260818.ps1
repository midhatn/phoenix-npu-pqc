# DR2d W0 token-tap diagnostic V2: compile-only cache build and evidence capture.
# This script must not set native authorization, create XRT tensors, or dispatch the NPU.
& {
  $ErrorActionPreference = "Stop"
  $py = ".\third_party\mlir-aie\ironenv\Scripts\python.exe"
  $bin = ".\third_party\mlir-aie\ironenv\Lib\site-packages\llvm-aie\bin"
  $objdump = "$bin\llvm-objdump.exe"
  $readobj = "$bin\llvm-readobj.exe"
  $retainedObject = "$HOME\.npu\cache\04f147d54cb01d160974a6e6\dr2d_kpke_keygen_seed_noise.o"
  $productionCache = [System.IO.Path]::GetFullPath(
    "$HOME\.npu\cache\04f147d54cb01d160974a6e6"
  )
  $compileScript = Join-Path $env:TEMP "compile_dr2d_w0_token_tap_no_dispatch_20260818.py"
  $evidence = ".\PQC_DR2D_W0_token_tap_compile_only_evidence_20260818.txt"

  Remove-Item Env:PQC_DR2D_W0_TAP_NATIVE_AUTHORIZATION -ErrorAction SilentlyContinue
  if (Test-Path Env:PQC_DR2D_W0_TAP_NATIVE_AUTHORIZATION) {
    throw "Native authorization variable remains present; refusing compile."
  }
  if (-not (Test-Path -LiteralPath $py -PathType Leaf)) {
    throw "Pinned IRON Python is missing: $py"
  }
  if (-not (Test-Path -LiteralPath $retainedObject -PathType Leaf)) {
    throw "Retained W0 comparison object is missing: $retainedObject"
  }
  if (Test-Path -LiteralPath $evidence) {
    throw "Evidence output already exists; refusing to overwrite: $evidence"
  }

  $env:PQC_DR2D_W0_RETAINED_OBJECT = $retainedObject

  $pythonSource = @'
from __future__ import annotations

import hashlib
import inspect
import os
from pathlib import Path

import numpy as np

from phoenix_sdr_dsp.pqc import dr2d_mlkem512_kpke_keygen_abi as abi
from phoenix_sdr_dsp.pqc import (
    dr2d_mlkem512_kpke_keygen_w0_token_tap_graph as tap,
)

AUTH_ENV = "PQC_DR2D_W0_TAP_NATIVE_AUTHORIZATION"

if os.environ.get(AUTH_ENV):
    raise SystemExit("REFUSED: native authorization is present during compile-only gate")

before = tap.verify_production_hashes()
print("HASH_GATE_BEFORE=PASS")
for name, digest in sorted(before.items()):
    print(f"PINNED_BEFORE {name}={digest}")

design = tap._program()
expected_compile_params = {
    "d_slots",
    "descriptor_slots",
    "secret_token_slots",
    "element_type",
}
actual_compile_params = set(design.compilable.compile_params)
if actual_compile_params != expected_compile_params:
    raise SystemExit(
        "REFUSED: diagnostic graph CompileTime[T] parameters are wrong: "
        f"expected {sorted(expected_compile_params)}, "
        f"observed {sorted(actual_compile_params)}"
    )

specialized = design.specialize(
    d_slots=abi.D_BYTES,
    descriptor_slots=abi.DESCRIPTOR_BYTES,
    secret_token_slots=abi.SECRET_TOKEN_BYTES,
    element_type=np.uint8,
)
actual_compile_kwargs = set(specialized.compilable.compile_kwargs)
if actual_compile_kwargs != expected_compile_params:
    raise SystemExit(
        "REFUSED: specialization keys do not match CompileTime[T] parameters: "
        f"expected {sorted(expected_compile_params)}, "
        f"observed {sorted(actual_compile_kwargs)}"
    )

mlir_text = specialized.as_mlir()
if "dr2d_kpke_keygen_seed_noise" not in mlir_text:
    raise SystemExit("REFUSED: generated MLIR is missing the W0 kernel")
if "dr2d_w0_tap_secret_token" not in mlir_text:
    raise SystemExit("REFUSED: generated MLIR is missing direct secret-token egress")
for forbidden_symbol in (
    "dr2d_kpke_keygen_row0_expand",
    "dr2d_kpke_keygen_row0_accumulate",
    "dr2d_kpke_keygen_row1_expand",
    "dr2d_kpke_keygen_row1_accumulate",
    "dr2d_kpke_keygen_serialize",
):
    if forbidden_symbol in mlir_text:
        raise SystemExit(
            f"REFUSED: generated MLIR contains forbidden symbol {forbidden_symbol}"
        )
print("COMPILETIME_PARAMETER_GATE=PASS")
print("SPECIALIZATION_KEY_GATE=PASS")
print("NO_DISPATCH_MLIR_GENERATION=PASS")
print("GENERATED_MLIR_SHA256=" + hashlib.sha256(mlir_text.encode("utf-8")).hexdigest())

callable_compile_source = inspect.getsource(type(specialized).compile)
compilable_compile_source = inspect.getsource(type(specialized.compilable).compile)

if "self.compilable.compile(" not in callable_compile_source:
    raise SystemExit(
        "REFUSED: CallableDesign.compile no longer delegates to "
        "CompilableDesign.compile"
    )

for label, source in (
    ("CallableDesign.compile", callable_compile_source),
    ("CompilableDesign.compile", compilable_compile_source),
):
    for forbidden in ("NPUKernel", "DefaultNPURuntime", "pyxrt"):
        if forbidden in source:
            raise SystemExit(
                f"REFUSED: {label} unexpectedly references execution surface "
                f"{forbidden}"
            )

print(
    "CALLABLE_COMPILE_SOURCE_SHA256="
    + hashlib.sha256(callable_compile_source.encode("utf-8")).hexdigest()
)
print(
    "COMPILABLE_COMPILE_SOURCE_SHA256="
    + hashlib.sha256(compilable_compile_source.encode("utf-8")).hexdigest()
)
print(
    "EXACT_COMPILE_EXPRESSION="
    "tap._program().specialize("
    "d_slots=32,descriptor_slots=16,secret_token_slots=2096,"
    "element_type=numpy.uint8).compile()"
)
print("NO_RUNTIME_TENSORS_CREATED=True")
print("NO_CALLABLE_DESIGN_INVOCATION=True")
print("COMPILE_ONLY_BEGIN=True")

xclbin_path, inst_path = specialized.compile()

xclbin = Path(xclbin_path).resolve()
if inst_path is None:
    raise SystemExit("REFUSED: compile-only build returned no instruction artifact")
insts = Path(inst_path).resolve()

if not xclbin.is_file():
    raise SystemExit(f"REFUSED: returned xclbin is missing: {xclbin}")
if not insts.is_file():
    raise SystemExit(f"REFUSED: returned instruction file is missing: {insts}")

cache_path = xclbin.parent.resolve()
if not cache_path.is_dir():
    raise SystemExit(f"REFUSED: returned cache directory is missing: {cache_path}")

pdis = [Path(path).resolve() for path in specialized.get_pdi_paths()]
if not pdis or any(not path.is_file() for path in pdis):
    raise SystemExit("REFUSED: compile-only build did not retain its PDI")

after = tap.verify_production_hashes()
if after != before:
    raise SystemExit("REFUSED: pinned production hashes changed during compilation")

print("HASH_GATE_AFTER=PASS")
for name, digest in sorted(after.items()):
    print(f"PINNED_AFTER {name}={digest}")

print(f"XCLBIN_PATH={xclbin}")
print(f"INST_PATH={insts}")
print(f"CACHE_PATH={cache_path}")
for path in pdis:
    print(f"PDI_PATH={path}")
print("COMPILE_ONLY_COMPLETE=True")
print("NPU_DISPATCH_ATTEMPTED=False")
'@

  [System.IO.File]::WriteAllText(
    $compileScript,
    $pythonSource,
    [System.Text.UTF8Encoding]::new($false)
  )

  & {
    "===== COMPILE-ONLY COMMAND PROVENANCE ====="
    "UTC_START=$([DateTime]::UtcNow.ToString('o'))"
    "POWERSHELL_PID=$PID"
    "PYTHON=$([System.IO.Path]::GetFullPath($py))"
    "PYTHON_SHA256=$((Get-FileHash -Algorithm SHA256 -LiteralPath $py).Hash)"
    "COMPILE_SCRIPT=$compileScript"
    "COMPILE_SCRIPT_SHA256=$((Get-FileHash -Algorithm SHA256 -LiteralPath $compileScript).Hash)"
    "RETAINED_OBJECT=$retainedObject"
    "RETAINED_OBJECT_SHA256=$((Get-FileHash -Algorithm SHA256 -LiteralPath $retainedObject).Hash)"
    "NATIVE_AUTHORIZATION_PRESENT=$([bool](Test-Path Env:PQC_DR2D_W0_TAP_NATIVE_AUTHORIZATION))"
    "EXACT_COMMAND=& `"$([System.IO.Path]::GetFullPath($py))`" `"$compileScript`""
    "===== COMPILE SCRIPT BEGIN ====="
    Get-Content -LiteralPath $compileScript -Raw
    "===== COMPILE SCRIPT END ====="

    $compileOutput = @(& $py $compileScript 2>&1)
    $compileExit = $LASTEXITCODE
    $compileOutput | ForEach-Object { [string]$_ }
    "COMPILE_EXIT=$compileExit"

    if ($compileExit -ne 0) {
      throw "Compile-only Python process failed with exit code $compileExit"
    }

    $cacheLine = $compileOutput |
      ForEach-Object { [string]$_ } |
      Where-Object { $_ -like "CACHE_PATH=*" } |
      Select-Object -Last 1
    if (-not $cacheLine) {
      throw "Compile-only process did not report CACHE_PATH"
    }

    $tapCache = [System.IO.Path]::GetFullPath(
      $cacheLine.Substring("CACHE_PATH=".Length)
    )
    $cacheRoot = [System.IO.Path]::GetFullPath("$HOME\.npu\cache")

    if ($tapCache -eq $productionCache) {
      throw "Diagnostic compilation reused the production cache; refusing evidence"
    }
    if (-not $tapCache.StartsWith($cacheRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
      throw "Reported cache is outside the pinned NPU cache root: $tapCache"
    }
    if (-not (Test-Path -LiteralPath $tapCache -PathType Container)) {
      throw "Reported diagnostic cache does not exist: $tapCache"
    }
    if (Test-Path Env:PQC_DR2D_W0_TAP_NATIVE_AUTHORIZATION) {
      throw "Native authorization appeared during compilation"
    }

    "===== EXACT CACHE PATH ====="
    "TAP_CACHE=$tapCache"
    "PRODUCTION_CACHE=$productionCache"
    "CACHE_IS_DISTINCT=True"

    "===== CACHE INVENTORY ====="
    Get-ChildItem -LiteralPath $tapCache -Recurse -File |
      Sort-Object FullName |
      ForEach-Object {
        "FILE=$($_.FullName) SIZE=$($_.Length) UTC=$($_.LastWriteTimeUtc.ToString('o')) SHA256=$((Get-FileHash -Algorithm SHA256 -LiteralPath $_.FullName).Hash)"
      }

    $requiredNames = @(
      "final.xclbin",
      "insts.bin",
      "deps.json",
      "input_with_addresses.mlir"
    )
    foreach ($name in $requiredNames) {
      $match = Get-ChildItem -LiteralPath $tapCache -Recurse -File |
        Where-Object { $_.Name -eq $name } |
        Select-Object -First 1
      if (-not $match) {
        throw "Required compile-only artifact is missing: $name"
      }
      "REQUIRED_ARTIFACT=$($match.FullName)"
    }

    "===== GENERATED TEXT ARTIFACTS ====="
    Get-ChildItem -LiteralPath $tapCache -Recurse -File |
      Where-Object {
        $_.Extension -in @(".mlir", ".json", ".map", ".ld", ".script", ".txt", ".log")
      } |
      Sort-Object FullName |
      ForEach-Object {
        "===== RAW BEGIN: $($_.FullName) ====="
        Get-Content -LiteralPath $_.FullName -Raw
        "===== RAW END: $($_.FullName) ====="
      }

    "===== OBJECT AND ELF INSPECTION ====="
    $binaryArtifacts = Get-ChildItem -LiteralPath $tapCache -Recurse -File |
      Where-Object { $_.Extension -in @(".o", ".elf") } |
      Sort-Object FullName
    if (-not $binaryArtifacts) {
      throw "Compile-only cache contains no object or ELF artifacts"
    }

    foreach ($artifact in $binaryArtifacts) {
      "===== BINARY BEGIN: $($artifact.FullName) ====="
      "SHA256=$((Get-FileHash -Algorithm SHA256 -LiteralPath $artifact.FullName).Hash)"
      & $readobj --file-headers --sections --symbols --relocations $artifact.FullName
      if ($LASTEXITCODE -ne 0) {
        throw "llvm-readobj failed for $($artifact.FullName)"
      }
      & $objdump -dr --triple=aie2 --disassemble-zeroes $artifact.FullName
      if ($LASTEXITCODE -ne 0) {
        throw "llvm-objdump failed for $($artifact.FullName)"
      }
      "===== BINARY END: $($artifact.FullName) ====="
    }

    "===== FINAL SAFETY ASSERTIONS ====="
    "NATIVE_AUTHORIZATION_PRESENT=$([bool](Test-Path Env:PQC_DR2D_W0_TAP_NATIVE_AUTHORIZATION))"
    "RUNNER_INVOKED=False"
    "XRT_TENSOR_CREATED=False"
    "NPU_DISPATCH_ATTEMPTED=False"
    "COMPILE_ONLY_GATE=PASS"
    "UTC_END=$([DateTime]::UtcNow.ToString('o'))"
  } 2>&1 | Tee-Object -FilePath $evidence
}
