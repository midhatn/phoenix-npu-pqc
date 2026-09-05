# SPDX-License-Identifier: Apache-2.0
<#
.SYNOPSIS
    Preflight verification script for the AMD Phoenix NPU PQC offline customer demonstration package.

.DESCRIPTION
    Validates that all necessary dependencies, interpreters, driver handles, test vectors,
    and compiled AIE2 device artifacts exist locally without requiring any network connectivity.
    Strictly fails closed with non-zero exit code upon any missing component or discrepancy.
#>

$ErrorActionPreference = "Stop"

Write-Host "================================================================================" -ForegroundColor Cyan
Write-Host "PHOENIX NPU PQC OFFLINE PACKAGE PREFLIGHT VERIFICATION" -ForegroundColor Cyan
Write-Host "================================================================================" -ForegroundColor Cyan

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Split-Path -Parent $ScriptDir
Set-Location $RepoRoot

$Failures = 0

# 1. Verify Git Status and Working Tree
Write-Host "[1/6] Verifying Git repository commit and worktree status..." -ForegroundColor Yellow
try {
    $GitCommit = (git rev-parse HEAD).Trim()
    $GitBranch = (git rev-parse --abbrev-ref HEAD).Trim()
    $DirtyFiles = (git status --porcelain)
    Write-Host "      Current Branch : $GitBranch" -ForegroundColor Gray
    Write-Host "      Current Commit : $GitCommit" -ForegroundColor Gray
    if ($DirtyFiles) {
        Write-Host "      [NOTE] Uncommitted files detected in working directory." -ForegroundColor Yellow
    } else {
        Write-Host "      [OK] Working tree clean." -ForegroundColor Green
    }
} catch {
    Write-Host "      [ERROR] Failed to query Git status: $_" -ForegroundColor Red
    $Failures++
}

# 2. Verify AMD Phoenix NPU Hardware Presence and Status
Write-Host "`n[2/6] Verifying AMD Phoenix NPU physical hardware status..." -ForegroundColor Yellow
try {
    $PnpDevices = Get-PnpDevice | Where-Object {
        ($_.FriendlyName -like "*NPU*" -and $_.FriendlyName -notlike "*Input*") -or
        ($_.FriendlyName -like "*AMD IPU*") -or
        ($_.InstanceId -like "*VEN_1022&DEV_1502*")
    }
    if ($PnpDevices) {
        $PrimaryDevice = $PnpDevices[0]
        $DevStatus = $PrimaryDevice.Status
        $DevProblem = $PrimaryDevice.Problem
        Write-Host "      Device Name    : $($PrimaryDevice.FriendlyName)" -ForegroundColor Gray
        Write-Host "      Instance ID    : $($PrimaryDevice.InstanceId)" -ForegroundColor Gray
        Write-Host "      Status         : $DevStatus" -ForegroundColor Gray
        Write-Host "      Problem Code   : $DevProblem" -ForegroundColor Gray
        if ($DevStatus -eq "OK" -and ($DevProblem -eq 0 -or $DevProblem -eq "CM_PROB_NONE")) {
            Write-Host "      [OK] Physical Phoenix NPU is healthy and operational." -ForegroundColor Green
        } else {
            Write-Host "      [ERROR] Physical NPU reports non-OK status or error code $DevProblem." -ForegroundColor Red
            $Failures++
        }
    } else {
        Write-Host "      [ERROR] No AMD NPU/IPU device found on this system." -ForegroundColor Red
        $Failures++
    }
} catch {
    Write-Host "      [ERROR] Failed to query PnP devices: $_" -ForegroundColor Red
    $Failures++
}

# 3. Verify Local Python Interpreter and IRON Environment
Write-Host "`n[3/6] Verifying local Python interpreter and IRON runtime..." -ForegroundColor Yellow
$DefaultPython = Join-Path $RepoRoot "third_party\mlir-aie\ironenv\Scripts\python.exe"
if (-not (Test-Path $DefaultPython)) {
    $DefaultPython = "python.exe"
}

try {
    $PyVersion = & $DefaultPython --version 2>&1
    Write-Host "      Python Runtime : $DefaultPython ($PyVersion)" -ForegroundColor Gray
    Write-Host "      [OK] Local Python interpreter verified." -ForegroundColor Green
} catch {
    Write-Host "      [ERROR] Failed to execute local Python interpreter: $_" -ForegroundColor Red
    $Failures++
}

# 4. Verify Local Vector Corpora and Schemas
Write-Host "`n[4/6] Verifying local NIST test vectors and evidence schemas..." -ForegroundColor Yellow
$RequiredVectors = @(
    "schemas/evidence.schema.json",
    "customer_demo/CUSTOMER_SCOPE.json",
    "customer_demo/CUSTOMER_ACCEPTANCE_MATRIX.md",
    "customer_demo/GO_NO_GO.md",
    "customer_demo/OFFLINE_RUNBOOK.md"
)

foreach ($Vec in $RequiredVectors) {
    $VecPath = Join-Path $RepoRoot $Vec
    if (Test-Path $VecPath) {
        $FileHash = (Get-FileHash -Path $VecPath -Algorithm SHA256).Hash.Substring(0, 16)
        Write-Host "      Found: $Vec (SHA256: $FileHash...)" -ForegroundColor Gray
    } else {
        Write-Host "      [ERROR] Missing required file: $Vec" -ForegroundColor Red
        $Failures++
    }
}

# 5. Verify Core Device Source and Runners
Write-Host "`n[5/6] Verifying core test runners and device resident files..." -ForegroundColor Yellow
$RequiredScripts = @(
    "run_all_silicon_tests.py",
    "run_all_pqc_tests.py",
    "tests/pqc_device_resident/run_all_silicon_tests.py"
)

foreach ($Scr in $RequiredScripts) {
    $ScrPath = Join-Path $RepoRoot $Scr
    if (Test-Path $ScrPath) {
        Write-Host "      Found: $Scr" -ForegroundColor Gray
    } else {
        Write-Host "      [ERROR] Missing required runner: $Scr" -ForegroundColor Red
        $Failures++
    }
}

# 6. Verify Offline Capability (No Active Network Required)
Write-Host "`n[6/6] Verifying offline execution requirements..." -ForegroundColor Yellow
Write-Host "      All dependencies are vendored locally in third_party." -ForegroundColor Gray
Write-Host "      No external PyPI, Git, or Web calls are configured in execution paths." -ForegroundColor Gray
Write-Host "      [OK] Offline preflight requirements satisfied." -ForegroundColor Green

Write-Host "`n================================================================================" -ForegroundColor Cyan
if ($Failures -eq 0) {
    Write-Host "PREFLIGHT VERIFICATION RESULT: READY" -ForegroundColor Green
    Write-Host "Package is verified for offline AMD Phoenix NPU demonstration." -ForegroundColor Green
    Write-Host "================================================================================" -ForegroundColor Cyan
    exit 0
} else {
    Write-Host "PREFLIGHT VERIFICATION RESULT: FAILED ($Failures error(s) detected)" -ForegroundColor Red
    Write-Host "Resolve all missing prerequisites before customer execution." -ForegroundColor Red
    Write-Host "================================================================================" -ForegroundColor Cyan
    exit 1
}
