[CmdletBinding()]
param(
    [switch]$InstallHostDependencies,
    [string]$Python = ""
)

# This normal-user PowerShell 7 audit is host-safe. It never calls a retained
# native gate, builds an AIE program, probes an NPU, or dispatches hardware.
$ErrorActionPreference = "Stop"
$repo = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$evidenceDirectory = Join-Path $repo "release-evidence\clean-clone"
New-Item -ItemType Directory -Force -Path $evidenceDirectory | Out-Null
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$report = Join-Path $evidenceDirectory "pqc-clean-clone-$stamp.txt"
$protectedRelative = "docs/pqc_dr2_evidence_20260818"
$manifestRelative = "$protectedRelative/SHA256SUMS"

function Write-Report {
    param([string]$Message)
    $Message | Tee-Object -FilePath $report -Append
}

function Invoke-Checked {
    param(
        [string]$Label,
        [string]$FilePath,
        [string[]]$Arguments
    )

    Write-Report "`n>>> $Label"
    Write-Report "> $FilePath $($Arguments -join ' ')"
    & $FilePath @Arguments 2>&1 | ForEach-Object { Write-Report "$_" }
    if ($LASTEXITCODE -ne 0) {
        throw "$Label failed with exit code $LASTEXITCODE."
    }
}

function Resolve-Python {
    param([string]$Requested)
    if ($Requested) {
        return $Requested
    }
    if (Get-Command py -ErrorAction SilentlyContinue) {
        return "py"
    }
    if (Get-Command python -ErrorAction SilentlyContinue) {
        return "python"
    }
    throw "Neither the Windows Python launcher ('py') nor 'python' is available."
}

function Test-HostDependencies {
    param(
        [string]$PythonCommand,
        [switch]$Install
    )

    if ($Install) {
        Invoke-Checked "Provision pinned dependency with the integrity-checked bootstrap" `
            $PythonCommand @("install", "--no-tests")
        return
    }

    & $PythonCommand @("install", "--check-only") 2>&1 |
        ForEach-Object { Write-Report "$_" }
    if ($LASTEXITCODE -ne 0) {
        throw (
            "Pinned NumPy is absent or mismatched. Re-run with " +
            "-InstallHostDependencies, which delegates only to py .\install " +
            "--no-tests and its pinned local-wheel verification."
        )
    }
    Write-Report "Pinned host dependency verified by the integrity-checked bootstrap."
}

function Test-Sha256Manifest {
    param([string]$Manifest)

    $manifestDirectory = Split-Path -Parent $Manifest
    $checked = 0
    foreach ($line in Get-Content -LiteralPath $Manifest) {
        if ([string]::IsNullOrWhiteSpace($line)) {
            continue
        }
        if ($line -notmatch '^(?<hash>[0-9a-fA-F]{64})\s+\*?(?<path>.+)$') {
            throw "Malformed SHA256SUMS entry: $line"
        }
        $relativePath = $matches.path -replace '^\./', ''
        $candidate = Join-Path $manifestDirectory $relativePath
        if (-not (Test-Path -LiteralPath $candidate -PathType Leaf)) {
            throw "Manifest file is missing: $relativePath"
        }
        $actual = (Get-FileHash -LiteralPath $candidate -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($actual -ne $matches.hash.ToLowerInvariant()) {
            throw "SHA-256 mismatch: $relativePath"
        }
        $checked++
    }
    if ($checked -eq 0) {
        throw "SHA256SUMS contains no file entries."
    }
    Write-Report "Protected evidence manifest entries verified: $checked"
}

try {
    Set-Location $repo
    Write-Report "Phoenix NPU PQC clean-clone evidence"
    Write-Report "Timestamp (local): $(Get-Date -Format o)"
    Write-Report "Repository: $repo"
    Write-Report "PowerShell: $($PSVersionTable.PSVersion)"
    Write-Report "Hardware access: disabled (no dispatch switch exists)"

    Invoke-Checked "Verify Git checkout" "git" @("rev-parse", "--is-inside-work-tree")
    Invoke-Checked "Record Git commit" "git" @("rev-parse", "HEAD")
    Invoke-Checked "Record Git status" "git" @("status", "--short", "--branch")
    Invoke-Checked "Record Git version" "git" @("--version")

    $protectedStatus = & git status --porcelain -- $protectedRelative
    if ($LASTEXITCODE -ne 0) {
        throw "Unable to inspect protected evidence status."
    }
    if ($protectedStatus) {
        throw "Protected evidence has a working-tree change; refusing to continue."
    }
    Invoke-Checked "Verify protected evidence matches HEAD" "git" @(
        "diff", "--exit-code", "--", $protectedRelative
    )

    $manifest = Join-Path $repo $manifestRelative
    if (-not (Test-Path -LiteralPath $manifest -PathType Leaf)) {
        throw "Protected SHA256SUMS is missing: $manifest"
    }
    Test-Sha256Manifest $manifest

    $pythonCommand = Resolve-Python $Python
    Invoke-Checked "Record Python version" $pythonCommand @("--version")
    Test-HostDependencies $pythonCommand -Install:$InstallHostDependencies
    Invoke-Checked "List host-safe test plan" $pythonCommand @("run_all_pqc_tests.py", "--dry-run")
    Invoke-Checked "Compile maintained Python" $pythonCommand @(
        "-m", "compileall", "-q", "phoenix_sdr_dsp", "tests", "tools",
        "install", "install.py", "run_all_pqc_tests.py", "run_all_silicon_tests.py"
    )
    Invoke-Checked "Run host-safe PQC suite" $pythonCommand @("run_all_pqc_tests.py")

    Write-Report "`nHost-safe audit: PASS"
    Write-Report "Historical native scripts: NOT RUN. No NPU access occurred."
    Write-Report "Evidence report: $report"
    exit 0
}
catch {
    Write-Report "`nRESULT: FAIL"
    Write-Report $_.Exception.Message
    Write-Report "Evidence report: $report"
    exit 1
}
