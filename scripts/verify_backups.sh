#!/usr/bin/env bash
set -euo pipefail

# Re-verify existing SQLite backups: SHA256 + sqlite3 integrity_check.
# 静的シェルなので Python も Docker も不要（sqlite3 と sha256sum のみ要求）。
# 用途: スケジュール実行で物理破損 / ビット腐敗を早期検出する。

PROJECT_DIR="${PROJECT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
BACKUP_DIR="${BACKUP_DIR:-${PROJECT_DIR}/backup}"

if [[ ! -d "${BACKUP_DIR}" ]]; then
  echo "backup directory not found: ${BACKUP_DIR}" >&2
  exit 1
fi

if ! command -v sqlite3 >/dev/null 2>&1; then
  echo "sqlite3 binary not found" >&2
  exit 1
fi
if ! command -v sha256sum >/dev/null 2>&1; then
  echo "sha256sum not found" >&2
  exit 1
fi

shopt -s nullglob
backups=("${BACKUP_DIR}"/db-*.sqlite3)
if [[ ${#backups[@]} -eq 0 ]]; then
  echo "no backups to verify in ${BACKUP_DIR}"
  exit 0
fi

failed=0
for backup in "${backups[@]}"; do
  sha_file="${backup}.sha256"
  echo "verify: ${backup}"
  if [[ ! -f "${sha_file}" ]]; then
    echo "  MISSING sha256: ${sha_file}" >&2
    failed=$((failed + 1))
    continue
  fi
  expected="$(awk '{print $1}' "${sha_file}")"
  actual="$(sha256sum "${backup}" | awk '{print $1}')"
  if [[ "${expected}" != "${actual}" ]]; then
    echo "  SHA256 MISMATCH (expected=${expected}, actual=${actual})" >&2
    failed=$((failed + 1))
    continue
  fi
  integrity="$(sqlite3 "file:${backup}?mode=ro" 'PRAGMA integrity_check' 2>&1 || true)"
  if [[ "${integrity}" != "ok" ]]; then
    echo "  INTEGRITY FAIL: ${integrity}" >&2
    failed=$((failed + 1))
    continue
  fi
  echo "  ok"
done

if [[ ${failed} -gt 0 ]]; then
  echo "${failed} backup(s) failed verification" >&2
  exit 2
fi

echo "all backups ok (${#backups[@]} files)"