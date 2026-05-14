from datetime import date

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from ledger.models import (
    Account,
    Category,
    ExpenseGroup,
    ExpenseGroupCategory,
    Transaction,
    Transfer,
)


class ExpenseGroupModelTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.cat_food = Category.objects.create(name='食費', kind=Category.Kind.EXPENSE)
        cls.cat_income = Category.objects.create(name='給与', kind=Category.Kind.INCOME)
        # migration 0009 で「食品・日用品」が事前作成されるため get_or_create で衝突回避
        cls.group, _ = ExpenseGroup.objects.get_or_create(name='食品・日用品')

    def test_income_category_rejected(self):
        m = ExpenseGroupCategory(group=self.group, category=self.cat_income)
        with self.assertRaises(ValidationError):
            m.save()
        self.assertEqual(ExpenseGroupCategory.objects.count(), 0)

    def test_expense_category_accepted(self):
        m = ExpenseGroupCategory(group=self.group, category=self.cat_food)
        m.save()
        self.assertEqual(ExpenseGroupCategory.objects.count(), 1)

    def test_one_category_one_group_constraint(self):
        ExpenseGroupCategory.objects.create(group=self.group, category=self.cat_food)
        other = ExpenseGroup.objects.create(name='別グループ')
        with self.assertRaises(Exception):
            # OneToOneField の unique 制約で 2 グループには所属不可
            ExpenseGroupCategory.objects.create(group=other, category=self.cat_food)


class ExpenseBreakdownGroupingTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username='test', password='pass')
        cls.account = Account.objects.create(name='口座A')
        cls.cat_income = Category.objects.create(name='給与', kind=Category.Kind.INCOME)
        cls.cat_super = Category.objects.create(name='スーパー', kind=Category.Kind.EXPENSE)
        cls.cat_conv = Category.objects.create(name='コンビニ', kind=Category.Kind.EXPENSE)
        cls.cat_coop = Category.objects.create(name='Co-op', kind=Category.Kind.EXPENSE)
        cls.cat_drug = Category.objects.create(name='ドラッグストア', kind=Category.Kind.EXPENSE)
        cls.cat_dept = Category.objects.create(name='百貨店', kind=Category.Kind.EXPENSE)
        cls.cat_transport = Category.objects.create(name='交通費', kind=Category.Kind.EXPENSE)

        cls.today = date.today()
        cls.month_str = f'{cls.today.year}-{cls.today.month:02d}'

        for cat, amt, desc in [
            (cls.cat_super, 10000, 'スーパー買い物'),
            (cls.cat_conv, 5000, 'コンビニ'),
            (cls.cat_coop, 8000, 'Co-op'),
            (cls.cat_drug, 3000, 'ドラッグ'),
            (cls.cat_dept, 4000, '百貨店'),
            (cls.cat_transport, 2000, '電車'),
        ]:
            Transaction.objects.create(
                date=cls.today, account=cls.account, category=cat,
                amount=amt, description=desc,
            )

    def setUp(self):
        self.client.login(username='test', password='pass')

    def test_no_groups_individual_categories(self):
        resp = self.client.get(reverse('ledger:expense_breakdown'))
        labels = [r['label'] for r in resp.context['monthly_rows']]
        self.assertIn('スーパー', labels)
        self.assertIn('コンビニ', labels)
        self.assertNotIn('食品・日用品', labels)

    def test_group_aggregation(self):
        g, _ = ExpenseGroup.objects.get_or_create(name='食品・日用品')
        for cat in [self.cat_super, self.cat_conv, self.cat_coop, self.cat_drug]:
            ExpenseGroupCategory.objects.get_or_create(group=g, category=cat)
        resp = self.client.get(reverse('ledger:expense_breakdown'))
        rows = resp.context['monthly_rows']
        food_row = next(r for r in rows if r['label'] == '食品・日用品')
        self.assertEqual(food_row['total'], 10000 + 5000 + 8000 + 3000)
        self.assertEqual(food_row['kind'], 'group')
        labels = [r['label'] for r in rows]
        self.assertNotIn('スーパー', labels)
        self.assertNotIn('コンビニ', labels)
        # 百貨店は未所属で個別表示
        self.assertIn('百貨店', labels)
        self.assertIn('交通費', labels)

    def test_department_store_not_auto_grouped(self):
        g, _ = ExpenseGroup.objects.get_or_create(name='食品・日用品')
        for cat in [self.cat_super, self.cat_conv, self.cat_coop, self.cat_drug]:
            ExpenseGroupCategory.objects.get_or_create(group=g, category=cat)
        resp = self.client.get(reverse('ledger:expense_breakdown'))
        food_row = next(r for r in resp.context['monthly_rows'] if r['label'] == '食品・日用品')
        # 百貨店4000は含まれない
        self.assertEqual(food_row['total'], 26000)

    def test_inactive_group_falls_back_to_individuals(self):
        g, _ = ExpenseGroup.objects.get_or_create(
            name='食品・日用品',
            defaults={'is_active': False},
        )
        # 既存（migration が作成）が active=True の可能性があるので明示的に無効化
        if g.is_active:
            g.is_active = False
            g.save(update_fields=['is_active'])
        for cat in [self.cat_super, self.cat_conv]:
            ExpenseGroupCategory.objects.get_or_create(group=g, category=cat)
        resp = self.client.get(reverse('ledger:expense_breakdown'))
        labels = [r['label'] for r in resp.context['monthly_rows']]
        self.assertIn('スーパー', labels)
        self.assertIn('コンビニ', labels)
        self.assertNotIn('食品・日用品', labels)

    def test_transfer_excluded_from_breakdown(self):
        acct_b = Account.objects.create(name='口座B')
        Transfer.objects.create(
            date=self.today, from_account=self.account, to_account=acct_b,
            amount=99999, description='振替',
        )
        resp = self.client.get(reverse('ledger:expense_breakdown'))
        labels = [r['label'] for r in resp.context['monthly_rows']]
        self.assertNotIn('振替', labels)
        # 月間合計に振替は含まれない
        expected_total = 10000 + 5000 + 8000 + 3000 + 4000 + 2000
        self.assertEqual(resp.context['monthly_total'], expected_total)


class IncomeRatioTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username='test', password='pass')
        cls.account = Account.objects.create(name='口座A')
        cls.cat_income = Category.objects.create(name='給与', kind=Category.Kind.INCOME)
        cls.cat_food = Category.objects.create(name='食費', kind=Category.Kind.EXPENSE)
        cls.cat_transport = Category.objects.create(name='交通費', kind=Category.Kind.EXPENSE)

    def setUp(self):
        self.client.login(username='test', password='pass')
        self.today = date.today()

    def _make(self, income, expenses):
        Transaction.objects.create(
            date=self.today, account=self.account, category=self.cat_income,
            amount=income, description='給与',
        )
        for cat, amt in expenses:
            Transaction.objects.create(
                date=self.today, account=self.account, category=cat,
                amount=amt, description='テスト',
            )

    def test_ratio_with_remainder(self):
        self._make(100000, [(self.cat_food, 30000), (self.cat_transport, 10000)])
        resp = self.client.get(reverse('ledger:expense_breakdown'))
        rows = {r['label']: r for r in resp.context['income_ratio_rows']}
        self.assertAlmostEqual(rows['食費']['pct'], 30.0, places=1)
        self.assertAlmostEqual(rows['交通費']['pct'], 10.0, places=1)
        self.assertEqual(resp.context['remainder'], 60000)
        self.assertAlmostEqual(resp.context['remainder_pct'], 60.0, places=1)
        self.assertFalse(resp.context['is_over_spent'])
        # チャートには残額が含まれる
        chart_labels = [c['label'] for c in resp.context['income_ratio_chart']]
        self.assertIn('残額', chart_labels)
        # Chart.js canvas 統一後: 視覚要素は canvas + JSON データに集約
        self.assertContains(resp, 'id="income-ratio-pie"')
        self.assertContains(resp, '"income-ratio-pie-data"')

    def test_over_spent_month(self):
        self._make(50000, [(self.cat_food, 60000), (self.cat_transport, 5000)])
        resp = self.client.get(reverse('ledger:expense_breakdown'))
        self.assertTrue(resp.context['is_over_spent'])
        self.assertEqual(resp.context['overspent_amount'], 65000 - 50000)
        # 残額は出さない
        chart_labels = [c['label'] for c in resp.context['income_ratio_chart']]
        self.assertNotIn('残額', chart_labels)
        # 表は支出構成として表示し、超過が分かる
        rows = resp.context['income_ratio_rows']
        self.assertTrue(any(r['pct'] > 100 for r in rows) or resp.context['is_over_spent'])

    def test_zero_income(self):
        Transaction.objects.create(
            date=self.today, account=self.account, category=self.cat_food,
            amount=5000, description='食費のみ',
        )
        resp = self.client.get(reverse('ledger:expense_breakdown'))
        self.assertFalse(resp.context['has_income'])
        self.assertEqual(resp.context['income_ratio_rows'], [])
        self.assertEqual(resp.context['income_ratio_chart'], [])
