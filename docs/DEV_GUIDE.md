# DEV_GUIDE.md - BudgetBook Development Guide

## 1. セットアップ

```powershell
cd budgetbook
python -m venv .venv
.venv\Scripts\activate
python -m pip install -U pip
python -m pip install -r requirements.txt
Copy-Item .env.example .env
python manage.py migrate
python manage.py seed_budget_data
python manage.py createsuperuser
python manage.py runserver
```

ブラウザ:

- `http://127.0.0.1:8000/`
- `http://127.0.0.1:8000/annual/`
- `http://127.0.0.1:8000/expense-breakdown/`
- `http://127.0.0.1:8000/settings/`

## 2. 日常開発コマンド

```powershell
cd budgetbook
python manage.py check
python manage.py test ledger
python manage.py makemigrations --check
```

Migration 作成時:

```powershell
python manage.py makemigrations ledger
python manage.py migrate
```

実運用 DB に migration を当てる前は `docs/RELEASE_CHECKLIST.md` を確認する。

## 3. 作業フロー

1. `CLAUDE.md`, `README.md`, 関連 `docs/` を読む。
2. 大きな変更は対象 `docs/specs/*.md` を読む、または必要に応じて更新する。
3. セキュリティ影響、DB 影響、既存データ影響、テスト計画、ロールバック方針を出す。
4. 必要最小限のファイルを変更する。
5. テストを追加・更新する。
6. `python manage.py test ledger` を実行する。
7. migration がある場合は `makemigrations --check` または migration 内容を報告する。
8. 変更ファイル、テスト結果、残課題を報告する。

## 4. Git / ワークツリー

- 未コミット変更はユーザー作業として扱う。
- 勝手に `git reset --hard` しない。
- `budgetbook/ledger/tests/test_auth.py` は現在削除状態のため、明示指示がない限り触らない。
- `.env`, `db.sqlite3`, `backup/`, `staticfiles/`, Cloudflare token は Git 管理しない。

## 5. UI 変更

- 既存の静かな業務ツール系デザインを維持する。
- 大きな装飾やランディングページ的な表現は不要。
- スマホで文字が重ならないことを確認する。
- Chart.js のデータは `json_script` で渡す。
- HTMX 更新後にグラフが再初期化されることを確認する。

## 6. DB 変更

- destructive migration は原則禁止。
- 既存データ変換は事前承認を取る。
- migration 前にバックアップ手順を明記する。
- SQLite DB は実データなので慎重に扱う。

## 7. 公開運用

Docker + Cloudflare Tunnel は導入済み。詳細は以下を参照する。

- `docs/DEPLOYMENT.md`
- `docs/PRODUCTION_RUNBOOK.md`
- `docs/SECURITY.md`
- `docs/RELEASE_CHECKLIST.md`
- `docs/specs/v1.5.0_docker_cloudflare.md`

本番反映前の代表チェック:

```powershell
cd budgetbook
python manage.py test ledger
python manage.py makemigrations --check
```

Ubuntu / Docker 環境ではリポジトリルートで以下も実行する。

```bash
scripts/audit_dependencies.sh
scripts/security_static_scan.sh
scripts/preflight_budgetbook.sh
```

GitHub Actions は無料枠節約のため、通常 push / PR では Django tests のみ、release tag / 週次 schedule / 手動実行で production checks を実行する。
