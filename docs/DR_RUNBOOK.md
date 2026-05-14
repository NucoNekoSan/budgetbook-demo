# BudgetBook 障害復旧 Runbook

パニック時に判断不要で動けることを目的にした、症状ベースのフローチャート。
**症状を一致させて該当章だけ読む**。順番に読まない。

## 索引

- [A. アプリにアクセスできない（タイムアウト）](#a-アプリにアクセスできないタイムアウト)
- [B. ログインできない（自分が axes でロックされた）](#b-ログインできない自分が-axes-でロックされた)
- [C. SQLite DB が破損したように見える](#c-sqlite-db-が破損したように見える)
- [D. 月次締めの drift が出る](#d-月次締めの-drift-が出る)
- [E. バックアップが取れていない](#e-バックアップが取れていない)
- [F. 容量が膨らんだ（DB / AuditLog 肥大化）](#f-容量が膨らんだ-db--auditlog-肥大化)
- [G. Cloudflare Tunnel が落ちている / DNS 解決不可](#g-cloudflare-tunnel-が落ちている--dns-解決不可)
- [H. デプロイ直後に 500 エラーが多発](#h-デプロイ直後に-500-エラーが多発)

---

## A. アプリにアクセスできない（タイムアウト）

1. ローカルから `curl http://127.0.0.1:8010/healthz` (Docker host)
   - 200 OK → ネットワーク経路の問題（→ G 章）
   - つながらない → コンテナが落ちている（次へ）
2. `docker compose ps` でステータス確認
3. 落ちていれば `docker compose logs --tail=200 budgetbook` で原因確認
4. `docker compose up -d budgetbook` で再起動
5. 再起動しても落ちる → H 章

## B. ログインできない（自分が axes でロックされた）

`AXES_FAILURE_LIMIT` (既定 5) を超えて失敗するとロック。`AXES_COOLOFF_TIME` (既定 0.5h) 待つか、強制解除する。

```bash
docker compose exec -T budgetbook python manage.py axes_reset_username <自分のユーザー名>
```

ユーザー全体をリセットしたいとき:
```bash
docker compose exec -T budgetbook python manage.py axes_reset
```

それでもログインできない場合、パスワードを忘れている可能性:
```bash
docker compose exec -T budgetbook python manage.py changepassword <ユーザー名>
```

## C. SQLite DB が破損したように見える

症状: 起動時 500 / `database disk image is malformed` / `self_check` の integrity_check が `ok` 以外。

1. **すぐにアプリを止める**：`docker compose stop budgetbook proxy`
2. 現状ファイルを退避：`cp data/db.sqlite3 data/db.sqlite3.broken-$(date +%F-%H%M%S)`
3. 最新の健全バックアップを特定：
   ```bash
   ls -lt backup/db-*.sqlite3 | head -5
   ./scripts/verify_backups.sh
   ```
4. verify が ok のものから最新を選び、PowerShell なら `scripts\restore_budgetbook.ps1`、Bash なら `scripts/restore_budgetbook.sh` を実行
5. `docker compose up -d` で再開
6. `python manage.py self_check --verbose` で緑確認
7. **退避した broken ファイルは別媒体に保管**（後日のフォレンジック / データ救出に備える）

## D. 月次締めの drift が出る

症状: `self_check` で `N monthly closing(s) drifted: 2026-04` 等。

1. `/accounting` を開き、対象月の drift 詳細を確認（締め時 vs 現在の差分）
2. **正しい状態がスナップショット側か現在側かを判断**
   - 締め後に正当な訂正が入った → 締めを取り直す（admin から削除 → 再作成）
   - 不正な変更が入った → AuditLog (`/admin/ledger/auditlog/`) で誰が何時何を変えたか確認 → 修正
3. `prune_audit_logs` を最近実行したなら、削除したログの archive ファイルも参照する
4. データ整合性が確認できたら新しい締めを登録

## E. バックアップが取れていない

`self_check` の `newest backup is XXh old` 警告が出る、または `backup/` に新しいファイルが出ない。

### Windows
```powershell
Get-ScheduledTask -TaskName 'BudgetBookDailyBackup'
Get-ScheduledTaskInfo -TaskName 'BudgetBookDailyBackup'
```
- 状態が `Disabled` なら `Enable-ScheduledTask`
- 直近実行に失敗していれば `Start-ScheduledTask -TaskName 'BudgetBookDailyBackup'` で手動起動し、エラーを確認
- 再登録は `scripts/register_budgetbook_backup_task.ps1 -Force`

### Linux (systemd timer)
```bash
systemctl --user status budgetbook-backup.timer
journalctl --user -u budgetbook-backup.service -n 100
```

### 共通: 手動で 1 度バックアップ
```bash
./scripts/backup_budgetbook.sh
```

## F. 容量が膨らんだ (DB / AuditLog 肥大化)

```bash
du -sh data/db.sqlite3 backup/
docker compose exec -T budgetbook python manage.py prune_audit_logs --dry-run --keep-days=365
```

実行:
```bash
docker compose exec -T budgetbook python manage.py prune_audit_logs --keep-days=365 --archive-dir=/app/backup/audit
docker compose exec -T budgetbook python -c "from django.db import connection; connection.cursor().execute('VACUUM')"
```

GFS retention に切り替えれば backup/ も自然に縮む:
```bash
RETENTION_POLICY=gfs ./scripts/backup_budgetbook.sh
```

## G. Cloudflare Tunnel が落ちている / DNS 解決不可

公開 URL でアクセスできない、ローカル `/healthz` は 200。

1. Cloudflare Zero Trust ダッシュボードで Tunnel の状態確認
2. `docker compose logs --tail=100 cloudflared` でローカル側エラー確認
3. 復旧見込みが立たない場合、**LAN 直接運用へフォールバック**:
   - PC の LAN IP を `.env` の `ALLOWED_HOSTS` に追加
   - `SECURE_COOKIES=0`, `TRUST_PROXY_SSL=0` で起動
   - スマホ/PC から `http://<LAN_IP>:8010/` で直接アクセス
4. 障害復旧後に `.env` を元に戻す

## I. CSS / JS の変更がブラウザに反映されない

症状: テンプレや CSS を編集してリロードしても古い見た目のまま。

1. `make refresh-ui` を実行する（`collectstatic` + nginx reload）
2. もしくは `docker compose exec budgetbook python manage.py collectstatic --noinput`
3. ブラウザで `Ctrl+Shift+R`（強制再読込）
4. それでも古い場合：
   - `STATIC_VERSION` 環境変数を更新して `docker compose up -d` で再起動 → URL の `?v=...` が変わりキャッシュ完全破棄
   - DevTools の Network タブで `style.css?v=...` の Status を確認（200 なら最新、304 ならキャッシュ）

新規コンテナ起動時は `entrypoint.sh` が必ず `collectstatic` を実行するため、
基本的に「ビルド忘れ」は発生しない。それでも反映されないときは上記順に確認。

## H. デプロイ直後に 500 エラーが多発

直前のデプロイをロールバックする。

```bash
git log --oneline -5
git revert <last-bad-commit>
git push
docker compose build && docker compose up -d
```

migration 由来の場合は復元シナリオ（C 章）に切り替えるかどうか判断。
**migration を逆順実行するより、バックアップから復元する方が安全な場合が多い**。

## チェック後の確認手順（共通）

復旧 / 操作後は必ず:
1. `python manage.py self_check --verbose` が緑
2. `/healthz?verbose=1` が `status: ok`
3. ダッシュボードを開いて当月収支が表示される
4. 何が起きたかを `docs/INCIDENTS.md`（任意）に簡潔に記録