# BudgetBook Deployment (Docker + Cloudflare Tunnel)

本番運用は Ubuntu Server + Docker + Cloudflare Tunnel + Cloudflare Access の構成を前提とする。
本人と妻の 2 名のみがアクセスできるようにする。

## 0. 絶対に守ること

- 自宅ルーターの 80/443 ポートを開けない。Cloudflare Tunnel のみで外部公開する。
- Cloudflare Access を Django ログインの前段に置き、二重認証にする。
- `.env`, `db.sqlite3`, `backup/`, `staticfiles/`, Cloudflare Tunnel token は Git 管理しない。
- `docker compose down -v` を実運用環境で使わない（volume / バインドマウントのデータ取り扱いを混乱させない）。
- migration / collectstatic は **自動実行しない**。運用者が明示コマンドで実行する。
- Docker ポートは example を基準にし、BudgetBook は `127.0.0.1:8010` に分離する。

## 1. 前提

- Ubuntu Server 22.04 以上
- Docker Engine と Docker Compose plugin (`docker compose` コマンド)
- Cloudflare アカウント（Tunnel と Access が利用可能なプラン）

```bash
docker --version
docker compose version
```

## 2. 初回セットアップ

### 2.1 リポジトリ配置

```bash
git clone <repo-url> budgetbook
cd budgetbook
```

### 2.2 永続化ディレクトリ作成

```bash
mkdir -p data backup staticfiles
```

### 2.3 既存 db.sqlite3 を移行（既存データがある場合）

ローカル PC 等から運用済みの `budgetbook/db.sqlite3` を持ち込む場合は、
**手動コピー** で `./data/db.sqlite3` に置く。

```bash
# 例: 既存ファイルを ./data に手動でコピーした上で、所有権を appuser(uid:1000) に揃える
cp /path/to/old/db.sqlite3 ./data/db.sqlite3
sudo chown 1000:1000 ./data/db.sqlite3 ./data ./backup ./staticfiles
```

新規環境で初めて立ち上げる場合は空のままでよい。後段の migrate で作成される。

### 2.4 .env 作成

```bash
cp budgetbook/.env.example budgetbook/.env
```

`budgetbook/.env` を以下のように編集する（例）。

```env
SECRET_KEY=（ランダムな十分長い文字列）
DEBUG=False
ALLOWED_HOSTS=127.0.0.1,localhost,home.example.com
CSRF_TRUSTED_ORIGINS=https://home.example.com

# 注意: コンテナ内の healthcheck が http://127.0.0.1:8010/accounts/login/ を叩くため、
# ALLOWED_HOSTS には本番ドメインに加えて 127.0.0.1 を必ず残してください。
# 127.0.0.1 を外すと healthcheck が DisallowedHost で 400 を返し、コンテナが unhealthy になります。

# Docker 内 DB パス（compose で同値を環境変数として注入する）
DJANGO_DB_PATH=/app/data/db.sqlite3

# Cloudflare Tunnel 配下では proxy 経由の HTTPS を信頼する
TRUST_PROXY_SSL=1

# Cloudflare 側で HTTPS を強制するため、Django 側の HTTPS リダイレクトは OFF
# ENABLE_HTTPS は コメントアウトのままにする

# 管理画面 URL は推測されにくいパスに変える
ADMIN_URL_PATH=secret-admin/

SESSION_COOKIE_AGE=86400
```

`SECRET_KEY` は `python -c 'from secrets import token_urlsafe;print(token_urlsafe(64))'` などで生成する。

### 2.5 build

```bash
docker compose build
```

### 2.6 migrate（明示実行）

```bash
docker compose run --rm budgetbook python manage.py migrate
```

### 2.7 superuser 作成（初回のみ）

```bash
docker compose run --rm budgetbook python manage.py createsuperuser
```

### 2.8 collectstatic（明示実行）

```bash
docker compose run --rm budgetbook python manage.py collectstatic --noinput
```

`DEBUG=False` + WhiteNoise 構成では、**collectstatic 実行後にアプリコンテナを再起動** しないと
新しい静的ファイルが配信されない場合がある。

### 2.9 起動

```bash
docker compose up -d
docker compose ps
docker compose logs -f budgetbook
```

ホスト内部の `127.0.0.1:8010` のみで待ち受ける。外部公開は Cloudflare Tunnel のみで行う。
このポートは Docker 内 Nginx proxy の `8080` に転送され、proxy から Gunicorn (`budgetbook:8010`) に転送する。
Gunicorn は host に直接公開しない。

## 3. Cloudflare Tunnel（host systemd 運用）

`cloudflared` は **本アプリの compose に含めない**。Ubuntu host 側で systemd サービスとして動かす。
Token のライフサイクルを compose と切り離すための設計判断。

### 3.1 cloudflared インストールと token 登録

```bash
# Cloudflare Zero Trust ダッシュボードで Tunnel を作成し token を取得
# 取得した <TOKEN> はメモやリポジトリに残さない
sudo cloudflared service install <TOKEN>
sudo systemctl enable --now cloudflared
sudo systemctl status cloudflared
```

### 3.2 Public Hostname 設定

Cloudflare Zero Trust > Networks > Tunnels > 該当 Tunnel > Public Hostname

| 項目 | 値 |
|---|---|
| Subdomain | `home` |
| Domain | `example.com` |
| Path | （空） |
| Service | `http://127.0.0.1:8010` |

`http://127.0.0.1:8010` は Docker compose が公開しているローカルエンドポイント。

## 4. Cloudflare Access（前段認証）

Cloudflare Zero Trust > Access > Applications > Add an application > **Self-hosted**

| 項目 | 値 |
|---|---|
| Application name | BudgetBook |
| Session Duration | 24 hours（任意） |
| Application domain | `home.example.com` |

**Policy**:

- Action: `Allow`
- Configure rules > Include > **Emails**
  - 本人メール
  - 妻メール
- それ以外は拒否（暗黙）

IdP は Cloudflare One-Time PIN（メール送信）または Google IdP を使う。

これで以下の二重認証になる:

1. Cloudflare Access のメールリンク認証
2. Django ログイン（既存の username/password + django-axes）

## 5. 起動・停止・更新

### 起動 / 停止

```bash
docker compose up -d
docker compose stop
docker compose down            # ← -v は付けない
```

### 更新（コード反映）

```bash
git pull
docker compose build
# 必要に応じて
docker compose run --rm budgetbook python manage.py migrate
docker compose run --rm budgetbook python manage.py collectstatic --noinput
docker compose up -d
docker compose restart budgetbook
```

migration が含まれるリリースは **必ず事前にバックアップ**（次節）してから適用する。

## 6. バックアップ / リストア

### バックアップ方針

SQLite DB は実データなので、単純な `cp` ではなく SQLite backup API を使う。
`scripts/backup_budgetbook.sh` は稼働中の DB から整合性のあるコピーを作成し、`PRAGMA integrity_check` と SHA-256 を残す。

保存先:

- DB: `./backup/db-YYYY-MM-DD-HHMMSS.sqlite3`
- checksum: `./backup/db-YYYY-MM-DD-HHMMSS.sqlite3.sha256`
- accounting integrity: `./backup/db-YYYY-MM-DD-HHMMSS.sqlite3.accounting_integrity.txt`

既定の保存期間は `RETENTION_DAYS=30`。必要なら systemd service の Environment で変更する。
バックアップ作成後に会計整合性チェックを実行する。差異が見つかった場合でも DB と checksum は残し、スクリプトは失敗終了する。

### バックアップ（手動）

```bash
chmod +x scripts/backup_budgetbook.sh scripts/restore_budgetbook.sh
scripts/backup_budgetbook.sh
```

Windows + Docker Desktop で同等のバックアップを作る場合:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/backup_budgetbook.ps1
```

Windows + Docker Desktop で日次バックアップをタスクスケジューラに登録する場合:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/register_budgetbook_backup_task.ps1
```

既定では `BudgetBookDailyBackup` というタスク名で毎日 03:30 に実行する。
Docker Desktop は通常ユーザーセッションに依存するため、このタスクは現在の Windows ユーザーのログオン中に実行する前提。
時刻や保持期間を変える場合:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/register_budgetbook_backup_task.ps1 -At 04:00 -RetentionDays 60 -Force
```

### バックアップ（systemd timer）

Ubuntu Server では cron より systemd timer を第一候補にする。

```bash
sudo install -m 0644 infra/systemd/budgetbook-backup.service /etc/systemd/system/budgetbook-backup.service
sudo install -m 0644 infra/systemd/budgetbook-backup.timer /etc/systemd/system/budgetbook-backup.timer
sudo systemctl daemon-reload
sudo systemctl enable --now budgetbook-backup.timer
systemctl list-timers budgetbook-backup.timer
```

手動実行:

```bash
sudo systemctl start budgetbook-backup.service
journalctl -u budgetbook-backup.service -n 80 --no-pager
ls -lh ./backup/
```

### リストア（手動）

バックアップファイルを上書き前に検証するだけなら、次を使う。

```bash
scripts/restore_budgetbook.sh --verify-only backup/db-2026-05-02-090000.sqlite3
```

Windows + Docker Desktop では:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/restore_budgetbook.ps1 -BackupFile backup/db-2026-05-02-090000.sqlite3 -VerifyOnly
```

検証のみの場合、Docker service の停止と `./data/db.sqlite3` の上書きは行わない。

```bash
scripts/restore_budgetbook.sh backup/db-2026-05-02-090000.sqlite3
```

Windows + Docker Desktop で同等のリストアを行う場合:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/restore_budgetbook.ps1 -BackupFile backup/db-2026-05-02-090000.sqlite3
```

**自動リストアはしない**。データ上書きは必ず人の判断で行う。

リストアスクリプトは以下を行う:

1. `.sha256` があれば検証
2. `PRAGMA integrity_check`
3. `proxy` と `budgetbook` を停止
4. 現在の `./data/db.sqlite3` を `backup/pre-restore-*.sqlite3` に退避
5. 指定バックアップを `./data/db.sqlite3` に配置
6. `budgetbook` と `proxy` を起動
7. Django check、migration 未適用チェック、会計整合性チェックを実行

## 7. ロールバック

### コードロールバック

```bash
git checkout <previous-tag>
docker compose build
docker compose up -d
```

### DB ロールバック

直前のバックアップを 6. の手順でリストアする。

### Docker やめる（ローカル開発に戻す）

```bash
docker compose down            # ← -v は付けない
cd budgetbook
python manage.py runserver
```

`.env` の `DJANGO_DB_PATH` を未設定にすれば、従来の `budgetbook/db.sqlite3` を参照する。

## 8. トラブルシューティング

| 現象 | 確認 |
|---|---|
| 502 Bad Gateway | `docker compose logs budgetbook` / `127.0.0.1:8010` がローカルから到達するか |
| CSRF verification failed | `CSRF_TRUSTED_ORIGINS=https://home.example.com` が設定されているか |
| DisallowedHost | `ALLOWED_HOSTS` に Tunnel ドメインが入っているか |
| リダイレクトループ | `ENABLE_HTTPS=1` を OFF に戻す（Cloudflare Tunnel 構成では原則 OFF） |
| 静的ファイル 404 | collectstatic 実行後に `docker compose restart budgetbook` を行ったか |
| Cloudflare Access が反応しない | Tunnel 状態 `systemctl status cloudflared` / Access policy のメール一致 |

## 9. 運用上の禁止事項（再掲）

- 80/443 ポート解放
- `docker compose down -v` の実運用使用
- Cloudflare Tunnel token を Git/Slack/メモに残すこと
- migration の自動実行
- 自動 DB 復元
- `db.sqlite3` の Git コミット
