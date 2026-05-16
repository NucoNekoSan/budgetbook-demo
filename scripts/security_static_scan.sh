#!/usr/bin/env bash
set -euo pipefail

# Run Python static security analysis with Bandit.
# Uses Docker when available so the project venv and production container stay untouched.

PROJECT_DIR="${PROJECT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
SCAN_RUNNER="${SCAN_RUNNER:-auto}"
SCAN_IMAGE="${SCAN_IMAGE:-python:3.12-slim}"
SCAN_FORMAT="${SCAN_FORMAT:-txt}"

EXCLUDE_PATHS=(
  "${PROJECT_DIR}/budgetbook/ledger/tests"
  "${PROJECT_DIR}/budgetbook/.venv"
  "${PROJECT_DIR}/budgetbook/staticfiles"
)

join_by_comma() {
  local IFS=","
  echo "$*"
}

if [[ "${SCAN_RUNNER}" == "auto" ]] && command -v docker >/dev/null 2>&1; then
  SCAN_RUNNER="docker"
fi

if [[ "${SCAN_RUNNER}" == "docker" ]]; then
  echo "Running Bandit with Docker image: ${SCAN_IMAGE}"
  docker run --rm \
    -v "${PROJECT_DIR}:/src:ro" \
    -e SCAN_FORMAT="${SCAN_FORMAT}" \
    "${SCAN_IMAGE}" \
    sh -lc 'python -m pip install --upgrade pip --root-user-action=ignore >/dev/null && python -m pip install --root-user-action=ignore "bandit[toml]>=1.8,<2" >/dev/null && bandit -r /src/budgetbook -x /src/budgetbook/ledger/tests,/src/budgetbook/.venv,/src/budgetbook/staticfiles -ll -f "${SCAN_FORMAT}"'
  exit 0
fi

TMP_DIR="$(mktemp -d)"
cleanup() {
  rm -rf "${TMP_DIR}"
}
trap cleanup EXIT

if ! "${PYTHON_BIN}" -m venv "${TMP_DIR}/venv"; then
  echo "failed to create Python venv. Install python3-venv or run with SCAN_RUNNER=docker." >&2
  exit 1
fi

# shellcheck disable=SC1091
source "${TMP_DIR}/venv/bin/activate"

python -m pip install --upgrade pip >/dev/null
python -m pip install "bandit[toml]>=1.8,<2" >/dev/null

bandit -r "${PROJECT_DIR}/budgetbook" -x "$(join_by_comma "${EXCLUDE_PATHS[@]}")" -ll -f "${SCAN_FORMAT}"
