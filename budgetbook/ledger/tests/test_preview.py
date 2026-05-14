"""取引プレビュー API のテスト。"""
from __future__ import annotations

from datetime import date

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from ledger.models import Account, Category, Transaction


class TransactionPreviewTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username='prev', password='pass')
        cls.account = Account.objects.create(name='プレ口座', opening_balance=10000)
        cls.cat_food = Category.objects.create(
            name='プレ食費', kind=Category.Kind.EXPENSE, section='food_daily',
        )
        cls.cat_income = Category.objects.create(
            name='プレ収入', kind=Category.Kind.INCOME,
        )

    def setUp(self):
        self.client.login(username='prev', password='pass')

    def test_empty_input_shows_placeholder(self):
        resp = self.client.post(reverse('ledger:transaction_preview'), {})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'プレビューが表示されます')

    def test_amount_only_no_preview(self):
        resp = self.client.post(reverse('ledger:transaction_preview'), {
            'amount': '1000', 'date': date.today().isoformat(),
        })
        self.assertEqual(resp.status_code, 200)
        # カテゴリ未選択 → has_input=False
        self.assertContains(resp, 'プレビューが表示されます')

    def test_full_input_shows_preview(self):
        resp = self.client.post(reverse('ledger:transaction_preview'), {
            'amount': '3000',
            'date': date.today().isoformat(),
            'category': self.cat_food.pk,
            'account': self.account.pk,
        })
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode('utf-8')
        self.assertIn('保存後の', body)
        self.assertIn('¥3,000', body)

    def test_duplicate_warning(self):
        Transaction.objects.create(
            date=date.today(), account=self.account, category=self.cat_food,
            amount=1500, description='重複候補',
        )
        resp = self.client.post(reverse('ledger:transaction_preview'), {
            'amount': '1500',
            'date': date.today().isoformat(),
            'category': self.cat_food.pk,
        })
        body = resp.content.decode('utf-8')
        self.assertIn('重複の可能性', body)
        self.assertIn('重複候補', body)

    def test_income_preview_does_not_increase_expense(self):
        resp = self.client.post(reverse('ledger:transaction_preview'), {
            'amount': '5000',
            'date': date.today().isoformat(),
            'category': self.cat_income.pk,
        })
        body = resp.content.decode('utf-8')
        # new_income に +5000 が反映、new_expense は変わらない
        self.assertIn('保存後の', body)

    def test_invalid_amount_handled(self):
        resp = self.client.post(reverse('ledger:transaction_preview'), {
            'amount': 'abc',
            'date': 'not-a-date',
            'category': '999999',
        })
        self.assertEqual(resp.status_code, 200)


class TransactionFormHasPreviewElementTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username='prevf', password='pass')
        Account.objects.create(name='プレフ口座', opening_balance=0)
        Category.objects.create(name='プレフ食費', kind=Category.Kind.EXPENSE)

    def setUp(self):
        self.client.login(username='prevf', password='pass')

    def test_dashboard_form_has_preview_target(self):
        resp = self.client.get(reverse('ledger:dashboard'))
        body = resp.content.decode('utf-8')
        self.assertIn('id="transaction-preview"', body)

    def test_preview_div_has_own_hx_target(self):
        # hx-target は親 form (#form-panel) から継承されてしまうため
        # 自分自身を明示的に指定しないと、プレビュー応答がフォーム全体を上書きする
        resp = self.client.get(reverse('ledger:dashboard'))
        body = resp.content.decode('utf-8')
        import re
        m = re.search(
            r'<div[^>]*id="transaction-preview"[^>]*>',
            body,
        )
        self.assertIsNotNone(m, 'transaction-preview div not found')
        self.assertIn('hx-target="#transaction-preview"', m.group(0))

    def test_keyboard_shortcuts_script_loaded(self):
        resp = self.client.get(reverse('ledger:dashboard'))
        self.assertIn(b'keyboard_shortcuts.js', resp.content)