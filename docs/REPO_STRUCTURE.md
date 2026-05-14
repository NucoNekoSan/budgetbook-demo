# REPO_STRUCTURE.md - BudgetBook Repository Structure

新しいファイルを追加する前に、この責務分担を確認する。

## 1. 全体構造

```text
budgetbook/
|- CLAUDE.md
|- README.md
|- .gitignore
|- .github/
|  |- workflows/ci.yml
|  `- dependabot.yml
|- .claude/
|- Dockerfile
|- docker-compose.yml
|- .dockerignore
|- infra/
|  |- nginx/
|  `- systemd/
|- scripts/
|  |- backup_budgetbook.sh
|  |- restore_budgetbook.sh
|  |- preflight_budgetbook.sh
|  |- audit_dependencies.sh
|  `- security_static_scan.sh
|- docs/
|  |- DEVELOPMENT_WALKTHROUGH.md
|  |- FILE_REFERENCE.md
|  |- OPERATIONS_GUIDE.md
|  |- REQUIREMENTS.md
|  |- TECH_SPEC.md
|  |- SECURITY.md
|  |- RELEASE_CHECKLIST.md
|  |- DEV_GUIDE.md
|  |- REPO_STRUCTURE.md
|  |- UBIQUITOUS.md
|  `- specs/
`- budgetbook/
   |- manage.py
   |- requirements.txt
   |- .env.example
   |- config/
   |- ledger/
   |- templates/
   |- static/
   |- staticfiles/  # Git 管理外
   |- backup/       # Git 管理外
   `- db.sqlite3    # Git 管理外
|- data/         # Docker DB bind mount, Git 管理外
|- backup/       # Docker backup bind mount, Git 管理外
`- staticfiles/  # Docker static bind mount, Git 管理外
```

## 2. 責務

| 場所 | 責務 | Git 管理 |
|---|---|---|
| `CLAUDE.md` | ClaudeCode 作業規律 | Yes |
| `docs/` | 設計・運用・仕様 | Yes |
| `docs/specs/` | バージョン別仕様 | Yes |
| `.github/workflows/` | CI | Yes |
| `.github/dependabot.yml` | 依存更新監視 | Yes |
| `Dockerfile`, `docker-compose.yml`, `.dockerignore` | Docker 運用 | Yes |
| `infra/nginx/` | Docker 内 Nginx reverse proxy 設定 | Yes |
| `infra/systemd/` | Ubuntu host 用 systemd timer/service | Yes |
| `scripts/` | バックアップ、復元、preflight、監査スクリプト | Yes |
| `budgetbook/config/` | Django プロジェクト設定 | Yes |
| `budgetbook/ledger/` | 家計簿アプリ本体 | Yes |
| `budgetbook/templates/` | HTML テンプレート | Yes |
| `budgetbook/static/` | 開発用 CSS / JS / vendor | Yes |
| `budgetbook/staticfiles/` | collectstatic 出力 | No |
| `budgetbook/backup/` | DB バックアップ | No |
| `budgetbook/db.sqlite3` | 実 DB | No |
| `data/` | Docker 運用 DB bind mount | No |
| `backup/` | Docker 運用バックアップ | No |
| `staticfiles/` | Docker 運用 collectstatic 出力 | No |
| `.claude/skills/` | ClaudeCode 補助 skill | Yes, 導入済み前提 |

## 3. 追加ルール

- 仕様変更は `docs/specs/` に追加・更新する。
- 実運用手順は `docs/OPERATIONS_GUIDE.md` または `docs/DEV_GUIDE.md` に反映する。
- セキュリティ方針は `docs/SECURITY.md` を正とする。
- 公開前確認は `docs/RELEASE_CHECKLIST.md` を正とする。
- Docker 運用はリポジトリルートの `Dockerfile`, `docker-compose.yml`, `.dockerignore`, `infra/`, `scripts/` を正とする。
- 本番 DB は `data/db.sqlite3` に置き、Git 管理しない。
- 通常 push / PR の CI は軽量、release tag / 週次 schedule / 手動実行で production checks を走らせる。
