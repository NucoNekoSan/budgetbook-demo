# BudgetBook 運用ガイド

開発サーバーの起動・停止、静的ファイルの更新手順、ログイン関連のトラブルシューティングをまとめています。

---

## 開発サーバーの起動と停止

### 起動

```bash
cd budgetbook
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # macOS / Linux

python manage.py runserver
```

LAN 内の別端末からアクセスする場合:

```bash
python manage.py runserver 0.0.0.0:8000
```

### 停止

ターミナルで `Ctrl+C` を押してサーバーを停止します。

**注意:** ターミナルを閉じただけではプロセスが残ることがあります。ポート 8000 が使用中のエラーが出る場合は、既存プロセスを確認・終了してください。

```bash
# Windows — ポート 8000 を使用しているプロセスの確認
netstat -ano | findstr :8000

# プロセスの終了（PID は上記コマンドで確認）
taskkill /PID <PID> /F
```

```bash
# macOS / Linux
lsof -i :8000
kill <PID>
```

複数の `runserver` プロセスが同時に動いていると、古いプロセスが古いファイルを配信し続け、ブラウザに表示される内容と実際のファイルが食い違う原因になります。サーバーを再起動する際は、既存プロセスが確実に終了していることを確認してください。

---

## 静的ファイルの更新

### DEBUG=True の場合

Django が `static/` ディレクトリを直接配信するため、CSS や JS を変更すればブラウザをリロードするだけで反映されます。`collectstatic` は不要です。

### DEBUG=False（WhiteNoise）の場合

WhiteNoise は **サーバー起動時にファイル一覧をメモリにキャッシュ** します。そのため、静的ファイルを変更した場合は以下の手順が必要です。

```bash
# 1. 静的ファイルを収集
python manage.py collectstatic --noinput

# 2. サーバーを再起動（Ctrl+C で停止してから再起動）
python manage.py runserver
```

**よくあるトラブル:**

| 症状 | 原因 | 対処 |
|------|------|------|
| 新しい JS ファイルが 404 になる | `collectstatic` 未実行、またはサーバー未再起動 | 上記の手順 1→2 を実行 |
| 古い内容が表示される | 古い `runserver` プロセスが残っている | 全プロセスを終了してから再起動 |
| JS が途中で切れる（`SyntaxError: Unexpected end of input`） | WhiteNoise が古いファイルサイズでキャッシュしている | 全プロセス終了 → `collectstatic` → 再起動 |

---

## ログイン関連のトラブルシューティング

### django-axes によるロックアウト

ログインに連続して失敗すると、django-axes がそのユーザー/IP をロックアウトします。

| 設定 | デフォルト値 | 説明 |
|------|------------|------|
| `AXES_FAILURE_LIMIT` | 5 | ログイン失敗許容回数 |
| `AXES_COOLOFF_TIME` | 0.5（30分） | ロックアウト解除までの時間（時間単位） |

ロックアウトされた場合の対処:

```bash
# 方法1: 30分待つ（デフォルトの AXES_COOLOFF_TIME）

# 方法2: 管理コマンドでロックアウトを解除
python manage.py axes_reset

# 方法3: 特定ユーザーのロックアウトのみ解除
python manage.py axes_reset_username <ユーザー名>
```

Django シェルから直接解除する場合:

```bash
python manage.py shell
```

```python
from axes.models import AccessAttempt
AccessAttempt.objects.all().delete()
```

### パスワードのリセット

パスワードを忘れた場合やリセットが必要な場合:

```bash
python manage.py changepassword <ユーザー名>
```

### ユーザーの新規作成

管理者ユーザーを新しく作成する場合:

```bash
python manage.py createsuperuser
```

---

## セキュリティ設定

### 常時有効（LAN 運用でも適用）

- `X-Frame-Options: DENY` — クリックジャッキング防止
- `X-Content-Type-Options: nosniff` — MIME タイプスニッフィング防止
- `Referrer-Policy: same-origin` — リファラー情報の漏洩防止
- django-axes によるログイン試行回数制限
- 管理画面 URL を環境変数 `ADMIN_URL_PATH` で変更可能（デフォルト `admin/`）
- セッション有効期間を `SESSION_COOKIE_AGE` で設定可能（デフォルト 24 時間）

### 公開モード（Cloudflare Tunnel）

Cloudflare Tunnel で公開する場合、HTTPS 化と HTTP→HTTPS 強制は Cloudflare 側に委ねます。
BudgetBook 側では `.env` に `TRUST_PROXY_SSL=1` と `SECURE_COOKIES=1` を設定し、`ENABLE_HTTPS=1` は通常使いません。

| 設定 | 効果 |
|------|------|
| `SESSION_COOKIE_SECURE=True` | セッション Cookie を HTTPS 通信でのみ送信 |
| `CSRF_COOKIE_SECURE=True` | CSRF Cookie を HTTPS 通信でのみ送信 |
| `SECURE_PROXY_SSL_HEADER` | Cloudflare Tunnel 経由の HTTPS 判定を Django に伝える |

`ENABLE_HTTPS=1` は Django 側で SSL redirect / HSTS を有効にする設定です。Cloudflare Tunnel 構成で有効化するとリダイレクトループの原因になるため、Django が直接 HTTPS 終端を管理する構成に変える場合だけ検討してください。

**HSTS preload について:**

HSTS preload は `ENABLE_HSTS_PRELOAD=1` で明示的に有効化します（デフォルト OFF）。preload を有効にすると、ブラウザの組み込みリストに登録申請でき、初回アクセスから HTTPS が強制されます。ただし一度登録すると解除に時間がかかるため、Cloudflare 側の HTTPS / HSTS 設計を固めた後に慎重に判断してください。

### CSP（Content Security Policy）について

現在、チャート関連の JavaScript はインラインスクリプトから外部ファイルに分離済みです（`static/js/` 配下）。
CSP ヘッダーは既定で有効です。

既定ポリシーでは `object-src 'none'` / `frame-ancestors 'none'` / `form-action 'self'` を強制します。
既存テンプレートには `json_script` と一部 inline style があるため、現段階では `script-src` / `style-src` に `'unsafe-inline'` を残しています。
問題切り分け時のみ `.env` に `ENABLE_CSP=0` を設定して一時停止できます。

---

## バックアップと復元

### バックアップ対象

- `budgetbook/db.sqlite3` — 全データ
- `budgetbook/.env` — 秘密情報（SECRET_KEY 等）

### PowerShell でのバックアップ

```powershell
cd budgetbook
$dir = "backup\$(Get-Date -Format 'yyyy-MM-dd_HHmmss')"
New-Item -ItemType Directory -Path $dir | Out-Null
Copy-Item db.sqlite3 -Destination $dir
```

### 復元

1. `runserver` を停止
2. `db.sqlite3` をバックアップから上書きコピー
3. `runserver` を再起動
## 支出カテゴリグループ（v1.3.0）

「支出構成」画面の円グラフでは、複数カテゴリを 1 つのグループに合算表示できます。グループは Django admin から管理します。

### 設定手順

1. 管理画面（`/<ADMIN_URL_PATH>/`）にログイン。
2. 「支出カテゴリグループ」を追加し、グループ名・表示順・有効フラグを設定。
3. インラインの「グループ所属カテゴリ」で対象カテゴリを追加。1 カテゴリは 1 グループにのみ所属可能（OneToOne 制約）。
4. 収入カテゴリは登録不可（モデル層で拒否）。
5. グループを `is_active=False` にすると、その所属カテゴリは集計時に未グループとして個別表示に戻る。

### 例: 食品・日用品グループ

- グループ名: `食品・日用品`
- 所属カテゴリ: スーパー / コンビニ / ドラッグストア など細分化された Category 群
- 百貨店は購入内容が多岐にわたるため、初期状態では所属させない。

## 運用補助 (v1.7.x)

### バックアップ世代管理 (GFS)

`scripts/backup_budgetbook.sh` は既定で flat retention（N 日より古いものを削除）を使うが、
`RETENTION_POLICY=gfs` を指定すると Grandfather-Father-Son 方式に切り替えられる。

| 環境変数 | 既定 | 説明 |
|---|---|---|
| `RETENTION_POLICY` | `flat` | `gfs` で世代管理を有効化 |
| `GFS_DAILY` | `7` | 直近の日次保持日数 |
| `GFS_WEEKLY` | `4` | ISO 週ごとに 1 件保持する週数 |
| `GFS_MONTHLY` | `12` | 月ごとに 1 件保持する月数 |

systemd timer や cron で `RETENTION_POLICY=gfs scripts/backup_budgetbook.sh` を呼ぶ。

### 既存バックアップの定期再検証

`scripts/verify_backups.sh` は `backup/` 配下の `db-*.sqlite3` 全件について
SHA256 と `PRAGMA integrity_check` を再検証する。物理破損 / ビット腐敗の早期検出向け。
`sqlite3` と `sha256sum` がホストにあれば Docker 不要で動作する。

例: 週次で実行
```bash
0 4 * * 0 cd /opt/budgetbook && scripts/verify_backups.sh >> /var/log/budgetbook/verify.log 2>&1
```

### ヘルスチェック

`GET /healthz` は DB に `SELECT 1` を流すだけの軽量エンドポイント。
JSON `{"status":"ok"}` を 200 で返す。認証なしのため Cloudflare Access /
内部ネットワークで保護する前提。Docker `healthcheck:` や監視ツールから利用する。

### 構造化ログ (JSON)

`DJANGO_LOG_FORMAT=json` を環境変数で指定すると、Django のログを 1 行 1 JSON で stdout に出力する。
`extra={...}` の任意フィールドはそのまま JSON のキーに展開されるため、
監査イベント (`logger=budgetbook.audit, event=audit, action, target_model, target_id, ip, ...`) を
Cloudflare Logs / Loki / journalctl などの集約基盤で検索しやすい。

| 環境変数 | 例 | 既定 |
|---|---|---|
| `DJANGO_LOG_FORMAT` | `json` / `plain` | 本番=json, 開発=plain |
| `DJANGO_LOG_LEVEL` | `INFO` / `WARNING` / `ERROR` | テスト=CRITICAL, それ以外=INFO |

### 二次レート制限

`axes` はログイン専用なので、それ以外のエンドポイントにも IP 単位の sliding window
レート制限を入れている（`config.middleware.RateLimitMiddleware`）。

| 環境変数 | 既定 | 説明 |
|---|---|---|
| `RATE_LIMIT_ENABLED` | `1` | `0` で無効化 |
| `RATE_LIMIT_MAX_EVENTS` | `600` | ウィンドウ内の上限 |
| `RATE_LIMIT_WINDOW_SECONDS` | `60` | スライドウィンドウ秒数 |
| 除外 path | `/healthz`, `/static/` | レート制限の対象外 |

超過時は 429 を返し、`logger=budgetbook.security, event=rate_limit` が出力される。

### `/healthz` verbose モード

`GET /healthz?verbose=1` で

- `db_write`: 書込み試験 (TX 内挿入→ロールバック)
- `accounting`: 直近 1 件の月次締めスナップショットと現在帳簿の差分

を返す。重いので監視ツールから常時ポーリングしないこと。
オペレータが手動 / 障害時のみ叩く想定。drift 検出時は `status=degraded` を返す。

### AuditLog 保管期間管理

無限に増える `AuditLog` テーブルを定期的に整理する。

```bash
python manage.py prune_audit_logs --keep-days=365 --archive-dir=/var/backup/budgetbook/audit
```

- 期間外行を `audit_log_until_<date>.jsonl.gz` にアーカイブしてから削除する。
- `--dry-run` で件数のみ確認可能。
- `--batch-size` で削除単位を制御し、長時間ロックを回避する。

---

## PWA (v1.9.0) の運用上の注意

`/manifest.webmanifest` + `/sw.js` を提供しており、ブラウザの「ホーム画面に追加」「インストール」でアプリ風起動が可能。

### Service Worker が動作する条件

Service Worker は **HTTPS または `localhost` / `127.0.0.1`** でのみ登録できる（ブラウザ仕様）。

| アクセス経路 | SW 登録 | PWA インストール | オフライン動作 |
|---|---|---|---|
| `http://127.0.0.1:8765/` (PC dev) | ✅ | ✅ | ✅ |
| `http://192.168.1.10:8010/` (LAN HTTP) | ❌ | △ (ブックマーク相当) | ❌ |
| Cloudflare Tunnel 経由 (HTTPS) | ✅ | ✅ | ✅ |

**結論**: iPad/スマホからフル PWA を使いたい場合は Cloudflare Tunnel 経由で接続する。LAN HTTP のみで使う場合は「ホーム画面のショートカット」程度の挙動になる（Safari は SW なしでも追加可）。

### SW の更新フロー

- `static/js/sw.js` の `CACHE_VERSION` を変更すれば、`activate` 時に旧キャッシュが自動 purge される。
- 大きな UI 変更後は必ず `CACHE_VERSION` をインクリメントすること（例: `bb-v1.9.0-1` → `bb-v1.9.0-2`）。
- ユーザー側でリロードしても古い SW が残る場合は DevTools → Application → Service Workers → Unregister で強制削除可能。

### アイコンの再生成

デザイン変更時:

```bash
python scripts/gen_pwa_icons.py
```

`budgetbook/static/icons/` 配下の PNG を再生成する。Pillow 依存なし（pure stdlib）。SVG (`icon.svg`) は手で編集する。

### キャッシュ対象から除外しているもの

- `/healthz` （運用観測のため常に最新）
- `/sw.js` 自身（常に最新を取得）
- POST / PUT / PATCH / DELETE 全般（家計データを古いキャッシュで上書きしないため）

---

## 観測性 (v1.10.0) の運用

### `/metrics` JSON エンドポイント

ログイン後 `GET /metrics` で口座・取引・残高・AuditLog 件数などの集計値を JSON で取得できる（生取引データは含まない）。設定ページの「📊 メトリクス JSON」リンク、または `curl` で取得可能:

```bash
# Cookie 認証経由（事前に curl でログインしてセッションを保存）
curl -b cookies.txt http://127.0.0.1:8010/metrics
```

### ログイン履歴

設定ページの「🔐 ログイン履歴」から過去 30 日分の成功・失敗ログを確認できる。データは django-axes が記録した `AccessLog` / `AccessAttempt` をそのまま表示する。失敗が連続している場合は IP / User-Agent を見て侵入試行か誤入力かを判断する。

### 5xx エラーメール通知

500 系エラー発生時に管理者にメール通知する。設定例:

```bash
# .env
ERROR_NOTIFY_TO=admin@example.com,backup@example.com
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_HOST_USER=demo@example.com
EMAIL_HOST_PASSWORD=<Gmail のアプリパスワード>
EMAIL_USE_TLS=True
DEFAULT_FROM_EMAIL=budgetbook@demo-user.example
```

- `ERROR_NOTIFY_TO` が空 / 未設定なら handler は attach されない。
- 同じ (パス, 例外クラス) の組は **5 分に 1 回** までしか送らない（バースト抑止）。
- メール本文に **リクエストボディ / cookie / session / 取引データは含まれない**。トレースバックは先頭 5 行のみ。
- 送信は別スレッドで fire-and-forget。送信失敗してもアプリは止まらない。
- ローカル開発で SMTP 設定しない場合は `EMAIL_BACKEND` がデフォルトで `console.EmailBackend` になっており、メール内容が標準出力に出るだけで安全。

## 利息自動計上 (v1.11.0)

年利 > 0 の有利子負債口座 (`LoanProfile.annual_rate_bp > 0`) に対して、当月利息相当額を支出 Transaction として一括生成する management command。

### 事前準備（初回のみ）

利息計上に使うカテゴリを 1 件作成する:

- 名前: `金利・手数料`（変えたい場合は `.env` に `LOAN_INTEREST_CATEGORY_NAME=他の名前` を設定）
- 区分: 支出
- 大分類: その他 (other)

`/settings/` の Web UI から作成するのが安全。

### 使い方

```bash
# 当月を dry-run
docker compose exec budgetbook python manage.py accrue_loan_interest

# 月指定で dry-run
docker compose exec budgetbook python manage.py accrue_loan_interest --month 2026-05

# 確定実行（--apply で初めて DB に書き込む）
docker compose exec budgetbook python manage.py accrue_loan_interest --month 2026-05 --apply

# 特定の口座だけ処理
docker compose exec budgetbook python manage.py accrue_loan_interest --month 2026-05 --account クレジットカードA --apply
```

### 動作仕様

- 対象: `annual_rate_bp > 0` かつ `Account.is_active=True` の LoanProfile
- 計算: 月初時点の残債（絶対値）× (年利 bp / 10000) / 12、四捨五入で整数円
- 計上日: 対象月の **月末日** 固定
- 生成: 支出 Transaction 1 件 / 口座、AuditLog に `source=accrue_loan_interest` で記録
- 同月同口座にすでに利息 Transaction がある場合は **エラー終了**（二重計上防止）
- atomic ブロック内で **再チェック** するため、同時実行で別プロセスが直前に INSERT してもロールバック
- MonthlyClosing 済み月は **拒否**

### 利息計算の精度について（運用上の注意）

本コマンドは **月単位の単純化計算** (`round(元本 × 年利/12)`) を採用しています。一方、実際のクレジットカード会社の利息明細は **日割計算** (日数 × 元本 × 日利) を使うのが標準です。

両者には数百円規模の誤差が生じます:

- 元本変動が小さい月: 誤差 ¥10〜¥50 程度
- 月内に大きな利用や返済があった月: 誤差 ¥100〜¥500 程度

家計簿としての P/L 把握には十分な精度ですが、**クレカ明細書との完全一致は期待しない**でください。年間ベースでは数千円の差になるので、年末の正確な集計が必要な場合は実明細を別途参照してください。

### 月初の運用フロー

毎月 1 回（前月分を計上するイメージ）:

```bash
# 1. dry-run で内容確認
docker compose exec budgetbook python manage.py accrue_loan_interest --month 2026-05

# 2. 妥当なら確定
docker compose exec budgetbook python manage.py accrue_loan_interest --month 2026-05 --apply

# 3. その後に通常通り月次締めを実行
```

### ロールバック

`--apply` 直後に取り消したい場合:

1. AuditLog で `metadata.source = "accrue_loan_interest"` の行を抽出
2. `target_id` の Transaction を Web UI から削除

`transaction.atomic` で囲んでいるので、部分失敗時は自動でロールバックされる（中途半端な状態は残らない）。

## 元金返済 Transfer 自動化 (v1.12.0)

毎月の引落（銀行→負債口座の Transfer）を自動生成する。v1.11.0 の利息計上と組み合わせて、有利子負債口座の月次手入力をゼロにする。

### 事前準備（初回のみ）

各 LoanProfile に「引落元口座」を設定する:

1. `/settings/` の「負債プロファイル」編集画面（リボ口座の鉛筆アイコン）を開く
2. 「**引落元口座**」で資産口座（普通預金Aなど）を選択
3. 「**月次返済額（目安）**」と「**引落日**」が 0 でないこと（自動生成の対象条件）
4. 保存

設定されていないプロファイルは自動生成の対象外（毎月手動入力に戻る）。

### 使い方

```bash
docker compose exec budgetbook python manage.py accrue_loan_principal --month 2026-06
docker compose exec budgetbook python manage.py accrue_loan_principal --month 2026-06 --apply
docker compose exec budgetbook python manage.py accrue_loan_principal --month 2026-06 --account クレジットカードA --apply
```

### 動作仕様

- 対象: `monthly_payment > 0 AND source_account NOT NULL AND 両口座 is_active=True`
- 0% ローン（ショッピング分割 / 分割返済B等）も `monthly_payment > 0` なら処理対象
- Transfer 1 件 / LoanProfile（from=source_account, to=loan.account, amount=monthly_payment）
- 計上日: `payment_day` をそのまま使用。0 / 月の日数超は月末にフォールバック
- AuditLog `source=accrue_loan_principal` で記録
- 同月同口座に accrue_loan_principal 由来 Transfer が既にあれば **エラー終了**
- MonthlyClosing 済み月は拒否

### 月次フルオート フロー

```bash
# 1. 利息計上
docker compose exec budgetbook python manage.py accrue_loan_interest --month 2026-06 --apply
# 2. 元金返済 Transfer
docker compose exec budgetbook python manage.py accrue_loan_principal --month 2026-06 --apply
# 3. その後に通常通り月次締めを実行
```

### ロールバック

- AuditLog で `metadata.source = "accrue_loan_principal"` を抽出
- `target_id` の Transfer を Web UI から削除
- `transaction.atomic` により部分失敗時は自動ロールバック

## 確定申告レポート (v1.13.0)

`Category.tax_tag` (medical / donation / business / other) で集計した支出取引を年単位で表示・CSV ダウンロードできる。確定申告期の医療費控除集計・ふるさと納税控除等に使用する。

### 事前準備

各カテゴリの「税控除タグ」を設定する:

1. `/settings/` のカテゴリ一覧から該当カテゴリ（例: 「医療費」）の編集ボタンを開く
2. 「税控除タグ」欄で適切なタグを選択
   - **医療費控除**: 医療費・薬代・治療費・通院交通費など
   - **寄附金（ふるさと納税等）**: ふるさと納税・慈善団体への寄附
   - **事業経費**: 副業の通信費・書籍・備品など
   - **その他控除**: セルフメディケーション税制対象品など
3. 保存

タグ未設定（`none`）のカテゴリはレポート対象外。

### 使い方

`/settings/` → 「📑 税控除レポート」 から `/reports/tax-deductions/` を開く。

- 年とタグをセレクトで切替（前年・次年ボタンも利用可）
- HTML プレビューで件数・合計金額・該当取引一覧を確認
- 医療費控除を選ぶと「あと ¥X で控除ライン突破」が表示される（10 万円ライン）
- 「↓ CSV ダウンロード」で `tax-{tag}-{year}.csv` を保存

### CSV 仕様

- 文字コード: UTF-8 BOM 付き（Excel 文字化け対策）
- ヘッダー: `日付,支払先,カテゴリ,金額,メモ`
- 行順: 日付昇順
- CSV インジェクション対策: `=`, `+`, `-`, `@` 始まりのセルにシングルクオート前置

### 想定運用フロー（年末〜申告期）

```
1. 毎年 1 月 / 12 月: 一年使ったカテゴリの tax_tag を見直す
2. 2-3 月: /reports/tax-deductions/?year=前年&tax_tag=medical を開く
3. 合計が控除ライン（¥100,000）を超えていれば申告メリットあり
4. CSV ダウンロード → E-Tax / 確定申告書作成コーナーに転記、または税理士に渡す
5. donation / business / other も同様
```

### 注意

- 補填される金額（保険金等）は本機能では集計しない。確定申告書記入時に手動で差し引くこと
- 取引の「医療を受けた方の氏名」「医療費の区分（診療/医薬品/介護等）」は本アプリでは保持していないので、CSV を Excel 等で加工する際に追加する
- v1.16.0 以降は「💊 医療費控除明細」を使うと、受診者・区分・補填額を含めた **国税庁様式 CSV** が直接出力できる（次節参照）

## 医療費控除明細管理 (v1.16.0)

国税庁「医療費控除の明細書」様式に準拠した医療費明細を管理する機能。v1.13.0 の汎用税控除レポートとは別動線として、医療費控除に特化した精緻な集計を提供する。

### 機能概要

- `/medical-expenses/?year=YYYY` 専用ページで医療費明細を CRUD
- 取引フォームで税控除タグ=医療費控除のカテゴリを選ぶと **HTMX で「受診者 / 医療機関 / 区分 / 補填額」入力欄が自動展開**
- 受診者別・医療機関別の小計集計
- 控除額自動計算（`max(0, 差引合計 − min(100,000, 総所得 × 5%))`）
- 国税庁様式 CSV（医療費控除の明細書に直接転記可能な列順）

### 事前準備

1. `/settings/` → 「📊 年次所得」から **対象年の総所得金額** を登録（源泉徴収票の「給与所得控除後の金額」欄）
   - 未登録でも控除額は 10 万円ラインで暫定計算される（総所得 200 万円超の世帯と同等）
   - 総所得 200 万円以下の世帯は必ず登録する（5% ラインの方が低くなり控除額が増える）
2. カテゴリの税控除タグに「医療費控除」を設定済みであること（v1.13.0 と同じ）

### 入力フロー

**A. 都度入力（推奨）** — 病院・薬局支払い時に取引を入力する際、自動展開される医療費詳細欄に入力:

1. ダッシュボードで「+ 取引を追加」
2. カテゴリで「医療費」（税控除タグ=医療費控除のもの）を選択
3. 「医療費控除の詳細」セクションが自動表示される
4. 受診者・医療機関・区分・補填額（あれば）を入力
5. 保存 → Transaction と MedicalExpense が atomic に同時作成

**B. 後追い入力 / 家計簿外医療費** — `/medical-expenses/new/` から直接登録:

- 保険組合の事後請求書、世帯メンバーが別途決済した医療費 等、Transaction を伴わない医療費を登録する場合
- 区分は 4 択（診療・治療 / 医薬品 / 介護保険サービス / その他）

### CSV 出力

`/medical-expenses.csv?year=YYYY` で `medical-expenses-{year}.csv` をダウンロード。

国税庁「医療費控除の明細書」の列順:

1. 医療を受けた方の氏名
2. 病院・薬局などの支払先の名称
3. 医療費の区分
4. 支払った医療費の額
5. 左のうち、補填される金額
6. 差引額
7. 支払日

末尾に【合計】【控除基準額】【医療費控除額】行を含む。UTF-8 BOM 付き、CSV injection 対策済み。

### 申告フロー

```
1. 翌年 2 月: /medical-expenses/?year=前年 を開く
2. 控除額カードに表示される金額を確認
3. 控除額 > 0 なら申告メリットあり → CSV ダウンロード
4. e-Tax / 確定申告書 第二表 ⑩医療費控除欄に控除額を記入
5. 明細書は CSV をプリントアウトして添付（または e-Tax で取り込み）
```

### 注意

- 補填額（保険金・出産育児一時金 等）は支払額と同年内であれば記録する。年をまたぐ場合は支払時の年に紐付ける
- v1.13.0 `/reports/tax-deductions/?tax_tag=medical` レポートは **後方互換のため残存**。MedicalExpense を登録していないカテゴリ取引は従来通り集計される
- 取引を削除すると `medical_expense_set.transaction` は SET_NULL で残り、MedicalExpense は孤児にならない（手動削除する）
- 月次締め済み月への医療費追加は制限なし（MedicalExpense は Transaction とは独立のため）


## 保険料控除明細管理 (v1.17.0)

生命保険料控除（一般 / 介護医療 / 個人年金）と地震保険料控除を、保険会社から届く「控除証明書」の数値入力から国税庁公式式で自動計算する機能。

### 機能概要

- 専用ページ `/insurance-premiums/?year=YYYY` で CRUD
- 国税庁公式式を整数除算で 1:1 実装
- 新旧契約混在時は **3 方式の最大値**を自動選択（新のみ / 旧のみ / 新ルール合算）
- 生命保険料控除 合算上限 **¥120,000**、地震保険料控除 上限 **¥50,000**
- **年末調整提出済フラグ**で確定申告レポートから除外可能
- 国税庁様式準拠 CSV ダウンロード

### 事前準備

カテゴリ設定不要（v1.13.0 / v1.16.0 と独立。Transaction と紐付かない）。

### 入力フロー

1. 10〜11 月: 保険会社から「生命保険料控除証明書」「地震保険料控除証明書」が到着
2. `/settings/` → 「🛡️ 保険料控除」 → 「+ 保険料を追加」
3. 控除証明書を見ながら以下を入力:
   - **区分**: 一般生命 / 介護医療 / 個人年金 / 地震
   - **契約区分**: 新（2012/1/1 以降）/ 旧（2011/12/31 以前）
     - 介護医療は新契約のみ（フォームで弾く）
     - 地震は不問（保存時 NEW に正規化）
   - **保険会社名 / 証券番号 / 年間支払保険料**（控除証明書の「申告額」または「年間払込予定額」）
   - **年末調整で提出済**: 給与所得者で会社に提出した分は ON
4. 集計カードで控除額が即時表示

### 共済の扱い

県民共済 / 全労済 / JA 共済等は **控除証明書の記載どおり**に区分を選択:
- 「生命保険料控除証明書」に「一般生命保険料」とあれば → 一般生命
- 「個人年金保険料」とあれば → 個人年金
- 介護医療と書かれていれば → 介護医療
- `insurer` には組合名を記入

### 申告フロー

```
1. 翌年 2-3 月: /insurance-premiums/?year=前年 を開く
2. 「年末調整提出済を除外」チェックを ON にする → 確定申告で実際に書く額が表示される
3. 「総控除額」カードの数値を確認 → CSV ダウンロード
4. 申告書 第二表 ⑮生命保険料控除欄 / ⑯地震保険料控除欄 に転記
```

### スコープ外

- **国民年金基金 / 小規模企業共済 / 国民健康保険料 / 国民年金 / 厚生年金 / 介護保険料**（社会保険）
  → これらは「保険料控除」ではなく **社会保険料控除 / 小規模企業共済等掛金控除** に該当。v1.17.0 ではカバーしない
- **旧長期損害保険料控除** — 対象家庭が限定的、需要発生時に v1.17.1 で検討
- **控除証明書 PDF 添付** — 数値のみ保持、紙保管前提

### 注意

- 控除証明書原本は紙で保管する（法令上 5 年保管推奨）。本アプリは数値のみ保持
- 年が変わったら新規入力（前年データは保持される、明細から再登録ボタン等は未実装）
- 介護医療を旧契約で登録しようとするとフォームで弾かれる（2012/1/1 新設のため）



## 確定申告レポート v2 (v1.18.0)

医療費控除（v1.16.0）+ 生命保険料控除・地震保険料控除（v1.17.0）+ 寄附金（v1.13.0 tax_tag=donation）を 1 ページに統合した申告期レポート。確定申告書 第二表の物理レイアウトに沿って 4 セクションを縦に並べ、各セクションに **申告書欄番号の転記支援テキスト**を併記する。

### 機能概要

- 専用ページ `/reports/tax-deductions/v2/?year=YYYY`
- 「年末調整提出済を除外」トグル（デフォルト ON = 確定申告で実際に書く額）
- 1 ファイル統合 CSV `/reports/tax-deductions/v2.csv?year=YYYY`
- v1.13.0 / v1.16.0 / v1.17.0 の各画面は **無変更で残置**（後方互換）

### 使い方

1. `/settings/` → 「📑 確定申告レポート v2」を開く
2. 翌年 2 月に対象年を選択（デフォルト現在年）
3. 「年末調整提出済を除外」が ON（デフォルト）であることを確認
4. 各セクションの「申告書 第二表 ⑩⑮⑯⑲」テキスト通りに転記
5. CSV ダウンロードで全控除の年間サマリを 1 ファイルで保管

### 申告書欄番号マッピング（2026 年現在）

| 欄番号 | 控除 | 本機能の表示 |
|---|---|---|
| ⑩ | 医療費控除 | medical.deduction |
| ⑮ | 生命保険料控除 | insurance.life.total（上限 12 万円適用後） |
| ⑯ | 地震保険料控除 | insurance.earthquake.deduction（上限 5 万円適用後） |
| ⑲ | 寄附金控除 | **年間支払合計のみ表示**（控除額は別途計算） |

※ 様式改訂時はテンプレ `tax_deductions_v2.html` 内の欄番号を手動更新。

### 寄附金の扱い

v1.18.0 では **控除額計算を実装しない**:
- ふるさと納税ワンストップ特例利用時は申告不要 → 計算不要
- 確定申告でふるさと納税控除を取る場合は申告書 B 様式の計算欄で実施
- v2 レポートでは年間支払合計のみ表示し、内訳取引一覧から金額確認

### CSV 構成

1 ファイル + セクション区切りで以下の順に出力:

1. 医療費控除（明細 + 合計 + 控除基準額 + 控除額）
2. 生命保険料控除（3 枠内訳 + 上限適用前/後）
3. 地震保険料控除（明細 + 合計）
4. 寄附金（参考、取引一覧 + 年間合計）
5. 総控除額（⑩+⑮+⑯、寄附金除く）

UTF-8 BOM 付き、`csv_safe_row` injection 対策。

### スコープ外

- ふるさと納税控除額の正確な計算（寄附金特別控除 / 住民税控除）→ v1.19.0 以降
- 還付額シミュレーション
- e-Tax 連携
- 申告書様式の自動 PDF 生成

### 注意

- 申告書欄番号は 2026 年現在の様式に基づく。様式改訂時はテンプレを手動更新
- v1 レポート（`/reports/tax-deductions/?tax_tag=...`）は引き続き利用可能（事業経費 / その他控除タグの集計用）
- 読み取り専用のため AuditLog は記録しない（v1.13.0 と同方針）

