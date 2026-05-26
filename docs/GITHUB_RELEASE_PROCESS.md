# GitHub Release Process

This project must publish desktop installers as release assets, not as Git-tracked files.

## Release ownership

- Keep source code, packaging scripts, and documentation in Git.
- Keep generated installers, DMGs, `.app` bundles, `dist/`, `build/`, and `release/` out of Git.
- Keep `.env`, databases, backups, Apple credentials, signing certificates, and private keys out of Git and GitHub Actions secrets unless a CI signing pipeline is explicitly designed.

## Pre-release checklist

Run the release preflight before creating a GitHub release:

```powershell
powershell -ExecutionPolicy Bypass -File packaging\prepare-release.ps1 -Version 0.1.0
```

For a final tagged release, require a reviewed clean tree:

```powershell
powershell -ExecutionPolicy Bypass -File packaging\prepare-release.ps1 -Version 0.1.0 -RequireClean
```

On macOS/Linux validation machines:

```bash
bash packaging/prepare-release.sh --version 0.1.0
```

## Distribution tracks

BudgetBook has two release tracks:

- Trusted release: Windows installer is Authenticode-signed; macOS DMG is Developer ID signed, notarized, and stapled.
- Unsigned self-risk release: artifacts may be published for free distribution only with explicit unsigned warnings, SHA256 verification instructions, and no advice to disable OS security globally. Follow `docs/UNSIGNED_SELF_RISK_DISTRIBUTION.md`.

Keep unsigned self-risk releases as GitHub prereleases unless the maintainer intentionally promotes that build to the latest public release.

## Windows release

Build on Windows for local validation:

```powershell
powershell -ExecutionPolicy Bypass -File packaging\windows\build-installer.ps1 -Version 0.1.0
```

For a trusted public release, sign the installer before upload:

```powershell
$env:WINDOWS_SIGN_CERT_SHA1="CERTIFICATE_THUMBPRINT"
powershell -ExecutionPolicy Bypass -File packaging\windows\build-installer.ps1 -Version 0.1.0 -Sign
```

Upload these files from `release/windows/` to a draft GitHub Release:

- `BudgetBook-Setup-0.1.0-Windows-x64.exe` (signed for trusted releases, unsigned only for self-risk releases)
- `BudgetBook-Setup-0.1.0-Windows-x64.exe.sha256`
- `BudgetBook-0.1.0-Windows-x64.manifest.json`

## macOS release

Build, sign, notarize, and staple on macOS:

```bash
export MACOS_DEVELOPER_ID_APPLICATION="Developer ID Application: Your Name or Company (TEAMID)"
export MACOS_NOTARY_PROFILE="BudgetBookNotary"
bash packaging/macos/build-macos.sh 0.1.0
bash packaging/macos/sign-and-notarize.sh 0.1.0
```

Upload these files from `release/macos/` to a draft GitHub Release:

- `BudgetBook-0.1.0-macOS-signed.dmg`
- `BudgetBook-0.1.0-macOS-signed.dmg.sha256`
- `BudgetBook-0.1.0-macOS-signed.manifest.json`

For an unsigned self-risk macOS release, build with `build-macos.sh` only and upload `BudgetBook-0.1.0-macOS.dmg`, its `.sha256`, and its manifest. The release notes must state that the DMG is unsigned and unnotarized.

## Release notes template

```markdown
## BudgetBook 0.1.0

### Installers
- Windows: `BudgetBook-Setup-0.1.0-Windows-x64.exe` (signed, or unsigned self-risk if explicitly labeled)
- macOS: `BudgetBook-0.1.0-macOS-signed.dmg` (signed/notarized, or unsigned self-risk if explicitly labeled)

### Security
- Ships with no users, household data, `.env`, or database.
- Creates runtime data under the user's app data folder on first launch.
- Local server binds to `127.0.0.1` only.
- SHA256 checksums and JSON manifests are attached.

### Unsigned self-risk warning
- This section is required when any attached artifact is unsigned or unnotarized.
- Windows may show Unknown Publisher, SmartScreen, or antivirus warnings.
- macOS may block the app because it is not Developer ID signed and notarized.
- Verify SHA256 before opening the installer or DMG.
- Do not install if the warning is unexpected or unacceptable.
```


## Local sensitive patterns

Do not commit real private values as detector patterns. If you need exact local leak detection, create `.sensitive-patterns.local` on your machine only:

```text
# One regular expression per line. Do not commit this file.
private-domain.example
real-personal-email@example.invalid
```

`packaging/audit_release.py`, `packaging/audit_source_sensitive.py`, `packaging/check_release_ready.py`, and `scripts/audit_docs_sensitive.sh` load this file automatically when it exists.

## GitHub security settings

Enable these repository settings before public distribution:

- Dependabot alerts and security updates.
- Code scanning alerts from CodeQL.
- Branch protection requiring CI and release-safety checks before merging to `master`.
- Draft releases until intended Windows and/or macOS artifacts are attached, checksums are verified, and the release track is clearly labeled.

## Artifact verification

Users or maintainers can verify an artifact against its checksum:

```powershell
Get-FileHash .\BudgetBook-Setup-0.1.0-Windows-x64.exe -Algorithm SHA256
```

```bash
shasum -a 256 BudgetBook-0.1.0-macOS-signed.dmg
```
