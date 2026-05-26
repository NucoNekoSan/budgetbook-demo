# Windows Installer Build

BudgetBook uses PyInstaller for the app folder and Inno Setup 6 for the user-facing installer.

## Prerequisites

- Windows x64
- Python environment already used by this repository
- Inno Setup 6 (`ISCC.exe`) installed locally

## Unsigned build

```powershell
powershell -ExecutionPolicy Bypass -File packaging\windows\build-installer.ps1 -Version 0.1.0
```

Unsigned installers may be used for local validation. They may also be published only as free unsigned self-risk releases when the GitHub Release clearly labels the artifact as unsigned, includes SHA256 verification, and does not instruct users to disable Windows security protections.

If `ISCC.exe` is not on `PATH`:

```powershell
powershell -ExecutionPolicy Bypass -File packaging\windows\build-installer.ps1 -Version 0.1.0 -ISCCPath "C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
```

## Signed trusted build

Install the Windows SDK, import an Authenticode code-signing certificate into the current user's certificate store, then set its SHA-1 thumbprint outside Git:

```powershell
$env:WINDOWS_SIGN_CERT_SHA1="CERTIFICATE_THUMBPRINT"
powershell -ExecutionPolicy Bypass -File packaging\windows\build-installer.ps1 -Version 0.1.0 -Sign
```

The script signs and verifies the installer with `signtool.exe`. Do not commit PFX files, private keys, certificate passwords, or private certificate identifiers.

## Output

- `release/windows/BudgetBook-Setup-<version>-Windows-x64.exe`
- `release/windows/BudgetBook-Setup-<version>-Windows-x64.exe.sha256`
- `release/windows/BudgetBook-<version>-Windows-x64.manifest.json`

## Security behavior

- Installer does not bundle `.env`, `db.sqlite3`, backups, or signing keys.
- User data remains under `%APPDATA%\BudgetBook` when uninstalling.
- Release artifacts are scanned by `packaging/audit_release.py` before publishing.
- Unsigned self-risk releases must follow `docs/UNSIGNED_SELF_RISK_DISTRIBUTION.md`.
