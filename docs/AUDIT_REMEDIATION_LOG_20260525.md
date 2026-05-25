# Audit Remediation Log - 2026-05-25

## Scope

2026-05-25 のプロジェクト監査に基づく改善ログ。対象は BudgetBook の運用・セキュリティ・会計整合性・アクセシビリティ・DB性能・復旧可能性。

## Completed Remediations

### Backup / Restore

- private repo の監査修正を demo repo に移植し、バックアップ/復元手順を同期。
- `self_check` のバックアップ鮮度判定をファイル名順ではなく `mtime` 順へ修正。
- `self_check` に `migrate --check` を追加し、未適用 migration を明示検出できるようにした。
- 非破壊の復旧演習スクリプト `scripts/restore_drill_budgetbook.ps1` を追加。
- demo repo では本番DBの置換は行わず、テストDBと静的検証で移植妥当性を確認。

### Health / Operations

- `/healthz?verbose=1` を `HEALTHZ_VERBOSE_ENABLED=1` 明示時だけ詳細診断する設計へ変更。
- verbose healthz が未認証で重い DB / 会計チェックを常時実行しないようにした。
- DR / maintenance / operations docs を更新。

### CSV Import

- CSV import の commit path で `Transaction.full_clean()` を実行し、`bulk_create` 前にモデル制約違反を検出。
- commit validation 失敗時は 500 ではなく user-facing error と redirect にする。
- 失敗時に部分書き込みが発生しないことをテストで固定。

### Accessibility

- 全 ledger table に `caption` と `th scope="col"` を付与。
- 主要画面と補助画面のテーブルを screen reader / mobile responsive table の構造に合わせた。
- `test_template_accessibility.py` を追加し、今後の table caption / th scope 漏れを静的検査。

### Dependency / Runtime Reproducibility

- runtime dependency constraints `budgetbook/requirements.lock` を追加。
- Docker build が `requirements.lock` を constraints として参照するように変更。
- `docker compose config --quiet` で構成整合を確認。

### Database Performance

- `Transaction`, `Transfer`, `AccountReconciliation` の月次・口座別 hot path に複合 index を追加。
- migration `0019_performance_indexes.py` を追加。
- index metadata の回帰テストを追加。

### RBAC

- `LEDGER_STAFF_ONLY=1` を追加し、Django 側で非 staff ユーザーの ledger private endpoint 到達を 403 にできるようにした。
- public operational / PWA / auth / admin paths は除外。
- staff / non-staff / anonymous / public exempt path のテストを追加。

### AuditLog Integrity

- `prune_audit_logs --archive-dir` が gzip JSONL archive に加えて `.sha256` sidecar を生成するようにした。
- `AuditLog` に `prev_hash` / `row_hash` を追加し、`verify_audit_log_chain` で改ざん検知できるようにした。
- `self_check` に AuditLog hash-chain 検証を統合し、日常点検で改ざん検知できるようにした。
- archive checksum の一致をテストで固定。
- operations / maintenance / DR docs に checksum と hash-chain 検証手順を追記。

## Validation Results

- `.venv-mirror\Scripts\python.exe budgetbook\manage.py test ledger --verbosity 1`: 585 tests OK
- `.venv-mirror\Scripts\python.exe budgetbook\manage.py test ledger.tests.test_csv_import --verbosity 2`: 31 tests OK
- `.venv-mirror\Scripts\python.exe budgetbook\manage.py makemigrations --check --dry-run`: OK
- `.venv-mirror\Scripts\python.exe budgetbook\manage.py check`: OK
- `.venv-mirror\Scripts\python.exe budgetbook\manage.py migrate --check`: OK after applying `ledger.0019` / `ledger.0020` to local ignored demo DB
- `.venv-mirror\Scripts\python.exe budgetbook\manage.py verify_audit_log_chain`: OK (`0 row(s)`)
- `.venv-mirror\Scripts\python.exe budgetbook\manage.py self_check --verbose`: OK with demo warnings
  - `backup directory not found: C:\budgetbook-demo\budgetbook\backup`
  - demo seed asset balances include negative `現金` / `電子マネー`
- `docker compose config --quiet`: OK
- `git diff --check`: OK（CRLF conversion warning only）
- `bash scripts/audit_docs_sensitive.sh`: OK
- Diff / untracked secret-pattern scan: OK（`.env.example` placeholder / test password fixtures only）

## Recommended Commit Split

1. `ops: harden backup health and restore drill`
   - `self_check` backup freshness fix
   - `restore_drill_budgetbook.ps1`
   - restore drill log and DR / operations docs

2. `security: gate verbose healthz and add staff-only mode`
   - `HEALTHZ_VERBOSE_ENABLED`
   - `LEDGER_STAFF_ONLY`
   - RBAC tests and environment docs

3. `fix: validate csv import rows before bulk create`
   - `CsvImportCommitError`
   - `full_clean()` before `bulk_create`
   - CSV import error handling tests

4. `a11y: add captions and scoped headers to ledger tables`
   - template table captions / header scopes
   - static template accessibility test

5. `perf: add ledger hot-path indexes`
   - model indexes
   - `0019_performance_indexes.py`
   - index metadata test

6. `ops: lock runtime dependencies and harden audit archives`
   - `requirements.lock`
   - Docker constraints install
   - AuditLog hash chain / archive `.sha256`
   - prune tests and docs

## Remaining Recommendations

- Run `pip-audit` again after dependency lock updates when network / tool environment is stable.
- Consider external signing or off-host append-only export if stronger tamper evidence is required than the in-DB hash chain.
- Decide whether `LEDGER_STAFF_ONLY=1` should be enabled in production after confirming daily users have `is_staff=True`.
