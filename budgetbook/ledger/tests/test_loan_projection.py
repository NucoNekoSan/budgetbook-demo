"""単一負債口座の完済予測 (v1.15.0) のテスト。

spec: docs/specs/v1.15.0_auto_payoff_projection.md
"""
from __future__ import annotations

from datetime import date

from django.test import TestCase

from ledger.models import Account, Category, LoanProfile, Transaction
from ledger.services.balance import balance_sheet
from ledger.services.loan_projection import project_fixed_principal_payoff


class LoanProjectionServiceTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.expense_cat = Category.objects.create(name='食費', kind=Category.Kind.EXPENSE)

    def _make_liability(self, name: str, opening: int) -> Account:
        return Account.objects.create(
            name=name, kind=Account.Kind.LIABILITY, opening_balance=opening,
        )

    def test_interest_bearing_loan_projects_finite_months(self):
        # 利息ありローン (demo ラウンド値): 残¥500,000 / 年16.80% / 月¥10,000
        acc = self._make_liability('クレジットカードA', -500_000)
        LoanProfile.objects.create(
            account=acc, annual_rate_bp=1680, monthly_payment=10_000, payment_day=27,
        )
        r = project_fixed_principal_payoff(acc, as_of=date(2026, 5, 1))
        self.assertIsNotNone(r)
        self.assertIsNone(r['warning'])
        self.assertEqual(r['monthly_payment'], 10_000)
        self.assertEqual(r['owed'], 500_000)
        # 月利息 = 500,000 × 16.80%/12 = 7,000 (ちょうど)
        self.assertEqual(r['next_interest'], 7_000)
        # 雪崩 1 件単独でも完済まで > 0 ヶ月
        self.assertIsNotNone(r['months_remaining'])
        self.assertGreater(r['months_remaining'], 0)
        self.assertGreater(r['total_interest'], 0)
        self.assertIsNotNone(r['payoff_date'])

    def test_zero_interest_loan_uses_ceil(self):
        # 利息ゼロローン (demo ラウンド値): 残¥50,000 / 0% / 月¥5,000
        acc = self._make_liability('ショッピング分割', -50_000)
        LoanProfile.objects.create(
            account=acc, annual_rate_bp=0, monthly_payment=5_000, payment_day=0,
        )
        r = project_fixed_principal_payoff(acc, as_of=date(2026, 5, 1))
        self.assertEqual(r['months_remaining'], 10)
        self.assertEqual(r['total_interest'], 0)
        self.assertEqual(r['total_paid'], 50_000)
        self.assertEqual(r['next_interest'], 0)
        self.assertIsNone(r['warning'])

    def test_payment_below_interest_warns(self):
        # 残¥100,000 / 18% (月利 1.5%) / 月¥1,000 < 月利息 ¥1,500 → 永遠に減らない
        acc = self._make_liability('破綻リボ', -100_000)
        LoanProfile.objects.create(
            account=acc, annual_rate_bp=1800, monthly_payment=1_000, payment_day=27,
        )
        r = project_fixed_principal_payoff(acc, as_of=date(2026, 5, 1))
        self.assertEqual(r['warning'], 'payment_below_interest')
        self.assertIsNone(r['months_remaining'])
        self.assertIsNone(r['payoff_date'])

    def test_no_profile_returns_none(self):
        acc = self._make_liability('プロファイル無', -50_000)
        r = project_fixed_principal_payoff(acc, as_of=date(2026, 5, 1))
        self.assertIsNone(r)

    def test_zero_monthly_payment_returns_none(self):
        acc = self._make_liability('分割返済B', -200_000)
        LoanProfile.objects.create(
            account=acc, annual_rate_bp=0, monthly_payment=0,
        )
        r = project_fixed_principal_payoff(acc, as_of=date(2026, 5, 1))
        self.assertIsNone(r)

    def test_already_paid_off_returns_none(self):
        # owed <= 0 のケース (口座が誤って資産化、または手入力で完済済)
        acc = self._make_liability('完済済', 0)
        LoanProfile.objects.create(
            account=acc, annual_rate_bp=1500, monthly_payment=5_000, payment_day=27,
        )
        r = project_fixed_principal_payoff(acc, as_of=date(2026, 5, 1))
        self.assertIsNone(r)

    def test_uses_current_balance_not_opening(self):
        # opening -50,000 だが、取引で -10,000 追加して -60,000 になる想定
        acc = self._make_liability('動的残高', -50_000)
        LoanProfile.objects.create(
            account=acc, annual_rate_bp=0, monthly_payment=10_000, payment_day=27,
        )
        Transaction.objects.create(
            date=date(2026, 4, 15), account=acc, category=self.expense_cat,
            amount=10_000, description='カード利用',
        )
        r = project_fixed_principal_payoff(acc, as_of=date(2026, 5, 1))
        # owed = 60,000 / monthly 10,000 → 6 ヶ月
        self.assertEqual(r['owed'], 60_000)
        self.assertEqual(r['months_remaining'], 6)

    def test_next_payment_date_month_end(self):
        # payment_day=0 → 月末
        acc = self._make_liability('月末ローン', -10_000)
        LoanProfile.objects.create(
            account=acc, annual_rate_bp=0, monthly_payment=5_000, payment_day=0,
        )
        r = project_fixed_principal_payoff(acc, as_of=date(2026, 5, 1))
        self.assertEqual(r['next_payment_date'], date(2026, 5, 31))


class BalanceSheetProjectionIntegrationTest(TestCase):
    def test_balance_sheet_attaches_projection_to_liabilities(self):
        acc = Account.objects.create(
            name='リボA', kind=Account.Kind.LIABILITY, opening_balance=-100_000,
        )
        LoanProfile.objects.create(
            account=acc, annual_rate_bp=1500, monthly_payment=10_000, payment_day=27,
        )
        # 手入力 payoff_date あり + 自動予測も併記される想定
        acc.loan_profile.payoff_date = date(2027, 12, 31)
        acc.loan_profile.save()

        bs = balance_sheet(date(2026, 5, 1))
        self.assertEqual(len(bs['liabilities']), 1)
        item = bs['liabilities'][0]
        self.assertIn('projection', item)
        self.assertIsNotNone(item['projection'])
        self.assertGreater(item['projection']['months_remaining'], 0)
        # 既存フィールドは維持されている
        self.assertEqual(item['owed'], 100_000)
        self.assertEqual(item['profile'].payoff_date, date(2027, 12, 31))

    def test_balance_sheet_projection_none_for_unprofiled_liability(self):
        Account.objects.create(
            name='プロファイル無負債', kind=Account.Kind.LIABILITY, opening_balance=-5_000,
        )
        bs = balance_sheet(date(2026, 5, 1))
        item = next(i for i in bs['liabilities'] if i['account'].name == 'プロファイル無負債')
        self.assertIsNone(item['projection'])