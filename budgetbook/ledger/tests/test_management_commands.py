from datetime import date
from io import StringIO
from unittest import mock

from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import OperationalError
from django.test import TestCase

from ledger.models import Account, Category, MonthlyClosing, Transaction


class CheckAccountingIntegrityCommandTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.account = Account.objects.create(name='普通預金A', opening_balance=10000)
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
        self.assertIn('account 普通預金A: +5000', body)

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
