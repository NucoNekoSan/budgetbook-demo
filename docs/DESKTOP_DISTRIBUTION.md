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
## Windows installer

Windows installer packaging is defined under `packaging/windows/`.

- `build-windows.ps1` creates the PyInstaller one-dir app.
- `BudgetBook.iss` defines the Inno Setup installer.
- `build-installer.ps1` builds the app, audits artifacts, compiles the installer, and writes a SHA256 file.

The installer intentionally keeps `%APPDATA%\BudgetBook` on uninstall to avoid accidental loss of household finance data. Windows public releases should be Authenticode-signed; unsigned installers are validation artifacts only.
## macOS app and DMG

macOS packaging lives under `packaging/macos/`.

- `build-macos.sh` creates an unsigned local `.app` and `.dmg` on macOS.
- `sign-and-notarize.sh` applies Developer ID signing, Hardened Runtime, notarization, stapling, and SHA256 generation.
- Unsigned DMGs are local validation artifacts only and must not be published for general users.

Apple's direct distribution path requires Developer ID signing and notarization for a user-trustworthy install experience. The project must not store Apple account credentials, app-specific passwords, certificates, or private keys in Git.
