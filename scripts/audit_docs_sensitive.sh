#!/usr/bin/env bash
# audit_docs_sensitive.sh — compatibility wrapper for source sensitive-data audit.
# 実値パターンは public repo に書かない。必要な場合は Git 管理外の
# .sensitive-patterns.local または BUDGETBOOK_SENSITIVE_PATTERNS で追加する。

set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
if [[ -z "${PYTHON_BIN:-}" ]]; then
  if command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="python3"
  else
    PYTHON_BIN="python"
  fi
fi
ARGS=()
for arg in "$@"; do
  case "$arg" in
    --staged) ARGS+=(--staged) ;;
    --verbose) ARGS+=(--verbose) ;;
    -h|--help)
      echo "Usage: bash scripts/audit_docs_sensitive.sh [--staged] [--verbose]"
      exit 0
      ;;
    *) echo "Unknown arg: $arg" >&2; exit 2 ;;
  esac
done

"${PYTHON_BIN}" "${REPO_ROOT}/packaging/audit_source_sensitive.py" "${ARGS[@]}"
