@echo off
REM BudgetBook - Stop Docker containers
chcp 65001 >nul
cd /d "%~dp0"

echo BudgetBook のコンテナを停止します...
docker compose down

echo.
echo 停止しました。データは data\db.sqlite3 に保存されています。
echo 再起動は start-windows.bat を実行してください。
echo.
pause
