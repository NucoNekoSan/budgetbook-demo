# BudgetBook Specs

このディレクトリは、ClaudeCode が実装前に参照する仕様書置き場です。

実運用中のため、大きな変更は「仕様確認 -> 実装計画 -> 実装 -> テスト -> 報告」の順で進めます。

上位ドキュメント:

- `docs/REQUIREMENTS.md` - 何を作るか
- `docs/TECH_SPEC.md` - どの技術でどう実装するか
- `docs/SECURITY.md` - セキュリティとデータ保護
- `docs/RELEASE_CHECKLIST.md` - 反映前チェック
- `docs/DEV_GUIDE.md` - 開発手順
- `docs/REPO_STRUCTURE.md` - ファイル配置
- `docs/UBIQUITOUS.md` - 用語定義

## Top Priority

BudgetBook は個人の金融情報を扱う実運用アプリです。すべての仕様実装で、セキュリティ、脆弱性対策、コード保守性、DB 可用性を最上位制約にします。

実装前に必ず確認すること:

- セキュリティ影響
- DB 影響
- 既存データへの影響
- テスト計画
- ロールバック方針

守ること:

- 秘密情報や実データを Git 管理しない。
- `DEBUG=False` 運用を前提にする。
- Cloudflare Access 前段 + Django ログインの二重認証を維持する。
- 入力値は Django Form / Model validation を通す。
- destructive migration、既存カラム削除、既存データ変換は原則禁止する。
- migration 前にはバックアップ手順とロールバック時の影響を明記する。
- SQLite DB は永続化、バックアップ、復元を前提に扱う。
- 会計ロジック変更にはテストを追加・更新する。

## バージョン計画

| Version | Theme | Status |
|---|---|---|
| v1.1.0 | 低リスク UX 改善 | 実装完了 |
| v1.2.0 | 口座間振替と繰越金対応 | 実装完了 |
| v1.3.0 | 収入に対する支出比率グラフ | 実装完了 |
| v1.4.0 | 取引一覧のインライン編集 | 実装完了 |
| v1.5.0 | Docker + Cloudflare Tunnel 運用対応 | 実装完了 |
| v1.6.0 | 月次締めと口座残高照合 | 実装完了 |
| v1.7.0 | 重要操作の監査ログ | 実装完了 |
| v1.8.0 | CSV インポート | 実装完了 |
| v1.9.0 | PWA 化 | 実装完了 |
| v1.10.0 | 観測性強化 | 実装完了 |
| v1.11.0 | LoanProfile 利息自動計上 | 実装完了 |
| v1.12.0 | LoanProfile 元金返済 Transfer 自動化 | 実装完了 |
| v1.13.0 | 確定申告レポート（税控除タグ集計） | 実装完了 |
| v1.14.0 | loan_strategy を current balance ベースに | 実装完了 |
| v1.15.0 | Auto payoff projection（B/S 各口座行に「あと N ヶ月」） | 実装完了 |
| v1.16.0 | 医療費控除の本格対応（家族別 + 補填差引 + 区分） | 実装完了 |
| v1.17.0 | 生命保険料控除・地震保険料控除（4 枠別、新旧契約、年調除外） | 実装完了 |
| v1.18.0 | 確定申告レポート v2（医療費+生保+地震+寄附金 統合、申告書欄番号併記） | 実装完了 |
| v1.18.5 | Public Demo / Self-host Distribution（DEMO_MODE + seed_demo_data + 公開 README） | 実装完了 |

## 作業ルール

- 仕様書の受け入れ条件を満たすこと。
- 非対象に書かれた作業を混ぜないこと。
- DB migration を伴う場合は、既存データへの影響とロールバック時の注意を明記すること。
- テストが落ちた場合は、落ちたテスト名と原因を報告すること。
