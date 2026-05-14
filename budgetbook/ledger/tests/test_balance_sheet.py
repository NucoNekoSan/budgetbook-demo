"""個人 B/S（貸借対照表）と Account.kind / Category.tax_tag のテスト。"""
from __future__ import annotations

from datetime import date

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from ledger.models import Account, Category, LoanProfile, Transaction, Transfer
from ledger.services.balance import balance_sheet


class AccountKindFieldTest(TestCase):
    def test_default_kind_is_asset(self):
        a = Account.objects.create(name='デフォ', opening_balance=0)
        self.assertEqual(a.kind, Account.Kind.ASSET)

    def test_liability_account_can_be_created(self):
        a = Account.objects.create(
            name='楽天カード', kind=Account.Kind.LIABILITY, opening_balance=0,
        )
        self.assertEqual(a.kind, 'liability')

    def test_asset_negative_opening_balance_rejected(self):
        a = Account(name='マイナス資産', kind=Account.Kind.ASSET, opening_balance=-1000)
        with self.assertRaises(ValidationError):
            a.full_clean()

    def test_liability_negative_opening_balance_allowed(self):
        # 負債は負値を許容（過去の借入残を表現可能）
        a = Account(name='ローン', kind=Account.Kind.LIABILITY, opening_balance=-50000)
        a.full_clean()  # 例外が出ないこと


class CategoryTaxTagTest(TestCase):
    def test_default_tax_tag_is_none(self):
        c = Category.objects.create(name='食費A', kind=Category.Kind.EXPENSE)
        self.assertEqual(c.tax_tag, Category.TaxTag.NONE)

    def test_set_medical_tax_tag(self):
        c = Category.objects.create(
            name='病院', kind=Category.Kind.EXPENSE,
            tax_tag=Category.TaxTag.MEDICAL,
        )
        self.assertEqual(c.tax_tag, 'medical')


class BalanceSheetServiceTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.bank = Account.objects.create(name='銀行A', kind=Account.Kind.ASSET, opening_balance=100000)
        cls.cash = Account.objects.create(name='現金', kind=Account.Kind.ASSET, opening_balance=20000)
        cls.card = Account.objects.create(name='カード', kind=Account.Kind.LIABILITY, opening_balance=0)
        cls.income_cat = Category.objects.create(name='給与', kind=Category.Kind.INCOME)
        cls.expense_cat = Category.objects.create(name='食費', kind=Category.Kind.EXPENSE)

    def test_basic_balance_sheet(self):
        bs = balance_sheet(date.today())
        self.assertEqual(bs['asset_total'], 120000)
        self.assertEqual(bs['liability_total'], 0)
        self.assertEqual(bs['net_worth'], 120000)
        self.assertEqual(len(bs['assets']), 2)
        self.assertEqual(len(bs['liabilities']), 1)

    def test_card_purchase_increases_liability(self):
        # クレジットカード購入: カード口座から「expense」を切る
        # → カード残高は -3000 (負債が 3000 増)
        Transaction.objects.create(
            date=date.today(), account=self.card, category=self.expense_cat,
            amount=3000, description='カード食費',
        )
        bs = balance_sheet(date.today())
        self.assertEqual(bs['asset_total'], 120000)
        self.assertEqual(bs['liability_total'], 3000)
        self.assertEqual(bs['net_worth'], 117000)


class BalanceSheetViewTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username='bs', password='pass')
        Account.objects.create(name='B/S銀行', kind=Account.Kind.ASSET, opening_balance=50000)

    def setUp(self):
        self.client.login(username='bs', password='pass')

    def test_balance_sheet_page_renders(self):
        resp = self.client.get(reverse('ledger:balance_sheet'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, '正味財産')
        self.assertContains(resp, '資産合計')
        self.assertContains(resp, '負債合計')

    def test_balance_sheet_in_navigation(self):
        resp = self.client.get(reverse('ledger:dashboard'))
        self.assertContains(resp, 'data-route-link="balance_sheet"')

    def test_balance_sheet_shows_payoff_date(self):
        liab = Account.objects.create(
            name='テストリボ', kind=Account.Kind.LIABILITY, opening_balance=-50000,
        )
        LoanProfile.objects.create(
            account=liab, annual_rate_bp=1500, monthly_payment=5000,
            payoff_date=date(2029, 12, 31),
        )
        resp = self.client.get(reverse('ledger:balance_sheet'))
        self.assertContains(resp, '完済予定日')
        self.assertContains(resp, '2029-12-31')

    def test_balance_sheet_shows_source_account(self):
        bank = Account.objects.create(
            name='テスト銀行', kind=Account.Kind.ASSET, opening_balance=100000,
        )
        liab = Account.objects.create(
            name='テストリボ2', kind=Account.Kind.LIABILITY, opening_balance=-50000,
        )
        LoanProfile.objects.create(
            account=liab, annual_rate_bp=1500, monthly_payment=5000,
            source_account=bank,
        )
        resp = self.client.get(reverse('ledger:balance_sheet'))
        self.assertContains(resp, '引落元')
        self.assertContains(resp, 'テスト銀行')


class LoanProfileTest(TestCase):
    def test_loan_profile_only_for_liability(self):
        asset = Account.objects.create(name='銀行X', kind=Account.Kind.ASSET, opening_balance=0)
        with self.assertRaises(ValidationError):
            LoanProfile(account=asset, annual_rate_bp=1500).full_clean()

    def test_annual_rate_pct_property(self):
        liab = Account.objects.create(name='リボA', kind=Account.Kind.LIABILITY, opening_balance=0)
        p = LoanProfile.objects.create(account=liab, annual_rate_bp=1500)
        self.assertAlmostEqual(p.annual_rate_pct, 15.0, places=2)


class BalanceSheetWithLoanTest(TestCase):
    def test_revolving_interest_estimate(self):
        liab = Account.objects.create(name='リボA', kind=Account.Kind.LIABILITY, opening_balance=-400000)
        LoanProfile.objects.create(
            account=liab, annual_rate_bp=1500,  # 15%
            method=LoanProfile.Method.REVOLVING,
            monthly_payment=10000, payment_day=27,
        )
        bs = balance_sheet(date.today())
        item = next(x for x in bs['liabilities'] if x['account'].pk == liab.pk)
        self.assertEqual(item['owed'], 400000)
        # 400000 * 15% = 60000/年, 5000/月
        self.assertEqual(item['annual_interest_est'], 60000)
        self.assertEqual(item['monthly_interest_est'], 5000)
        self.assertEqual(bs['monthly_interest_total'], 5000)
        self.assertEqual(bs['annual_interest_total'], 60000)

    def test_zero_rate_loan_no_interest(self):
        liab = Account.objects.create(name='分割返済C', kind=Account.Kind.LIABILITY, opening_balance=-50000)
        LoanProfile.objects.create(account=liab, annual_rate_bp=0, method=LoanProfile.Method.OTHER)
        bs = balance_sheet(date.today())
        item = next(x for x in bs['liabilities'] if x['account'].pk == liab.pk)
        self.assertEqual(item['owed'], 50000)
        self.assertEqual(item['monthly_interest_est'], 0)
        self.assertEqual(item['annual_interest_est'], 0)


class SelfCheckNegativeAssetTest(TestCase):
    def test_negative_asset_warns(self):
        from io import StringIO
        from django.core.management import call_command
        # 資産口座に大きな支出 → 残高マイナス
        acct = Account.objects.create(name='マイナス検出口座', kind=Account.Kind.ASSET, opening_balance=1000)
        cat = Category.objects.create(name='大支出', kind=Category.Kind.EXPENSE)
        Transaction.objects.create(
            date=date.today(), account=acct, category=cat,
            amount=5000, description='オーバー',
        )
        out = StringIO()
        try:
            call_command('self_check', stdout=out)
        except SystemExit:
            pass
        self.assertIn('negative balance', out.getvalue())