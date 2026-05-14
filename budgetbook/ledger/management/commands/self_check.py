"""統合健全性コマンド。

`python manage.py self_check` を実行すると以下を 1 度に検証する:

- Django system checks
- migrations 未生成差分の有無
- SQLite PRAGMA (journal_mode=WAL, foreign_keys=on, integrity_check)
- accounting integrity (月次締めスナップショットと現在帳簿の差分)
- バックアップディレクトリの最新ファイル鮮度（既定 36 時間以内）
- AuditLog 最古行の経過日数（保管期間オーバー警告）

長期保守で「今アプリは健全か」を 1 コマンドで把握するための運用補助。
障害発生時はまず `python manage.py self_check --verbose` を実行することを
DR_RUNBOOK / MAINTENANCE_PLAYBOOK で推奨する。
"""
from __future__ import annotations

from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import connection
from django.utils import timezone

from ledger.models import Account, AuditLog, MonthlyClosing
from ledger.services.closing import enrich_monthly_closings_with_drift


class Command(BaseCommand):
    help = 'One-stop health check covering Django, SQLite, accounting, backups, and audit log retention.'

    def add_arguments(self, parser):
        parser.add_argument('--backup-dir', type=str, default='',
                            help='Override backup directory (default: BASE_DIR/backup or /app/backup).')
        parser.add_argument('--backup-max-age-hours', type=int, default=36,
                            help='Warn if newest backup is older than this many hours. Default: 36.')
        parser.add_argument('--audit-max-age-days', type=int, default=400,
                            help='Warn if oldest AuditLog row is older than this many days. Default: 400.')
        parser.add_argument('--verbose', action='store_true',
                            help='Print details of all checks.')

    def handle(self, *args, **options):
        verbose = options['verbose']
        warnings: list[str] = []
        errors: list[str] = []

        def section(title: str):
            if verbose:
                self.stdout.write(self.style.NOTICE(f'\n--- {title} ---'))

        # 1. Django system checks
        section('Django system check')
        try:
            call_command('check', verbosity=0)
            self._ok('django system check')
        except Exception as exc:
            errors.append(f'django system check failed: {exc}')

        # 2. migrations
        section('Migrations')
        try:
            call_command('makemigrations', '--check', '--dry-run', verbosity=0)
            self._ok('migrations are up to date')
        except SystemExit as exc:
            if int(getattr(exc, 'code', 1)) != 0:
                errors.append('makemigrations --check reported pending model changes')
            else:
                self._ok('migrations are up to date')
        except Exception as exc:
            errors.append(f'migrations check failed: {exc}')

        # 3. SQLite PRAGMA
        section('SQLite PRAGMAs')
        if connection.vendor == 'sqlite':
            try:
                with connection.cursor() as cur:
                    cur.execute('PRAGMA journal_mode')
                    journal = cur.fetchone()[0]
                    cur.execute('PRAGMA foreign_keys')
                    fk = cur.fetchone()[0]
                    cur.execute('PRAGMA integrity_check')
                    integrity = cur.fetchone()[0]
                if str(journal).lower() != 'wal':
                    warnings.append(f'SQLite journal_mode={journal} (expected wal)')
                if int(fk) != 1:
                    errors.append('SQLite foreign_keys is OFF')
                if integrity != 'ok':
                    errors.append(f'SQLite integrity_check={integrity}')
                self._ok(f'sqlite journal={journal}, foreign_keys={fk}, integrity={integrity}')
            except Exception as exc:
                errors.append(f'sqlite pragma read failed: {exc}')
        else:
            self._ok(f'non-sqlite backend: {connection.vendor}')

        # 4. accounting integrity
        section('Accounting integrity')
        closings = list(MonthlyClosing.objects.order_by('month'))
        if closings:
            try:
                checked = enrich_monthly_closings_with_drift(closings)
                drifted = [c for c in checked if c.has_drift]
                if drifted:
                    months = ', '.join(c.month.strftime('%Y-%m') for c in drifted)
                    errors.append(f'{len(drifted)} monthly closing(s) drifted: {months}')
                else:
                    self._ok(f'{len(checked)} monthly closing(s) consistent')
            except Exception as exc:
                errors.append(f'accounting drift check failed: {exc}')
        else:
            self._ok('no monthly closings yet')

        # 5. backup freshness
        section('Backup freshness')
        backup_dir = Path(options['backup_dir']) if options['backup_dir'] else self._guess_backup_dir()
        if not backup_dir.exists():
            warnings.append(f'backup directory not found: {backup_dir}')
        else:
            backups = sorted(backup_dir.glob('db-*.sqlite3'), reverse=True)
            if not backups:
                warnings.append(f'no backups in {backup_dir}')
            else:
                newest = backups[0]
                age_hours = (timezone.now().timestamp() - newest.stat().st_mtime) / 3600
                if age_hours > options['backup_max_age_hours']:
                    warnings.append(
                        f'newest backup is {age_hours:.1f}h old (threshold {options["backup_max_age_hours"]}h): {newest.name}'
                    )
                else:
                    self._ok(f'newest backup: {newest.name} ({age_hours:.1f}h old)')

        # 6a. 異常残高検出: 資産口座の残高がマイナス
        section('Asset balance anomalies')
        from ledger.services.balance import all_account_balances
        from datetime import date as _date
        try:
            balances = all_account_balances(_date.today())
            for acct in Account.objects.filter(kind=Account.Kind.ASSET, is_active=True):
                b = balances.get(acct.pk, acct.opening_balance)
                if b < 0:
                    warnings.append(f'asset account "{acct.name}" has negative balance {b}')
            self._ok('asset balances are non-negative')
        except Exception as exc:
            warnings.append(f'asset balance scan failed: {exc}')

        # 6. audit log retention
        section('AuditLog retention')
        oldest = AuditLog.objects.order_by('created_at').values_list('created_at', flat=True).first()
        if oldest:
            age_days = (timezone.now() - oldest).total_seconds() / 86400
            if age_days > options['audit_max_age_days']:
                warnings.append(
                    f'oldest AuditLog row is {age_days:.0f} days old; consider running prune_audit_logs'
                )
            else:
                self._ok(f'oldest AuditLog row {age_days:.0f}d old (threshold {options["audit_max_age_days"]}d)')
        else:
            self._ok('no AuditLog rows yet')

        # サマリー
        self.stdout.write('')
        if errors:
            for e in errors:
                self.stdout.write(self.style.ERROR(f'ERROR: {e}'))
        for w in warnings:
            self.stdout.write(self.style.WARNING(f'WARN:  {w}'))
        if not errors and not warnings:
            self.stdout.write(self.style.SUCCESS('self_check: all green'))
        elif not errors:
            self.stdout.write(self.style.WARNING('self_check: ok with warnings'))
        else:
            self.stdout.write(self.style.ERROR('self_check: FAILED'))
            raise SystemExit(2)

    def _ok(self, message: str) -> None:
        # verbose 時のみ詳細を出す。常に集計サマリーは末尾で表示。
        pass

    def _guess_backup_dir(self) -> Path:
        candidates = [
            Path('/app/backup'),
            Path(settings.BASE_DIR) / 'backup',
            Path(settings.BASE_DIR).parent / 'backup',
        ]
        for c in candidates:
            if c.exists():
                return c
        return candidates[1]