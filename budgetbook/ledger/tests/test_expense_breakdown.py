from datetime import date

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from ledger.models import Account, Category, Transaction


class ExpenseBreakdownViewTest(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username='test', password='pass')
        cls.account = Account.objects.create(name='口座A')
        cls.cat_income = Category.objects.create(name='給与', kind=Category.Kind.INCOME)
        cls.cat_food = Category.objects.create(name='食費', kind=Category.Kind.EXPENSE)
        cls.cat_transport = Category.objects.create(name='交通費', kind=Category.Kind.EXPENSE)

        today = date.today()
        cls.year = today.year
        cls.month = today.month

        Transaction.objects.create(
            date=date(cls.year, cls.month, 5), account=cls.account,
            category=cls.cat_food, amount=3000, description='スーパー',
        )
        Transaction.objects.create(
            date=date(cls.year, cls.month, 10), account=cls.account,
            category=cls.cat_food, amount=2000, description='コンビニ',
        )
        Transaction.objects.create(
            date=date(cls.year, cls.month, 15), account=cls.account,
            category=cls.cat_transport, amount=1000, description='電車',
        )
        Transaction.objects.create(
            date=date(cls.year, cls.month, 1), account=cls.account,
            category=cls.cat_income, amount=50000, description='給与',
        )

    def setUp(self):
        self.client.login(username='test', password='pass')

    def test_page_loads(self):
        resp = self.client.get(reverse('ledger:expense_breakdown'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, '支出構成')

    def test_requires_login(self):
        self.client.logout()
        resp = self.client.get(reverse('ledger:expense_breakdown'))
        self.assertEqual(resp.status_code, 302)

    def test_monthly_total(self):
        resp = self.client.get(reverse('ledger:expense_breakdown'))
        self.assertEqual(resp.context['monthly_total'], 6000)

    def test_monthly_rows_sorted_by_amount_desc(self):
        resp = self.client.get(reverse('ledger:expense_breakdown'))
        rows = resp.context['monthly_rows']
        self.assertEqual(rows[0]['category__name'], '食費')
        self.assertEqual(rows[0]['total'], 5000)
        self.assertEqual(rows[1]['category__name'], '交通費')
        self.assertEqual(rows[1]['total'], 1000)

    def test_monthly_percentages(self):
        resp = self.client.get(reverse('ledger:expense_breakdown'))
        rows = resp.context['monthly_rows']
        self.assertAlmostEqual(rows[0]['pct'], 83.3, places=1)
        self.assertAlmostEqual(rows[1]['pct'], 16.7, places=1)

    def test_yearly_total(self):
        resp = self.client.get(reverse('ledger:expense_breakdown'))
        self.assertEqual(resp.context['yearly_total'], 6000)

    def test_income_excluded(self):
        resp = self.client.get(reverse('ledger:expense_breakdown'))
        names = [r['category__name'] for r in resp.context['monthly_rows']]
        self.assertNotIn('給与', names)

    def test_zero_data_month(self):
        resp = self.client.get(
            reverse('ledger:expense_breakdown'), {'month': '2020-01', 'year': '2020'}
        )
        self.assertEqual(resp.context['monthly_total'], 0)
        self.assertEqual(resp.context['monthly_rows'], [])
        self.assertContains(resp, '支出データがありません')

    def test_zero_data_year(self):
        resp = self.client.get(
            reverse('ledger:expense_breakdown'), {'year': '2020', 'month': '2020-01'}
        )
        self.assertEqual(resp.context['yearly_total'], 0)
        self.assertEqual(resp.context['yearly_rows'], [])

    def test_future_year_clamped(self):
        resp = self.client.get(
            reverse('ledger:expense_breakdown'), {'year': '2099'}
        )
        self.assertEqual(resp.context['year'], date.today().year)

    def test_income_category_transaction_excluded_from_totals(self):
        """income カテゴリの取引は金額・件数ともに支出構成に含まれない。"""
        resp = self.client.get(reverse('ledger:expense_breakdown'))
        self.assertEqual(resp.context['monthly_total'], 6000)
        all_names_monthly = [r['category__name'] for r in resp.context['monthly_rows']]
        self.assertNotIn('給与', all_names_monthly)
        all_names_yearly = [r['category__name'] for r in resp.context['yearly_rows']]
        self.assertNotIn('給与', all_names_yearly)

    def test_rows_grouped_by_category_id(self):
        """category_id でグループ化されるため、行数がカテゴリ数と一致する。"""
        resp = self.client.get(reverse('ledger:expense_breakdown'))
        rows = resp.context['monthly_rows']
        self.assertEqual(len(rows), 2)
        ids = [r['category_id'] for r in rows]
        self.assertEqual(len(ids), len(set(ids)))
