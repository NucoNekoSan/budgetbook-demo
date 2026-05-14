@echo off
REM BudgetBook - データバックアップ
chcp 65001 >nul
cd /d "%~dp0"

if not exist "backup" mkdir backup

if exist "scripts\backup_budgetbook.ps1" (
    powershell -ExecutionPolicy Bypass -File "scripts\backup_budgetbook.ps1"
) else (
    set TS=%date:~0,4%%date:~5,2%%date:~8,2%-%time:~0,2%%time:~3,2%%time:~6,2%
    set TS=!TS: =0!
    if exist "data\db.sqlite3" (
        copy "data\db.sqlite3" "backup\db-!TS!.sqlite3"
        echo backup\db-!TS!.sqlite3 を作成しました。
    ) else (
        echo data\db.sqlite3 が見つかりません。
    )
)
pause