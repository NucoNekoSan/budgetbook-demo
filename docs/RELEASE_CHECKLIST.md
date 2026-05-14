# RELEASE_CHECKLIST.md - BudgetBook Release Checklist

実運用環境へ反映する前に確認するチェックリスト。1つでも A が満たせない場合は公開・反映しない。

## A. 必須

### A-1. 変更前バックアップ

- [ ] Docker運用時は `scripts/backup_budgetbook.sh` で `./data/db.sqlite3` のバックアップを作成した
- [ ] Windows + Docker Desktop でバックアップする場合は `scripts/backup_budgetbook.ps1` でバックアップを作成した
- [ ] ローカル開発時は `budgetbook/db.sqlite3` を `backup/` にコピーした
- [ ] 直近バックアップの `.sha256` と `PRAGMA integrity_check` が通る
- [ ] 直近バックアップの `.accounting_integrity.txt` が作成され、会計整合性チェックが通る
- [ ] 変更対象と migration 内容を確認した
- [ ] ロールバック時に失われるデータを把握した
- [ ] `.env` と Cloudflare token をバックアップやログに混ぜていない

### A-2. Django 設定

- [ ] `DEBUG=False`
- [ ] `SECRET_KEY` は `.env` のみ
- [ ] `ALLOWED_HOSTS` が本番ホストに限定されている
- [ ] `CSRF_TRUSTED_ORIGINS` が本番 HTTPS URL と一致している
- [ ] `SECURE_COOKIES=1` で `SESSION_COOKIE_SECURE=True` / `CSRF_COOKIE_SECURE=True`
- [ ] `ADMIN_URL_PATH` が設定可能
- [ ] `django-axes` が有効
- [ ] `python manage.py check` が通る

### A-3. DB / migration

- [ ] destructive migration がない
- [ ] 既存カラム削除がない
- [ ] 既存データ変換がある場合は事前承認済み
- [ ] `python manage.py makemigrations --check` が通る、または作成 migration の内容を説明済み
- [ ] `python manage.py migrate` の適用順を確認した

### A-4. テスト

- [ ] `python manage.py test ledger` が通る
- [ ] 会計ロジック変更に対応するテストがある
- [ ] 収入・支出・振替・繰越・口座残高の回帰を確認した
- [ ] 締め済み月の通常取引・振替の追加、編集、削除が拒否される
- [ ] 締め済み月のトップページと入力フォームが閲覧専用になり、追加・編集・削除ボタンが表示されない
- [ ] 締め・照合画面の締め前チェックで、見込み集計、月末照合未登録口座、月末照合差額を確認した
- [ ] 締め・照合画面で締め済みスナップショットと現在帳簿の差異検知が表示される
- [ ] `python manage.py check_accounting_integrity` が通る
- [ ] 月次締め後に口座初期残高の変更が拒否される
- [ ] 口座残高照合で帳簿残高がサーバー側計算値になり、差額が保存される
- [ ] CSV export のユーザー入力欄で式注入対策が効いている
- [ ] 取引・振替・設定・締め・照合の成功操作で監査ログが作成される
- [ ] `scripts/audit_dependencies.sh` が通り、Python 依存の既知脆弱性がない
- [ ] `scripts/security_static_scan.sh` が通り、Python コードの静的セキュリティ指摘がない
- [ ] 未確認の Dependabot PR が残っていない、または今回リリース対象外として理由を説明できる
- [ ] GitHub Actions の release tag CI で `Production checks` が成功している

### A-5. 主要画面

- [ ] `/` が 200
- [ ] `/annual/` が 200
- [ ] `/expense-breakdown/` が 200
- [ ] `/accounting/` が 200
- [ ] `/settings/` が 200
- [ ] `/accounts/login/` が 200
- [ ] 未ログインではダッシュボードへアクセスできない

## B. Docker / Cloudflare 導入時

- [ ] `./data/db.sqlite3` がバインドマウントされ永続化されている
- [ ] `docker compose config` が通る
- [ ] `docker compose build` が通る
- [ ] `scripts/preflight_budgetbook.sh` が通る
- [ ] Windows + Docker Desktop で確認する場合は `scripts/preflight_budgetbook.ps1` が通る
- [ ] `scripts/preflight_budgetbook.sh` 内で `check_accounting_integrity` が通る
- [ ] migration / collectstatic は entrypoint で自動実行されない（手動コマンドのみ）
- [ ] `DJANGO_DB_PATH=/app/data/db.sqlite3` が compose で注入されている
- [ ] `TRUST_PROXY_SSL=1` のときのみ `SECURE_PROXY_SSL_HEADER` が有効
- [ ] `ENABLE_HTTPS=0` でも Secure Cookie が有効
- [ ] `ENABLE_HTTPS` は Cloudflare Tunnel 構成では OFF（リダイレクトループ防止）
- [ ] Cloudflare Tunnel token は host systemd の cloudflared サービスのみで管理（Git 管理禁止）
- [ ] ルーターの 80/443 を開けていない
- [ ] ports は Nginx proxy の `127.0.0.1:8010:8080` に限定されている
- [ ] Gunicorn (`budgetbook:8010`) は host に直接公開されていない
- [ ] `budgetbook` / `proxy` に `cap_drop: [ALL]` と `no-new-privileges:true` が設定されている
- [ ] `budgetbook` は read-only rootfs で、書き込み先が bind mount / tmpfs に限定されている
- [ ] SQLite `busy_timeout` / `foreign_keys` / `WAL` が有効
- [ ] example の Docker ポート設計と競合していない
- [ ] Cloudflare Access policy が本人と妻のメールのみに限定されている
- [ ] Django ログインが残っている
- [ ] Cloudflare アカウント 2FA が有効
- [ ] `budgetbook-backup.timer` が有効化されている
- [ ] `systemctl list-timers budgetbook-backup.timer` で次回実行予定を確認した
- [ ] `journalctl -u budgetbook-backup.service` に直近エラーがない
- [ ] Windows + Docker Desktop で運用する場合は `BudgetBookDailyBackup` タスクを登録し、手動実行でバックアップ作成を確認した
- [ ] リストア手順が復元後 Django check / migration check / 会計整合性チェックまで含むことを確認した
- [ ] 対象バックアップを `restore_budgetbook.sh --verify-only` または `restore_budgetbook.ps1 -VerifyOnly` で検証した
- [ ] Windows + Docker Desktop でリストアする場合は `scripts/restore_budgetbook.ps1` の手順を確認した
- [ ] `docker compose down -v` を運用環境で使わない

## C. 公開後確認

- [ ] 保存・更新・削除の flash が表示される
- [ ] CSV export が開ける
- [ ] CSV export を表計算ソフトで開いても、摘要・メモ・口座名・カテゴリ名が式として実行されない
- [ ] 支出構成グラフが表示される
- [ ] 収支推移グラフが横スクロールできる
- [ ] 振替が収入・支出に混入しない
- [ ] バックアップから復元する手順を確認した

## X. 体調不良時に触らない

- [ ] migration
- [ ] DB ファイルの手動コピー・復元
- [ ] Docker volume 削除
- [ ] Cloudflare DNS / Access policy 変更
- [ ] `ENABLE_HTTPS`, HSTS, proxy 設定変更
