"""Category.section（大分類）の回帰テスト。"""
from __future__ import annotations

from datetime import date

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from ledger.models import Account, Category, ExpenseGroup, ExpenseGroupCategory, Transaction


class CategorySectionFieldTest(TestCase):
    def test_default_section_is_other(self):
        cat = Category.objects.create(name='テスト食費', kind=Category.Kind.EXPENSE)
        self.assertEqual(cat.section, Category.Section.OTHER)

    def test_section_choices_include_food_daily(self):
        labels = dict(Category.Section.choices)
        self.assertIn('food_daily', labels)
        self.assertEqual(labels['food_daily'], '食品・日用品')

    def test_can_assign_section(self):
        cat = Category.objects.create(
            name='イオン・テスト',
            kind=Category.Kind.EXPENSE,
            section=Category.Section.FOOD_DAILY,
        )
        cat.refresh_from_db()
        self.assertEqual(cat.section, 'food_daily')
        self.assertEqual(cat.get_section_display(), '食品・日用品')


class CategoryFormSectionTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username='sectest', password='pass')

    def setUp(self):
        self.client.login(username='sectest', password='pass')

    def test_create_category_with_section(self):
        resp = self.client.post(reverse('ledger:category_create'), {
            'name': 'スーパーテスト',
            'kind': 'expense',
            'section': 'food_daily',
            'tax_tag': 'none',
            'notes': '',
        })
        self.assertEqual(resp.status_code, 200)
        cat = Category.objects.get(name='スーパーテスト')
        self.assertEqual(cat.section, 'food_daily')

    def test_settings_page_shows_section_column(self):
        Category.objects.create(
            name='断面表示テスト',
            kind=Category.Kind.EXPENSE,
            section=Category.Section.FOOD_DAILY,
        )
        resp = self.client.get(reverse('ledger:settings'))
        self.assertContains(resp, '大分類')
        self.assertContains(resp, '食品・日用品')


class ExpenseBreakdownSectionAggregationTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username='secagg', password='pass')
        cls.account = Account.objects.create(name='大分類口座', opening_balance=0)
        cls.cat_food = Category.objects.create(
            name='大分類食品店', kind=Category.Kind.EXPENSE,
            section=Category.Section.FOOD_DAILY,
        )
        cls.cat_transport = Category.objects.create(
            name='大分類交通', kind=Category.Kind.EXPENSE,
            section=Category.Section.TRANSPORT,
        )

    def setUp(self):
        self.client.login(username='secagg', password='pass')

    def test_section_rows_in_context(self):
        today = date.today()
        Transaction.objects.create(
            date=today, account=self.account, category=self.cat_food,
            amount=3000, description='食品買物',
        )
        Transaction.objects.create(
            date=today, account=self.account, category=self.cat_transport,
            amount=1000, description='交通',
        )
        resp = self.client.get(reverse('ledger:expense_breakdown'))
        rows = {r['section']: r for r in resp.context['section_rows']}
        self.assertEqual(rows['food_daily']['total'], 3000)
        self.assertEqual(rows['transport']['total'], 1000)
        self.assertAlmostEqual(rows['food_daily']['pct'], 75.0, places=1)

    def test_section_summary_panel_renders(self):
        Transaction.objects.create(
            date=date.today(), account=self.account, category=self.cat_food,
            amount=500, description='X',
        )
        resp = self.client.get(reverse('ledger:expense_breakdown'))
        self.assertContains(resp, '大分類サマリー')


class AnnualSectionAggregationTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username='annsec', password='pass')
        cls.account = Account.objects.create(name='年口座', opening_balance=0)
        cls.cat = Category.objects.create(
            name='年食品店', kind=Category.Kind.EXPENSE,
            section=Category.Section.FOOD_DAILY,
        )

    def setUp(self):
        self.client.login(username='annsec', password='pass')

    def test_annual_section_rows_in_context(self):
        Transaction.objects.create(
            date=date(date.today().year, 6, 15),
            account=self.account, category=self.cat,
            amount=5000, description='年支出',
        )
        resp = self.client.get(reverse('ledger:annual'))
        rows = {r['section']: r for r in resp.context['annual_section_rows']}
        self.assertEqual(rows['food_daily']['total'], 5000)


class DashboardSectionTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username='dashsec', password='pass')
        cls.account = Account.objects.create(name='Dash口座', opening_balance=0)
        cls.cat = Category.objects.create(
            name='Dash食品', kind=Category.Kind.EXPENSE,
            section=Category.Section.FOOD_DAILY,
        )

    def setUp(self):
        self.client.login(username='dashsec', password='pass')

    def test_dashboard_shows_section_breakdown(self):
        Transaction.objects.create(
            date=date.today(), account=self.account, category=self.cat,
            amount=2000, description='X',
        )
        resp = self.client.get(reverse('ledger:dashboard'))
        body = resp.content.decode('utf-8')
        # v1.16.0 で「大分類別 支出」と「支出カテゴリ別 (Top 8)」を
        # 「支出の内訳」パネルに統合し、内部のサブタイトルとして「大分類別」を出すよう変更
        self.assertIn('支出の内訳', body)
        self.assertIn('大分類別', body)
        self.assertIn('食品・日用品', body)


class FoodDailyDataMigrationTest(TestCase):
    """0008 マイグレーションのロジック相当を、新規データに対して再現できるか。

    マイグレーション本体は migrate 実行時に走る。テスト DB では空 → 何もしない。
    ここでは「ドラッグストアを ExpenseGroup「食品・日用品」に追加」する手順が
    ExpenseGroupCategory の OneToOne 制約に違反しないことを確認する。
    """

    def test_assign_drugstore_to_food_daily_group(self):
        cat = Category.objects.create(
            name='テストドラッグストア', kind=Category.Kind.EXPENSE,
        )
        # migration 0009 で「食品・日用品」が事前作成済のため get_or_create
        group, _ = ExpenseGroup.objects.get_or_create(name='食品・日用品')
        membership = ExpenseGroupCategory.objects.create(group=group, category=cat)
        self.assertEqual(membership.group, group)
        # 二重登録は OneToOne 制約と full_clean により ValidationError
        from django.core.exceptions import ValidationError
        with self.assertRaises(ValidationError):
            ExpenseGroupCategory.objects.create(group=group, category=cat)
