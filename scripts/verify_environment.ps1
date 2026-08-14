[CmdletBinding()]
param(
    [string]$XrtRoot = "C:\Xilinx\XRT",
    [string]$MlirAieRoot = (Join-Path $PSScriptRoot "..\third_party\mlir-aie"),
    [string]$XrtSmi = "C:\Windows\System32\AMD\xrt-smi.exe"
)

$ErrorActionPreference = "Stop"
$failed = $false

function Test-Requirement {
    param(
        [string]$Name,
        [scriptblock]$Check
    )

    try {
        & $Check
        Write-Host "[PASS] $Name" -ForegroundColor Green
    }
    catch {
        Write-Host "[FAIL] $Name" -ForegroundColor Red
        Write-Host "       $($_.Exception.Message)" -ForegroundColor Yellow
        $script:failed = $true
    }
}

function Invoke-NativeCommand {
    param(
        [string]$FilePath,
        [string[]]$Arguments,
        [string]$ErrorMessage
    )

    $output = & $FilePath @Arguments 2>&1
    $exitCode = $LASTEXITCODE

    if ($exitCode -ne 0) {
        $details = $output -join [Environment]::NewLine
        throw "$ErrorMessage (exit code $exitCode)`n$details"
    }

    return $output
}

Write-Host "Phoenix SDR-DSP Native Windows Environment Check"
Write-Host "================================================="

Test-Requirement "Python is available" {
    $pythonVersion = Invoke-NativeCommand `
        -FilePath "python" `
        -Arguments @("--version") `
        -ErrorMessage "python command failed"

    $pythonVersion | ForEach-Object { Write-Host "       $_" }
}

Test-Requirement "CMake is available" {
    $cmakeVersion = Invoke-NativeCommand `
        -FilePath "cmake" `
        -Arguments @("--version") `
        -ErrorMessage "cmake command failed"

    $cmakeVersion |
        Select-Object -First 1 |
        ForEach-Object { Write-Host "       $_" }
}

Test-Requirement "XRT SDK root exists" {
    if (-not (Test-Path -LiteralPath $XrtRoot)) {
        throw "Missing XRT SDK directory: $XrtRoot"
    }

    Write-Host "       $XrtRoot"
}

Test-Requirement "MLIR-AIE checkout exists" {
    if (-not (Test-Path -LiteralPath $MlirAieRoot)) {
        throw "Missing MLIR-AIE checkout: $MlirAieRoot"
    }

    Write-Host "       $MlirAieRoot"
}

Test-Requirement "MLIR-AIE Python package imports" {
    $aiePath = Invoke-NativeCommand `
        -FilePath "python" `
        -Arguments @("-c", "import aie; print(aie.__file__)") `
        -ErrorMessage "Unable to import aie"

    $aiePath | ForEach-Object { Write-Host "       $_" }
}

Test-Requirement "XRT Python binding imports" {
    $pyxrtPath = Invoke-NativeCommand `
        -FilePath "python" `
        -Arguments @("-c", "import pyxrt; print(pyxrt.__file__)") `
        -ErrorMessage "Unable to import pyxrt"

    $pyxrtPath | ForEach-Object { Write-Host "       $_" }
}

Test-Requirement "NPU is visible through xrt-smi" {
    if (-not (Test-Path -LiteralPath $XrtSmi)) {
        throw "Missing xrt-smi executable: $XrtSmi"
    }

    $report = Invoke-NativeCommand `
        -FilePath $XrtSmi `
        -Arguments @("examine") `
        -ErrorMessage "xrt-smi examine failed"

    $reportText = $report -join [Environment]::NewLine

    if ($reportText -notmatch "NPU Phoenix") {
        throw "NPU Phoenix was not found in xrt-smi output"
    }

    $report |
        Select-String -Pattern "Version|NPU Driver Version|NPU Firmware Version|NPU Phoenix" |
        ForEach-Object { Write-Host "       $($_.Line)" }
}

Write-Host "================================================="

if ($failed) {
    Write-Host "Environment verification failed." -ForegroundColor Red
    return $false
}

Write-Host "Environment verification passed." -ForegroundColor Green
return $true
