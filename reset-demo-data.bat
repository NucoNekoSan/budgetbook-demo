@echo off
REM BudgetBook - Demo データを初期状態にリセット（既存データは消えます）
chcp 65001 >nul
cd /d "%~dp0"

echo.
echo ============================================================
echo [WARNING] 既存のデータをすべて削除して demo データを再投入します。
echo           入力済みの家計データは戻りません。
echo ============================================================
echo.
set /p ANS="続行しますか？ (y/N): "
if /i not "%ANS%"=="y" goto cancel

REM Backup before reset
if exist "data\db.sqlite3" (
    if not exist "backup" mkdir backup
    set TS=%date:~0,4%%date:~5,2%%date:~8,2%-%time:~0,2%%time:~3,2%%time:~6,2%
    set TS=!TS: =0!
    copy "data\db.sqlite3" "backup\db-pre-reset-!TS!.sqlite3" >nul
    echo バックアップを backup\db-pre-reset-!TS!.sqlite3 に作成しました。
)

docker compose run --rm budgetbook python manage.py migrate
docker compose run --rm budgetbook python manage.py seed_demo_data --reset

echo.
echo Demo データをリセットしました。
echo ブラウザで http://127.0.0.1:8010/ を再読み込みしてください。
pause
goto end

:cancel
echo キャンセルしました。

:end