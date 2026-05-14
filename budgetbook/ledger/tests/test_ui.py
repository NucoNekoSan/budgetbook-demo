"""UI/UX 回帰テスト。

- Hero card / route 属性 / theme toggle ボタン / empty CTA / aria-live を検証。
- 視覚スタイルそのものはテストしないが、構造マークアップは固定する。
"""
from __future__ import annotations

from datetime import date

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from ledger.models import Account, Category, Transaction


class DashboardUITest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username='ui', password='pass')
        cls.account = Account.objects.create(name='UI口座', opening_balance=10000)
        cls.income = Category.objects.create(name='UI給与', kind=Category.Kind.INCOME)

    def setUp(self):
        self.client.login(username='ui', password='pass')

    def test_hero_card_renders(self):
        resp = self.client.get(reverse('ledger:dashboard'))
        self.assertEqual(resp.status_code, 200)
        # hero-card には modifier クラス (--compact) が付くため class= で完全一致は使わない
        self.assertIn(b'hero-card', resp.content)
        self.assertIn(b'class="hero-card__value', resp.content)
        # 月末残高が HERO に表示される
        self.assertIn('月末残高'.encode('utf-8'), resp.content)

    def test_route_attribute_set(self):
        resp = self.client.get(reverse('ledger:dashboard'))
        self.assertIn(b'data-route="dashboard"', resp.content)

    def test_theme_toggle_button_present(self):
        resp = self.client.get(reverse('ledger:dashboard'))
        self.assertIn(b'data-theme-toggle', resp.content)
        self.assertIn(b'theme_toggle.js', resp.content)

    def test_aria_live_flash_region(self):
        resp = self.client.get(reverse('ledger:dashboard'))
        self.assertIn(b'aria-live="polite"', resp.content)

    def test_empty_state_has_cta(self):
        # 取引なしで開く
        resp = self.client.get(reverse('ledger:dashboard'))
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode('utf-8')
        self.assertIn('この月の取引はまだありません', body)
        self.assertIn('右側のフォーム', body)

    def test_transaction_cells_have_data_label(self):
        Transaction.objects.create(
            date=date.today(), account=self.account, category=self.income,
            amount=1000, description='レスポンシブカード化',
        )
        resp = self.client.get(reverse('ledger:dashboard'))
        body = resp.content.decode('utf-8')
        # モバイルカードレイアウトのため data-label がすべて付与されていること
        for label in ('日付', '摘要', '口座', 'カテゴリ', '金額', '操作'):
            self.assertIn(f'data-label="{label}"', body)
        # tx-table クラスが付いていること
        self.assertIn('class="tx-table"', body)
        self.assertIn('table-wrap--responsive', body)

    def test_inline_action_buttons_have_aria_label(self):
        Transaction.objects.create(
            date=date.today(), account=self.account, category=self.income,
            amount=1000, description='UIテスト',
        )
        resp = self.client.get(reverse('ledger:dashboard'))
        body = resp.content.decode('utf-8')
        self.assertIn('aria-label="UIテスト の取引を編集"', body)
        self.assertIn('aria-label="UIテスト の取引を削除"', body)


class ChartConsistencyTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username='chart', password='pass')
        cls.account = Account.objects.create(name='グラフ口座', opening_balance=0)
        cls.income = Category.objects.create(name='グラフ給与', kind=Category.Kind.INCOME)
        cls.expense = Category.objects.create(name='グラフ食費', kind=Category.Kind.EXPENSE)

    def setUp(self):
        self.client.login(username='chart', password='pass')

    def test_income_ratio_uses_chartjs_canvas(self):
        Transaction.objects.create(
            date=date.today(), account=self.account, category=self.income,
            amount=10000, description='給与',
        )
        Transaction.objects.create(
            date=date.today(), account=self.account, category=self.expense,
            amount=3000, description='食費',
        )
        resp = self.client.get(reverse('ledger:expense_breakdown'))
        body = resp.content.decode('utf-8')
        # 統一: canvas で描画
        self.assertIn('id="income-ratio-pie"', body)
        # 旧 conic-gradient 由来の inline <style> はもう出ない
        self.assertNotIn('css-pie-chart--current', body)


class LoginUITest(TestCase):
    def test_login_page_uses_external_styles_only(self):
        resp = self.client.get('/accounts/login/')
        self.assertEqual(resp.status_code, 200)
        # inline <style> ブロックを排除しているはず
        self.assertNotIn(b'<style>', resp.content)
        # nonce 付きの theme_toggle.js が読み込まれる
        self.assertIn(b'theme_toggle.js', resp.content)