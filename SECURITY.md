# Security Policy

## 脆弱性の報告 / Reporting a Vulnerability

このリポジトリのコードや配布物に **セキュリティ上の脆弱性** を発見された場合、以下の手順でご連絡ください。

### 連絡方法

GitHub の **Security Advisories** 経由で **private に報告**してください:

1. このリポジトリの **Security** タブを開く
2. **Report a vulnerability** をクリック
3. 詳細を記入して送信

→ <https://github.com/NucoNekoSan/budgetbook-demo/security/advisories/new>

### 公開 issue は使わないでください

Public な GitHub Issue として脆弱性を報告すると、修正前に攻撃者にも情報が渡るため、**Security Advisories の private 報告**を必ず使ってください。

### 対応方針

- 受領後、**できる限り早く確認**します（個人運営のため数日かかる場合があります）
- 影響範囲・修正方針を返信します
- 修正後に CVE が割当されるレベルの脆弱性であれば、CVE 申請を行います
- 報告者のクレジット表記を希望される場合は明記してください

## 対応バージョン

| Version | Supported |
|---------|-----------|
| latest `master` / `main` | ✅ |
| それ以前のタグ | ❌ (最新を使ってください) |

## Out of scope

以下は本リポジトリのセキュリティ対象外です:

- セルフホスト時の利用者側の運用ミス（弱いパスワード設定、ポート開放等）
- 第三者の依存ライブラリの既知脆弱性（Dependabot で別途追跡）
- 物理的アクセスを前提とした攻撃

## セルフホスト時の注意

- `seed_demo_data` は **公開デモ／ローカル動作確認専用** です。**本番 DB に対しては絶対に実行しないでください**。実行すると `demo` 一般ユーザーが作成されます（パスワード `demo`、auto-login 前提の read-only 想定）。
- `--create-demo-users` を `DEMO_MODE=1` のときに指定した場合のみ、`admin` superuser が **ランダム生成パスワード** で作成されます（stdout に一度だけ表示。既存 `admin` は上書きしません）。
- 本番運用では `python manage.py createsuperuser` で個別に superuser を作成してください。
- `.env` の `SECRET_KEY` は `python -c "import secrets; print(secrets.token_urlsafe(64))"` 等で十分に長いランダム値を生成し、Git や OneDrive 同期下に置かないでください（`~/.budgetbook-secrets/.env` 推奨。詳細は `budgetbook/.env.example`）。
