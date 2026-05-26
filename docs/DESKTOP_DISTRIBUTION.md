# Desktop Distribution Plan

BudgetBook desktop builds must ship as an empty local app. Real data, demo data, and users are created only on the user's computer.

## Non-negotiable security rules

- Do not bundle `.env`, `db.sqlite3`, backups, certificates, or signing keys.
- Store runtime data under the user's application data directory.
- Bind the local web server to `127.0.0.1` only.
- Generate `SECRET_KEY` on first launch and store it outside the install directory.
- Run migrations on first launch before opening the browser.
- Require first-run setup when no users exist.

## Runtime data paths

- Windows: `%APPDATA%\BudgetBook\`
- macOS: `~/Library/Application Support/BudgetBook/`

## Build safety

Run `python packaging/audit_release.py <artifact-root>` before publishing any desktop artifact. Run `python packaging/check_release_ready.py` before creating a GitHub release, and upload each installer/DMG with its `.sha256` and manifest JSON.

## Distribution tracks

BudgetBook supports two desktop distribution tracks:

- Trusted release: signed Windows installer and signed/notarized macOS DMG. This is the recommended path for general users.
- Unsigned self-risk release: free public distribution is allowed only when the GitHub Release, asset names, checksums, and release notes clearly state that artifacts are unsigned, unnotarized where applicable, and used at the user's own risk.

Unsigned self-risk releases must never ask users to disable operating-system security globally. If Windows SmartScreen, antivirus, or macOS Gatekeeper warnings are unacceptable to a user, the correct guidance is to stop installation and wait for a trusted signed release.

## Windows installer

Windows installer packaging is defined under `packaging/windows/`.

- `build-windows.ps1` creates the PyInstaller one-dir app.
- `BudgetBook.iss` defines the Inno Setup installer.
- `build-installer.ps1` builds the app, audits artifacts, compiles the installer, and writes a SHA256 file.

The installer intentionally keeps `%APPDATA%\BudgetBook` on uninstall to avoid accidental loss of household finance data. Windows public releases should be Authenticode-signed when possible. Unsigned public artifacts are permitted only under the unsigned self-risk release rules above.
## macOS app and DMG

macOS packaging lives under `packaging/macos/`.

- `build-macos.sh` creates an unsigned local `.app` and `.dmg` on macOS.
- `sign-and-notarize.sh` applies Developer ID signing, Hardened Runtime, notarization, stapling, and SHA256 generation.
- Unsigned DMGs may be published only as unsigned self-risk releases with explicit warnings and checksums.

Apple's direct distribution path requires Developer ID signing and notarization for a user-trustworthy install experience. The project must not store Apple account credentials, app-specific passwords, certificates, or private keys in Git.
