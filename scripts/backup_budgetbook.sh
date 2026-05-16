#!/usr/bin/env bash
set -euo pipefail

# BudgetBook production SQLite backup.
# Run this on the Ubuntu host from the repository root, or set PROJECT_DIR.

PROJECT_DIR="${PROJECT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
SERVICE_NAME="${SERVICE_NAME:-budgetbook}"
BACKUP_DIR="${BACKUP_DIR:-${PROJECT_DIR}/backup}"
RETENTION_DAYS="${RETENTION_DAYS:-30}"
TIMESTAMP="$(date +%F-%H%M%S)"
BACKUP_NAME="db-${TIMESTAMP}.sqlite3"
CONTAINER_BACKUP="/app/backup/${BACKUP_NAME}"
ACCOUNTING_REPORT="${BACKUP_DIR}/${BACKUP_NAME}.accounting_integrity.txt"

cd "${PROJECT_DIR}"
mkdir -p "${BACKUP_DIR}"
chmod 700 "${BACKUP_DIR}"

docker compose exec -T "${SERVICE_NAME}" python - "${CONTAINER_BACKUP}" <<'PY'
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
PY

# --- 世代管理 -----------------------------------------------------------------
# RETENTION_POLICY=flat  : 既存通り N 日より古いものを削除（デフォルト）
# RETENTION_POLICY=gfs   : Grandfather-Father-Son
#   日次: 直近 ${GFS_DAILY:-7} 日
#   週次: 各 ISO 週で最新 1 件を ${GFS_WEEKLY:-4} 週保持
#   月次: 各月で最新 1 件を ${GFS_MONTHLY:-12} ヶ月保持
RETENTION_POLICY="${RETENTION_POLICY:-flat}"
GFS_DAILY="${GFS_DAILY:-7}"
GFS_WEEKLY="${GFS_WEEKLY:-4}"
GFS_MONTHLY="${GFS_MONTHLY:-12}"

if [[ "${RETENTION_POLICY}" == "gfs" ]]; then
  python3 - "${BACKUP_DIR}" "${GFS_DAILY}" "${GFS_WEEKLY}" "${GFS_MONTHLY}" <<'PY'
import os
import re
import sys
from datetime import date, timedelta
from pathlib import Path

backup_dir = Path(sys.argv[1])
keep_daily = int(sys.argv[2])
keep_weekly = int(sys.argv[3])
keep_monthly = int(sys.argv[4])

pattern = re.compile(r'^db-(\d{4})-(\d{2})-(\d{2})-\d{6}\.sqlite3$')
items = []
for child in backup_dir.iterdir():
    if not child.is_file():
        continue
    m = pattern.match(child.name)
    if not m:
        continue
    y, mo, d = (int(x) for x in m.groups())
    items.append((date(y, mo, d), child))

if not items:
    sys.exit(0)

items.sort(key=lambda x: x[1].name, reverse=True)

today = date.today()
cutoff_daily = today - timedelta(days=keep_daily)

keep = set()

# Daily
for d, path in items:
    if d > cutoff_daily:
        keep.add(path.name)

# Weekly: ISO 年・週でグループ化、各週 1 件
weekly_groups = {}
for d, path in items:
    iso_year, iso_week, _ = d.isocalendar()
    key = (iso_year, iso_week)
    weekly_groups.setdefault(key, []).append(path)
weekly_keys = sorted(weekly_groups.keys(), reverse=True)[:keep_weekly]
for key in weekly_keys:
    keep.add(sorted(weekly_groups[key], key=lambda p: p.name, reverse=True)[0].name)

# Monthly
monthly_groups = {}
for d, path in items:
    key = (d.year, d.month)
    monthly_groups.setdefault(key, []).append(path)
monthly_keys = sorted(monthly_groups.keys(), reverse=True)[:keep_monthly]
for key in monthly_keys:
    keep.add(sorted(monthly_groups[key], key=lambda p: p.name, reverse=True)[0].name)

removed = 0
for _d, path in items:
    if path.name in keep:
        continue
    base = path.with_suffix('')  # strip .sqlite3
    for ext in ('.sqlite3', '.sqlite3.sha256', '.sqlite3.accounting_integrity.txt'):
        target = backup_dir / f"{base.name}{ext}"
        if target.exists():
            target.unlink()
            removed += 1
            print(f"removed: {target}")
print(f"GFS retention applied: kept={len(keep)} removed_files={removed}")
PY
else
  find "${BACKUP_DIR}" -type f -name 'db-*.sqlite3' -mtime "+${RETENTION_DAYS}" -print -delete
  find "${BACKUP_DIR}" -type f -name 'db-*.sqlite3.sha256' -mtime "+${RETENTION_DAYS}" -print -delete
  find "${BACKUP_DIR}" -type f -name 'db-*.sqlite3.accounting_integrity.txt' -mtime "+${RETENTION_DAYS}" -print -delete
fi

set +e
docker compose exec -T "${SERVICE_NAME}" python manage.py check_accounting_integrity > "${ACCOUNTING_REPORT}" 2>&1
ACCOUNTING_STATUS=$?
set -e

cat "${ACCOUNTING_REPORT}"
ls -lh "${BACKUP_DIR}/${BACKUP_NAME}" "${BACKUP_DIR}/${BACKUP_NAME}.sha256" "${ACCOUNTING_REPORT}"

if [ "${ACCOUNTING_STATUS}" -ne 0 ]; then
  echo "accounting integrity check failed; backup was created but requires investigation: ${ACCOUNTING_REPORT}" >&2
  exit "${ACCOUNTING_STATUS}"
fi
