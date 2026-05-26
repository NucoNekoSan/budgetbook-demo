param(
    [string]$Version = "0.1.0",
    [switch]$BuildWindows,
    [switch]$RequireClean
)

$ErrorActionPreference = "Stop"

function Invoke-Checked {
    param(
        [string]$FilePath,
        [string[]]$ArgumentList
    )
    & $FilePath @ArgumentList
    if ($LASTEXITCODE -ne 0) {
        throw "$FilePath failed with exit code $LASTEXITCODE"
    }
}

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$Python = Join-Path $RepoRoot ".venv-mirror\Scripts\python.exe"
if (-not (Test-Path $Python)) {
    $Python = Join-Path $RepoRoot "budgetbook\.venv\Scripts\python.exe"
}
if (-not (Test-Path $Python)) { $Python = "python" }

Push-Location $RepoRoot
try {
    Invoke-Checked $Python @(
        "-m",
        "py_compile",
        "desktop\launcher.py",
        "packaging\audit_release.py",
        "packaging\audit_source_sensitive.py",
        "packaging\check_release_ready.py",
        "packaging\release_manifest.py",
        "packaging\sensitive_patterns.py"
    )

    Invoke-Checked $Python @("packaging\audit_source_sensitive.py", "--verbose")

    $releaseReadyArgs = @("packaging\check_release_ready.py")
    if ($RequireClean) { $releaseReadyArgs += "--require-clean" }
    Invoke-Checked $Python $releaseReadyArgs

    Push-Location (Join-Path $RepoRoot "budgetbook")
    try {
        Invoke-Checked $Python @("manage.py", "test", "ledger.tests.test_first_run_setup", "ledger.tests.test_default_master_seed", "ledger.tests.test_pwa")
    }
    finally {
        Pop-Location
    }

    if ($BuildWindows) {
        Invoke-Checked "powershell" @("-ExecutionPolicy", "Bypass", "-File", "packaging\windows\build-installer.ps1", "-Version", $Version)
    }

    Write-Host "Release preflight completed for version $Version."
    if ($BuildWindows) {
        Write-Host "Upload release/windows/*.exe, *.sha256, and *.manifest.json to a draft GitHub Release."
    }
}
finally {
    Pop-Location
}
