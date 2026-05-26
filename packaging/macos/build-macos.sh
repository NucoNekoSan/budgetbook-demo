#!/usr/bin/env bash
set -euo pipefail

VERSION="${1:-0.1.0}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
APP_ROOT="${REPO_ROOT}/budgetbook"
LAUNCHER="${REPO_ROOT}/desktop/launcher.py"
PYTHON_BIN="${PYTHON_BIN:-python3}"
APP_NAME="BudgetBook"
DIST_DIR="${APP_ROOT}/dist"
APP_BUNDLE="${DIST_DIR}/${APP_NAME}.app"
RELEASE_DIR="${REPO_ROOT}/release/macos"
DMG_PATH="${RELEASE_DIR}/${APP_NAME}-${VERSION}-macOS.dmg"

cd "${APP_ROOT}"
"${PYTHON_BIN}" -m pip install -r requirements.txt
"${PYTHON_BIN}" -m pip install 'pyinstaller>=6,<7'
"${PYTHON_BIN}" -m PyInstaller --noconfirm --clean --name "${APP_NAME}" --onedir --windowed \
  --paths "${APP_ROOT}" \
  --hidden-import dotenv \
  --hidden-import axes \
  --hidden-import axes.apps \
  --hidden-import axes.backends \
  --hidden-import axes.middleware \
  --hidden-import django_htmx \
  --hidden-import django_htmx.middleware \
  --hidden-import whitenoise.middleware \
  --hidden-import whitenoise.storage \
  --collect-submodules axes \
  --collect-submodules django_htmx \
  --collect-submodules whitenoise \
  --add-data "static:static" \
  --add-data "templates:templates" \
  --add-data "ledger:ledger" \
  --add-data "config:config" \
  "${LAUNCHER}"

cd "${REPO_ROOT}"
"${PYTHON_BIN}" packaging/audit_release.py "${APP_BUNDLE}"

rm -rf "${RELEASE_DIR}"
mkdir -p "${RELEASE_DIR}"
rm -f "${DMG_PATH}"
hdiutil create -volname "${APP_NAME}" -srcfolder "${APP_BUNDLE}" -ov -format UDZO "${DMG_PATH}"
shasum -a 256 "${DMG_PATH}" | tee "${DMG_PATH}.sha256"
"${PYTHON_BIN}" packaging/release_manifest.py --platform macos --version "${VERSION}" --unsigned --root "${RELEASE_DIR}" --output "${RELEASE_DIR}/${APP_NAME}-${VERSION}-macOS.manifest.json" "${DMG_PATH}"

echo "macOS unsigned DMG created: ${DMG_PATH}"
echo "For public distribution, run packaging/macos/sign-and-notarize.sh before release."
