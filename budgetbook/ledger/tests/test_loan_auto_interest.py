"""v1.11.0: accrue_loan_interest management command のテスト。"""
from datetime import date
from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from ledger.models import (
    Account,
    AuditLog,
    Category,
    LoanProfile,
    MonthlyClosing,
    Transaction,
)


class AccrueLoanInterestTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        # 利息計上カテゴリ
        cls.interest_cat = Category.objects.create(
            name='金利・手数料',
            kind=Category.Kind.EXPENSE,
        )
        # 利息計上の対象になる負債口座 (16.80% 残債 ¥¥XXX,XXX)
        cls.acct_revolving = Account.objects.create(
            name='クレジットカードA',
            kind=Account.Kind.LIABILITY,
            opening_balance=-500000,
        )
        cls.profile_revolving = LoanProfile.objects.create(
            account=cls.acct_revolving,
            annual_rate_bp=1680,  # 16.80%
            method=LoanProfile.Method.REVOLVING,
        )
        # 利率 0% (対象外)
        cls.acct_zero = Account.objects.create(
            name='分割返済B',
            kind=Account.Kind.LIABILITY,
            opening_balance=-200000,
        )
        cls.profile_zero = LoanProfile.objects.create(
            account=cls.acct_zero,
            annual_rate_bp=0,
        )

    def _call(self, **kwargs):
        out = StringIO()
        err = StringIO()
        call_command('accrue_loan_interest', stdout=out, stderr=err, **kwargs)
        return out.getvalue()

    def test_dry_run_default_lists_eligible(self):
        output = self._call(month='2026-05')
        self.assertIn('[DRY-RUN]', output)
        self.assertIn('クレジットカードA', output)
        # 元本 ¥¥XXX,XXX × 16.80%/12 = ¥5,444.5598 → round = ¥¥X,XXX
        self.assertIn('¥¥X,XXX', output)
        self.assertNotIn('分割返済B', output)  # 0% はスキップ
        # DB は変更されていない
        self.assertEqual(Transaction.objects.count(), 0)
        self.assertEqual(AuditLog.objects.count(), 0)

    def test_zero_rate_profile_skipped(self):
        output = self._call(month='2026-05')
        self.assertNotIn('分割返済B', output)

    def test_inactive_account_skipped(self):
        self.acct_revolving.is_active = False
        self.acct_revolving.save()
        output = self._call(month='2026-05')
        # 残り対象がなくなる
        self.assertIn('対象となる LoanProfile が見つかりませんでした', output)

    def test_apply_creates_transaction(self):
        output = self._call(month='2026-05', apply=True)
        self.assertIn('[APPLY]', output)
        tx = Transaction.objects.get()
        self.assertEqual(tx.date, date(2026, 5, 31))
        self.assertEqual(tx.account, self.acct_revolving)
        self.assertEqual(tx.category, self.interest_cat)
        self.assertEqual(tx.amount, 7000)

    def test_apply_records_audit_log(self):
        self._call(month='2026-05', apply=True)
        log = AuditLog.objects.get()
        self.assertEqual(log.action, AuditLog.Action.CREATE)
        self.assertEqual(log.target_model, 'Transaction')
        self.assertEqual(log.metadata['source'], 'accrue_loan_interest')
        self.assertEqual(log.metadata['month'], '2026-05')
        self.assertEqual(log.metadata['account'], 'クレジットカードA')
        self.assertEqual(log.metadata['interest'], 7000)

    def test_duplicate_month_rejected(self):
        self._call(month='2026-05', apply=True)
        with self.assertRaises(CommandError) as ctx:
            self._call(month='2026-05', apply=True)
        self.assertIn('既に存在', str(ctx.exception))

    def test_closed_month_rejected(self):
        MonthlyClosing.objects.create(
            month=date(2026, 5, 1),
            opening_carry=0, income=0, expense=0, net=0, closing_balance=0,
            account_balances=[],
        )
        with self.assertRaises(CommandError) as ctx:
            self._call(month='2026-05')
        self.assertIn('月次締め済み', str(ctx.exception))

    def test_missing_category_errors(self):
        self.interest_cat.delete()
        with self.assertRaises(CommandError) as ctx:
            self._call(month='2026-05')
        self.assertIn('金利・手数料', str(ctx.exception))

    def test_category_kind_must_be_expense(self):
        self.interest_cat.kind = Category.Kind.INCOME
        self.interest_cat.save()
        with self.assertRaises(CommandError) as ctx:
            self._call(month='2026-05')
        self.assertIn('kind=expense', str(ctx.exception))

    def test_account_filter(self):
        # 別のリボ口座を追加
        acct_b = Account.objects.create(
            name='クレジットカードB',
            kind=Account.Kind.LIABILITY,
            opening_balance=-100000,
        )
        LoanProfile.objects.create(
            account=acct_b, annual_rate_bp=1500,
        )
        output = self._call(month='2026-05', account='クレジットカードA')
        self.assertIn('クレジットカードA', output)
        self.assertNotIn('クレジットカードB', output)

    def test_invalid_month_format(self):
        with self.assertRaises(CommandError):
            self._call(month='2026/05')

    def test_apply_balance_includes_prior_transactions(self):
        """月初時点の残高に過去 Transaction が反映されること。"""
        # 4 月末に追加支出 ¥10,000 (リボ残高が -398,897 になる)
        expense_cat = Category.objects.create(name='テスト支出', kind=Category.Kind.EXPENSE)
        Transaction.objects.create(
            date=date(2026, 4, 30),
            account=self.acct_revolving,
            category=expense_cat,
            amount=10000,
            description='テスト',
        )
        self._call(month='2026-05', apply=True)
        tx = Transaction.objects.filter(category=self.interest_cat).get()
        # 元本 398,897 × 16.80%/12 = 5,584.558 → 5,585
        self.assertEqual(tx.amount, 5585)