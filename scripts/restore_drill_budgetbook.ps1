param(
    [string]$ProjectDir = "",
    [string]$BackupDir = "",
    [string]$BackupFile = "",
    [string]$PythonExe = "",
    [switch]$KeepTemp
)

$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($ProjectDir)) {
    $scriptDir = $PSScriptRoot
    if ([string]::IsNullOrWhiteSpace($scriptDir)) {
        $scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
    }
    $ProjectDir = (Resolve-Path (Join-Path $scriptDir "..")).Path
}
Set-Location $ProjectDir

if ([string]::IsNullOrWhiteSpace($BackupDir)) {
    $BackupDir = Join-Path $ProjectDir "backup"
}

if ([string]::IsNullOrWhiteSpace($BackupFile)) {
    $latestBackup = Get-ChildItem -Path $BackupDir -File -Filter "db-*.sqlite3" |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1
    if ($null -eq $latestBackup) {
        throw "backup file not found in $BackupDir"
    }
    $BackupFile = $latestBackup.FullName
}

if ([string]::IsNullOrWhiteSpace($PythonExe)) {
    $rootVenvPython = Join-Path $ProjectDir ".venv\Scripts\python.exe"
    if (Test-Path -LiteralPath $rootVenvPython) {
        $PythonExe = $rootVenvPython
    }
    else {
        $PythonExe = "python"
    }
}

$backupPath = Resolve-Path $BackupFile
$backupItem = Get-Item $backupPath
if ($backupItem.Length -le 0) {
    throw "backup file is empty: $backupPath"
}

$shaPath = "$($backupItem.FullName).sha256"
if (Test-Path -LiteralPath $shaPath) {
    $expectedLine = Get-Content -Path $shaPath -TotalCount 1
    $expectedHash = ($expectedLine -split "\s+")[0].ToLowerInvariant()
    $actualHash = (Get-FileHash -Algorithm SHA256 -Path $backupItem.FullName).Hash.ToLowerInvariant()
    if ($expectedHash -ne $actualHash) {
        throw "backup sha256 mismatch: $shaPath"
    }
    Write-Host "backup sha256: ok"
}
else {
    Write-Host "backup sha256: skipped (sidecar not found)"
}

$integrityScript = @'
import os
import sqlite3

path = os.environ["BUDGETBOOK_RESTORE_TARGET"]
with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as conn:
    result = conn.execute("PRAGMA integrity_check").fetchone()[0]
    if result != "ok":
        raise SystemExit(f"backup integrity_check failed: {result}")
print("backup integrity_check: ok")
'@

$env:BUDGETBOOK_RESTORE_TARGET = $backupItem.FullName
try {
    $integrityEncoded = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($integrityScript))
    & $PythonExe -c "import base64; exec(base64.b64decode('$integrityEncoded').decode('utf-8'))"
    if ($LASTEXITCODE -ne 0) {
        throw "backup integrity_check failed"
    }
}
finally {
    Remove-Item Env:BUDGETBOOK_RESTORE_TARGET -ErrorAction SilentlyContinue
}

$tempDir = Join-Path ([System.IO.Path]::GetTempPath()) ("budgetbook-restore-drill-" + [System.Guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $tempDir -Force | Out-Null
$drillDb = Join-Path $tempDir "restore-drill.sqlite3"
Copy-Item -LiteralPath $backupItem.FullName -Destination $drillDb -Force

Write-Host "restore drill temp db: $drillDb"

$previousDbPath = $env:DJANGO_DB_PATH
$managePy = Join-Path $ProjectDir "budgetbook\manage.py"
try {
    $env:DJANGO_DB_PATH = $drillDb

    & $PythonExe $managePy check
    if ($LASTEXITCODE -ne 0) { throw "Django check failed in restore drill" }

    & $PythonExe $managePy migrate --noinput
    if ($LASTEXITCODE -ne 0) { throw "migration failed in restore drill" }

    & $PythonExe $managePy migrate --check
    if ($LASTEXITCODE -ne 0) { throw "migration check failed in restore drill" }

    & $PythonExe $managePy check_accounting_integrity
    if ($LASTEXITCODE -ne 0) { throw "accounting integrity failed in restore drill" }

    Write-Host "restore drill: ok"
    Write-Host "No Docker services were stopped and data/db.sqlite3 was not changed."
}
finally {
    if ($null -eq $previousDbPath) {
        Remove-Item Env:DJANGO_DB_PATH -ErrorAction SilentlyContinue
    }
    else {
        $env:DJANGO_DB_PATH = $previousDbPath
    }

    if (-not $KeepTemp) {
        Remove-Item -LiteralPath $tempDir -Recurse -Force -ErrorAction SilentlyContinue
    }
    else {
        Write-Host "restore drill temp dir kept: $tempDir"
    }
}
