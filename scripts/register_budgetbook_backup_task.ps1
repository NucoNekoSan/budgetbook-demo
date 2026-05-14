param(
    [string]$ProjectDir = "",
    [string]$TaskName = "BudgetBookDailyBackup",
    [string]$At = "03:30",
    [int]$RetentionDays = 30,
    [switch]$Force,
    [switch]$RunNow
)

$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($ProjectDir)) {
    $scriptDir = $PSScriptRoot
    if ([string]::IsNullOrWhiteSpace($scriptDir)) {
        $scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
    }
    $ProjectDir = (Resolve-Path (Join-Path $scriptDir "..")).Path
}

$backupScript = Join-Path $ProjectDir "scripts\backup_budgetbook.ps1"
if (-not (Test-Path -LiteralPath $backupScript)) {
    throw "backup script not found: $backupScript"
}

if ($At -notmatch '^\d{1,2}:\d{2}$') {
    throw "At must be HH:mm, for example 03:30"
}

$existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($existing -and -not $Force) {
    throw "scheduled task already exists: $TaskName. Use -Force to replace it."
}

if ($existing -and $Force) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
}

$startTime = [datetime]::ParseExact($At, "H:mm", [Globalization.CultureInfo]::InvariantCulture)
$argument = @(
    "-NoProfile",
    "-ExecutionPolicy", "Bypass",
    "-File", "`"$backupScript`"",
    "-ProjectDir", "`"$ProjectDir`"",
    "-RetentionDays", $RetentionDays
) -join " "

$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $argument -WorkingDirectory $ProjectDir
$trigger = New-ScheduledTaskTrigger -Daily -At $startTime
$settings = New-ScheduledTaskSettingsSet `
    -MultipleInstances IgnoreNew `
    -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Hours 2)
$principal = New-ScheduledTaskPrincipal `
    -UserId "$env:USERDOMAIN\$env:USERNAME" `
    -LogonType Interactive `
    -RunLevel Limited

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Principal $principal `
    -Description "Run BudgetBook SQLite backup with integrity and accounting checks." `
    | Out-Null

Write-Host "scheduled task registered: $TaskName"
Get-ScheduledTask -TaskName $TaskName | Select-Object TaskName, State, TaskPath

if ($RunNow) {
    Start-ScheduledTask -TaskName $TaskName
    Write-Host "scheduled task started: $TaskName"
}
