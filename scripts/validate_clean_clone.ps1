[CmdletBinding()]
param(
    [switch]$InstallHostDependencies,
    [string]$Python = ""
)

# This normal-user PowerShell 7 clean-checkout audit is host-safe. Despite the
# retained filename, it does not create a clone: it rejects every staged,
# unstaged, or untracked change before testing and records the exact HEAD
# commit. It never calls a native gate, builds an AIE program, or dispatches
# hardware. It therefore produces NO silicon evidence. Canonical silicon
# validation is the separate physical run of `py .\run_all_silicon_tests.py`
# on the target Phoenix laptop.
# Installer modes used here are non-dispatching only: `install --check-only`
# for the prerequisite report and, with -InstallHostDependencies,
# `install --no-tests` for native provisioning without the automatic handoff
# to the canonical physical runner.
$ErrorActionPreference = "Stop"
$repo = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$evidenceDirectory = Join-Path $repo "release-evidence\clean-checkout"
New-Item -ItemType Directory -Force -Path $evidenceDirectory | Out-Null
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$report = Join-Path $evidenceDirectory "pqc-clean-checkout-$stamp.txt"
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
        Invoke-Checked "Provision the native toolchain with the pinned installer (no dispatch)" `
            $PythonCommand @("install", "--no-tests")
        return
    }

    & $PythonCommand @("install", "--check-only") 2>&1 |
        ForEach-Object { Write-Report "$_" }
    if ($LASTEXITCODE -ne 0) {
        throw (
            "Native prerequisites are absent or mismatched. Re-run with " +
            "-InstallHostDependencies, which delegates only to py .\install " +
            "--no-tests and its pinned, size- and SHA-256-verified artifact " +
            "provisioning. Neither mode compiles an AIE program or " +
            "dispatches hardware."
        )
    }
    Write-Report "Native prerequisite report produced by the pinned installer (--check-only)."
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
    $isWorkTree = (& git rev-parse --is-inside-work-tree).Trim()
    if ($LASTEXITCODE -ne 0 -or $isWorkTree -ne "true") {
        throw "Repository root is not a Git working tree; refusing clean-checkout audit."
    }
    $testedCommit = (& git rev-parse --verify HEAD).Trim()
    if ($LASTEXITCODE -ne 0 -or -not $testedCommit) {
        throw "Unable to resolve an immutable HEAD commit; refusing clean-checkout audit."
    }
    $initialStatus = & git status --porcelain=v1 --untracked-files=all
    if ($LASTEXITCODE -ne 0) {
        throw "Unable to inspect full checkout status; refusing clean-checkout audit."
    }
    if ($initialStatus) {
        throw (
            "Checkout is dirty (staged, unstaged, or untracked content); refusing " +
            "clean-checkout audit for HEAD $testedCommit."
        )
    }

    Write-Report "Phoenix NPU PQC clean-checkout host-audit evidence"
    Write-Report "Timestamp (local): $(Get-Date -Format o)"
    Write-Report "Repository: $repo"
    Write-Report "Tested commit (immutable HEAD): $testedCommit"
    Write-Report "PowerShell: $($PSVersionTable.PSVersion)"
    Write-Report "Hardware access: disabled (no dispatch switch exists)"
    Write-Report "This audit is host preflight only and is NOT silicon validation."

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
    Invoke-Checked "List host preflight test plan" $pythonCommand @("run_all_pqc_tests.py", "--dry-run")
    Invoke-Checked "List canonical native gate plan (no dispatch)" $pythonCommand @(
        "run_all_silicon_tests.py", "--list"
    )
    Invoke-Checked "Compile maintained Python" $pythonCommand @(
        "-m", "compileall", "-q", "phoenix_sdr_dsp", "tests", "tools",
        "install", "install.py", "run_all_pqc_tests.py", "run_all_silicon_tests.py"
    )
    Invoke-Checked "Run host preflight PQC suite" $pythonCommand @("run_all_pqc_tests.py")

    $finalCommit = (& git rev-parse --verify HEAD).Trim()
    if ($LASTEXITCODE -ne 0 -or $finalCommit -ne $testedCommit) {
        throw (
            "HEAD changed during audit (expected $testedCommit, observed $finalCommit); " +
            "refusing to certify the result."
        )
    }
    $finalStatus = & git status --porcelain=v1 --untracked-files=all
    if ($LASTEXITCODE -ne 0) {
        throw "Unable to re-check full checkout status after audit."
    }
    if ($finalStatus) {
        throw "Checkout changed during audit; refusing to certify the result."
    }
    Write-Report "Verified immutable HEAD unchanged: $testedCommit"
    Write-Report "Verified full checkout clean after audit (including untracked files)."

    Write-Report "`nHost preflight audit: PASS"
    Write-Report "Native gates: NOT RUN. No AIE compilation or NPU dispatch occurred."
    Write-Report "No NPU claim follows from this report. Only canonical native"
    Write-Report "runner output from the target laptop can support one."
    Write-Report "Evidence report: $report"
    exit 0
}
catch {
    Write-Report "`nRESULT: FAIL"
    Write-Report $_.Exception.Message
    Write-Report "Evidence report: $report"
    exit 1
}
