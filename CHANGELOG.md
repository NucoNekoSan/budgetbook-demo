# Changelog

このプロジェクトの変更履歴。書式は [Keep a Changelog](https://keepachangelog.com/ja/1.1.0/) を参考にし、
バージョニングは [Semantic Versioning](https://semver.org/lang/ja/) に準拠する。

## 運用ルール

- 機能を追加・変更・削除したら **同じ PR で `[Unreleased]` 節に 1 行追記**する。後からまとめて書こうとすると忘れる。
- リリース時に `[Unreleased]` を `[X.Y.Z] - YYYY-MM-DD` に切り替え、新しい `[Unreleased]` を最上部に立てる。
- 区分: `Added` / `Changed` / `Fixed` / `Removed` / `Security` / `Deprecated`。
- 1 行は「ユーザーから見た差分」を書く。実装詳細は git ログに任せる。
- セキュリティ修正は **必ず `Security` で書き出す**。CVE 番号があれば併記。

## [Unreleased]

(現在、未リリースの変更はありません)

## [1.18.5] - 2026-05-14

### Added
- Public Demo / Self-host Distribution 対応
- `DEMO_MODE` / `DEMO_ALLOW_WRITES` / `DEMO_AUTO_LOGIN` 環境変数を追加
- `DemoModeWriteBlockMiddleware`: `DEMO_MODE=1` で mutation を 403 ブロック（GET / login flow は通過）
- `seed_demo_data --reset` 管理コマンド: 一般家庭向け demo データを生成（口座 8 / カテゴリ 21 / 取引 55 / 医療費 6 / 保険料 4 等）
- `base.html` に「デモデータです」バナー（`DEMO_MODE=1` のとき表示）
- `start-windows.bat` / `stop-windows.bat` / `reset-demo-data.bat` / `backup-data.bat` を追加
- 公開用 README / LICENSE (MIT) を整備
- DEMO_MODE / seed_demo_data のテスト 13 件追加（全 500 件 pass）

## [1.18.0] - 2026-05-14

### Added
- `/reports/tax-deductions/v2/` 確定申告レポート v2（医療費 + 生命保険料 + 地震保険料 + 寄附金 を 1 ページに統合、申告書 第二表 ⑩⑮⑯⑲ の欄番号併記）
- `/reports/tax-deductions/v2.csv` 統合 CSV エクスポート（セクション区切り）

## [1.17.0] - 2026-05-14

### Added
- 生命保険料控除・地震保険料控除の管理機能（`InsurancePremium` モデル、`/insurance-premiums/`）
- 新契約 / 旧契約の有利選択を自動計算（生命保険料 3 枠合算上限 ¥120,000、地震保険料上限 ¥50,000）
- 年末調整提出済フラグで確定申告レポートから除外可能
- 国税庁様式準拠 CSV エクスポート

## [1.16.0] - 2026-05-14

### Added
- 医療費控除の本格対応（`MedicalExpense` モデル、`/medical-expenses/`）
- 受診者・医療機関・区分・補填額を国税庁「医療費控除の明細書」様式で管理
- 取引フォームで医療費控除タグ選択時に詳細欄を HTMX で自動展開
- 年次総所得スナップショット（`AnnualIncomeSnapshot`）で控除基準額を正確に計算
- 国税庁様式準拠 CSV エクスポート

## [1.15.0] - 2026-05-13

### Added
- `/balance-sheet/` の各負債口座行に「あと N ヶ月で完済」予測を表示（`loan_projection` サービス）

## [1.14.0] - 2026-05-13

### Changed
- `/loan-strategy/` を実残高ベースに変更（`collect_loan_states` が `all_account_balances` を使い、取引・振替・自動生成された利息/返済をすべて反映）

### Added
- `/balance-sheet/` の負債項目に「完済予定日」と「引落元口座」を表示
- 任意日付での過去断面確認用に `compare_strategies(as_of=...)` を追加

## [1.13.0] - 2026-05-12

### Added
- `/reports/tax-deductions/`（HTML プレビュー）+ `/reports/tax-deductions.csv`（ダウンロード）を新設
- 年 + `tax_tag`（medical / donation / business / other）で支出取引を集計
- 医療費控除選択時に「あと ¥X で控除ライン突破（10 万円）」表示
- 設定ページに「📑 税控除レポート」ボタン
- CSV は UTF-8 BOM 付き、`csv_safe_row` で injection 対策、日付昇順

## [1.12.0] - 2026-05-12

### Added
- `LoanProfile.source_account`（nullable FK）を追加、UI で「引落元口座」を選択可能に
- `python manage.py accrue_loan_principal --month YYYY-MM [--apply] [--account ...]` を新設
- 月次の銀行→負債口座 Transfer を自動生成（dry-run デフォルト、AuditLog 記録、二重計上・締め月拒否）
- migration `0013_loanprofile_source_account`（破壊的でない）

## [1.11.0] - 2026-05-12

### Added
- `python manage.py accrue_loan_interest --month YYYY-MM [--apply] [--account ...]` を新設
- 当月利息相当額を支出 Transaction として自動生成（dry-run デフォルト、`transaction.atomic`、AuditLog 記録）
- `LOAN_INTEREST_CATEGORY_NAME` 設定（デフォルト「金利・手数料」）
- 二重計上 / 月次締め済み月 / 不在カテゴリ / kind ミスマッチを拒否

### Fixed
- 取引フォームで区分・金額・カテゴリ等を変更するとフォーム自体が閉じる不具合（`#transaction-preview` の `hx-target` 継承）

## [1.10.0] - 2026-05-12

### Added
- `/metrics` JSON エンドポイント（ログイン必須、生取引データは含まない）
- `/settings/login-history/` — django-axes の AccessLog / AccessAttempt を表示
- 5xx エラーメール通知（`ERROR_NOTIFY_TO` 設定時のみ、SMTP 経由、レート制限 5 分 / (path, 例外) 組）

### Changed
- 設定ページから「📊 メトリクス JSON」ボタンを削除（監視ツール用エンドポイントなので人間動線に出さない）

## [1.9.0] - 2026-05-12

### Added
- PWA 化: `/manifest.webmanifest`, `/sw.js`, `/offline` を view 経由で配信
- アイコン: SVG + PNG 4 種（192/512/maskable/apple-touch、`scripts/gen_pwa_icons.py` で pure stdlib 生成）
- Service Worker: precache app shell / static は cache-first / HTML は network-first / POST は intercept しない

## [1.8.0] - 2026-05-12

### Added
- `/transactions/import/` プレビュー → 確定の 2 段階 CSV インポート
- UTF-8 (BOM 可) / Shift_JIS 自動判定、上限 1000 行 / 1 MiB
- 口座・カテゴリは名前完全一致のみ、振替はスキップ
- 月次締め済み月への取込拒否、重複検出、CSV インジェクション警告
- 確定処理は `transaction.atomic`、AuditLog に `created_ids` 保存

## [1.7.2] - 2026-05-07

### Added (入力 UX / 集計)
- 取引フォームのリアルタイムプレビュー（保存後の月次合計を即時表示）
- 重複検出（同日同額同カテゴリの soft warning）
- キーボードショートカット（n / / / Esc / ?）
- 月次予算機能（section 単位、進捗バー、超過警告）
- 大分類 (Category.section) 一括振り分け + 一括編集 UI
- 返済戦略シミュレーター（雪崩法 / 雪だるま法 / 繰上返済）
- 月次締めの取消・再計算 + 照合の取消 + 操作説明 UI
- 個人 B/S（資産・負債・正味財産・税控除タグ）
- `LoanProfile`（利率・返済方式・引落日）

### Added (UI/UX overhaul)
- ダークモード対応（システム連動 / 手動切替トグル、`localStorage` に保存）
- ダッシュボードの HERO カード（月末残高 + 当月収支トレンド）
- ナビゲーションに現在ページのアクティブ表示
- HTMX 要求中のローディング状態
- 取引一覧テーブルのモバイルカード化（768px 以下）
- Chart.js のテーマ連動（`budgetbook:theme-changed` イベント）
- favicon (SVG)
- UI 回帰テスト

### Changed
- ダッシュボードの月末残高を資産口座のみに（負債は `/balance-sheet/` へ役割分離）
- Docker compose: LAN 内アクセス許可（`0.0.0.0:8010`）
- 収入比率の円グラフを CSS conic-gradient → Chart.js doughnut に統一
- タイポグラフィ・カラートークン整理、WCAG AA コントラスト調整
- inline `<style nonce>` ブロックを撤廃し CSS に集約

### Removed
- 旧 `.css-pie-chart` 系の CSS（dead code）

## [1.7.1] - 2026-05-04

### Added
- AuditLog に IP / User-Agent を記録（プロキシ信頼ポリシーに準拠）
- ペネトレーション回帰テスト（CSRF / セキュリティヘッダ / XSS / CSV / IDOR / axes / Cookie / 締めガード）
- CSP nonce 化（`<script>` / `<style>` から `'unsafe-inline'` 排除）
- `/healthz` 軽量ヘルスチェック + `?verbose=1` モード（DB 書込み試験 / 会計整合性スポット）
- 構造化 JSON ログ（stdout、`DJANGO_LOG_FORMAT=json`）
- 全ビュー対象の二次レート制限（IP 単位 sliding window、既定 600 req / 60s）
- バックアップ GFS retention（`RETENTION_POLICY=gfs`）
- `scripts/verify_backups.sh` で既存バックアップを SHA256 + integrity_check 再検証
- `prune_audit_logs` 管理コマンド（gzip JSONL アーカイブ + 削除）
- `self_check` 統合健全性コマンド（Django / migration / SQLite / drift / バックアップ鮮度 / AuditLog 保管期間）
- `dependency-audit` CI ジョブ（毎 PR / push で `pip-audit`）
- `Makefile` で運用コマンド集約
- `docs/MAINTENANCE_PLAYBOOK.md` / `docs/DR_RUNBOOK.md`

### Changed
- `MonthlyClosingForm` で未来月の締めをバリデーションエラーに
- `views.py` (1738 行) を `ledger/services/` と `ledger/views/` パッケージに分割
- 残高集計を batched 化して dashboard / closing snapshot / drift の N+1 を解消
- `Account.save` / `Transfer.save` で `full_clean` を実行し、フォーム外保存も検証
- CSP `script-src` / `style-src` から `'unsafe-inline'` を排除し nonce を必須化
- `SECURE_HSTS_SECONDS` 既定を 60 秒（段階展開向け）に変更、preload 整合性検証を追加

### Security
- CSV 出力ヘッダにも `csv_safe_row` を適用
- HSTS preload 有効化前に `SECURE_HSTS_SECONDS >= 31536000` を起動時に強制

## 過去のリリース

実装済みの主要機能（CLAUDE.md 記載）:

- `v1.1.0` 低リスク UX 改善
- `v1.2.0` 口座間振替と繰越金対応
- `v1.3.0` 収入に対する支出比率グラフ
- `v1.4.0` 取引一覧のインライン編集
- `v1.5.0` Docker + Cloudflare Tunnel 運用対応
- `v1.6.0` 月次締めと口座残高照合
- `v1.7.0` 重要操作の監査ログ