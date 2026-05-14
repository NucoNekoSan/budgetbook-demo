param(
    [Parameter(Mandatory = $true)]
    [string]$BackupFile,
    [string]$ProjectDir = "",
    [string]$ServiceName = "budgetbook",
    [switch]$VerifyOnly
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

$backupPath = Resolve-Path $BackupFile
$backupItem = Get-Item $backupPath
if ($backupItem.Length -le 0) {
    throw "backup file is empty: $backupPath"
}

$shaPath = "$($backupItem.FullName).sha256"
if (Test-Path $shaPath) {
    $expectedLine = Get-Content -Path $shaPath -TotalCount 1
    $expectedHash = ($expectedLine -split "\s+")[0].ToLowerInvariant()
    $actualHash = (Get-FileHash -Algorithm SHA256 -Path $backupItem.FullName).Hash.ToLowerInvariant()
    if ($expectedHash -ne $actualHash) {
        throw "backup sha256 mismatch: $shaPath"
    }
    Write-Host "backup sha256: ok"
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
    python -c "import base64; exec(base64.b64decode('$integrityEncoded').decode('utf-8'))"
    if ($LASTEXITCODE -ne 0) {
        throw "backup integrity_check failed"
    }
}
finally {
    Remove-Item Env:BUDGETBOOK_RESTORE_TARGET -ErrorAction SilentlyContinue
}

if ($VerifyOnly) {
    Write-Host "restore verify-only: ok"
    Write-Host "No Docker services were stopped and data/db.sqlite3 was not changed."
    exit 0
}

Write-Host "This will stop Docker services and replace ./data/db.sqlite3 with: $($backupItem.FullName)"
$answer = Read-Host "Type RESTORE to continue"
if ($answer -ne "RESTORE") {
    Write-Host "restore cancelled"
    exit 1
}

docker compose stop proxy $ServiceName
if ($LASTEXITCODE -ne 0) {
    throw "failed to stop Docker services"
}

New-Item -ItemType Directory -Path "data" -Force | Out-Null
New-Item -ItemType Directory -Path "backup" -Force | Out-Null

if (Test-Path "data/db.sqlite3") {
    $timestamp = Get-Date -Format "yyyy-MM-dd-HHmmss"
    Copy-Item -LiteralPath "data/db.sqlite3" -Destination "backup/pre-restore-$timestamp.sqlite3"
}

Copy-Item -LiteralPath $backupItem.FullName -Destination "data/db.sqlite3" -Force

docker compose up -d $ServiceName proxy
if ($LASTEXITCODE -ne 0) {
    throw "failed to start Docker services"
}

Write-Host "post-restore Django checks"
docker compose exec -T $ServiceName python manage.py check
if ($LASTEXITCODE -ne 0) { throw "Django check failed after restore" }
docker compose exec -T $ServiceName python manage.py migrate --check
if ($LASTEXITCODE -ne 0) { throw "migration check failed after restore" }
docker compose exec -T $ServiceName python manage.py check_accounting_integrity
if ($LASTEXITCODE -ne 0) { throw "accounting integrity check failed after restore" }

Write-Host "restore completed and verified"
