param(
    [Parameter(Mandatory = $true)]
    [string]$ArtifactPath,
    [string]$CertSha1 = $env:WINDOWS_SIGN_CERT_SHA1,
    [string]$TimestampUrl = "http://timestamp.digicert.com",
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

function Find-SignTool {
    param([string]$ExplicitPath)
    if ($ExplicitPath -and (Test-Path $ExplicitPath)) { return (Resolve-Path $ExplicitPath).Path }
    $cmd = Get-Command signtool.exe -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    $kitsRoot = Join-Path ${env:ProgramFiles(x86)} "Windows Kits\10\bin"
    if (Test-Path $kitsRoot) {
        $candidate = Get-ChildItem -Path $kitsRoot -Recurse -Filter signtool.exe -ErrorAction SilentlyContinue |
            Where-Object { $_.FullName -match '\\x64\\signtool\.exe$' } |
            Sort-Object FullName -Descending |
            Select-Object -First 1
        if ($candidate) { return $candidate.FullName }
    }
    throw "signtool.exe was not found. Install the Windows SDK or pass -SignToolPath."
}

if (-not (Test-Path $ArtifactPath)) { throw "Artifact not found: $ArtifactPath" }
if (-not $CertSha1) { throw "Set WINDOWS_SIGN_CERT_SHA1 or pass -CertSha1. Do not store PFX files or private keys in Git." }

$SignTool = Find-SignTool -ExplicitPath $SignToolPath
$ResolvedArtifact = (Resolve-Path $ArtifactPath).Path
Invoke-Checked $SignTool @("sign", "/fd", "SHA256", "/tr", $TimestampUrl, "/td", "SHA256", "/sha1", $CertSha1, $ResolvedArtifact)
Invoke-Checked $SignTool @("verify", "/pa", "/v", $ResolvedArtifact)
Write-Host "Signed and verified: $ResolvedArtifact"
