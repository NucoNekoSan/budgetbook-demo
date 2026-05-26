# macOS App/DMG Build

macOS artifacts must be built on macOS. Cross-building from Windows is not supported for the release path.

## Prerequisites

- macOS with Xcode command line tools
- Python 3.13 or compatible runtime
- PyInstaller installed by the script
- Apple Developer Program membership for trusted public distribution
- Developer ID Application certificate in the login keychain for trusted public distribution
- `notarytool` keychain profile for trusted public distribution

Create the notary profile on the Mac once:

```bash
xcrun notarytool store-credentials "BudgetBookNotary" \
  --apple-id "APPLE_ID_EMAIL" \
  --team-id "TEAM_ID" \
  --password "APP_SPECIFIC_PASSWORD"
```

Do not commit Apple IDs, team IDs, passwords, certificates, or exported private keys.

## Unsigned build

```bash
bash packaging/macos/build-macos.sh 0.1.0
```

Output:

- `release/macos/BudgetBook-0.1.0-macOS.dmg`
- `release/macos/BudgetBook-0.1.0-macOS.dmg.sha256`
- `release/macos/BudgetBook-0.1.0-macOS.manifest.json`

Unsigned builds may be used for local validation. They may also be published only as free unsigned self-risk releases when the GitHub Release clearly states that the DMG is unsigned and unnotarized, includes SHA256 verification, and does not instruct users to disable macOS security protections globally.

## Signed and notarized build

```bash
export MACOS_DEVELOPER_ID_APPLICATION="Developer ID Application: Your Name or Company (TEAMID)"
export MACOS_NOTARY_PROFILE="BudgetBookNotary"
bash packaging/macos/build-macos.sh 0.1.0
bash packaging/macos/sign-and-notarize.sh 0.1.0
```

Output:

- `release/macos/BudgetBook-0.1.0-macOS-signed.dmg`
- `release/macos/BudgetBook-0.1.0-macOS-signed.dmg.sha256`
- `release/macos/BudgetBook-0.1.0-macOS-signed.manifest.json`

## Security notes

- Runtime `.env` and `db.sqlite3` are created under `~/Library/Application Support/BudgetBook/` by the launcher.
- The release audit scans the `.app` bundle before DMG creation.
- Trusted public distribution requires Developer ID signing, Hardened Runtime, notarization, and stapling.
- Unsigned self-risk releases must follow `docs/UNSIGNED_SELF_RISK_DISTRIBUTION.md`.
