<#
.SYNOPSIS
    Phoenix SDR-DSP environment bootstrap for Windows 11 + AMD Ryzen AI (Phoenix NPU).

.DESCRIPTION
    Idempotent script that repairs / rebuilds a broken ironenv:
      1. (Re)creates ironenv if missing
      2. Reinstalls mlir-aie + llvm-aie (Peano) wheels
      3. Copies the vendored pyxrt.pyd from third_party\xrt_windows_sdk into site-packages
      4. Writes sitecustomize.py so pyxrt can find its DLLs (System32 + AMD + xrt_sdk)
      5. Sets PEANO_INSTALL_DIR (user scope) and prepends Peano\bin to PATH for this session
      6. Runs a smoke check (import pyxrt, clang++ --version)

    Requires: Windows 11, Python 3.10+, git, AMD Ryzen AI NPU driver installed,
              <RepoRoot>\third_party\xrt_windows_sdk populated. RepoRoot is
              auto-detected as the parent of this script's directory; override
              with -RepoRoot when the checkout lives elsewhere or the script is
              invoked from an unusual working directory.

.PARAMETER RepoRoot
    Absolute path to the phoenix-sdr-dsp checkout. Defaults to the parent of
    the directory containing this script (i.e. the repo root when this file
    lives at scripts\bootstrap_env.ps1).

.EXAMPLE
    .\scripts\bootstrap_env.ps1

.EXAMPLE
    .\scripts\bootstrap_env.ps1 -RepoRoot D:\phoenix-sdr-dsp
#>

[CmdletBinding()]
param(
    [string]$RepoRoot = (Split-Path -Parent $PSScriptRoot)
)

$ErrorActionPreference = "Stop"
$MlirAie    = "$RepoRoot\third_party\mlir-aie"
$IronEnv    = "$MlirAie\ironenv"
$XrtSdk     = "$RepoRoot\third_party\xrt_windows_sdk\xrt_sdk\xrt"
$XrtPyxrt   = "$XrtSdk\python\pyxrt.pyd"

function Section($msg) { Write-Host "`n=== $msg ===" -ForegroundColor Cyan }

Section "Prereq check"
if (-not (Test-Path $RepoRoot)) { throw "Repo not found at $RepoRoot" }
if (-not (Test-Path $XrtPyxrt))  { throw "Missing $XrtPyxrt. Restore third_party\xrt_windows_sdk\ first." }
python --version
git --version | Out-Null

Section "Ensure mlir-aie clone exists"
if (-not (Test-Path $MlirAie\.git)) {
    New-Item -ItemType Directory -Force -Path "$RepoRoot\third_party" | Out-Null
    git clone https://github.com/Xilinx/mlir-aie.git $MlirAie
}

Section "Ensure ironenv exists"
if (-not (Test-Path "$IronEnv\Scripts\Activate.ps1")) {
    python -m venv $IronEnv
}
& "$IronEnv\Scripts\Activate.ps1"
python -m pip install --upgrade pip wheel | Out-Null

Section "Install / repair mlir-aie + llvm-aie"
python -m pip install --upgrade mlir-aie
python -m pip install --upgrade --force-reinstall llvm-aie `
    -f https://github.com/Xilinx/llvm-aie/releases/expanded_assets/nightly

$sitePkgs = python -c "import site; print(site.getsitepackages()[0])"
Write-Host "site-packages: $sitePkgs"

Section "Install vendored pyxrt.pyd from xrt_windows_sdk"
Copy-Item $XrtPyxrt "$sitePkgs\pyxrt.pyd" -Force
Write-Host "Copied pyxrt.pyd -> $sitePkgs\pyxrt.pyd"

Section "Write sitecustomize.py for DLL search paths"
$siteCustomize = @"
import os
_paths = [
    r"C:\Windows\System32",
    r"C:\Windows\System32\AMD",
    r"$XrtSdk",
]
for _p in _paths:
    if os.path.isdir(_p):
        try:
            os.add_dll_directory(_p)
        except Exception:
            pass
        if _p not in os.environ.get("PATH", ""):
            os.environ["PATH"] = _p + os.pathsep + os.environ.get("PATH", "")
"@
Set-Content -Path "$sitePkgs\sitecustomize.py" -Value $siteCustomize -Encoding UTF8

Section "Set PEANO_INSTALL_DIR (user scope) and PATH (session)"
$peanoDir = "$sitePkgs\llvm-aie"
if (-not (Test-Path "$peanoDir\bin\clang++.exe")) {
    throw "Peano clang++ not found at $peanoDir\bin\clang++.exe"
}
[System.Environment]::SetEnvironmentVariable("PEANO_INSTALL_DIR", $peanoDir, "User")
$env:PEANO_INSTALL_DIR = $peanoDir
$env:PATH = "$peanoDir\bin;$env:PATH"
Write-Host "PEANO_INSTALL_DIR = $peanoDir"

Section "Smoke check"
python -c "import pyxrt; print('pyxrt OK:', pyxrt.__file__)"
python -c "import aie; from aie.iron import ObjectFifo; print('mlir-aie / IRON OK')"
& "$peanoDir\bin\clang++.exe" --version | Select-Object -First 2

Write-Host "`nBootstrap complete. Now run:  python run_all_silicon_tests.py" -ForegroundColor Green
