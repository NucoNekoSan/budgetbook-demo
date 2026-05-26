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

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$AppRoot = Join-Path $RepoRoot "budgetbook"
$Launcher = Join-Path $RepoRoot "desktop\launcher.py"
$Python = Join-Path $RepoRoot ".venv-mirror\Scripts\python.exe"
if (-not (Test-Path $Python)) { $Python = "python" }

Push-Location $AppRoot
try {
    Invoke-Checked $Python @("-m", "pip", "install", "-r", "requirements.txt")
    Invoke-Checked $Python @("-m", "pip", "install", "pyinstaller>=6,<7")
    Invoke-Checked $Python @(
        "-m", "PyInstaller", "--noconfirm", "--clean", "--name", "BudgetBook", "--onedir",
        "--paths", $AppRoot,
        "--hidden-import", "dotenv",
        "--hidden-import", "axes",
        "--hidden-import", "axes.apps",
        "--hidden-import", "axes.backends",
        "--hidden-import", "axes.middleware",
        "--hidden-import", "django_htmx",
        "--hidden-import", "django_htmx.middleware",
        "--hidden-import", "whitenoise.middleware",
        "--hidden-import", "whitenoise.storage",
        "--collect-submodules", "axes",
        "--collect-submodules", "django_htmx",
        "--collect-submodules", "whitenoise",
        "--add-data", "static;static",
        "--add-data", "templates;templates",
        "--add-data", "ledger;ledger",
        "--add-data", "config;config",
        $Launcher
    )
}
finally {
    Pop-Location
}

Invoke-Checked $Python @((Join-Path $RepoRoot "packaging\audit_release.py"), (Join-Path $AppRoot "dist\BudgetBook"))