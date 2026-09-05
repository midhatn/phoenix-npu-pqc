<#
.SYNOPSIS
    Automated fresh-clone validation tool for phoenix-npu-pqc.

.DESCRIPTION
    Clones the repository from a remote URL to a clean destination directory,
    validates the environment and dependencies, executes the documented test suites
    (host-only preflight and/or canonical physical silicon suite), and produces a
    fail-closed machine-readable report with sensitive path redaction.

.PARAMETER RepoUrl
    Remote Git repository URL to clone from (default: https://github.com/midhatn/phoenix-npu-pqc.git).

.PARAMETER Ref
    Git commit, branch, or tag to checkout and validate (default: main).

.PARAMETER Destination
    Target directory path for the fresh clone. Must not exist or must be completely empty.

.PARAMETER HostOnly
    Runs host preflight contract tests (run_all_pqc_tests.py). Requires no NPU hardware.

.PARAMETER Hardware
    Runs canonical physical silicon test suite (run_all_silicon_tests.py) on AMD Phoenix NPU.

.PARAMETER PythonExe
    Path to Python executable to use for running tests. Defaults to the current active Python.

.EXAMPLE
    .\tools\validate_fresh_clone.ps1 -Destination "C:\Projects\clean test clone" -HostOnly
#>

[CmdletBinding()]
param (
    [string]$RepoUrl = "https://github.com/midhatn/phoenix-npu-pqc.git",
    [string]$Ref = "main",
    [Parameter(Mandatory = $true)]
    [string]$Destination,
    [switch]$HostOnly,
    [switch]$Hardware,
    [string]$PythonExe = ""
)

$ErrorActionPreference = "Stop"

function Redact-Path {
    param ([string]$Text)
    if ([string]::IsNullOrEmpty($Text)) { return "" }
    # Redact personal user directory paths matching C:\Users\<username>
    $redacted = [regex]::Replace($Text, '(?i)[a-z]:\\Users\\[a-zA-Z0-9_.-]+', 'C:\Users\<redacted>')
    return $redacted
}

Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host "        PHOENIX-NPU-PQC AUTOMATED FRESH-CLONE VALIDATOR              " -ForegroundColor Cyan
Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host " Remote URL   : $RepoUrl"
Write-Host " Target Ref   : $Ref"
Write-Host " Destination  : $Destination"
Write-Host " Host Only    : $HostOnly"
Write-Host " Hardware NPU : $Hardware"
Write-Host " Timestamp    : $(Get-Date -Format 'o')"
Write-Host ""

# 1. Mode check: must specify at least one mode
if (-not $HostOnly -and -not $Hardware) {
    Write-Error "Execution mode required. Specify -HostOnly, -Hardware, or both."
    exit 1
}

# 2. Refuse to overwrite non-empty destination
if (Test-Path -LiteralPath $Destination) {
    $existingItems = Get-ChildItem -LiteralPath $Destination -Force
    if ($existingItems.Count -gt 0) {
        Write-Error "Destination directory '$Destination' already exists and is not empty. Refusing to overwrite."
        exit 1
    }
}

# 3. Resolve Python executable
if ([string]::IsNullOrEmpty($PythonExe)) {
    $PythonExe = (Get-Command python -ErrorAction Stop).Source
}
if (-not (Test-Path -LiteralPath $PythonExe)) {
    Write-Error "Python executable not found at: $PythonExe"
    exit 1
}

$pyVersion = & $PythonExe -c "import sys; print(sys.version.split()[0])"
Write-Host " Using Python : $PythonExe ($pyVersion)"

# 4. Clone repository
Write-Host "`n>>> [1/4] Cloning remote repository..." -ForegroundColor Yellow
$gitCloneArgs = @("clone", "--quiet", $RepoUrl, $Destination)
$cloneProc = Start-Process -FilePath "git" -ArgumentList $gitCloneArgs -Wait -PassThru -NoNewWindow
if ($cloneProc.ExitCode -ne 0) {
    Write-Error "git clone failed with exit code $($cloneProc.ExitCode)"
    exit $cloneProc.ExitCode
}

# 5. Checkout requested ref
Write-Host ">>> [2/4] Checking out ref: $Ref..." -ForegroundColor Yellow
Push-Location -LiteralPath $Destination
try {
    $gitCheckoutArgs = @("checkout", $Ref)
    $checkoutProc = Start-Process -FilePath "git" -ArgumentList $gitCheckoutArgs -Wait -PassThru -NoNewWindow
    if ($checkoutProc.ExitCode -ne 0) {
        Write-Error "git checkout '$Ref' failed with exit code $($checkoutProc.ExitCode)"
        exit $checkoutProc.ExitCode
    }

    $actualCommit = (& git rev-parse HEAD).Trim()
    $actualBranch = (& git rev-parse --abbrev-ref HEAD).Trim()
    Write-Host " Checked out commit: $actualCommit (branch: $actualBranch)" -ForegroundColor Green

    # Prepare results record
    $results = @{
        timestamp = (Get-Date -Format 'o')
        repo_url = $RepoUrl
        requested_ref = $Ref
        tested_commit = $actualCommit
        tested_branch = $actualBranch
        destination = (Redact-Path -Text $Destination)
        python_version = $pyVersion
        host_only_requested = [bool]$HostOnly
        hardware_requested = [bool]$Hardware
        host_preflight = $null
        hardware_silicon = $null
        overall_status = "UNKNOWN"
    }

    # 6. Run Host-Only Preflight Suite if requested
    if ($HostOnly) {
        Write-Host "`n>>> [3/4] Running Host Preflight Contract Tests (run_all_pqc_tests.py)..." -ForegroundColor Yellow
        $hostStartTime = Get-Date
        
        $hostProc = Start-Process -FilePath $PythonExe -ArgumentList @("run_all_pqc_tests.py") -Wait -PassThru -NoNewWindow
        $hostDuration = ((Get-Date) - $hostStartTime).TotalSeconds

        $results.host_preflight = @{
            exit_code = $hostProc.ExitCode
            duration_seconds = [math]::Round($hostDuration, 2)
            status = if ($hostProc.ExitCode -eq 0) { "PASS" } else { "FAIL" }
        }

        if ($hostProc.ExitCode -ne 0) {
            Write-Host " Host preflight tests FAILED (exit code $($hostProc.ExitCode))" -ForegroundColor Red
            $results.overall_status = "FAIL"
            $jsonOut = $results | ConvertTo-Json -Depth 4
            Set-Content -Path (Join-Path $Destination "validation_report.json") -Value $jsonOut -Encoding utf8
            exit $hostProc.ExitCode
        } else {
            Write-Host " Host preflight tests PASSED ($([math]::Round($hostDuration, 2))s)" -ForegroundColor Green
        }
    }

    # 7. Run Canonical Physical Silicon Suite if requested
    if ($Hardware) {
        Write-Host "`n>>> [4/4] Running Canonical Physical Silicon Suite (run_all_silicon_tests.py)..." -ForegroundColor Yellow
        $hwStartTime = Get-Date

        $hwProc = Start-Process -FilePath $PythonExe -ArgumentList @("run_all_silicon_tests.py") -Wait -PassThru -NoNewWindow
        $hwDuration = ((Get-Date) - $hwStartTime).TotalSeconds

        $results.hardware_silicon = @{
            exit_code = $hwProc.ExitCode
            duration_seconds = [math]::Round($hwDuration, 2)
            status = if ($hwProc.ExitCode -eq 0) { "PASS" } else { "FAIL" }
        }

        if ($hwProc.ExitCode -ne 0) {
            Write-Host " Hardware silicon tests FAILED (exit code $($hwProc.ExitCode))" -ForegroundColor Red
            $results.overall_status = "FAIL"
            $jsonOut = $results | ConvertTo-Json -Depth 4
            Set-Content -Path (Join-Path $Destination "validation_report.json") -Value $jsonOut -Encoding utf8
            exit $hwProc.ExitCode
        } else {
            Write-Host " Hardware silicon tests PASSED ($([math]::Round($hwDuration, 2))s)" -ForegroundColor Green
        }
    }

    $results.overall_status = "PASS"
    $jsonOut = $results | ConvertTo-Json -Depth 4
    Set-Content -Path (Join-Path $Destination "validation_report.json") -Value $jsonOut -Encoding utf8

    Write-Host "`n======================================================================" -ForegroundColor Cyan
    Write-Host "           FRESH-CLONE VALIDATION COMPLETE: PASS                     " -ForegroundColor Green
    Write-Host " Report written to: $(Join-Path $Destination 'validation_report.json')"
    Write-Host "======================================================================" -ForegroundColor Cyan
    exit 0
}
finally {
    Pop-Location
}
