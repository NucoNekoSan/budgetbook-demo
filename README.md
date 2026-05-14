# BudgetBook

> 家計簿 + 個人 B/S + 確定申告レポートを統合した **Django + HTMX + PWA** 製の自己ホスト型ファイナンスアプリ。

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
![Python 3.13+](https://img.shields.io/badge/Python-3.13%2B-blue)
![Django 5.2](https://img.shields.io/badge/Django-5.2-green)
![Tests 500 passing](https://img.shields.io/badge/Tests-500%20passing-brightgreen)

このリポジトリは **公開デモ / セルフホスト配布** 用です。実際のデータは含まれず、`seed_demo_data` コマンドで生成される **架空の 4 人家族家計** のみが入っています。

---

## ✨ 何ができるか

- **日々の家計簿**: 収入・支出・振替を口座別 / カテゴリ別に管理。HTMX によるリアルタイム入力 UX
- **個人バランスシート**: 資産口座（現金・預金・証券）と負債口座（住宅ローン・自動車ローン等）の「正味財産」可視化
- **月次予算と進捗バー**: section 単位の予算設定、超過警告
- **月次締めと残高照合**: 確定済み月の保護、口座残高との突合
- **CSV 入出力**: UTF-8 BOM 付き、CSV injection 対策済み
- **PWA 化**: スマホのホーム画面に追加で「アプリ風」起動
- **監査ログ**: 重要操作（取引/振替/締め/照合）の作成・更新・削除を自動記録
- **🆕 確定申告レポート v2**: 医療費控除・生命保険料控除・地震保険料控除を国税庁様式に準拠した形で集計、申告書欄番号 (⑩⑮⑯⑲) を併記
- **🆕 医療費控除明細**: 受診者・医療機関・区分・補填額を国税庁「医療費控除の明細書」様式で管理
- **🆕 保険料控除**: 新旧契約有利選択を自動計算（生命保険料 3 枠合算上限 12 万円、地震保険料上限 5 万円）
- **🆕 観測性**: `/metrics` JSON、ログイン履歴、5xx 通知メール（任意）

## 📸 Screenshots

> ※ 全てデモデータ（`seed_demo_data --reset` で生成される架空の家計）。

| 画面 | 説明 |
|---|---|
| `/` ダッシュボード | 月次収支サマリ + 取引一覧 |
| `/balance-sheet/` 個人 B/S | 資産・負債・正味財産 |
| `/expense-breakdown/` 支出構成 | カテゴリ別円グラフ + 支出比率 |
| `/budgets/` 月次予算 | section 単位の予算と進捗バー |
| `/reports/tax-deductions/v2/` | 確定申告レポート（医療費 + 生保 + 地震 + 寄附金 統合） |

---

## 🌐 オンラインデモ

> （デモホスティング URL を Release 後に追加予定）

デモは **読み取り専用** です。`DEMO_MODE=1` で `POST/PUT/PATCH/DELETE` がブロックされ、画面は全閲覧可。

---

## 🏠 セルフホストで使う（推奨: Docker）

### 事前準備

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (Windows / macOS)
- または `docker` + `docker compose` (Linux)

### 起動

```bash
git clone https://github.com/YOURNAME/budgetbook-demo.git
cd budgetbook-demo
cp budgetbook/.env.example budgetbook/.env
# .env を開いて SECRET_KEY を任意のランダム文字列に変更してください
docker compose build
docker compose run --rm budgetbook python manage.py migrate
docker compose run --rm budgetbook python manage.py seed_demo_data --reset
docker compose up -d
```

ブラウザで <http://127.0.0.1:8010/> を開く → デモユーザー `demo` / `demo` でログイン。

### Windows ワンクリック起動

```cmd
start-windows.bat
```

`reset-demo-data.bat` でデータをリセット可。

### データ保存場所

| 環境 | DB ファイル |
|---|---|
| Docker | `./data/db.sqlite3` (Docker volume bind mount) |
| 直接 runserver | `budgetbook/db.sqlite3` |

**あなたの家計データはあなたのローカル PC にのみ保存されます**。外部に送信する経路はありません。

### バックアップ

```bash
# Linux / Mac
scripts/backup_budgetbook.sh

# Windows
powershell -ExecutionPolicy Bypass -File scripts/backup_budgetbook.ps1
```

`backup/db-{timestamp}.sqlite3` と SHA256 サイドカーが生成されます。

---

## 🧪 Demo mode 詳細

`.env` の以下フラグで demo 挙動を制御:

| 環境変数 | デフォルト | 効果 |
|---|---|---|
| `DEMO_MODE` | `0` | `1` で「デモデータです」バナー + mutation ブロック |
| `DEMO_ALLOW_WRITES` | `0` | `1` で `DEMO_MODE` 中でも書き込みを許可 |
| `DEMO_AUTO_LOGIN` | `0` | （将来用、未実装）`1` で demo ユーザーで自動ログイン |

**自宅で普通に使う場合は全て `0` のままで OK** です（通常のセルフホスト動作）。

---

## 🔒 セキュリティと プライバシー

- データは **あなたのローカル PC** にのみ保存（外部送信なし）
- HTTPS 化が必要な場合は Cloudflare Tunnel / Nginx 等で前段を構成（リポジトリの `infra/` 参照）
- **ルーターのポート開放は推奨しません**。外部公開する場合は必ず Cloudflare Tunnel 等を経由してください
- 管理画面 URL は `.env` の `ADMIN_URL_PATH` で変更可能
- `django-axes` によるログイン試行回数制限が有効
- CSP / CSRF / Secure cookies / HSTS の段階的ロールアウトをサポート

詳細は [docs/SECURITY.md](docs/SECURITY.md) を参照。

---

## ⚙️ Tech stack

| カテゴリ | 採用技術 |
|---|---|
| Backend | Python 3.13+, Django 5.2 |
| Frontend | HTMX, Vanilla JS, CSS (CSS Variables, Grid, Flexbox) |
| Database | SQLite (WAL mode) |
| Auth | Django auth + `django-axes` |
| Web Server | Gunicorn + Nginx (Docker) / WhiteNoise (静的配信) |
| PWA | Service Worker + Web App Manifest |
| Test | Django TestCase (500 件、全 pass) |
| CI | GitHub Actions |

詳細な設計判断は [docs/TECH_SPEC.md](docs/TECH_SPEC.md) と [docs/DEVELOPMENT_WALKTHROUGH.md](docs/DEVELOPMENT_WALKTHROUGH.md) を参照。

---

## 📜 License

[MIT License](LICENSE) — 自由に fork / 改造 / 自己ホストして使ってください。

---

## ⚠️ 免責

- 本ソフトは **家計管理サンプル** であり、金融助言ではありません
- 確定申告レポートは申告書記入の **補助** です。最終的な記入内容と税額は税理士または税務署にご確認ください
- 自己責任で利用してください
