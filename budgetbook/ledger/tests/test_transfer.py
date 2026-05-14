from datetime import date, timedelta

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from ledger.forms import TransferForm
from ledger.models import Account, Category, Transaction, Transfer
from ledger.views import (
    calculate_account_balance,
    calculate_total_balance,
    get_dashboard_context,
    month_param,
)


class TransferModelTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.acct_a = Account.objects.create(name='普通預金A', opening_balance=10000)
        cls.acct_b = Account.objects.create(name='普通預金B', opening_balance=5000)

    def test_same_account_transfer_validation_error(self):
        t = Transfer(
            date=date.today(),
            from_account=self.acct_a,
            to_account=self.acct_a,
            amount=1000,
            description='自己振替',
        )
        with self.assertRaises(ValidationError):
            t.full_clean()

    def test_amount_min_validation(self):
        t = Transfer(
            date=date.today(),
            from_account=self.acct_a,
            to_account=self.acct_b,
            amount=0,
            description='ゼロ',
        )
        with self.assertRaises(ValidationError):
            t.full_clean()


class TransferAggregationTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username='test', password='pass')
        cls.acct_a = Account.objects.create(name='普通預金A', opening_balance=100000)
        cls.acct_b = Account.objects.create(name='普通預金B', opening_balance=50000)
        cls.cat_income = Category.objects.create(name='給与', kind=Category.Kind.INCOME)
        cls.cat_food = Category.objects.create(name='食費', kind=Category.Kind.EXPENSE)

    def setUp(self):
        self.client.login(username='test', password='pass')
        self.today = date.today()
        self.month_str = f'{self.today.year}-{self.today.month:02d}'
        self.target_month = date(self.today.year, self.today.month, 1)
        Transaction.objects.create(
            date=self.today, account=self.acct_a, category=self.cat_income,
            amount=200000, description='給与振込',
        )
        Transaction.objects.create(
            date=self.today, account=self.acct_a, category=self.cat_food,
            amount=3000, description='スーパー',
        )
        Transfer.objects.create(
            date=self.today, from_account=self.acct_a, to_account=self.acct_b,
            amount=20000, description='Bへ移動',
        )

    def test_transfer_excluded_from_income_total(self):
        ctx = get_dashboard_context(self.target_month)
        self.assertEqual(ctx['income'], 200000)

    def test_transfer_excluded_from_expense_total(self):
        ctx = get_dashboard_context(self.target_month)
        self.assertEqual(ctx['expense'], 3000)

    def test_transfer_excluded_from_category_breakdown(self):
        ctx = get_dashboard_context(self.target_month)
        names = [r['category__name'] for r in ctx['expense_by_category']]
        self.assertIn('食費', names)
        self.assertNotIn('Bへ移動', names)
        self.assertNotIn('振替', names)

    def test_transfer_excluded_from_daily_trend(self):
        ctx = get_dashboard_context(self.target_month)
        today_entry = ctx['daily_trend'][self.today.day - 1]
        self.assertEqual(today_entry['income'], 200000)
        self.assertEqual(today_entry['expense'], 3000)

    def test_transfer_decreases_from_account_balance(self):
        bal = calculate_account_balance(self.acct_a, self.today)
        # 100000 + 200000 - 3000 - 20000 = 277000
        self.assertEqual(bal, 277000)

    def test_transfer_increases_to_account_balance(self):
        bal = calculate_account_balance(self.acct_b, self.today)
        # 50000 + 20000 = 70000
        self.assertEqual(bal, 70000)

    def test_transfer_preserves_total_balance(self):
        # 振替なし合計
        baseline = (
            self.acct_a.opening_balance + self.acct_b.opening_balance
            + 200000 - 3000
        )
        total = calculate_total_balance(self.today)
        self.assertEqual(total, baseline)

    def test_existing_transactions_unchanged(self):
        ctx = get_dashboard_context(self.target_month)
        self.assertEqual(ctx['income'], 200000)
        self.assertEqual(ctx['expense'], 3000)
        self.assertEqual(ctx['net'], 197000)

    def test_opening_carry_and_closing_balance(self):
        ctx = get_dashboard_context(self.target_month)
        prev = self.target_month - timedelta(days=1)
        # 月初繰越は前日時点の合計 = 開始残高のみ(当月の取引はまだない)
        self.assertEqual(ctx['opening_carry'], calculate_total_balance(prev))
        # 月末残高は当月末日時点
        from calendar import monthrange
        m_end = date(
            self.target_month.year,
            self.target_month.month,
            monthrange(self.target_month.year, self.target_month.month)[1],
        )
        self.assertEqual(ctx['closing_balance'], calculate_total_balance(m_end))


class TransferFilterTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username='test', password='pass')
        cls.acct_a = Account.objects.create(name='普通預金A')
        cls.acct_b = Account.objects.create(name='普通預金B')
        cls.acct_c = Account.objects.create(name='普通預金C')
        cls.cat = Category.objects.create(name='食費', kind=Category.Kind.EXPENSE)

    def setUp(self):
        self.client.login(username='test', password='pass')
        self.today = date.today()
        self.month_str = f'{self.today.year}-{self.today.month:02d}'
        self.tx = Transaction.objects.create(
            date=self.today, account=self.acct_a, category=self.cat,
            amount=500, description='スーパー',
        )
        self.transfer = Transfer.objects.create(
            date=self.today, from_account=self.acct_a, to_account=self.acct_b,
            amount=10000, description='AからBへ',
        )

    def test_account_filter_includes_from_account_transfer(self):
        resp = self.client.get(
            reverse('ledger:dashboard'),
            {'month': self.month_str, 'account': self.acct_a.pk},
        )
        rows = list(resp.context['page_obj'])
        kinds = [getattr(r, 'row_type', None) for r in rows]
        self.assertIn('transfer', kinds)

    def test_account_filter_includes_to_account_transfer(self):
        resp = self.client.get(
            reverse('ledger:dashboard'),
            {'month': self.month_str, 'account': self.acct_b.pk},
        )
        rows = list(resp.context['page_obj'])
        descs = [r.description for r in rows]
        self.assertIn('AからBへ', descs)

    def test_account_filter_excludes_unrelated_transfer(self):
        resp = self.client.get(
            reverse('ledger:dashboard'),
            {'month': self.month_str, 'account': self.acct_c.pk},
        )
        rows = list(resp.context['page_obj'])
        self.assertEqual(len(rows), 0)

    def test_category_filter_excludes_transfer(self):
        resp = self.client.get(
            reverse('ledger:dashboard'),
            {'month': self.month_str, 'category': self.cat.pk},
        )
        rows = list(resp.context['page_obj'])
        for r in rows:
            self.assertEqual(getattr(r, 'row_type', None), 'transaction')

    def test_search_q_matches_transfer_description(self):
        resp = self.client.get(
            reverse('ledger:dashboard'),
            {'month': self.month_str, 'q': 'AからBへ'},
        )
        rows = list(resp.context['page_obj'])
        descs = [r.description for r in rows]
        self.assertIn('AからBへ', descs)


class TransferCRUDTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username='test', password='pass')
        cls.acct_a = Account.objects.create(name='口座A', opening_balance=10000)
        cls.acct_b = Account.objects.create(name='口座B', opening_balance=10000)
        cls.acct_c = Account.objects.create(name='口座C', opening_balance=10000)

    def setUp(self):
        self.client.login(username='test', password='pass')
        self.today = date.today()
        self.month_str = f'{self.today.year}-{self.today.month:02d}'

    def test_create_transfer(self):
        resp = self.client.post(
            reverse('ledger:transfer_create') + f'?month={self.month_str}',
            {
                'date': self.today.isoformat(),
                'from_account': self.acct_a.pk,
                'to_account': self.acct_b.pk,
                'amount': 5000,
                'description': '移動',
                'memo': '',
                'month': self.month_str,
            },
        )
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(Transfer.objects.filter(description='移動').exists())
        self.assertEqual(calculate_account_balance(self.acct_a, self.today), 5000)
        self.assertEqual(calculate_account_balance(self.acct_b, self.today), 15000)

    def test_htmx_create_transfer_uses_saved_date_month_for_dashboard(self):
        previous_month = date(self.today.year, self.today.month, 1) - timedelta(days=1)
        previous_month_str = f'{previous_month.year}-{previous_month.month:02d}'
        resp = self.client.post(
            reverse('ledger:transfer_create') + f'?month={previous_month_str}',
            {
                'date': self.today.isoformat(),
                'from_account': self.acct_a.pk,
                'to_account': self.acct_b.pk,
                'amount': 5000,
                'description': '月ズレ確認',
                'memo': '',
                'month': previous_month_str,
            },
            HTTP_HX_REQUEST='true',
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, f'name="month" value="{self.month_str}"')
        self.assertContains(resp, '¥5,000')
        self.assertContains(resp, '¥15,000')

    def test_create_same_account_validation(self):
        resp = self.client.post(
            reverse('ledger:transfer_create') + f'?month={self.month_str}',
            {
                'date': self.today.isoformat(),
                'from_account': self.acct_a.pk,
                'to_account': self.acct_a.pk,
                'amount': 100,
                'description': '同一口座',
                'memo': '',
                'month': self.month_str,
            },
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(Transfer.objects.count(), 0)

    def test_htmx_create_same_account_returns_swappable_error(self):
        resp = self.client.post(
            reverse('ledger:transfer_create') + f'?month={self.month_str}',
            {
                'date': self.today.isoformat(),
                'from_account': self.acct_a.pk,
                'to_account': self.acct_a.pk,
                'amount': 100,
                'description': '同一口座',
                'memo': '',
                'month': self.month_str,
            },
            HTTP_HX_REQUEST='true',
        )
        self.assertEqual(resp.status_code, 422)
        self.assertContains(resp, '出金元口座と入金先口座は別の口座を指定してください。', status_code=422)
        self.assertContains(resp, '振替を追加', status_code=422)
        self.assertEqual(Transfer.objects.count(), 0)

    def test_new_transfer_form_defaults_to_different_accounts(self):
        form = TransferForm()
        self.assertEqual(form.fields['from_account'].initial, self.acct_a.pk)
        self.assertEqual(form.fields['to_account'].initial, self.acct_b.pk)
        self.assertNotEqual(form.fields['from_account'].initial, form.fields['to_account'].initial)

    def test_existing_transfer_can_keep_disabled_accounts(self):
        t = Transfer.objects.create(
            date=self.today, from_account=self.acct_a, to_account=self.acct_b,
            amount=3000, description='無効口座履歴',
        )
        self.acct_a.is_active = False
        self.acct_a.save()
        self.acct_b.is_active = False
        self.acct_b.save()
        form = TransferForm(data={
            'date': self.today.isoformat(),
            'from_account': self.acct_a.pk,
            'to_account': self.acct_b.pk,
            'amount': 3500,
            'description': '無効口座履歴修正',
            'memo': '',
        }, instance=t)
        self.assertTrue(form.is_valid(), form.errors)

    def test_update_transfer_recalculates_balance(self):
        t = Transfer.objects.create(
            date=self.today, from_account=self.acct_a, to_account=self.acct_b,
            amount=3000, description='初版',
        )
        # 編集: 出金元を C に変更し金額を 2000 に
        resp = self.client.post(
            reverse('ledger:transfer_update', args=[t.pk]) + f'?month={self.month_str}',
            {
                'date': self.today.isoformat(),
                'from_account': self.acct_c.pk,
                'to_account': self.acct_b.pk,
                'amount': 2000,
                'description': '改訂',
                'memo': '',
                'month': self.month_str,
            },
        )
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(calculate_account_balance(self.acct_a, self.today), 10000)
        self.assertEqual(calculate_account_balance(self.acct_c, self.today), 8000)
        self.assertEqual(calculate_account_balance(self.acct_b, self.today), 12000)

    def test_delete_transfer_restores_balance(self):
        t = Transfer.objects.create(
            date=self.today, from_account=self.acct_a, to_account=self.acct_b,
            amount=4000, description='削除予定',
        )
        self.assertEqual(calculate_account_balance(self.acct_a, self.today), 6000)
        resp = self.client.post(
            reverse('ledger:transfer_delete', args=[t.pk]) + f'?month={self.month_str}',
            {'month': self.month_str},
        )
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(calculate_account_balance(self.acct_a, self.today), 10000)
        self.assertEqual(calculate_account_balance(self.acct_b, self.today), 10000)

    def test_delete_transfer_via_htmx_updates_dashboard_only(self):
        t = Transfer.objects.create(
            date=self.today, from_account=self.acct_a, to_account=self.acct_b,
            amount=4000, description='HTMX削除予定',
        )
        resp = self.client.post(
            reverse('ledger:transfer_delete', args=[t.pk]) + f'?month={self.month_str}&page=1',
            {'month': self.month_str},
            HTTP_HX_REQUEST='true',
        )
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(Transfer.objects.filter(pk=t.pk).exists())
        body = resp.content.decode('utf-8')
        self.assertIn('id="dashboard-content"', body)
        self.assertIn('hx-swap-oob', body)
        self.assertIn('id="flash"', body)
        self.assertIn('振替を削除しました。', body)
        self.assertNotIn('id="form-panel"', body)

    def test_dashboard_transfer_delete_button_posts_inline(self):
        t = Transfer.objects.create(
            date=self.today, from_account=self.acct_a, to_account=self.acct_b,
            amount=4000, description='一覧削除ボタン',
        )
        resp = self.client.get(reverse('ledger:dashboard'), {'month': self.month_str})
        body = resp.content.decode('utf-8')
        self.assertIn(reverse('ledger:transfer_delete', args=[t.pk]), body)
        self.assertIn('hx-post=', body)
        self.assertIn('hx-swap="none"', body)
        self.assertIn('この振替を削除します', body)


class TransferCsvExportTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username='test', password='pass')
        cls.acct_a = Account.objects.create(name='口座A')
        cls.acct_b = Account.objects.create(name='口座B')
        cls.cat = Category.objects.create(name='食費', kind=Category.Kind.EXPENSE)

    def setUp(self):
        self.client.login(username='test', password='pass')
        self.today = date.today()
        self.month_str = f'{self.today.year}-{self.today.month:02d}'
        Transaction.objects.create(
            date=self.today, account=self.acct_a, category=self.cat,
            amount=500, description='コンビニ',
        )
        Transfer.objects.create(
            date=self.today, from_account=self.acct_a, to_account=self.acct_b,
            amount=8000, description='AからB',
        )

    def test_csv_export_includes_transfer_row(self):
        resp = self.client.get(
            reverse('ledger:transaction_export'),
            {'month': self.month_str},
        )
        content = resp.content.decode('utf-8-sig')
        self.assertIn('振替', content)
        self.assertIn('口座A → 口座B', content)
        self.assertIn('AからB', content)
        # 通常取引行も残っている
        self.assertIn('コンビニ', content)
