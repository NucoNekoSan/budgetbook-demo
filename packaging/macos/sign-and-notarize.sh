#!/usr/bin/env bash
set -euo pipefail

VERSION="${1:-0.1.0}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
APP_NAME="BudgetBook"
APP_BUNDLE="${REPO_ROOT}/budgetbook/dist/${APP_NAME}.app"
RELEASE_DIR="${REPO_ROOT}/release/macos"
DMG_PATH="${RELEASE_DIR}/${APP_NAME}-${VERSION}-macOS.dmg"
SIGNED_DMG_PATH="${RELEASE_DIR}/${APP_NAME}-${VERSION}-macOS-signed.dmg"
ENTITLEMENTS="${SCRIPT_DIR}/entitlements.plist"

: "${MACOS_DEVELOPER_ID_APPLICATION:?Set MACOS_DEVELOPER_ID_APPLICATION, e.g. Developer ID Application: Example Corp (TEAMID)}"
: "${MACOS_NOTARY_PROFILE:?Set MACOS_NOTARY_PROFILE, created with xcrun notarytool store-credentials}"

if [[ ! -d "${APP_BUNDLE}" ]]; then
  echo "App bundle not found: ${APP_BUNDLE}. Run build-macos.sh first." >&2
  exit 2
fi

codesign --force --deep --timestamp --options runtime \
  --entitlements "${ENTITLEMENTS}" \
  --sign "${MACOS_DEVELOPER_ID_APPLICATION}" \
  "${APP_BUNDLE}"

codesign --verify --deep --strict --verbose=2 "${APP_BUNDLE}"
spctl --assess --type execute --verbose=2 "${APP_BUNDLE}" || true

rm -f "${DMG_PATH}" "${SIGNED_DMG_PATH}" "${SIGNED_DMG_PATH}.sha256"
hdiutil create -volname "${APP_NAME}" -srcfolder "${APP_BUNDLE}" -ov -format UDZO "${SIGNED_DMG_PATH}"

codesign --force --timestamp --sign "${MACOS_DEVELOPER_ID_APPLICATION}" "${SIGNED_DMG_PATH}"
codesign --verify --verbose=2 "${SIGNED_DMG_PATH}"

xcrun notarytool submit "${SIGNED_DMG_PATH}" --keychain-profile "${MACOS_NOTARY_PROFILE}" --wait
xcrun stapler staple "${SIGNED_DMG_PATH}"
xcrun stapler validate "${SIGNED_DMG_PATH}"
spctl --assess --type open --context context:primary-signature --verbose=2 "${SIGNED_DMG_PATH}"

shasum -a 256 "${SIGNED_DMG_PATH}" | tee "${SIGNED_DMG_PATH}.sha256"
"${PYTHON_BIN:-python3}" "${REPO_ROOT}/packaging/release_manifest.py" --platform macos --version "${VERSION}" --signed --root "${RELEASE_DIR}" --output "${RELEASE_DIR}/${APP_NAME}-${VERSION}-macOS-signed.manifest.json" "${SIGNED_DMG_PATH}"
echo "macOS signed and notarized DMG created: ${SIGNED_DMG_PATH}"
