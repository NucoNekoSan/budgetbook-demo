from datetime import date

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from ledger.models import Account, Category, Transaction, Transfer


class TransactionInlineEditTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username='test', password='pass')
        cls.account = Account.objects.create(name='口座A')
        cls.cat = Category.objects.create(name='食費', kind=Category.Kind.EXPENSE)

    def setUp(self):
        self.client.login(username='test', password='pass')
        self.today = date.today()
        self.month_str = f'{self.today.year}-{self.today.month:02d}'
        self.tx = Transaction.objects.create(
            date=self.today, account=self.account, category=self.cat,
            amount=500, description='元の取引',
        )

    def test_get_returns_inline_form(self):
        resp = self.client.get(
            reverse('ledger:transaction_inline_update', args=[self.tx.pk]),
            {'month': self.month_str, 'page': 2},
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode('utf-8')
        self.assertIn(f'inline-edit-tx-{self.tx.pk}', body)
        self.assertIn('colspan="6"', body)
        self.assertIn('元の取引', body)
        self.assertIn('name="page" value="2"', body)
        self.assertIn('hx-swap="outerHTML show:#transaction-list-panel:top"', body)

    def test_post_success_via_htmx_retargets_dashboard_content(self):
        resp = self.client.post(
            reverse('ledger:transaction_inline_update', args=[self.tx.pk]) + f'?month={self.month_str}',
            {
                'date': self.today.isoformat(),
                'account': self.account.pk,
                'kind': 'expense',
                'category': self.cat.pk,
                'amount': 1500,
                'description': '更新後',
                'memo': '',
                'month': self.month_str,
            },
            HTTP_HX_REQUEST='true',
        )
        self.assertEqual(resp.status_code, 200)
        self.tx.refresh_from_db()
        self.assertEqual(self.tx.description, '更新後')
        self.assertEqual(self.tx.amount, 1500)
        body = resp.content.decode('utf-8')
        self.assertIn('hx-swap-oob', body)
        self.assertIn('id="flash"', body)
        self.assertIn('id="transaction-list-panel"', body)
        # form-panel を更新する OOB は含まれない
        self.assertNotIn('id="form-panel"', body)
        self.assertEqual(resp.headers['HX-Retarget'], '#dashboard-content')
        self.assertEqual(
            resp.headers['HX-Reswap'],
            'innerHTML show:#transaction-list-panel:top',
        )

    def test_post_success_preserves_page_context(self):
        for idx in range(25):
            Transaction.objects.create(
                date=self.today, account=self.account, category=self.cat,
                amount=100 + idx, description=f'追加{idx}',
            )

        resp = self.client.post(
            reverse('ledger:transaction_inline_update', args=[self.tx.pk]) + f'?month={self.month_str}&page=2',
            {
                'date': self.today.isoformat(),
                'account': self.account.pk,
                'kind': 'expense',
                'category': self.cat.pk,
                'amount': 1500,
                'description': 'ページ維持',
                'memo': '',
                'month': self.month_str,
                'page': 2,
            },
            HTTP_HX_REQUEST='true',
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, '2 / 2 ページ')

    def test_post_success_keeps_filter_values_separate_from_edited_values(self):
        filter_account = Account.objects.create(name='絞り込み口座')
        filter_category = Category.objects.create(name='絞り込みカテゴリ', kind=Category.Kind.EXPENSE)

        resp = self.client.get(
            reverse('ledger:transaction_inline_update', args=[self.tx.pk]),
            {
                'month': self.month_str,
                'account': filter_account.pk,
                'category': filter_category.pk,
            },
        )
        body = resp.content.decode('utf-8')
        self.assertIn(f'name="filter_account" value="{filter_account.pk}"', body)
        self.assertIn(f'name="filter_category" value="{filter_category.pk}"', body)

        resp = self.client.post(
            reverse('ledger:transaction_inline_update', args=[self.tx.pk]) + f'?month={self.month_str}',
            {
                'date': self.today.isoformat(),
                'account': self.account.pk,
                'kind': 'expense',
                'category': self.cat.pk,
                'amount': 1500,
                'description': 'フィルタ維持',
                'memo': '',
                'month': self.month_str,
                'filter_account': filter_account.pk,
                'filter_category': filter_category.pk,
            },
            HTTP_HX_REQUEST='true',
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode('utf-8')
        self.assertIn(f'<option value="{filter_account.pk}" selected>絞り込み口座</option>', body)
        self.assertIn(f'<option value="{filter_category.pk}" selected>絞り込みカテゴリ</option>', body)
        self.assertNotIn(f'<option value="{self.account.pk}" selected>口座A</option>', body)
        self.assertNotIn(f'<option value="{self.cat.pk}" selected>食費</option>', body)

    def test_post_validation_error_returns_422(self):
        resp = self.client.post(
            reverse('ledger:transaction_inline_update', args=[self.tx.pk]) + f'?month={self.month_str}',
            {
                'date': self.today.isoformat(),
                'account': self.account.pk,
                'kind': 'expense',
                'category': self.cat.pk,
                'amount': 0,
                'description': '',
                'memo': '',
                'month': self.month_str,
            },
            HTTP_HX_REQUEST='true',
        )
        self.assertEqual(resp.status_code, 422)
        self.tx.refresh_from_db()
        self.assertEqual(self.tx.description, '元の取引')
        body = resp.content.decode('utf-8')
        self.assertIn(f'inline-edit-tx-{self.tx.pk}', body)

    def test_non_htmx_post_redirects(self):
        resp = self.client.post(
            reverse('ledger:transaction_inline_update', args=[self.tx.pk]) + f'?month={self.month_str}',
            {
                'date': self.today.isoformat(),
                'account': self.account.pk,
                'kind': 'expense',
                'category': self.cat.pk,
                'amount': 999,
                'description': '非HTMX',
                'memo': '',
                'month': self.month_str,
            },
        )
        self.assertEqual(resp.status_code, 302)
        self.tx.refresh_from_db()
        self.assertEqual(self.tx.description, '非HTMX')

    def test_cancel_returns_empty_placeholder(self):
        resp = self.client.get(
            reverse('ledger:transaction_inline_cancel', args=[self.tx.pk]),
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode('utf-8')
        self.assertIn(f'inline-edit-tx-{self.tx.pk}', body)
        self.assertIn('colspan="6"', body)


class TransferInlineEditTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username='test', password='pass')
        cls.acct_a = Account.objects.create(name='口座A', opening_balance=10000)
        cls.acct_b = Account.objects.create(name='口座B', opening_balance=10000)

    def setUp(self):
        self.client.login(username='test', password='pass')
        self.today = date.today()
        self.month_str = f'{self.today.year}-{self.today.month:02d}'
        self.transfer = Transfer.objects.create(
            date=self.today, from_account=self.acct_a, to_account=self.acct_b,
            amount=2000, description='元振替',
        )

    def test_get_returns_inline_form(self):
        resp = self.client.get(
            reverse('ledger:transfer_inline_update', args=[self.transfer.pk]),
            {'month': self.month_str, 'page': 2},
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode('utf-8')
        self.assertIn(f'inline-edit-tr-{self.transfer.pk}', body)
        self.assertIn('元振替', body)
        self.assertIn('name="page" value="2"', body)

    def test_post_success_updates(self):
        resp = self.client.post(
            reverse('ledger:transfer_inline_update', args=[self.transfer.pk]) + f'?month={self.month_str}',
            {
                'date': self.today.isoformat(),
                'from_account': self.acct_a.pk,
                'to_account': self.acct_b.pk,
                'amount': 3500,
                'description': '振替更新',
                'memo': '',
                'month': self.month_str,
            },
            HTTP_HX_REQUEST='true',
        )
        self.assertEqual(resp.status_code, 200)
        self.transfer.refresh_from_db()
        self.assertEqual(self.transfer.amount, 3500)
        self.assertEqual(self.transfer.description, '振替更新')
        body = resp.content.decode('utf-8')
        self.assertIn('id="transaction-list-panel"', body)
        self.assertNotIn('id="form-panel"', body)
        self.assertEqual(resp.headers['HX-Retarget'], '#dashboard-content')
        self.assertEqual(
            resp.headers['HX-Reswap'],
            'innerHTML show:#transaction-list-panel:top',
        )

    def test_post_same_account_returns_422(self):
        resp = self.client.post(
            reverse('ledger:transfer_inline_update', args=[self.transfer.pk]) + f'?month={self.month_str}',
            {
                'date': self.today.isoformat(),
                'from_account': self.acct_a.pk,
                'to_account': self.acct_a.pk,
                'amount': 100,
                'description': '同一',
                'memo': '',
                'month': self.month_str,
            },
            HTTP_HX_REQUEST='true',
        )
        self.assertEqual(resp.status_code, 422)
        self.transfer.refresh_from_db()
        self.assertEqual(self.transfer.amount, 2000)

    def test_cancel_returns_empty_placeholder(self):
        resp = self.client.get(
            reverse('ledger:transfer_inline_cancel', args=[self.transfer.pk]),
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode('utf-8')
        self.assertIn(f'inline-edit-tr-{self.transfer.pk}', body)


class DashboardPlaceholderRowsTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username='test', password='pass')
        cls.account = Account.objects.create(name='口座A')
        cls.acct_b = Account.objects.create(name='口座B')
        cls.cat = Category.objects.create(name='食費', kind=Category.Kind.EXPENSE)

    def setUp(self):
        self.client.login(username='test', password='pass')
        self.today = date.today()
        self.month_str = f'{self.today.year}-{self.today.month:02d}'
        self.tx = Transaction.objects.create(
            date=self.today, account=self.account, category=self.cat,
            amount=500, description='ABC',
        )
        self.transfer = Transfer.objects.create(
            date=self.today, from_account=self.account, to_account=self.acct_b,
            amount=1000, description='XYZ振替',
        )

    def test_dashboard_includes_placeholder_rows(self):
        resp = self.client.get(reverse('ledger:dashboard'), {'month': self.month_str})
        body = resp.content.decode('utf-8')
        self.assertIn('id="transaction-list-panel"', body)
        self.assertIn(f'?month={self.month_str}&page=1', body)
        self.assertIn(f'inline-edit-tx-{self.tx.pk}', body)
        self.assertIn(f'inline-edit-tr-{self.transfer.pk}', body)

    def test_existing_create_form_unchanged(self):
        # 右側フォーム経由の新規登録が引き続き動く回帰チェック
        resp = self.client.post(
            reverse('ledger:transaction_create') + f'?month={self.month_str}',
            {
                'date': self.today.isoformat(),
                'account': self.account.pk,
                'kind': 'expense',
                'category': self.cat.pk,
                'amount': 333,
                'description': '新規回帰',
                'memo': '',
                'month': self.month_str,
            },
        )
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(Transaction.objects.filter(description='新規回帰').exists())
