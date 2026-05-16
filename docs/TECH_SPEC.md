# TECH_SPEC.md - BudgetBook Technical Specification

このファイルは BudgetBook の技術仕様を定義する。

## 1. 技術スタック

| 技術 | 用途 | 現状 |
|---|---|---|
| Python | アプリケーション言語 | 3.10 以上想定 |
| Django | Web フレームワーク | 5.2 系 |
| SQLite | データベース | 実運用中 |
| HTMX | 部分更新 UI | 導入済み |
| Chart.js | グラフ描画 | ローカル vendor 配置 |
| WhiteNoise | 静的ファイル配信 | 導入済み |
| django-axes | ログイン試行制限 | 導入済み |
| python-dotenv | `.env` 読み込み | 導入済み |
| Docker | 自宅サーバー運用 | 導入済み |
| Cloudflare Tunnel / Access | 外出先アクセス保護 | 導入済み |

## 2. ディレクトリ

```text
budgetbook/
|- CLAUDE.md
|- README.md
|- docs/
|- budgetbook/
|  |- manage.py
|  |- config/
|  |- ledger/
|  |- templates/
|  |- static/
|  |- staticfiles/  # Git 管理外
|  |- backup/       # Git 管理外
|  `- db.sqlite3    # Git 管理外
`- .claude/
```

詳細は `docs/REPO_STRUCTURE.md` を参照。

## 3. Django 設定

現在は `budgetbook/config/settings.py` の単一設定ファイルで運用する。

重要設定:

- `SECRET_KEY` は `.env` 必須。
- `DEBUG` は `.env` から読み込む。
- `ALLOWED_HOSTS` はカンマ区切り。
- `CSRF_TRUSTED_ORIGINS` は公開時に設定する。
- `ENABLE_HTTPS=1` は HTTPS / proxy 設計を確認してから使う。
- `ADMIN_URL_PATH` で管理画面 URL を変更可能。
- `AXES_ENABLED` はテスト時に無効。

## 4. 会計モデル

### Account

口座。`opening_balance` は開始残高として扱う。無効化された口座も過去残高の整合性上、全口座合計計算には含める。
月次締めが 1 件でも存在する場合、`opening_balance` の変更はモデル検証で拒否する。初期残高の後変更は全期間の残高を再計算し、締め済みスナップショットとの整合性を崩すため。

### Category

収入・支出カテゴリ。取引の種別は `Category.kind` で判定する。

### Transaction

通常の収入・支出。振替は含めない。

### Transfer

口座間振替。収入・支出集計には含めず、口座残高にのみ反映する。

### ExpenseGroup / ExpenseGroupCategory

v1.3.0 で導入。支出分析用のカテゴリグループ。既存 `Category` を変更せず、表示集計だけを合算する。

### MonthlyClosing

月次締め。対象月の月初繰越、収入、支出、当月収支、月末残高、口座別残高をスナップショットとして保存する。`month` は月初日で一意。締め済み月の `Transaction` / `Transfer` 作成・更新・削除は view 層で拒否する。

### AccountReconciliation

口座残高照合。照合日、口座、帳簿残高、実残高、差額を保存する。帳簿残高は `calculate_account_balance(account, reconciled_on)` でサーバー側計算し、POST 値を信用しない。`account + reconciled_on` は一意。

### AuditLog

重要操作の監査ログ。作成、更新、削除、無効化、月次締め、口座照合について、操作ユーザー、対象モデル、対象 ID、対象表示名、概要、補足 metadata を保存する。通常運用の閲覧口は Django admin とし、admin 上では追加・変更を禁止する。

## 5. 集計仕様

通常取引:

```text
income = sum(Transaction.amount where category.kind = income)
expense = sum(Transaction.amount where category.kind = expense)
net = income - expense
```

口座残高:

```text
balance =
  opening_balance
  + income_transactions_until_date
  - expense_transactions_until_date
  - transfers_out_until_date
  + transfers_in_until_date
```

月次:

- 月初繰越 = 対象月前日までの全口座合計残高。
- 当月収支 = 当月収入 - 当月支出。
- 月末残高 = 対象月末時点の全口座合計残高。

月次締め:

- `build_monthly_closing_snapshot(target_month)` で締め時点の集計値を保存する。
- 締め済み判定は `MonthlyClosing.month == month_from_entry_date(entry_date)`。
- 締め済み月の通常取引・振替 mutation は HTTP 409 で拒否する。
- 締め済み月のダッシュボードと入力フォームは閲覧専用として描画し、追加・編集・削除ボタンを表示しない。サーバー側 409 拒否を正とし、UI 制御は誤操作防止の補助とする。
- 締め・照合画面では、対象月の締め前チェックとして見込み集計、通常取引件数、振替件数、月末日照合の未登録口座、月末照合差額を表示する。これは締め前の会計確認を支援する警告であり、締め処理自体の強制ブロック条件にはしない。
- 締め・照合画面では、保存済み `MonthlyClosing` スナップショットと現在の帳簿再計算値を比較し、収入、支出、当月収支、月末残高、口座別残高に差異があれば警告表示する。これは admin 操作や手動データ修正後の検知用途であり、自動修正はしない。
- `python manage.py check_accounting_integrity` でも同じ差異検知を実行できる。差異があれば失敗終了し、`--warn-only` 指定時だけ警告表示に留める。
- 締め解除画面は持たない。必要時はバックアップ取得後、Django admin で個別対応する。

## 6. フロントエンド

- テンプレートは Django Templates。
- 部分更新は HTMX。
- グラフは Chart.js。
- Python の集計データは `json_script` で渡す。
- `safe` フィルターは原則使わない。
- CSS は `static/css/style.css` に集約する。

## 7. テスト

基本コマンド:

```bash
cd budgetbook
python manage.py test ledger
python manage.py makemigrations --check
```

会計ロジック、migration、セキュリティ設定、公開運用に関わる変更はテスト追加必須。

## 8. Docker / Cloudflare 方針

v1.5.0 で導入。詳細は `docs/DEPLOYMENT.md`。

- `budgetbook` service は非 root ユーザで Gunicorn 起動する。
- `proxy` service は `nginxinc/nginx-unprivileged` で起動し、公開入口を Nginx に集約する。
- `budgetbook` / `proxy` ともに `cap_drop: [ALL]`, `no-new-privileges:true` を適用する。
- `budgetbook` は read-only rootfs で起動し、書き込みは `./data`, `./backup`, `./staticfiles`, `/tmp` に限定する。
- SQLite DB は host バインドマウント `./data/db.sqlite3`（`DJANGO_DB_PATH` で切替可）。
- SQLite 接続時に `busy_timeout`, `foreign_keys=ON`, `journal_mode=WAL`, `synchronous=NORMAL` を適用する。
- migration / collectstatic は entrypoint で自動実行しない。運用者が `docker compose run --rm` で明示実行する。
- ports は Nginx proxy の `127.0.0.1:8010:8080` に限定。Gunicorn は host に公開しない。
- example の Docker ポート設計を基準にし、BudgetBook の host 公開ポートは 8010 に分離する。
- `cloudflared` は compose に含めず、Ubuntu host の systemd で運用する（token を compose と切り離す）。
- Cloudflare Tunnel Public Hostname `home.example.com` → `http://127.0.0.1:8010`。
- Cloudflare Access self-hosted policy で許可済みメール（世帯メンバーのみ）を通す。Django ログインは残し二重認証。
- Cloudflare Tunnel 配下では `TRUST_PROXY_SSL=1`、`SECURE_COOKIES=1`、Django の `ENABLE_HTTPS` は OFF（リダイレクトループ防止）。

## 9. Backup / Restore 方針

- 本番バックアップは `scripts/backup_budgetbook.sh` を使う。
- SQLite backup API で稼働中 DB から整合性のあるコピーを作る。
- バックアップごとに `PRAGMA integrity_check` と SHA-256 checksum を実行する。
- バックアップ作成後に `check_accounting_integrity` を実行し、`db-*.sqlite3.accounting_integrity.txt` を同じ保存先に残す。差異がある場合でも DB バックアップは残し、スクリプトは失敗終了して調査を促す。
- 保存先は `./backup/db-YYYY-MM-DD-HHMMSS.sqlite3`。
- systemd timer `budgetbook-backup.timer` で毎日 03:30 に実行する。
- 既定保持期間は `RETENTION_DAYS=30`。
- リストアは `scripts/restore_budgetbook.sh <backup-file>` を使い、自動復元はしない。復元後に Django check、migration 未適用チェック、会計整合性チェックを実行する。
