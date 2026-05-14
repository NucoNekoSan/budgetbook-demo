"""月次予算 (SectionBudget) のテスト。"""
from __future__ import annotations

from datetime import date

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from ledger.models import Account, Category, SectionBudget, Transaction
from ledger.services.budget import section_budget_summary


class SectionBudgetModelTest(TestCase):
    def test_unique_section_per_month(self):
        SectionBudget.objects.create(
            month=date(2026, 5, 1),
            section=Category.Section.FOOD_DAILY,
            amount=50000,
        )
        with self.assertRaises(Exception):
            SectionBudget.objects.create(
                month=date(2026, 5, 1),
                section=Category.Section.FOOD_DAILY,
                amount=60000,
            )

    def test_month_must_be_first_of_month(self):
        b = SectionBudget(
            month=date(2026, 5, 15),
            section=Category.Section.FOOD_DAILY,
            amount=50000,
        )
        with self.assertRaises(ValidationError):
            b.full_clean()


class SectionBudgetSummaryTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.account = Account.objects.create(name='予算テスト口座', opening_balance=0)
        cls.cat_food = Category.objects.create(
            name='予算テスト食費', kind=Category.Kind.EXPENSE,
            section=Category.Section.FOOD_DAILY,
        )
        cls.cat_transport = Category.objects.create(
            name='予算テスト交通', kind=Category.Kind.EXPENSE,
            section=Category.Section.TRANSPORT,
        )

    def test_summary_with_budget_set(self):
        SectionBudget.objects.create(
            month=date(2026, 5, 1),
            section=Category.Section.FOOD_DAILY,
            amount=50000,
        )
        Transaction.objects.create(
            date=date(2026, 5, 10), account=self.account, category=self.cat_food,
            amount=20000, description='食費A',
        )
        s = section_budget_summary(date(2026, 5, 1))
        food_row = next(r for r in s['rows'] if r['section'] == 'food_daily')
        self.assertEqual(food_row['budget'], 50000)
        self.assertEqual(food_row['spent'], 20000)
        self.assertEqual(food_row['remaining'], 30000)
        self.assertEqual(food_row['pct_for_display'], 40)
        self.assertFalse(food_row['over'])
        self.assertEqual(s['total_budget'], 50000)
        self.assertEqual(s['total_spent'], 20000)

    def test_over_budget(self):
        SectionBudget.objects.create(
            month=date(2026, 5, 1),
            section=Category.Section.FOOD_DAILY,
            amount=10000,
        )
        Transaction.objects.create(
            date=date(2026, 5, 5), account=self.account, category=self.cat_food,
            amount=15000, description='食費オーバー',
        )
        s = section_budget_summary(date(2026, 5, 1))
        food_row = next(r for r in s['rows'] if r['section'] == 'food_daily')
        self.assertTrue(food_row['over'])
        self.assertEqual(s['over_sections'], 1)

    def test_unset_section_not_shown_when_no_spending(self):
        s = section_budget_summary(date(2026, 5, 1))
        self.assertEqual(s['rows'], [])

    def test_unset_section_shown_when_spending_exists(self):
        Transaction.objects.create(
            date=date(2026, 5, 8), account=self.account, category=self.cat_transport,
            amount=3000, description='交通A',
        )
        s = section_budget_summary(date(2026, 5, 1))
        transport_rows = [r for r in s['rows'] if r['section'] == 'transport']
        self.assertEqual(len(transport_rows), 1)
        self.assertFalse(transport_rows[0]['has_budget'])
        self.assertIn('交通', s['unset_sections'])


class BudgetEditViewTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username='budget', password='pass')

    def setUp(self):
        self.client.login(username='budget', password='pass')

    def test_get_renders(self):
        resp = self.client.get(reverse('ledger:budget_edit'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, '月次予算')
        self.assertContains(resp, '食品・日用品')

    def test_save_creates_budgets(self):
        resp = self.client.post(reverse('ledger:budget_edit') + '?month=2026-05', {
            'month': '2026-05',
            'amount_food_daily': '50000',
            'amount_transport': '10000',
            'action': 'save',
        })
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(SectionBudget.objects.count(), 2)
        food = SectionBudget.objects.get(month=date(2026, 5, 1), section='food_daily')
        self.assertEqual(food.amount, 50000)

    def test_empty_input_deletes_existing(self):
        SectionBudget.objects.create(
            month=date(2026, 5, 1), section='food_daily', amount=50000,
        )
        resp = self.client.post(reverse('ledger:budget_edit') + '?month=2026-05', {
            'month': '2026-05',
            'amount_food_daily': '',
            'action': 'save',
        })
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(SectionBudget.objects.filter(section='food_daily').exists())

    def test_copy_from_previous_month(self):
        SectionBudget.objects.create(
            month=date(2026, 4, 1), section='food_daily', amount=50000,
        )
        SectionBudget.objects.create(
            month=date(2026, 4, 1), section='transport', amount=10000,
        )
        resp = self.client.post(reverse('ledger:budget_edit') + '?month=2026-05', {
            'month': '2026-05',
            'action': 'copy_prev',
        })
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(SectionBudget.objects.filter(month=date(2026, 5, 1)).count(), 2)


class DashboardBudgetPanelTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username='dash', password='pass')
        cls.account = Account.objects.create(name='ダッシュ口座', opening_balance=10000)
        cls.cat = Category.objects.create(
            name='ダッシュ食費', kind=Category.Kind.EXPENSE,
            section='food_daily',
        )

    def setUp(self):
        self.client.login(username='dash', password='pass')

    def test_dashboard_shows_budget_panel(self):
        SectionBudget.objects.create(
            month=date.today().replace(day=1), section='food_daily', amount=50000,
        )
        Transaction.objects.create(
            date=date.today(), account=self.account, category=self.cat,
            amount=10000, description='ダッシュ',
        )
        resp = self.client.get(reverse('ledger:dashboard'))
        body = resp.content.decode('utf-8')
        self.assertIn('月次予算進捗', body)
        self.assertIn('progress-bar', body)