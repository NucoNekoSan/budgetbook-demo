@echo off
REM ============================================================================
REM BudgetBook - Windows quick start (self-host)
REM ============================================================================
REM 初回起動時に Docker イメージをビルド、migration を適用、demo データを seed し、
REM ブラウザを開きます。2 回目以降は既存 DB を保持したまま起動します。
REM ============================================================================
setlocal enabledelayedexpansion
chcp 65001 >nul

cd /d "%~dp0"

REM -- Docker が動いているか確認
docker info >nul 2>&1
if errorlevel 1 (
    echo.
    echo [ERROR] Docker Desktop が起動していません。
    echo Docker Desktop を起動してから、もう一度このスクリプトを実行してください。
    echo.
    pause
    exit /b 1
)

REM -- .env がなければ .env.example からコピー
if not exist "budgetbook\.env" (
    if exist "budgetbook\.env.example" (
        copy "budgetbook\.env.example" "budgetbook\.env" >nul
        echo.
        echo [INFO] budgetbook\.env を新規作成しました。
        echo        必要に応じて SECRET_KEY をランダム文字列に変更してください。
        echo.
    )
)

REM -- イメージビルド
echo [1/4] Docker イメージをビルドします...
docker compose build budgetbook
if errorlevel 1 goto build_error

REM -- migration 適用
echo.
echo [2/4] Database migration を適用します...
docker compose run --rm budgetbook python manage.py migrate
if errorlevel 1 goto migrate_error

REM -- 初回起動なら demo データを seed
if not exist "data\db.sqlite3" goto seed
docker compose run --rm budgetbook python manage.py shell -c "from ledger.models import Transaction; print(Transaction.objects.count())" 2>nul | findstr "^0$" >nul
if errorlevel 1 goto skip_seed

:seed
echo.
echo [3/4] Demo データを投入します（初回のみ）...
docker compose run --rm budgetbook python manage.py seed_demo_data --reset
goto launch

:skip_seed
echo.
echo [3/4] 既存 DB を保持します（seed_demo_data はスキップ）。

:launch
echo.
echo [4/4] サーバーを起動します...
docker compose up -d
if errorlevel 1 goto up_error

timeout /t 3 /nobreak >nul
echo.
echo ============================================================
echo BudgetBook が起動しました。
echo   URL: http://127.0.0.1:8010/
echo   ログイン: demo / demo
echo   管理画面: admin / admin
echo ============================================================
echo.

start http://127.0.0.1:8010/

endlocal
exit /b 0

:build_error
echo [ERROR] Docker build に失敗しました。
pause
exit /b 1

:migrate_error
echo [ERROR] Migration に失敗しました。
pause
exit /b 1

:up_error
echo [ERROR] コンテナの起動に失敗しました。
pause
exit /b 1
