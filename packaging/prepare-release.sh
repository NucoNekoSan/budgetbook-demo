#!/usr/bin/env bash
set -euo pipefail

VERSION="0.1.0"
BUILD_MACOS=0
REQUIRE_CLEAN=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --version) VERSION="$2"; shift 2 ;;
    --build-macos) BUILD_MACOS=1; shift ;;
    --require-clean) REQUIRE_CLEAN=1; shift ;;
    -h|--help)
      echo "Usage: bash packaging/prepare-release.sh [--version 0.1.0] [--build-macos] [--require-clean]"
      exit 0
      ;;
    *) echo "Unknown arg: $1" >&2; exit 2 ;;
  esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"

cd "${REPO_ROOT}"
"${PYTHON_BIN}" -m py_compile \
  desktop/launcher.py \
  packaging/audit_release.py \
  packaging/audit_source_sensitive.py \
  packaging/check_release_ready.py \
  packaging/release_manifest.py \
  packaging/sensitive_patterns.py

"${PYTHON_BIN}" packaging/audit_source_sensitive.py --verbose

READY_ARGS=(packaging/check_release_ready.py)
if [[ "${REQUIRE_CLEAN}" -eq 1 ]]; then
  READY_ARGS+=(--require-clean)
fi
"${PYTHON_BIN}" "${READY_ARGS[@]}"

(cd budgetbook && "${PYTHON_BIN}" manage.py test ledger.tests.test_first_run_setup ledger.tests.test_default_master_seed ledger.tests.test_pwa)

if [[ "${BUILD_MACOS}" -eq 1 ]]; then
  bash packaging/macos/build-macos.sh "${VERSION}"
fi

echo "Release preflight completed for version ${VERSION}."
if [[ "${BUILD_MACOS}" -eq 1 ]]; then
  echo "For public release, sign and notarize with packaging/macos/sign-and-notarize.sh before uploading."
fi
