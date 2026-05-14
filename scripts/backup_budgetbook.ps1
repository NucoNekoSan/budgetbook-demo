param(
    [string]$ProjectDir = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path,
    [string]$ServiceName = "budgetbook",
    [string]$BackupDir = "",
    [int]$RetentionDays = 30
)

$ErrorActionPreference = "Stop"
Set-Location $ProjectDir

if ([string]::IsNullOrWhiteSpace($BackupDir)) {
    $BackupDir = Join-Path $ProjectDir "backup"
}

New-Item -ItemType Directory -Path $BackupDir -Force | Out-Null

$timestamp = Get-Date -Format "yyyy-MM-dd-HHmmss"
$backupName = "db-$timestamp.sqlite3"
$containerBackup = "/app/backup/$backupName"
$hostBackup = Join-Path $BackupDir $backupName
$hostSha = "$hostBackup.sha256"
$accountingReport = "$hostBackup.accounting_integrity.txt"

$backupScript = @'
import hashlib
import os
import sqlite3
import sys
from pathlib import Path

src = Path("/app/data/db.sqlite3")
dst = Path(sys.argv[1])
tmp = dst.with_suffix(dst.suffix + ".tmp")

if not src.exists():
    raise SystemExit(f"source database does not exist: {src}")
if src.stat().st_size <= 0:
    raise SystemExit(f"source database is empty: {src}")

dst.parent.mkdir(parents=True, exist_ok=True)
if tmp.exists():
    tmp.unlink()

with sqlite3.connect(f"file:{src}?mode=ro", uri=True) as source:
    with sqlite3.connect(tmp) as target:
        target.execute("PRAGMA journal_mode=DELETE")
        source.backup(target)
        target.commit()

with sqlite3.connect(tmp) as check_conn:
    result = check_conn.execute("PRAGMA integrity_check").fetchone()[0]
    if result != "ok":
        tmp.unlink(missing_ok=True)
        raise SystemExit(f"backup integrity_check failed: {result}")

digest = hashlib.sha256()
with tmp.open("rb") as fh:
    for chunk in iter(lambda: fh.read(1024 * 1024), b""):
        digest.update(chunk)

os.replace(tmp, dst)
tmp.with_name(tmp.name + "-wal").unlink(missing_ok=True)
tmp.with_name(tmp.name + "-shm").unlink(missing_ok=True)

sha_path = Path(str(dst) + ".sha256")
sha_path.write_text(f"{digest.hexdigest()}  {dst.name}\n", encoding="utf-8")
print(dst)
print(sha_path)
'@

$backupScriptEncoded = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($backupScript))
$backupCommand = "import base64, sys; exec(base64.b64decode('$backupScriptEncoded').decode('utf-8'))"
docker compose exec -T $ServiceName python -c $backupCommand $containerBackup
if ($LASTEXITCODE -ne 0) {
    throw "database backup failed"
}

$cutoff = (Get-Date).AddDays(-$RetentionDays)
Get-ChildItem -Path $BackupDir -File -Filter "db-*.sqlite3" | Where-Object { $_.LastWriteTime -lt $cutoff } | Remove-Item -Force
Get-ChildItem -Path $BackupDir -File -Filter "db-*.sqlite3.sha256" | Where-Object { $_.LastWriteTime -lt $cutoff } | Remove-Item -Force
Get-ChildItem -Path $BackupDir -File -Filter "db-*.sqlite3.accounting_integrity.txt" | Where-Object { $_.LastWriteTime -lt $cutoff } | Remove-Item -Force

docker compose exec -T $ServiceName python manage.py check_accounting_integrity *> $accountingReport
$accountingStatus = $LASTEXITCODE

Get-Content -Path $accountingReport
Get-Item -Path $hostBackup, $hostSha, $accountingReport | Select-Object FullName, Length, LastWriteTime

if ($accountingStatus -ne 0) {
    throw "accounting integrity check failed; backup was created but requires investigation: $accountingReport"
}
