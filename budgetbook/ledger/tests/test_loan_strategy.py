"""返済戦略シミュレータのテスト。"""
from __future__ import annotations

from datetime import date

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from ledger.models import Account, Category, LoanProfile, Transaction, Transfer
from ledger.services.loan_strategy import (
    LoanState,
    collect_loan_states,
    compare_strategies,
    simulate_payoff,
)


class SimulatePayoffTest(TestCase):
    def test_zero_rate_loan_pays_off_at_minimum(self):
        """無利息ローン: 残高 ÷ 月次返済額 + α ヶ月で完済する。"""
        states = [LoanState(name='無利息', owed=10000, annual_rate_bp=0, monthly_minimum=1000)]
        result = simulate_payoff(states, monthly_extra=0, strategy='avalanche')
        self.assertEqual(result.months_to_payoff, 10)
        self.assertEqual(result.total_interest, 0)

    def test_avalanche_beats_snowball_in_total_interest(self):
        """大残高×高金利と小残高×低金利が混在すると、雪崩法のほうが総利息が小さい。
        雪だるま法は小残高（低金利）から潰すので、高金利の大残高が長く利息を生む。
        """
        states = [
            LoanState(name='大残・高金利', owed=300000, annual_rate_bp=2000, monthly_minimum=5000),  # 20%
            LoanState(name='小残・低金利', owed=50000, annual_rate_bp=300, monthly_minimum=2000),    # 3%
        ]
        av = simulate_payoff(states, monthly_extra=10000, strategy='avalanche')
        sb = simulate_payoff(states, monthly_extra=10000, strategy='snowball')
        self.assertLess(av.total_interest, sb.total_interest)

    def test_extra_payment_shortens_payoff(self):
        states = [LoanState(name='X', owed=100000, annual_rate_bp=1500, monthly_minimum=5000)]
        without = simulate_payoff(states, monthly_extra=0, strategy='avalanche')
        with_extra = simulate_payoff(states, monthly_extra=5000, strategy='avalanche')
        self.assertLess(with_extra.months_to_payoff, without.months_to_payoff)
        self.assertLess(with_extra.total_interest, without.total_interest)

    def test_max_months_safety(self):
        """異常入力（極端に少ない返済額）でも 600ヶ月で打ち切る。"""
        states = [LoanState(name='巨大', owed=10_000_000, annual_rate_bp=2000, monthly_minimum=100)]
        result = simulate_payoff(states, monthly_extra=0, strategy='avalanche')
        self.assertLessEqual(result.months_to_payoff, 600)


class CollectLoanStatesTest(TestCase):
    def test_skips_zero_balance_and_assets(self):
        Account.objects.create(name='資産口座', kind=Account.Kind.ASSET, opening_balance=10000)
        Account.objects.create(name='完済負債', kind=Account.Kind.LIABILITY, opening_balance=0)
        liab = Account.objects.create(name='返済中', kind=Account.Kind.LIABILITY, opening_balance=-50000)
        LoanProfile.objects.create(account=liab, annual_rate_bp=1500, monthly_payment=3000)
        states = collect_loan_states()
        self.assertEqual(len(states), 1)
        self.assertEqual(states[0].name, '返済中')
        self.assertEqual(states[0].owed, 50000)

    def test_reflects_repayment_transfer_in_current_balance(self):
        """v1.12.0 で自動生成された返済 Transfer が残債に反映される。"""
        bank = Account.objects.create(name='銀行', kind=Account.Kind.ASSET, opening_balance=100000)
        liab = Account.objects.create(name='リボ', kind=Account.Kind.LIABILITY, opening_balance=-50000)
        LoanProfile.objects.create(account=liab, annual_rate_bp=1500, monthly_payment=3000)
        # 過去日付で返済 Transfer を作成（today より過去）
        Transfer.objects.create(
            date=date(2020, 1, 15),
            from_account=bank, to_account=liab,
            amount=8000, description='返済',
        )
        states = collect_loan_states()
        # opening_balance -50000 + transfer_in 8000 = -42000 → owed=42000
        self.assertEqual(states[0].owed, 42000)

    def test_reflects_interest_expense_in_current_balance(self):
        """v1.11.0 で自動生成された利息 Transaction が残債を増やす方向に動く。"""
        liab = Account.objects.create(name='リボ', kind=Account.Kind.LIABILITY, opening_balance=-50000)
        LoanProfile.objects.create(account=liab, annual_rate_bp=1500, monthly_payment=3000)
        interest_cat = Category.objects.create(name='金利・手数料', kind=Category.Kind.EXPENSE)
        Transaction.objects.create(
            date=date(2020, 1, 31),
            account=liab, category=interest_cat,
            amount=625, description='1月利息',
        )
        states = collect_loan_states()
        # opening -50000 - expense 625 = -50625 → owed=50625
        self.assertEqual(states[0].owed, 50625)

    def test_as_of_past_returns_state_at_that_date(self):
        """as_of で過去時点の状態を取得できる。"""
        bank = Account.objects.create(name='銀行', kind=Account.Kind.ASSET, opening_balance=100000)
        liab = Account.objects.create(name='リボ', kind=Account.Kind.LIABILITY, opening_balance=-50000)
        LoanProfile.objects.create(account=liab, annual_rate_bp=1500, monthly_payment=3000)
        Transfer.objects.create(
            date=date(2025, 6, 1), from_account=bank, to_account=liab, amount=5000, description='6月返済',
        )
        # 5月時点では返済前
        states_may = collect_loan_states(as_of=date(2025, 5, 31))
        self.assertEqual(states_may[0].owed, 50000)
        # 6月以降は返済済み
        states_jun = collect_loan_states(as_of=date(2025, 6, 30))
        self.assertEqual(states_jun[0].owed, 45000)


class LoanStrategyViewTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username='ls', password='pass')
        liab = Account.objects.create(name='テストリボ', kind=Account.Kind.LIABILITY, opening_balance=-100000)
        LoanProfile.objects.create(account=liab, annual_rate_bp=1500, monthly_payment=5000)

    def setUp(self):
        self.client.login(username='ls', password='pass')

    def test_page_renders(self):
        resp = self.client.get(reverse('ledger:loan_strategy'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, '返済戦略')
        self.assertContains(resp, '雪崩法')
        self.assertContains(resp, '雪だるま法')

    def test_extra_payment_simulation(self):
        resp = self.client.get(reverse('ledger:loan_strategy') + '?extra=10000')
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, '繰上返済した場合')

    def test_compare_strategies_function(self):
        result = compare_strategies(monthly_extra=0)
        self.assertIn('avalanche', result)
        self.assertIn('snowball', result)
        self.assertIn('savings', result)