from datetime import date
from io import StringIO
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import time
from unittest import mock

from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import OperationalError
from django.test import TestCase

from ledger.models import Account, AuditLog, Category, MonthlyClosing, Transaction


class CheckAccountingIntegrityCommandTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.account = Account.objects.create(name='メイン口座', opening_balance=10000)
        cls.income = Category.objects.create(name='給与', kind=Category.Kind.INCOME)

    def test_no_monthly_closings_is_ok(self):
        out = StringIO()

        call_command('check_accounting_integrity', stdout=out)

        self.assertIn('OK: no monthly closings to check.', out.getvalue())

    def test_matching_monthly_closing_is_ok(self):
        MonthlyClosing.objects.create(
            month=date(2026, 4, 1),
            opening_carry=10000,
            income=0,
            expense=0,
            net=0,
            closing_balance=10000,
            account_balances=[{
                'account_id': self.account.pk,
                'name': self.account.name,
                'opening_balance': self.account.opening_balance,
                'balance': 10000,
                'is_active': True,
            }],
        )
        out = StringIO()

        call_command('check_accounting_integrity', stdout=out)

        self.assertIn('OK: 1 monthly closing(s) are consistent.', out.getvalue())

    def test_drift_fails_by_default(self):
        MonthlyClosing.objects.create(
            month=date(2026, 4, 1),
            opening_carry=10000,
            income=0,
            expense=0,
            net=0,
            closing_balance=10000,
            account_balances=[{
                'account_id': self.account.pk,
                'name': self.account.name,
                'opening_balance': self.account.opening_balance,
                'balance': 10000,
                'is_active': True,
            }],
        )
        Transaction.objects.create(
            date=date(2026, 4, 20),
            account=self.account,
            category=self.income,
            amount=5000,
            description='締め後追加',
        )
        out = StringIO()

        with self.assertRaises(CommandError):
            call_command('check_accounting_integrity', stdout=out)

        body = out.getvalue()
        self.assertIn('DRIFT: 2026-04 monthly closing differs from current ledger.', body)
        self.assertIn('income: +5000', body)
        self.assertIn('account メイン口座: +5000', body)

    def test_drift_warn_only_exits_successfully(self):
        MonthlyClosing.objects.create(
            month=date(2026, 4, 1),
            opening_carry=10000,
            income=0,
            expense=0,
            net=0,
            closing_balance=10000,
            account_balances=[{
                'account_id': self.account.pk,
                'name': self.account.name,
                'opening_balance': self.account.opening_balance,
                'balance': 10000,
                'is_active': True,
            }],
        )
        Transaction.objects.create(
            date=date(2026, 4, 20),
            account=self.account,
            category=self.income,
            amount=5000,
            description='締め後追加',
        )
        out = StringIO()

        call_command('check_accounting_integrity', '--warn-only', stdout=out)

        self.assertIn('WARNING: 1 of 1 monthly closing(s) have drift.', out.getvalue())

    @mock.patch(
        'ledger.management.commands.check_accounting_integrity.enrich_monthly_closings_with_drift',
        side_effect=OperationalError('no such table'),
    )
    def test_unmigrated_database_returns_clear_error(self, _mock_enrich):
        with self.assertRaisesMessage(CommandError, 'Accounting tables are not ready. Run migrations first.'):
            call_command('check_accounting_integrity')


class SelfCheckCommandTest(TestCase):
    def test_backup_freshness_uses_file_mtime_not_name_order(self):
        out = StringIO()
        with TemporaryDirectory() as tmp_dir:
            backup_dir = Path(tmp_dir)
            old_by_mtime_but_late_by_name = backup_dir / 'db-windows-smoke-2026-05-03-084802.sqlite3'
            new_by_mtime = backup_dir / 'db-2026-05-25-174426.sqlite3'
            old_by_mtime_but_late_by_name.write_bytes(b'old')
            new_by_mtime.write_bytes(b'new')
            os.utime(old_by_mtime_but_late_by_name, (0, 0))
            now = time.time()
            os.utime(new_by_mtime, (now, now))

            call_command(
                'self_check',
                backup_dir=str(backup_dir),
                backup_max_age_hours=999999,
                verbose=True,
                stdout=out,
            )

        body = out.getvalue()
        self.assertNotIn('newest backup is', body)
        self.assertNotIn('db-windows-smoke-2026-05-03-084802.sqlite3', body)

    def test_audit_log_hash_chain_failure_fails_self_check(self):
        log = AuditLog.objects.create(
            action=AuditLog.Action.CREATE,
            target_model='Transaction',
            target_id='1',
            target_repr='tamper target',
            summary='before',
            metadata={'amount': 1000},
        )
        AuditLog.objects.filter(pk=log.pk).update(summary='after')

        out = StringIO()
        with TemporaryDirectory() as tmp_dir:
            backup_dir = Path(tmp_dir)
            backup = backup_dir / 'db-2026-05-25-174426.sqlite3'
            backup.write_bytes(b'backup')
            now = time.time()
            os.utime(backup, (now, now))

            with self.assertRaises(SystemExit) as raised:
                call_command(
                    'self_check',
                    backup_dir=str(backup_dir),
                    backup_max_age_hours=999999,
                    stdout=out,
                )

        self.assertEqual(raised.exception.code, 2)
        self.assertIn('AuditLog hash chain failed', out.getvalue())

    @mock.patch('ledger.management.commands.self_check.call_command')
    def test_unapplied_migrations_fail_self_check(self, mocked_call_command):
        def fake_call_command(command_name, *args, **kwargs):
            if command_name == 'migrate':
                raise SystemExit(1)

        mocked_call_command.side_effect = fake_call_command

        out = StringIO()
        with TemporaryDirectory() as tmp_dir:
            backup_dir = Path(tmp_dir)
            backup = backup_dir / 'db-2026-05-25-174426.sqlite3'
            backup.write_bytes(b'backup')
            now = time.time()
            os.utime(backup, (now, now))

            with self.assertRaises(SystemExit) as raised:
                call_command(
                    'self_check',
                    backup_dir=str(backup_dir),
                    backup_max_age_hours=999999,
                    stdout=out,
                )

        self.assertEqual(raised.exception.code, 2)
        self.assertIn('migrate --check reported unapplied migrations', out.getvalue())
