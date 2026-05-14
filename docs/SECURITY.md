# SECURITY.md - BudgetBook Security Policy

BudgetBook は個人の金融情報を扱う実運用アプリである。利便性より漏洩防止とデータ保護を優先する。

## 1. 原則

1. 秘密情報を Git、ログ、AI プロンプトに含めない。
2. 一般公開しない。アクセス対象は本人と妻に限定する。
3. Django ログインに加え、外部アクセスでは Cloudflare Access を前段に置く。
4. migration は既存データを壊さない。
5. 会計ロジック変更にはテストを追加する。
6. 迷ったら公開しない、削除しない、migration しない側に倒す。

## 2. Django セキュリティ

必須:

- `DEBUG=False`
- `SECRET_KEY` は `.env` のみ。
- `ALLOWED_HOSTS` にワイルドカードを使わない。
- `CSRF_TRUSTED_ORIGINS` は公開 URL のみ。
- `SESSION_COOKIE_HTTPONLY=True`
- `SESSION_COOKIE_SAMESITE=Lax`
- `SECURE_COOKIES=1` により `SESSION_COOKIE_SECURE=True` / `CSRF_COOKIE_SECURE=True`
- `X_FRAME_OPTIONS=DENY`
- `SECURE_CONTENT_TYPE_NOSNIFF=True`
- `SECURE_REFERRER_POLICY=same-origin`
- `Content-Security-Policy` を既定で有効化し、`object-src 'none'` / `frame-ancestors 'none'` / `form-action 'self'` を強制する。
- `django-axes` によるログイン試行制限を維持する。
- `ADMIN_URL_PATH` により管理画面 URL を変更可能な状態を維持する。

HTTPS:

- Cloudflare Tunnel 配下では HTTPS 化を Cloudflare 側に委ね、Django 側の `ENABLE_HTTPS` は OFF のままにする（リダイレクトループ防止）。
- `ENABLE_HTTPS` は SSL リダイレクト/HSTS 用であり、Secure Cookie とは分離する。
- Cloudflare Tunnel など信頼できるリバースプロキシ配下のときだけ `TRUST_PROXY_SSL=1` を設定し、`SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')` を有効にする。
- HTTPS 設定変更は必ず実機確認する。

## 3. 入力検証

- Django Form / Model validation を通す。
- `request.POST` の値を直接信用しない。
- 生 SQL、`extra()`, unsafe な文字列連結は禁止。
- `safe` / `mark_safe` は原則禁止。必要なら理由を明記する。
- CSV 出力では CSV injection を考慮し、ユーザー入力文字列が `=`, `+`, `-`, `@`, tab, CR で始まる場合は式として解釈されないようエスケープする。

## 4. 秘密情報

Git 管理禁止:

- `.env`
- `db.sqlite3`
- `backup/`
- `staticfiles/`
- Cloudflare Tunnel token
- 実運用ログ
- 個人情報を含む export

`.gitignore` / `.dockerignore` で除外し、レビュー時にも確認する。

## 5. DB とバックアップ

SQLite DB は機密情報として扱う。

必須:

- migration 前に `db.sqlite3` のバックアップを取る。
- destructive migration は原則禁止。
- 既存カラム削除、既存データ変換、bulk update は事前承認を取る。
- Docker 化では DB をコンテナ内 ephemeral filesystem に置かない。
- バックアップには `.env` や token を混ぜない。
- 本番 SQLite では `busy_timeout`, `foreign_keys`, `journal_mode=WAL`, `synchronous=NORMAL` を接続時に適用する。
- バックアップは SQLite backup API を使い、`PRAGMA integrity_check` と SHA-256 を記録する。
- バックアップ後に会計整合性チェックを実行し、締め済みスナップショットとの差異があればバックアップを残したまま異常終了させる。
- リストア後は Django check、migration 未適用チェック、会計整合性チェックを実行し、復元後の実行可能性と帳簿整合性を確認する。
- 月次締め済みの月は、通常取引・振替の作成、更新、削除をサーバー側で拒否し、締め後の帳簿改変を防ぐ。
- 重要操作は `AuditLog` に記録し、操作ユーザー、日時、対象、操作内容を追跡できる状態を保つ。

推奨バックアップ:

```bash
scripts/backup_budgetbook.sh
```

## 6. Cloudflare 公開方針

推奨構成:

```text
外出先ブラウザ
-> Cloudflare Access
-> Cloudflare Tunnel
-> 自宅 Ubuntu Server
-> Docker
-> BudgetBook
```

必須:

- ルーターの 80/443 ポート開放をしない。
- Cloudflare Access の Allow policy は本人と妻のメールのみ。
- Django ログインを残す。
- Tunnel token は BudgetBook の `.env` / compose に入れず、Ubuntu host 側の `cloudflared` systemd サービスだけで管理する。
- Cloudflare アカウントは 2FA を有効にする。

## 7. 依存・脆弱性対応

定期対応:

- Django / django-axes / django-htmx / WhiteNoise のセキュリティリリースを確認する。
- Docker 導入後は base image の更新を定期実施する。
- リリース前と月次で `scripts/audit_dependencies.sh` を実行し、Python 依存の既知脆弱性を確認する。
- GitHub Dependabot が作成した依存更新 PR は、CI 成功と release notes を確認してから取り込む。
- リリース前と月次で `scripts/security_static_scan.sh` を実行し、Python コードの静的セキュリティ検査を行う。
- GitHub Actions の無料枠を節約するため、通常 push / PR では Django test のみを実行し、
  依存監査・静的セキュリティスキャン・Docker build は release tag / 週次 schedule / 手動実行に限定する。

```bash
scripts/audit_dependencies.sh
scripts/security_static_scan.sh
```

これらのスクリプトは Docker が使える環境では一時コンテナ内で実行する。
Docker がない場合のみ一時 venv を作る。プロジェクトの `.venv` や本番コンテナには変更を加えない。

対応目標:

| 深刻度 | 対応期限 |
|---|---|
| Critical | 72 時間以内 |
| High | 7 日以内 |
| Medium | 30 日以内 |
| Low | 次回定期更新 |

## 8. インシデント対応

1. 外部アクセスを止める。
2. DB とログを保全する。
3. Cloudflare Access / Tunnel / Django admin のログを確認する。
4. 最後の健全バックアップへ戻す。
5. 原因と再発防止を docs に追記する。
