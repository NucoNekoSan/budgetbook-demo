# BudgetBook 保守プレイブック

「半年放置 → 復帰 → 引き続き運用」を可能にするための、未来の自分宛のチェックリスト。
**毎回ゼロから考えない**。判断を要するのは異常検知時だけ。

## 0. 復帰時にまず実行する 1 コマンド

```bash
docker compose exec -T budgetbook python manage.py self_check --verbose
```

`self_check` は Django システムチェック / migrations 差分 / SQLite PRAGMA / 月次締め drift /
バックアップ鮮度 / AuditLog 保管期間を一括検証する。
- `self_check: all green` → 通常運用に復帰してよい。
- `self_check: ok with warnings` → 警告内容を読み、本ドキュメントの「警告別対応」を参照。
- `self_check: FAILED` → 異常。`docs/DR_RUNBOOK.md`（後述）を参照。

## 1. 日次（自動）

すべて自動。手動操作なし。

| 時刻 (例) | 仕組み | 失敗時 |
|---|---|---|
| 03:30 | `scripts/backup_budgetbook.sh` (Windows: 登録済タスク) | 失敗ログを確認、`backup/` の最新ファイル日時を確認 |
| - | バックアップ書き込み時に SHA256 + integrity_check | 失敗時はバックアップ自体が作られない |

## 2. 週次（自動 + 軽い目視）

| 時刻 (例) | 仕組み | チェック |
|---|---|---|
| 日 04:00 | `scripts/verify_backups.sh`（cron 推奨） | エラー出力なしか確認 |
| 任意 | dependabot からの PR 一覧確認 | `dependency-audit` ジョブが green な PR は基本マージ可。後述「依存更新の判断」 |
| 月初め | `python manage.py prune_audit_logs --dry-run --keep-days=365` | 件数が想定外に多くないか |

## 3. 月次（手動 5 分想定）

毎月 1 日に実施。

1. `python manage.py self_check --verbose` を実行し緑を確認
2. `python manage.py check_accounting_integrity` で drift がないことを確認
3. ダッシュボードを開き、前月の家計が正しく集計されているか目視
4. `/accounting` で月次締め登録（前月分）
5. 必要なら口座照合を入力（残高合わせ）
6. **monthly closing がないと drift detect が無意味なので毎月締める**

## 4. 四半期（30 分想定）

- `git fetch && git log master..origin/master` で取り込み忘れがないか
- dependabot の保留 PR をまとめてレビュー → マージ
- `pip-audit` で報告された警告があれば対応
- `RELEASE_CHECKLIST.md` を眺め直し、現運用と齟齬がないか

## 5. 年次

- `SECRET_KEY` のローテーション検討（漏洩疑いがなければ強制ではない）
- `ADMIN_URL_PATH` 変更の検討
- HSTS preload を検討（運用安定確認後）→ `.env.example` の段階的ロールアウト参照
- `prune_audit_logs --keep-days=365 --archive-dir=...` で AuditLog をアーカイブ
- 古いバックアップ（GFS で残った monthly 12 ヶ月分以外）を別媒体にオフサイト保管

## 6. 警告別対応

| `self_check` 出力 | 対処 |
|---|---|
| `newest backup is XXh old` | バックアップタスクが止まっている。Windows: タスクスケジューラで `BudgetBookDailyBackup` の状態確認 |
| `SQLite journal_mode=DELETE` | 何か (たぶん手動スクリプト) が WAL を切った。再起動で復帰 |
| `oldest AuditLog row is XXX days old` | `prune_audit_logs --archive-dir=...` を実行 |
| `N monthly closing(s) drifted` | 帳簿が締め後に変更されている。`/accounting` で内容確認、必要なら締めを取り直し |
| `pending model changes` | `models.py` を編集して migration を作っていない。`makemigrations` を実行 |

## 7. 復旧シナリオへのリンク

すべて `docs/DR_RUNBOOK.md` に集約。

- DB ファイル破損
- 認証ロックアウト（自分の axes ロックを解除する手順）
- Cloudflare Tunnel 障害 → ローカル LAN 直接運用へのフォールバック
- 監査ログ肥大化による DB 肥大

## 8. 依存更新の判断（dependabot 対応）

dependabot は週次月曜 9:00 JST で `pip` / `docker` / `github-actions` の PR を生成する。
major バージョン更新は ignore 設定済みのため通常は patch / minor のみ届く。

| 種別 | 対応 | 確認ポイント |
|---|---|---|
| security alert | 即マージ | CI green、`dependency-audit` ジョブパス |
| pip: Django patch (5.2.x → 5.2.y) | CI green ならマージ | release notes (security 修正の有無) |
| pip: その他 patch/minor | CI green ならマージ | テスト数が変わっていないか |
| docker base image (python:3.12-slim) | minor 以上は dependabot 側で抑止済 | patch なら CI green でマージ |
| github-actions | green ならマージ | actions の breaking change 履歴を一読 |
| 上記が ignore されているはずの major | dependabot config を見直す | PR は通常閉じる |

### 月内処理ルール

- 月初の月次保守タイミング（§3）でその月の dependabot PR をまとめてレビュー。
- 1 週間以上 stale な PR があれば閉じて新しい再生成を待つ（rebase 競合の温床）。
- マージしたら `CHANGELOG.md` の `[Unreleased] / Security` または `Changed` に 1 行残す。

迷ったらマージしない。長期保守では「何もしない」も正しい選択肢。

## 9. スマホからの簡易メンテ

PC 不在時にスマホだけで対処する想定。Cloudflare Tunnel が生きていれば公開 URL で
`/admin/` および `/accounting/` にアクセス可能。

| やりたいこと | スマホ可能か | 操作 |
|---|---|---|
| 取引/振替の追加・編集・削除 | 可能 | ダッシュボードから通常操作。HTMX UI はスマホ最適化済み |
| 月次締め登録 | 可能 | `/accounting` で締めボタン |
| AuditLog 確認 | 可能 | `/admin/ledger/auditlog/` （read-only） |
| バックアップ取得 | 不可 | サーバー側 cron / タスクスケジューラに依存。手動実行は SSH 必要 |
| DB 復元 | 不可 | C 章どおり host で `restore_budgetbook.*` 実行 |
| `self_check` | 不可 | SSH / RDP 必要。代替: `/healthz?verbose=1` を URL でアクセス |

スマホで `/healthz?verbose=1` を叩き `status: ok` を確認するだけでも、
DB 疎通 / 書込み / 直近月次締めの整合性まで一括確認できる。

## 10. ホスト不在時の自動復帰

Windows 自動更新による再起動や停電復電後にアプリが上がっていない事故を防ぐ。

### Docker Compose の restart policy

`docker-compose.yml` の `restart: unless-stopped` を確認すること。
明示的に `docker compose stop` した場合以外は OS 起動時に自動で再開する。

### 起動後の自動検証

タスクスケジューラ（Windows）または systemd timer（Linux）で、
OS 起動 5 分後に下記を実行する設定を推奨:

```bash
# 例: cron / scheduled task
docker compose exec -T budgetbook python manage.py self_check >> /var/log/budgetbook/boot_check.log 2>&1
```

`SystemExit 2` が返ったら通知を飛ばす運用にすると、自動復帰時の不整合を早期検知できる。

### バックアップタスクの再有効化確認

OS 再起動後、`BudgetBookDailyBackup` が `Disabled` になっていないかを月次保守で確認する（§3）。

## 11. このアプリを誰かに引き継ぐ場合

1. `CLAUDE.md` / `docs/REQUIREMENTS.md` / `docs/SECURITY.md` / 本ドキュメント / `DR_RUNBOOK.md` を読んでもらう
2. `.env.example` をコピーして `.env` を作成
3. `docker compose up -d` で起動
4. `python manage.py self_check --verbose` で疎通確認

以上で運用開始可能。秘密情報（`.env`、Cloudflare token、admin パスワード）は別経路で渡す。