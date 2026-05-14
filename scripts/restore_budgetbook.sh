#!/usr/bin/env bash
set -euo pipefail

# BudgetBook production SQLite restore.
# Usage:
#   scripts/restore_budgetbook.sh backup/db-YYYY-MM-DD-HHMMSS.sqlite3
#   scripts/restore_budgetbook.sh --verify-only backup/db-YYYY-MM-DD-HHMMSS.sqlite3

VERIFY_ONLY=0
if [[ "${1:-}" == "--verify-only" ]]; then
  VERIFY_ONLY=1
  shift
fi

if [[ $# -ne 1 ]]; then
  echo "usage: $0 [--verify-only] <backup-sqlite3-file>" >&2
  exit 2
fi

PROJECT_DIR="${PROJECT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
SERVICE_NAME="${SERVICE_NAME:-budgetbook}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
BACKUP_FILE="$1"

cd "${PROJECT_DIR}"

if [[ ! -f "${BACKUP_FILE}" ]]; then
  echo "backup file not found: ${BACKUP_FILE}" >&2
  exit 1
fi
if [[ ! -s "${BACKUP_FILE}" ]]; then
  echo "backup file is empty: ${BACKUP_FILE}" >&2
  exit 1
fi

if [[ -f "${BACKUP_FILE}.sha256" ]]; then
  (cd "$(dirname "${BACKUP_FILE}")" && sha256sum -c "$(basename "${BACKUP_FILE}.sha256")")
fi

"${PYTHON_BIN}" - "${BACKUP_FILE}" <<'PY'
import sqlite3
import sys

path = sys.argv[1]
with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as conn:
    result = conn.execute("PRAGMA integrity_check").fetchone()[0]
    if result != "ok":
        raise SystemExit(f"backup integrity_check failed: {result}")
print("backup integrity_check: ok")
PY

if [[ "${VERIFY_ONLY}" -eq 1 ]]; then
  echo "restore verify-only: ok"
  echo "No Docker services were stopped and data/db.sqlite3 was not changed."
  exit 0
fi

echo "This will stop Docker services and replace ./data/db.sqlite3 with: ${BACKUP_FILE}"
read -r -p "Type RESTORE to continue: " answer
if [[ "${answer}" != "RESTORE" ]]; then
  echo "restore cancelled"
  exit 1
fi

docker compose stop proxy "${SERVICE_NAME}"

mkdir -p data
if [[ -f data/db.sqlite3 ]]; then
  cp data/db.sqlite3 "backup/pre-restore-$(date +%F-%H%M%S).sqlite3"
fi

cp "${BACKUP_FILE}" data/db.sqlite3
chown 1000:1000 data/db.sqlite3 2>/dev/null || true

docker compose up -d "${SERVICE_NAME}" proxy

echo "post-restore Django checks"
docker compose exec -T "${SERVICE_NAME}" python manage.py check
docker compose exec -T "${SERVICE_NAME}" python manage.py migrate --check
docker compose exec -T "${SERVICE_NAME}" python manage.py check_accounting_integrity

echo "restore completed and verified"
