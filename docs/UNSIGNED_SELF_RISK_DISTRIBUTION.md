# Unsigned Self-Risk Distribution

BudgetBook may be distributed for free as unsigned desktop artifacts when paid code-signing is not available. This is a lower-trust distribution track and must be presented honestly to users.

## Policy

- Use this track only for free public releases where the maintainer accepts SmartScreen, antivirus, and Gatekeeper friction.
- Do not describe unsigned artifacts as trusted, verified by the OS vendor, or equivalent to signed/notarized builds.
- Do not provide commands or instructions that disable Windows SmartScreen, antivirus, macOS Gatekeeper, SIP, quarantine, or other operating-system protections globally.
- Attach SHA256 files and manifest JSON files to every GitHub Release.
- Tell users to stop installation if any warning is unexpected, the checksum does not match, or the download source is not the official GitHub Release.

## Release naming

Use explicit naming in the GitHub Release title and notes:

```text
BudgetBook 0.1.0 - Unsigned Self-Risk Release
```

Recommended asset labels:

- `BudgetBook-Setup-0.1.0-Windows-x64.exe` - unsigned Windows installer.
- `BudgetBook-0.1.0-macOS.dmg` - unsigned and unnotarized macOS DMG.

## User-facing warning template

```markdown
This is an unsigned self-risk release.

- Windows may show "Unknown publisher" or SmartScreen warnings.
- macOS may block the app because it is not signed with Developer ID and is not notarized.
- Install only if you understand this risk and downloaded the file from this official GitHub Release.
- Verify the attached SHA256 checksum before opening the installer or DMG.
- If the warning is unacceptable, do not install this release.
```

## Verification commands

Windows:

```powershell
Get-FileHash .\BudgetBook-Setup-0.1.0-Windows-x64.exe -Algorithm SHA256
Get-Content .\BudgetBook-Setup-0.1.0-Windows-x64.exe.sha256
```

macOS:

```bash
shasum -a 256 BudgetBook-0.1.0-macOS.dmg
cat BudgetBook-0.1.0-macOS.dmg.sha256
```

The computed hash must match the attached `.sha256` file exactly.

## macOS opening guidance

Do not instruct users to run `spctl --master-disable`, remove quarantine attributes with `xattr`, disable SIP, or change security policy broadly.

If a user chooses to proceed after verifying the source and checksum, point them to Apple's official "Open Anyway" flow in System Settings > Privacy & Security. Users who do not understand the warning should not proceed.

Reference: <https://support.apple.com/guide/mac-help/open-an-app-by-overriding-security-settings-mh40617/mac>

## Windows opening guidance

Do not instruct users to disable SmartScreen, reputation-based protection, antivirus, or browser download protection globally.

If Windows blocks or warns on the file, users should verify the GitHub source and SHA256 checksum first. Users who do not understand the warning should not proceed.

Reference: <https://support.microsoft.com/windows/app-browser-control-in-the-windows-security-app-8f68fb65-ebb4-3cfb-4bd7-ef0f376f3dc3>

User install guide: [WINDOWS_UNSIGNED_INSTALL.md](WINDOWS_UNSIGNED_INSTALL.md)
