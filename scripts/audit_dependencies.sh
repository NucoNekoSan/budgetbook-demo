#!/usr/bin/env bash
set -euo pipefail

# Audit Python dependencies for known vulnerabilities.
# Runs in a temporary virtual environment and does not modify the project venv.

PROJECT_DIR="${PROJECT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
REQUIREMENTS_FILE="${REQUIREMENTS_FILE:-${PROJECT_DIR}/budgetbook/requirements.txt}"
AUDIT_FORMAT="${AUDIT_FORMAT:-columns}"
AUDIT_RUNNER="${AUDIT_RUNNER:-auto}"
AUDIT_IMAGE="${AUDIT_IMAGE:-python:3.12-slim}"

if [[ ! -f "${REQUIREMENTS_FILE}" ]]; then
  echo "requirements file not found: ${REQUIREMENTS_FILE}" >&2
  exit 1
fi

if [[ "${AUDIT_RUNNER}" == "auto" ]] && command -v docker >/dev/null 2>&1; then
  AUDIT_RUNNER="docker"
fi

if [[ "${AUDIT_RUNNER}" == "docker" ]]; then
  echo "Auditing with Docker image: ${AUDIT_IMAGE}"
  docker run --rm \
    -v "${PROJECT_DIR}:/src:ro" \
    -e AUDIT_FORMAT="${AUDIT_FORMAT}" \
    "${AUDIT_IMAGE}" \
    sh -lc 'python -m pip install --upgrade pip --root-user-action=ignore >/dev/null && python -m pip install --root-user-action=ignore "pip-audit>=2.8,<3" >/dev/null && pip-audit --requirement /src/budgetbook/requirements.txt --strict --format "${AUDIT_FORMAT}"'
  exit 0
fi

TMP_DIR="$(mktemp -d)"
cleanup() {
  rm -rf "${TMP_DIR}"
}
trap cleanup EXIT

if ! "${PYTHON_BIN}" -m venv "${TMP_DIR}/venv"; then
  echo "failed to create Python venv. Install python3-venv or run with AUDIT_RUNNER=docker." >&2
  exit 1
fi
# shellcheck disable=SC1091
source "${TMP_DIR}/venv/bin/activate"

python -m pip install --upgrade pip >/dev/null
python -m pip install "pip-audit>=2.8,<3" >/dev/null

echo "Auditing: ${REQUIREMENTS_FILE}"
pip-audit --requirement "${REQUIREMENTS_FILE}" --strict --format "${AUDIT_FORMAT}"
