param(
    [string]$Version = "0.1.0",
    [string]$ISCCPath = "",
    [switch]$Sign,
    [string]$WindowsCertSha1 = $env:WINDOWS_SIGN_CERT_SHA1,
    [string]$SignToolPath = ""
)

$ErrorActionPreference = "Stop"

function Invoke-Checked {
    param(
        [string]$FilePath,
        [string[]]$ArgumentList
    )
    & $FilePath @ArgumentList
    if ($LASTEXITCODE -ne 0) {
        throw "$FilePath failed with exit code $LASTEXITCODE"
    }
}

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$Python = Join-Path $RepoRoot ".venv-mirror\Scripts\python.exe"
if (-not (Test-Path $Python)) { $Python = "python" }

function Find-ISCC {
    param([string]$ExplicitPath)
    if ($ExplicitPath -and (Test-Path $ExplicitPath)) { return (Resolve-Path $ExplicitPath).Path }
    $cmd = Get-Command ISCC.exe -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    $candidates = @(
        "C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
        "C:\Program Files\Inno Setup 6\ISCC.exe",
        (Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 6\ISCC.exe")
    )
    foreach ($candidate in $candidates) {
        if (Test-Path $candidate) { return $candidate }
    }
    throw "Inno Setup Compiler (ISCC.exe) was not found. Install Inno Setup 6 or pass -ISCCPath."
}

$ISCC = Find-ISCC -ExplicitPath $ISCCPath

& (Join-Path $PSScriptRoot "build-windows.ps1")

$DistDir = Join-Path $RepoRoot "budgetbook\dist\BudgetBook"
Invoke-Checked $Python @((Join-Path $RepoRoot "packaging\audit_release.py"), $DistDir)

$ReleaseDir = Join-Path $RepoRoot "release\windows"
New-Item -ItemType Directory -Force -Path $ReleaseDir | Out-Null
$IssPath = Join-Path $PSScriptRoot "BudgetBook.iss"
Invoke-Checked $ISCC @("/DMyAppVersion=$Version", "/DSourceDir=$DistDir", "/DOutputDir=$ReleaseDir", $IssPath)

$Setup = Join-Path $ReleaseDir "BudgetBook-Setup-$Version-Windows-x64.exe"
if (-not (Test-Path $Setup)) { throw "Installer was not created: $Setup" }
if ($Sign) {
    $signArgs = @("-ArtifactPath", $Setup, "-CertSha1", $WindowsCertSha1)
    if ($SignToolPath) { $signArgs += @("-SignToolPath", $SignToolPath) }
    & (Join-Path $PSScriptRoot "sign-windows.ps1") @signArgs
}
Invoke-Checked $Python @((Join-Path $RepoRoot "packaging\audit_release.py"), $ReleaseDir)
Get-FileHash -Algorithm SHA256 -LiteralPath $Setup | ForEach-Object {
    "$($_.Hash)  $(Split-Path -Leaf $_.Path)" | Set-Content -Encoding ASCII -LiteralPath "$Setup.sha256"
}
$Manifest = Join-Path $ReleaseDir "BudgetBook-$Version-Windows-x64.manifest.json"
$SignatureFlag = if ($Sign) { "--signed" } else { "--unsigned" }
Invoke-Checked $Python @((Join-Path $RepoRoot "packaging\release_manifest.py"), "--platform", "windows", "--version", $Version, $SignatureFlag, "--root", $ReleaseDir, "--output", $Manifest, $Setup)
Write-Host "Installer created: $Setup"
Write-Host "Manifest created: $Manifest"
