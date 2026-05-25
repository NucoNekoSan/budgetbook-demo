# Restore Drill Log - 2026-05-25

## Scope

- Mode: non-destructive sandbox restore drill
- Backup: `backup/db-2026-05-25-174426.sqlite3`
- Backup size: 712,704 bytes
- Production DB: `data/db.sqlite3`
- Production DB last write before/after drill: unchanged during drill (`2026-05-25 16:43:13`)

## Command

```powershell
powershell -ExecutionPolicy Bypass -File scripts\restore_drill_budgetbook.ps1
```

## Result

- `backup sha256: ok`
- `backup integrity_check: ok`
- Temporary restore DB was created under `%TEMP%`
- `python manage.py check`: OK
- `python manage.py migrate --noinput`: applied `ledger.0019_performance_indexes` to the temporary DB
- `python manage.py migrate --check`: OK
- `python manage.py check_accounting_integrity`: OK (`no monthly closings to check`)
- `restore drill: ok`
- Docker services were not stopped
- `data/db.sqlite3` was not replaced

## Follow-up

- No recovery action required.
- Keep using the same non-destructive drill after schema migrations and before any destructive restore.
