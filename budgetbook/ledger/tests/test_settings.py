from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from ledger.forms import AccountForm
from ledger.forms import TransactionForm
from ledger.models import Account, Category, MonthlyClosing, Transaction, Transfer


class SettingsPageTest(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username='test', password='pass')
        cls.account = Account.objects.create(name='メイン口座', opening_balance=10000)
        cls.category = Category.objects.create(name='食費', kind=Category.Kind.EXPENSE)

    def setUp(self):
        self.client.login(username='test', password='pass')

    def test_settings_page_loads(self):
        resp = self.client.get(reverse('ledger:settings'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, '設定')
        self.assertContains(resp, '家計簿に戻る')

    def test_settings_page_shows_accounts_and_categories(self):
        resp = self.client.get(reverse('ledger:settings'))
        self.assertContains(resp, 'メイン口座')
        self.assertContains(resp, '食費')


class AccountCrudTest(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username='test', password='pass')

    def setUp(self):
        self.client.login(username='test', password='pass')

    def test_create_account(self):
        resp = self.client.post(reverse('ledger:account_create'), {
            'name': '新規口座',
            'kind': 'asset',
            'opening_balance': 5000,
            'notes': '',
        })
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(Account.objects.filter(name='新規口座').exists())
        self.assertContains(resp, '口座を追加しました')

    def test_duplicate_name_shows_friendly_error(self):
        Account.objects.create(name='既存口座')
        resp = self.client.post(reverse('ledger:account_create'), {
            'name': '既存口座',
            'kind': 'asset',
            'opening_balance': 0,
            'notes': '',
        })
        self.assertEqual(resp.status_code, 422)
        self.assertContains(resp, '既に使われています', status_code=422)

    def test_edit_account_name(self):
        acct = Account.objects.create(name='旧名', opening_balance=1000)
        resp = self.client.post(reverse('ledger:account_update', args=[acct.pk]), {
            'name': '新名',
            'kind': 'asset',
            'opening_balance': 1000,
            'notes': '',
        })
        self.assertEqual(resp.status_code, 200)
        acct.refresh_from_db()
        self.assertEqual(acct.name, '新名')

    def test_edit_unused_account_opening_balance(self):
        acct = Account.objects.create(name='未使用口座', opening_balance=5000)
        resp = self.client.post(reverse('ledger:account_update', args=[acct.pk]), {
            'name': '未使用口座',
            'kind': 'asset',
            'opening_balance': 12000,
            'notes': '',
        })
        self.assertEqual(resp.status_code, 200)
        acct.refresh_from_db()
        self.assertEqual(acct.opening_balance, 12000)

    def test_unused_account_form_opening_balance_is_editable(self):
        acct = Account.objects.create(name='未使用フォーム口座', opening_balance=5000)
        form = AccountForm(instance=acct)
        self.assertNotIn('readonly', form.fields['opening_balance'].widget.attrs)

    def test_edit_account_opening_balance_when_transactions_exist(self):
        acct = Account.objects.create(name='残高テスト', opening_balance=5000)
        cat = Category.objects.create(name='食費', kind=Category.Kind.EXPENSE)
        Transaction.objects.create(
            date='2026-04-01',
            account=acct,
            category=cat,
            amount=1000,
            description='履歴',
        )
        self.client.post(reverse('ledger:account_update', args=[acct.pk]), {
            'name': '残高テスト',
            'kind': 'asset',
            'opening_balance': 99999,
            'notes': '',
        })
        acct.refresh_from_db()
        self.assertEqual(acct.opening_balance, 99999)

    def test_used_account_form_opening_balance_is_editable_with_warning(self):
        acct = Account.objects.create(name='使用済みフォーム口座', opening_balance=5000)
        cat = Category.objects.create(name='通信費', kind=Category.Kind.EXPENSE)
        Transaction.objects.create(
            date='2026-04-01',
            account=acct,
            category=cat,
            amount=1000,
            description='履歴',
        )
        form = AccountForm(instance=acct)
        self.assertNotIn('readonly', form.fields['opening_balance'].widget.attrs)
        self.assertIn('再計算', form.fields['opening_balance'].help_text)

    def test_edit_account_opening_balance_when_transfer_exists(self):
        acct_a = Account.objects.create(name='振替元', opening_balance=5000)
        acct_b = Account.objects.create(name='振替先', opening_balance=5000)
        Transfer.objects.create(
            date='2026-04-01',
            from_account=acct_a,
            to_account=acct_b,
            amount=1000,
            description='振替履歴',
        )
        self.client.post(reverse('ledger:account_update', args=[acct_a.pk]), {
            'name': '振替元',
            'kind': 'asset',
            'opening_balance': 99999,
            'notes': '',
        })
        acct_a.refresh_from_db()
        self.assertEqual(acct_a.opening_balance, 99999)

    def test_edit_account_opening_balance_rejected_after_monthly_closing(self):
        acct = Account.objects.create(name='締め後口座', opening_balance=5000)
        MonthlyClosing.objects.create(
            month='2026-04-01',
            opening_carry=0,
            income=0,
            expense=0,
            net=0,
            closing_balance=0,
            account_balances=[],
        )
        resp = self.client.post(reverse('ledger:account_update', args=[acct.pk]), {
            'name': '締め後口座',
            'kind': 'asset',
            'opening_balance': 99999,
            'notes': '',
        })
        self.assertEqual(resp.status_code, 422)
        self.assertContains(resp, '月次締めが存在するため', status_code=422)
        acct.refresh_from_db()
        self.assertEqual(acct.opening_balance, 5000)

    def test_edit_account_name_allowed_after_monthly_closing(self):
        acct = Account.objects.create(name='締め後名称変更前', opening_balance=5000)
        MonthlyClosing.objects.create(
            month='2026-04-01',
            opening_carry=0,
            income=0,
            expense=0,
            net=0,
            closing_balance=0,
            account_balances=[],
        )
        resp = self.client.post(reverse('ledger:account_update', args=[acct.pk]), {
            'name': '締め後名称変更後',
            'kind': 'asset',
            'opening_balance': 5000,
            'notes': '',
        })
        self.assertEqual(resp.status_code, 200)
        acct.refresh_from_db()
        self.assertEqual(acct.name, '締め後名称変更後')
        self.assertEqual(acct.opening_balance, 5000)

    def test_toggle_account(self):
        acct = Account.objects.create(name='トグル口座')
        self.assertTrue(acct.is_active)
        self.client.post(reverse('ledger:account_toggle', args=[acct.pk]))
        acct.refresh_from_db()
        self.assertFalse(acct.is_active)
        self.client.post(reverse('ledger:account_toggle', args=[acct.pk]))
        acct.refresh_from_db()
        self.assertTrue(acct.is_active)

    def test_delete_unused_account_removes_row(self):
        acct = Account.objects.create(name='未使用削除口座')
        resp = self.client.post(reverse('ledger:account_delete', args=[acct.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(Account.objects.filter(pk=acct.pk).exists())
        self.assertContains(resp, '削除しました')

    def test_unused_account_shows_complete_delete_action(self):
        Account.objects.create(name='未使用表示口座')
        resp = self.client.get(reverse('ledger:settings'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, '未使用表示口座')
        self.assertContains(resp, '未使用')
        # 削除ボタンの存在 (アイコン + ラベル)
        self.assertContains(resp, '🗑 削除')

    def test_delete_used_account_is_rejected_with_message(self):
        """関連取引がある口座の削除は拒否し、無効化はしない（責務分離）。"""
        acct = Account.objects.create(name='使用済み削除口座')
        cat = Category.objects.create(name='削除テスト食費', kind=Category.Kind.EXPENSE)
        Transaction.objects.create(
            date='2026-04-01',
            account=acct,
            category=cat,
            amount=1000,
            description='履歴',
        )
        resp = self.client.post(reverse('ledger:account_delete', args=[acct.pk]))
        self.assertEqual(resp.status_code, 200)
        acct.refresh_from_db()
        # 削除はされず、is_active も勝手に False にしない（無効化は account_toggle の責務）
        self.assertTrue(Account.objects.filter(pk=acct.pk).exists())
        self.assertTrue(acct.is_active)
        self.assertContains(resp, '削除できません')
        self.assertContains(resp, '先に「停止」で無効化')

    def test_used_account_shows_disabled_delete_button_and_counts(self):
        """使用中の口座は『削除不可』の disabled ボタンを表示し、削除は提供しない。"""
        acct = Account.objects.create(name='使用中表示口座')
        cat = Category.objects.create(name='表示テスト食費', kind=Category.Kind.EXPENSE)
        Transaction.objects.create(
            date='2026-04-01',
            account=acct,
            category=cat,
            amount=1000,
            description='履歴',
        )
        resp = self.client.get(reverse('ledger:settings'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, '使用中表示口座')
        self.assertContains(resp, '使用中')
        self.assertContains(resp, '取引 1 / 振替 0')
        # 使用中口座には disabled の削除不可ボタンが出る（責務分離）
        self.assertContains(resp, '🚫 削除不可')
        self.assertContains(resp, 'disabled')
        # 削除可能なボタン (hx-post 削除) は出ない
        self.assertNotContains(resp, f'hx-post="{reverse("ledger:account_delete", args=[acct.pk])}"')

    def test_deactivated_account_hidden_from_dashboard_balance(self):
        """口座を「停止」(account_toggle) で無効化するとダッシュボードの口座残高に出ない。"""
        acct = Account.objects.create(name='非表示口座')
        cat = Category.objects.create(name='非表示テスト食費', kind=Category.Kind.EXPENSE)
        Transaction.objects.create(
            date='2026-04-01',
            account=acct,
            category=cat,
            amount=1000,
            description='履歴',
        )
        # 削除ではなく無効化（責務分離後）
        self.client.post(reverse('ledger:account_toggle', args=[acct.pk]))
        acct.refresh_from_db()
        self.assertFalse(acct.is_active)
        resp = self.client.get(reverse('ledger:dashboard'), {'month': '2026-04'})
        account_names = [account.name for account in resp.context['account_balances']]
        self.assertNotIn('非表示口座', account_names)


class CategoryCrudTest(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username='test', password='pass')

    def setUp(self):
        self.client.login(username='test', password='pass')

    def test_create_category(self):
        resp = self.client.post(reverse('ledger:category_create'), {
            'name': '交通費',
            'kind': 'expense',
            'section': 'transport',
            'tax_tag': 'none',
            'notes': '',
        })
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(Category.objects.filter(name='交通費').exists())

    def test_duplicate_category_name_shows_friendly_error(self):
        Category.objects.create(name='食費', kind=Category.Kind.EXPENSE)
        resp = self.client.post(reverse('ledger:category_create'), {
            'name': '食費',
            'kind': 'income',
            'section': 'other',
            'tax_tag': 'none',
            'notes': '',
        })
        self.assertEqual(resp.status_code, 422)
        self.assertContains(resp, '既に使われています', status_code=422)

    def test_edit_category_kind_is_immutable(self):
        cat = Category.objects.create(name='給与', kind=Category.Kind.INCOME)
        self.client.post(reverse('ledger:category_update', args=[cat.pk]), {
            'name': '給与改名',
            'kind': 'expense',
            'section': 'other',
            'tax_tag': 'none',
            'notes': '',
        })
        cat.refresh_from_db()
        self.assertEqual(cat.name, '給与改名')
        self.assertEqual(cat.kind, Category.Kind.INCOME)

    def test_toggle_category(self):
        cat = Category.objects.create(name='趣味', kind=Category.Kind.EXPENSE)
        self.client.post(reverse('ledger:category_toggle', args=[cat.pk]))
        cat.refresh_from_db()
        self.assertFalse(cat.is_active)

    def test_unused_category_shows_complete_delete_action(self):
        Category.objects.create(name='未使用カテゴリ', kind=Category.Kind.EXPENSE)
        resp = self.client.get(reverse('ledger:settings'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, '未使用カテゴリ')
        self.assertContains(resp, '未使用')
        self.assertContains(resp, '🗑 削除')

    def test_used_category_shows_usage_counts_without_complete_delete(self):
        account = Account.objects.create(name='カテゴリ表示口座')
        cat = Category.objects.create(name='使用中カテゴリ', kind=Category.Kind.EXPENSE)
        Transaction.objects.create(
            date='2026-04-01',
            account=account,
            category=cat,
            amount=1000,
            description='履歴',
        )
        resp = self.client.get(reverse('ledger:settings'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, '使用中カテゴリ')
        self.assertContains(resp, '使用中')
        # 1 行表示に圧縮されたあとの形式
        self.assertContains(resp, '取引 1 / 分析G 0')
        # 使用中カテゴリには「カテゴリ削除」用の aria-label を持つボタンが出ない
        self.assertNotContains(resp, 'aria-label="使用中カテゴリ を削除"')


class SettingsAffectsTransactionFormTest(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username='test', password='pass')
        cls.account = Account.objects.create(name='口座X')
        cls.category = Category.objects.create(name='光熱費', kind=Category.Kind.EXPENSE)

    def setUp(self):
        self.client.login(username='test', password='pass')

    def test_disabled_account_hidden_from_transaction_form(self):
        self.account.is_active = False
        self.account.save()
        resp = self.client.get(reverse('ledger:dashboard'))
        self.assertNotContains(resp, '口座X')

    def test_new_account_appears_in_transaction_form(self):
        Account.objects.create(name='新しい口座')
        resp = self.client.get(reverse('ledger:dashboard'))
        self.assertContains(resp, '新しい口座')

    def test_disabled_category_hidden_from_transaction_form(self):
        self.category.is_active = False
        self.category.save()
        resp = self.client.get(reverse('ledger:dashboard'))
        self.assertNotContains(resp, '光熱費')

    def test_existing_transaction_can_keep_disabled_account(self):
        self.account.is_active = False
        self.account.save()
        tx = Transaction.objects.create(
            date='2026-04-01',
            account=self.account,
            category=self.category,
            amount=1000,
            description='履歴',
        )
        form = TransactionForm(data={
            'date': '2026-04-01',
            'account': self.account.pk,
            'kind': Category.Kind.EXPENSE,
            'category': self.category.pk,
            'amount': 1200,
            'description': '履歴修正',
            'memo': '',
        }, instance=tx)
        self.assertTrue(form.is_valid(), form.errors)

    def test_existing_transaction_can_keep_disabled_category(self):
        self.category.is_active = False
        self.category.save()
        tx = Transaction.objects.create(
            date='2026-04-01',
            account=self.account,
            category=self.category,
            amount=1000,
            description='履歴',
        )
        form = TransactionForm(data={
            'date': '2026-04-01',
            'account': self.account.pk,
            'kind': Category.Kind.EXPENSE,
            'category': self.category.pk,
            'amount': 1200,
            'description': '履歴修正',
            'memo': '',
        }, instance=tx)
        self.assertTrue(form.is_valid(), form.errors)
