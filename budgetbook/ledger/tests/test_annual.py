from datetime import date

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from ledger.models import Account, Category, Transaction
from ledger.views import parse_year, clamp_future_year


class ParseYearTest(TestCase):

    def test_valid_year(self):
        self.assertEqual(parse_year('2025'), 2025)

    def test_none_returns_current_year(self):
        self.assertEqual(parse_year(None), date.today().year)

    def test_invalid_returns_current_year(self):
        self.assertEqual(parse_year('abc'), date.today().year)


class ClampFutureYearTest(TestCase):

    def test_future_year_clamped(self):
        self.assertEqual(clamp_future_year(2099), date.today().year)

    def test_current_year_not_clamped(self):
        self.assertEqual(clamp_future_year(date.today().year), date.today().year)

    def test_past_year_not_clamped(self):
        self.assertEqual(clamp_future_year(2020), 2020)


class AnnualViewTest(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username='test', password='pass')
        cls.account = Account.objects.create(name='口座A')
        cls.cat_income = Category.objects.create(name='給与', kind=Category.Kind.INCOME)
        cls.cat_expense = Category.objects.create(name='食費', kind=Category.Kind.EXPENSE)

        today = date.today()
        cls.year = today.year

        Transaction.objects.create(
            date=date(cls.year, 1, 15), account=cls.account,
            category=cls.cat_income, amount=10000, description='1月給与',
        )
        Transaction.objects.create(
            date=date(cls.year, 1, 20), account=cls.account,
            category=cls.cat_expense, amount=3000, description='1月食費',
        )
        Transaction.objects.create(
            date=date(cls.year, 3, 10), account=cls.account,
            category=cls.cat_expense, amount=5000, description='3月食費',
        )

    def setUp(self):
        self.client.login(username='test', password='pass')

    def test_annual_page_loads(self):
        resp = self.client.get(reverse('ledger:annual'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, f'{self.year}年 年間サマリー')

    def test_annual_has_12_months(self):
        resp = self.client.get(reverse('ledger:annual'), {'year': self.year})
        self.assertEqual(len(resp.context['months']), 12)

    def test_annual_month_data_correct(self):
        resp = self.client.get(reverse('ledger:annual'), {'year': self.year})
        months = resp.context['months']
        jan = months[0]
        self.assertEqual(jan['income'], 10000)
        self.assertEqual(jan['expense'], 3000)
        self.assertEqual(jan['net'], 7000)

    def test_annual_total_matches_sum(self):
        resp = self.client.get(reverse('ledger:annual'), {'year': self.year})
        months = resp.context['months']
        self.assertEqual(
            resp.context['total_income'],
            sum(m['income'] for m in months),
        )
        self.assertEqual(
            resp.context['total_expense'],
            sum(m['expense'] for m in months),
        )
        self.assertEqual(
            resp.context['total_net'],
            resp.context['total_income'] - resp.context['total_expense'],
        )

    def test_future_year_clamped_to_current(self):
        resp = self.client.get(reverse('ledger:annual'), {'year': 2099})
        self.assertEqual(resp.context['year'], date.today().year)

    def test_empty_months_have_zero(self):
        resp = self.client.get(reverse('ledger:annual'), {'year': self.year})
        feb = resp.context['months'][1]
        self.assertEqual(feb['income'], 0)
        self.assertEqual(feb['expense'], 0)
        self.assertEqual(feb['net'], 0)

    def test_no_next_year_link_for_current_year(self):
        resp = self.client.get(reverse('ledger:annual'), {'year': self.year})
        self.assertIsNone(resp.context['next_year'])

    def test_past_year_has_next_year_link(self):
        resp = self.client.get(reverse('ledger:annual'), {'year': self.year - 1})
        self.assertEqual(resp.context['next_year'], self.year)

    def test_month_link_points_to_dashboard(self):
        resp = self.client.get(reverse('ledger:annual'), {'year': self.year})
        self.assertContains(resp, f'month={self.year}-01')