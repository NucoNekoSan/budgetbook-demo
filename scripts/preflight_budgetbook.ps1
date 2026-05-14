param(
    [string]$ProjectDir = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path,
    [string]$ServiceName = "budgetbook",
    [string]$BaseUrl = "http://127.0.0.1:8010"
)

$ErrorActionPreference = "Stop"
Set-Location $ProjectDir

function Invoke-Step {
    param(
        [string]$Title,
        [scriptblock]$Action
    )
    Write-Host ""
    Write-Host $Title
    & $Action
}

function Assert-NativeSuccess {
    param([string]$Message)
    if ($LASTEXITCODE -ne 0) {
        throw $Message
    }
}

Invoke-Step "[1/8] docker compose config" {
    docker compose config --quiet
}

Invoke-Step "[2/8] docker compose ps" {
    docker compose ps
}

Invoke-Step "[3/8] Django system checks" {
    docker compose exec -T $ServiceName python manage.py check
    docker compose exec -T $ServiceName python manage.py makemigrations --check
    docker compose exec -T $ServiceName python manage.py migrate --check
}

Invoke-Step "[4/8] SQLite integrity and runtime PRAGMAs" {
    $pragmaScript = @'
from django.db import connection

cursor = connection.cursor()
values = {
    "integrity_check": cursor.execute("PRAGMA integrity_check").fetchone()[0],
    "journal_mode": cursor.execute("PRAGMA journal_mode").fetchone()[0],
    "foreign_keys": cursor.execute("PRAGMA foreign_keys").fetchone()[0],
    "busy_timeout": cursor.execute("PRAGMA busy_timeout").fetchone()[0],
}

for key, value in values.items():
    print(f"{key}={value}")

if values["integrity_check"] != "ok":
    raise SystemExit("SQLite integrity_check failed")
if str(values["journal_mode"]).lower() != "wal":
    raise SystemExit("SQLite journal_mode is not WAL")
if int(values["foreign_keys"]) != 1:
    raise SystemExit("SQLite foreign_keys is not enabled")
if int(values["busy_timeout"]) < 1000:
    raise SystemExit("SQLite busy_timeout is too low")
'@
    $pragmaEncoded = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($pragmaScript))
    $pragmaCommand = "import base64; exec(base64.b64decode('$pragmaEncoded').decode('utf-8'))"
    docker compose exec -T $ServiceName python manage.py shell -c $pragmaCommand
    Assert-NativeSuccess "SQLite PRAGMA check failed"
}

Invoke-Step "[5/8] accounting integrity" {
    docker compose exec -T $ServiceName python manage.py check_accounting_integrity
}

Invoke-Step "[6/8] application data smoke" {
    docker compose exec -T $ServiceName python manage.py shell -c "from django.contrib.auth import get_user_model; from ledger.models import Account, Category, Transaction, Transfer; print('users=', get_user_model().objects.count()); print('accounts=', Account.objects.count()); print('categories=', Category.objects.count()); print('transactions=', Transaction.objects.count()); print('transfers=', Transfer.objects.count())"
}

Invoke-Step "[7/8] HTTP smoke and CSRF login POST" {
    $loginBodyFile = New-TemporaryFile
    $postBodyFile = New-TemporaryFile
    $staticBodyFile = New-TemporaryFile
    $cookieFile = New-TemporaryFile
    try {
        $loginStatus = & curl.exe -sS -L -c $cookieFile.FullName -o $loginBodyFile.FullName -w "%{http_code}" "$BaseUrl/accounts/login/"
        Assert-NativeSuccess "login page request failed"
        Write-Host "/accounts/login/=$loginStatus"
        if ($loginStatus -ne "200") {
            throw "login page did not return 200"
        }

        $staticStatus = & curl.exe -sS -I -o $staticBodyFile.FullName -w "%{http_code}" "$BaseUrl/static/css/style.css"
        Assert-NativeSuccess "static css request failed"
        Write-Host "/static/css/style.css=$staticStatus"
        if ($staticStatus -ne "200") {
            throw "static css did not return 200"
        }

        $loginContent = Get-Content -Raw $loginBodyFile.FullName
        $match = [regex]::Match($loginContent, 'name="csrfmiddlewaretoken" value="([^"]+)"')
        if (-not $match.Success) {
            throw "csrf token not found in login page"
        }

        $postStatus = & curl.exe -sS -L `
            -b $cookieFile.FullName `
            -c $cookieFile.FullName `
            -o $postBodyFile.FullName `
            -w "%{http_code}" `
            -H "Origin: $BaseUrl" `
            -H "Referer: $BaseUrl/accounts/login/" `
            --data-urlencode "username=__preflight_invalid_user__" `
            --data-urlencode "password=__preflight_invalid_password__" `
            --data-urlencode "csrfmiddlewaretoken=$($match.Groups[1].Value)" `
            "$BaseUrl/accounts/login/"
        Assert-NativeSuccess "login POST request failed"
        Write-Host "login_post_with_origin=$postStatus"
        $postContent = Get-Content -Raw $postBodyFile.FullName
        $hasCsrfFailure = ($postContent -like "*CSRF verification failed*") -or ($postContent -like "*CSRF検証に失敗*")
        if ($postStatus -eq "403" -or $hasCsrfFailure) {
            throw "login POST failed CSRF validation"
        }
    }
    finally {
        Remove-Item -LiteralPath $loginBodyFile.FullName, $postBodyFile.FullName, $staticBodyFile.FullName, $cookieFile.FullName -Force -ErrorAction SilentlyContinue
    }
}

Invoke-Step "[8/8] recent error log scan" {
    $logs = docker compose logs --since=10m $ServiceName
    $matches = $logs | Select-String -Pattern 'ERROR|Traceback| 500 | 502 '
    if ($matches) {
        $matches | ForEach-Object { Write-Error $_.Line }
        throw "recent application errors were found"
    }
}

Write-Host ""
Write-Host "preflight: ok"
