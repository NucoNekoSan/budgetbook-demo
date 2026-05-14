"""v1.12.0: accrue_loan_principal management command のテスト。"""
from datetime import date
from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from ledger.forms import LoanProfileForm
from ledger.models import (
    Account,
    AuditLog,
    LoanProfile,
    MonthlyClosing,
    Transfer,
)


class AccrueLoanPrincipalTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.bank = Account.objects.create(
            name='普通預金A', kind=Account.Kind.ASSET, opening_balance=500000,
        )
        cls.revolving = Account.objects.create(
            name='クレジットカードA', kind=Account.Kind.LIABILITY, opening_balance=-388897,
        )
        cls.zero_loan = Account.objects.create(
            name='分割返済B', kind=Account.Kind.LIABILITY, opening_balance=-184907,
        )
        cls.profile_active = LoanProfile.objects.create(
            account=cls.revolving,
            annual_rate_bp=1680,
            monthly_payment=30000,
            payment_day=27,
            source_account=cls.bank,
        )
        cls.profile_zero = LoanProfile.objects.create(
            account=cls.zero_loan,
            annual_rate_bp=0,
            monthly_payment=5000,
            payment_day=25,
            source_account=cls.bank,
        )

    def _call(self, **kwargs):
        out = StringIO()
        call_command('accrue_loan_principal', stdout=out, stderr=StringIO(), **kwargs)
        return out.getvalue()

    def test_dry_run_lists_eligible(self):
        output = self._call(month='2026-06')
        self.assertIn('[DRY-RUN]', output)
        self.assertIn('クレジットカードA', output)
        self.assertIn('分割返済B', output)  # 0% でも対象
        self.assertIn('¥30,000', output)
        self.assertIn('¥5,000', output)
        self.assertEqual(Transfer.objects.count(), 0)

    def test_no_source_account_skipped(self):
        self.profile_active.source_account = None
        self.profile_active.save()
        output = self._call(month='2026-06')
        self.assertNotIn('クレジットカードA', output)
        self.assertIn('分割返済B', output)

    def test_zero_monthly_payment_skipped(self):
        self.profile_active.monthly_payment = 0
        self.profile_active.save()
        output = self._call(month='2026-06')
        self.assertNotIn('クレジットカードA', output)

    def test_inactive_source_account_skipped(self):
        self.bank.is_active = False
        self.bank.save()
        output = self._call(month='2026-06')
        self.assertIn('対象となる LoanProfile が見つかりませんでした', output)

    def test_inactive_target_account_skipped(self):
        self.revolving.is_active = False
        self.revolving.save()
        output = self._call(month='2026-06')
        self.assertNotIn('クレジットカードA', output)
        self.assertIn('分割返済B', output)

    def test_apply_creates_transfer(self):
        self._call(month='2026-06', apply=True)
        tr = Transfer.objects.get(to_account=self.revolving)
        self.assertEqual(tr.from_account, self.bank)
        self.assertEqual(tr.amount, 30000)
        self.assertEqual(tr.date, date(2026, 6, 27))
        self.assertIn('2026-06 返済', tr.description)

    def test_apply_uses_payment_day(self):
        self._call(month='2026-06', apply=True)
        tr_a = Transfer.objects.get(to_account=self.revolving)
        tr_b = Transfer.objects.get(to_account=self.zero_loan)
        self.assertEqual(tr_a.date.day, 27)
        self.assertEqual(tr_b.date.day, 25)

    def test_payment_day_zero_falls_back_to_month_end(self):
        self.profile_active.payment_day = 0
        self.profile_active.save()
        self._call(month='2026-06', apply=True)
        tr = Transfer.objects.get(to_account=self.revolving)
        self.assertEqual(tr.date, date(2026, 6, 30))  # 6 月は 30 日まで

    def test_payment_day_exceeds_month_end_uses_month_end(self):
        self.profile_active.payment_day = 31
        self.profile_active.save()
        self._call(month='2026-02', apply=True)
        tr = Transfer.objects.get(to_account=self.revolving)
        # 2026 年 2 月は 28 日まで（うるう年ではない）
        self.assertEqual(tr.date, date(2026, 2, 28))

    def test_apply_records_audit_log(self):
        self._call(month='2026-06', apply=True)
        logs = AuditLog.objects.filter(
            metadata__source='accrue_loan_principal',
        )
        self.assertEqual(logs.count(), 2)
        for log in logs:
            self.assertEqual(log.action, AuditLog.Action.CREATE)
            self.assertEqual(log.target_model, 'Transfer')
            self.assertEqual(log.metadata['month'], '2026-06')
            self.assertEqual(log.metadata['source_account'], '普通預金A')

    def test_duplicate_month_rejected(self):
        self._call(month='2026-06', apply=True)
        with self.assertRaises(CommandError) as ctx:
            self._call(month='2026-06', apply=True)
        self.assertIn('既に存在', str(ctx.exception))

    def test_closed_month_rejected(self):
        MonthlyClosing.objects.create(
            month=date(2026, 6, 1),
            opening_carry=0, income=0, expense=0, net=0, closing_balance=0,
            account_balances=[],
        )
        with self.assertRaises(CommandError) as ctx:
            self._call(month='2026-06')
        self.assertIn('月次締め済み', str(ctx.exception))

    def test_account_filter(self):
        output = self._call(month='2026-06', account='クレジットカードA')
        self.assertIn('クレジットカードA', output)
        self.assertNotIn('分割返済B', output)

    def test_zero_rate_loan_still_processed(self):
        # zero_loan は annual_rate_bp=0 だが monthly_payment > 0 なので処理対象
        self._call(month='2026-06', apply=True)
        Transfer.objects.get(to_account=self.zero_loan)  # 例外が出なければ OK

    def test_invalid_month_format(self):
        with self.assertRaises(CommandError):
            self._call(month='2026/06')


class LoanProfileFormSourceAccountTest(TestCase):
    """LoanProfileForm に source_account フィールドが含まれること。"""

    @classmethod
    def setUpTestData(cls):
        cls.bank = Account.objects.create(
            name='普通預金A', kind=Account.Kind.ASSET, opening_balance=500000,
        )
        cls.cash = Account.objects.create(
            name='現金', kind=Account.Kind.ASSET, opening_balance=10000,
        )
        cls.liability = Account.objects.create(
            name='クレジットカードA', kind=Account.Kind.LIABILITY, opening_balance=-100000,
        )

    def test_form_has_source_account_field(self):
        form = LoanProfileForm()
        self.assertIn('source_account', form.fields)

    def test_source_account_choices_only_asset_accounts(self):
        form = LoanProfileForm()
        qs = form.fields['source_account'].queryset
        self.assertIn(self.bank, qs)
        self.assertIn(self.cash, qs)
        self.assertNotIn(self.liability, qs)

    def test_source_account_can_be_empty(self):
        form = LoanProfileForm(data={
            'annual_rate_pct_input': '15.0',
            'method': LoanProfile.Method.REVOLVING,
            'monthly_payment': 0,
            'payment_day': 0,
        })
        form.instance.account = self.liability
        self.assertTrue(form.is_valid(), msg=form.errors)