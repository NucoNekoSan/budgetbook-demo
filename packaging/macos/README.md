# macOS App/DMG Build

macOS artifacts must be built on macOS. Cross-building from Windows is not supported for the release path.

## Prerequisites

- macOS with Xcode command line tools
- Python 3.13 or compatible runtime
- PyInstaller installed by the script
- Apple Developer Program membership for public distribution
- Developer ID Application certificate in the login keychain
- `notarytool` keychain profile

Create the notary profile on the Mac once:

```bash
xcrun notarytool store-credentials "BudgetBookNotary" \
  --apple-id "APPLE_ID_EMAIL" \
  --team-id "TEAM_ID" \
  --password "APP_SPECIFIC_PASSWORD"
```

Do not commit Apple IDs, team IDs, passwords, certificates, or exported private keys.

## Unsigned local build

```bash
bash packaging/macos/build-macos.sh 0.1.0
```

Output:

- `release/macos/BudgetBook-0.1.0-macOS.dmg`
- `release/macos/BudgetBook-0.1.0-macOS.dmg.sha256`
- `release/macos/BudgetBook-0.1.0-macOS.manifest.json`

Unsigned builds are for local validation only. Do not publish them for general users.

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
- Public distribution requires Developer ID signing, Hardened Runtime, notarization, and stapling.
