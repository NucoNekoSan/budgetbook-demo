import csv
from datetime import date, timedelta

from django.contrib.auth.models import User
from django.test import TestCase, Client
from django.urls import reverse

from ledger.models import Account, Category, Transaction
from ledger.views import clamp_future_month, month_param


class ClampFutureMonthTest(TestCase):

    def test_future_month_clamped_to_current(self):
        today = date.today()
        future = date(today.year + 1, 1, 1)
        result = clamp_future_month(future)
        self.assertEqual(result, date(today.year, today.month, 1))

    def test_current_month_not_clamped(self):
        today = date.today()
        current = date(today.year, today.month, 1)
        self.assertEqual(clamp_future_month(current), current)

    def test_past_month_not_clamped(self):
        past = date(2020, 1, 1)
        self.assertEqual(clamp_future_month(past), past)


class DashboardFutureMonthTest(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username='test', password='pass')
        cls.account = Account.objects.create(name='口座A')
        cls.category = Category.objects.create(name='食費', kind=Category.Kind.EXPENSE)

    def setUp(self):
        self.client.login(username='test', password='pass')

    def test_future_month_query_shows_current_month(self):
        today = date.today()
        future_param = f'{today.year + 1}-06'
        resp = self.client.get(reverse('ledger:dashboard'), {'month': future_param})
        self.assertEqual(resp.status_code, 200)
        ctx_month = resp.context['month_param']
        expected = month_param(date(today.year, today.month, 1))
        self.assertEqual(ctx_month, expected)

    def test_dashboard_loads_htmx_error_swap_config(self):
        resp = self.client.get(reverse('ledger:dashboard'))
        self.assertContains(resp, 'js/htmx_config.js')


class TransactionExportTest(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username='test', password='pass')
        cls.account = Account.objects.create(name='メイン口座')
        cls.category = Category.objects.create(name='食費', kind=Category.Kind.EXPENSE)
        today = date.today()
        cls.month_str = f'{today.year}-{today.month:02d}'
        Transaction.objects.create(
            date=today,
            account=cls.account,
            category=cls.category,
            amount=500,
            description='コンビニ',
        )

    def setUp(self):
        self.client.login(username='test', password='pass')

    def test_export_returns_200(self):
        url = reverse('ledger:transaction_export')
        resp = self.client.get(url, {'month': self.month_str})
        self.assertEqual(resp.status_code, 200)

    def test_export_has_csv_header_row(self):
        url = reverse('ledger:transaction_export')
        resp = self.client.get(url, {'month': self.month_str})
        content = resp.content.decode('utf-8-sig')
        first_line = content.split('\r\n')[0]
        self.assertEqual(first_line, '日付,種別,口座,カテゴリ,金額,摘要,メモ')

    def test_export_content_disposition_has_filename(self):
        url = reverse('ledger:transaction_export')
        resp = self.client.get(url, {'month': self.month_str})
        cd = resp['Content-Disposition']
        self.assertIn('attachment', cd)
        self.assertIn(f'kakeibo-{self.month_str}.csv', cd)

    def test_export_contains_transaction_data(self):
        url = reverse('ledger:transaction_export')
        resp = self.client.get(url, {'month': self.month_str})
        content = resp.content.decode('utf-8-sig')
        self.assertIn('コンビニ', content)
        self.assertIn('500', content)

    def test_export_escapes_formula_like_user_input(self):
        dangerous_account = Account.objects.create(name='+危険口座')
        dangerous_category = Category.objects.create(name='-危険カテゴリ', kind=Category.Kind.EXPENSE)
        Transaction.objects.create(
            date=date.today(),
            account=dangerous_account,
            category=dangerous_category,
            amount=100,
            description='=HYPERLINK("http://example.test")',
            memo=' @SUM(1,1)',
        )
        url = reverse('ledger:transaction_export')
        resp = self.client.get(url, {'month': self.month_str})
        content = resp.content.decode('utf-8-sig').splitlines()
        rows = list(csv.reader(content))
        dangerous_row = next(row for row in rows if row[5].startswith("'=HYPERLINK"))
        self.assertEqual(dangerous_row[2], "'+危険口座")
        self.assertEqual(dangerous_row[3], "'-危険カテゴリ")
        self.assertEqual(dangerous_row[5], '\'=HYPERLINK("http://example.test")')
        self.assertEqual(dangerous_row[6], "' @SUM(1,1)")


class DashboardSearchFilterTest(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username='test', password='pass')
        cls.account_a = Account.objects.create(name='口座A')
        cls.account_b = Account.objects.create(name='口座B')
        cls.cat_food = Category.objects.create(name='食費', kind=Category.Kind.EXPENSE)
        cls.cat_transport = Category.objects.create(name='交通費', kind=Category.Kind.EXPENSE)

        today = date.today()
        cls.tx1 = Transaction.objects.create(
            date=today, account=cls.account_a, category=cls.cat_food,
            amount=800, description='スーパー',
        )
        cls.tx2 = Transaction.objects.create(
            date=today, account=cls.account_b, category=cls.cat_transport,
            amount=200, description='電車',
        )
        cls.month_str = f'{today.year}-{today.month:02d}'

    def setUp(self):
        self.client.login(username='test', password='pass')

    def test_search_by_description(self):
        resp = self.client.get(
            reverse('ledger:dashboard'),
            {'month': self.month_str, 'q': 'スーパー'},
        )
        self.assertEqual(resp.status_code, 200)
        transactions = list(resp.context['page_obj'])
        descriptions = [tx.description for tx in transactions]
        self.assertIn('スーパー', descriptions)
        self.assertNotIn('電車', descriptions)

    def test_filter_by_account(self):
        resp = self.client.get(
            reverse('ledger:dashboard'),
            {'month': self.month_str, 'account': self.account_a.pk},
        )
        transactions = list(resp.context['page_obj'])
        self.assertTrue(all(tx.account_id == self.account_a.pk for tx in transactions))
        self.assertEqual(len(transactions), 1)

    def test_filter_by_category(self):
        resp = self.client.get(
            reverse('ledger:dashboard'),
            {'month': self.month_str, 'category': self.cat_transport.pk},
        )
        transactions = list(resp.context['page_obj'])
        self.assertEqual(len(transactions), 1)
        self.assertEqual(transactions[0].description, '電車')

    def test_search_no_match(self):
        resp = self.client.get(
            reverse('ledger:dashboard'),
            {'month': self.month_str, 'q': '存在しない摘要'},
        )
        transactions = list(resp.context['page_obj'])
        self.assertEqual(len(transactions), 0)

    def test_invalid_filter_values_do_not_500(self):
        resp = self.client.get(
            reverse('ledger:dashboard'),
            {'month': self.month_str, 'account': 'abc', 'category': '!@#'},
        )
        self.assertEqual(resp.status_code, 200)


class DailyTrendTest(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username='test', password='pass')
        cls.account = Account.objects.create(name='口座A')
        cls.cat_income = Category.objects.create(name='給与', kind=Category.Kind.INCOME)
        cls.cat_expense = Category.objects.create(name='食費', kind=Category.Kind.EXPENSE)

        today = date.today()
        cls.today = today
        cls.month_str = f'{today.year}-{today.month:02d}'
        Transaction.objects.create(
            date=today, account=cls.account, category=cls.cat_income,
            amount=5000, description='給与',
        )
        Transaction.objects.create(
            date=today, account=cls.account, category=cls.cat_expense,
            amount=2000, description='スーパー',
        )

    def setUp(self):
        self.client.login(username='test', password='pass')

    def test_trend_covers_all_days_in_month(self):
        resp = self.client.get(reverse('ledger:dashboard'), {'month': self.month_str})
        trend = resp.context['daily_trend']
        from calendar import monthrange
        expected_days = monthrange(self.today.year, self.today.month)[1]
        self.assertEqual(len(trend), expected_days)

    def test_trend_includes_today_data(self):
        resp = self.client.get(reverse('ledger:dashboard'), {'month': self.month_str})
        trend = resp.context['daily_trend']
        today_entry = trend[self.today.day - 1]
        self.assertEqual(today_entry['label'], f'{self.today.day}日')
        self.assertEqual(today_entry['income'], 5000)
        self.assertEqual(today_entry['expense'], 2000)
        self.assertEqual(today_entry['net'], 3000)

    def test_trend_empty_days_have_zero(self):
        resp = self.client.get(reverse('ledger:dashboard'), {'month': self.month_str})
        trend = resp.context['daily_trend']
        empty_idx = 0 if self.today.day != 1 else 1
        empty = trend[empty_idx]
        self.assertEqual(empty['income'], 0)
        self.assertEqual(empty['expense'], 0)
        self.assertEqual(empty['net'], 0)

    def test_trend_unaffected_by_filters(self):
        resp = self.client.get(
            reverse('ledger:dashboard'),
            {'month': self.month_str, 'q': '存在しない'},
        )
        trend = resp.context['daily_trend']
        today_entry = trend[self.today.day - 1]
        self.assertEqual(today_entry['income'], 5000)
        self.assertEqual(today_entry['expense'], 2000)


class TransactionCreateTest(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username='test', password='pass')
        cls.account = Account.objects.create(name='口座A')
        cls.cat_expense = Category.objects.create(name='食費', kind=Category.Kind.EXPENSE)

    def setUp(self):
        self.client.login(username='test', password='pass')
        today = date.today()
        self.month_str = f'{today.year}-{today.month:02d}'

    def _post_data(self, **overrides):
        data = {
            'date': date.today().isoformat(),
            'account': self.account.pk,
            'kind': 'expense',
            'category': self.cat_expense.pk,
            'amount': 1000,
            'description': 'テスト取引',
            'memo': '',
            'month': self.month_str,
        }
        data.update(overrides)
        return data

    def test_create_success_redirects(self):
        resp = self.client.post(
            reverse('ledger:transaction_create') + f'?month={self.month_str}',
            self._post_data(),
        )
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(Transaction.objects.filter(description='テスト取引').exists())

    def test_create_redirects_to_saved_date_month(self):
        today = date.today()
        previous_month = date(today.year, today.month, 1) - timedelta(days=1)
        previous_month_str = f'{previous_month.year}-{previous_month.month:02d}'
        resp = self.client.post(
            reverse('ledger:transaction_create') + f'?month={previous_month_str}',
            self._post_data(month=previous_month_str, date=today.isoformat()),
        )
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp['Location'], f"{reverse('ledger:dashboard')}?month={self.month_str}")

    def test_create_saves_correct_values(self):
        self.client.post(
            reverse('ledger:transaction_create') + f'?month={self.month_str}',
            self._post_data(amount=2500, description='スーパー'),
        )
        tx = Transaction.objects.get(description='スーパー')
        self.assertEqual(tx.amount, 2500)
        self.assertEqual(tx.account, self.account)
        self.assertEqual(tx.category, self.cat_expense)

    def test_create_missing_description_returns_200(self):
        resp = self.client.post(
            reverse('ledger:transaction_create') + f'?month={self.month_str}',
            self._post_data(description=''),
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(Transaction.objects.count(), 0)

    def test_create_zero_amount_returns_200(self):
        resp = self.client.post(
            reverse('ledger:transaction_create') + f'?month={self.month_str}',
            self._post_data(amount=0),
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(Transaction.objects.count(), 0)


class TransactionUpdateTest(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username='test', password='pass')
        cls.account = Account.objects.create(name='口座A')
        cls.cat_expense = Category.objects.create(name='食費', kind=Category.Kind.EXPENSE)

    def setUp(self):
        self.client.login(username='test', password='pass')
        today = date.today()
        self.month_str = f'{today.year}-{today.month:02d}'
        self.tx = Transaction.objects.create(
            date=today, account=self.account, category=self.cat_expense,
            amount=500, description='元の取引',
        )

    def test_update_success_redirects(self):
        resp = self.client.post(
            reverse('ledger:transaction_update', args=[self.tx.pk]) + f'?month={self.month_str}',
            {
                'date': self.tx.date.isoformat(),
                'account': self.account.pk,
                'kind': 'expense',
                'category': self.cat_expense.pk,
                'amount': 800,
                'description': '更新後',
                'memo': '',
                'month': self.month_str,
            },
        )
        self.assertEqual(resp.status_code, 302)
        self.tx.refresh_from_db()
        self.assertEqual(self.tx.description, '更新後')
        self.assertEqual(self.tx.amount, 800)

    def test_update_nonexistent_returns_404(self):
        resp = self.client.get(
            reverse('ledger:transaction_update', args=[99999]) + f'?month={self.month_str}',
        )
        self.assertEqual(resp.status_code, 404)

    def test_update_validation_error_returns_200(self):
        resp = self.client.post(
            reverse('ledger:transaction_update', args=[self.tx.pk]) + f'?month={self.month_str}',
            {
                'date': self.tx.date.isoformat(),
                'account': self.account.pk,
                'kind': 'expense',
                'category': self.cat_expense.pk,
                'amount': 0,
                'description': '',
                'memo': '',
                'month': self.month_str,
            },
        )
        self.assertEqual(resp.status_code, 200)
        self.tx.refresh_from_db()
        self.assertEqual(self.tx.description, '元の取引')


class TransactionDeleteTest(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username='test', password='pass')
        cls.account = Account.objects.create(name='口座A')
        cls.cat_expense = Category.objects.create(name='食費', kind=Category.Kind.EXPENSE)

    def setUp(self):
        self.client.login(username='test', password='pass')
        today = date.today()
        self.month_str = f'{today.year}-{today.month:02d}'
        self.tx = Transaction.objects.create(
            date=today, account=self.account, category=self.cat_expense,
            amount=300, description='削除対象',
        )

    def test_delete_get_shows_confirmation(self):
        resp = self.client.get(
            reverse('ledger:transaction_delete', args=[self.tx.pk]) + f'?month={self.month_str}',
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, '削除対象')

    def test_delete_post_removes_transaction(self):
        resp = self.client.post(
            reverse('ledger:transaction_delete', args=[self.tx.pk]) + f'?month={self.month_str}',
            {'month': self.month_str},
        )
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(Transaction.objects.filter(pk=self.tx.pk).exists())

    def test_delete_post_via_htmx_updates_dashboard_only(self):
        resp = self.client.post(
            reverse('ledger:transaction_delete', args=[self.tx.pk]) + f'?month={self.month_str}&page=1',
            {'month': self.month_str},
            HTTP_HX_REQUEST='true',
        )
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(Transaction.objects.filter(pk=self.tx.pk).exists())
        body = resp.content.decode('utf-8')
        self.assertIn('id="dashboard-content"', body)
        self.assertIn('hx-swap-oob', body)
        self.assertIn('id="flash"', body)
        self.assertIn('取引を削除しました。', body)
        self.assertNotIn('id="form-panel"', body)

    def test_dashboard_delete_button_posts_inline(self):
        resp = self.client.get(reverse('ledger:dashboard'), {'month': self.month_str})
        body = resp.content.decode('utf-8')
        self.assertIn(reverse('ledger:transaction_delete', args=[self.tx.pk]), body)
        self.assertIn('hx-post=', body)
        self.assertIn('hx-swap="none"', body)
        self.assertIn('この取引を削除します', body)

    def test_delete_nonexistent_returns_404(self):
        resp = self.client.post(
            reverse('ledger:transaction_delete', args=[99999]) + f'?month={self.month_str}',
        )
        self.assertEqual(resp.status_code, 404)
