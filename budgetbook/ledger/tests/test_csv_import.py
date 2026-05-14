"""v1.8.0 CSV インポートのテスト。"""
from __future__ import annotations

from datetime import date

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from ledger.models import (
    Account,
    AuditLog,
    Category,
    MonthlyClosing,
    Transaction,
)
from ledger.services.csv_import import (
    MAX_BYTES,
    MAX_ROWS,
    CsvImportError,
    build_preview_rows,
    decode_csv_bytes,
    parse_csv,
)


HEADER = '日付,種別,口座,カテゴリ,金額,摘要,メモ\n'


def _make_csv(rows: list[list[str]], header: str = HEADER) -> str:
    body = ''
    for r in rows:
        body += ','.join(r) + '\n'
    return header + body


class DecodeTest(TestCase):
    def test_utf8_no_bom(self):
        text = decode_csv_bytes('日付'.encode('utf-8'))
        self.assertEqual(text, '日付')

    def test_utf8_with_bom(self):
        text = decode_csv_bytes(b'\xef\xbb\xbf' + '日付'.encode('utf-8'))
        self.assertEqual(text, '日付')

    def test_shift_jis_fallback(self):
        text = decode_csv_bytes('日付,支出'.encode('cp932'))
        self.assertEqual(text, '日付,支出')

    def test_oversize_rejected(self):
        big = b'a' * (MAX_BYTES + 1)
        with self.assertRaises(CsvImportError):
            decode_csv_bytes(big)

class ParseTest(TestCase):
    def test_header_mismatch_rejected(self):
        with self.assertRaises(CsvImportError):
            parse_csv('foo,bar\n1,2\n')

    def test_empty_rejected(self):
        with self.assertRaises(CsvImportError):
            parse_csv('')

    def test_max_rows_rejected(self):
        rows = [['2026-05-01', '支出', 'a', 'b', '1', 'd', ''] for _ in range(MAX_ROWS + 1)]
        with self.assertRaises(CsvImportError):
            parse_csv(_make_csv(rows))


class PreviewTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.account = Account.objects.create(name='テスト口座', opening_balance=10000)
        cls.cat_food = Category.objects.create(
            name='テスト食費', kind=Category.Kind.EXPENSE, section='food_daily',
        )
        cls.cat_income = Category.objects.create(
            name='テスト給与', kind=Category.Kind.INCOME,
        )

    def _preview(self, rows):
        return build_preview_rows(rows)

    def test_ok_row(self):
        pr = self._preview([['2026-05-01', '支出', 'テスト口座', 'テスト食費', '500', 'コンビニ', '']])
        self.assertEqual(pr[0].status, 'ok')
        self.assertEqual(pr[0].amount, 500)
        self.assertEqual(pr[0].account_id, self.account.pk)

    def test_income_kind_ok(self):
        pr = self._preview([['2026-05-01', '収入', 'テスト口座', 'テスト給与', '300000', '給料', '']])
        self.assertEqual(pr[0].status, 'ok')

    def test_invalid_date(self):
        pr = self._preview([['notdate', '支出', 'テスト口座', 'テスト食費', '500', '', '']])
        self.assertEqual(pr[0].status, 'error_date')

    def test_future_date_rejected(self):
        future = '2099-01-01'
        pr = self._preview([[future, '支出', 'テスト口座', 'テスト食費', '500', '', '']])
        self.assertEqual(pr[0].status, 'error_date')

    def test_invalid_amount(self):
        pr = self._preview([['2026-05-01', '支出', 'テスト口座', 'テスト食費', 'abc', '', '']])
        self.assertEqual(pr[0].status, 'error_amount')

    def test_zero_amount(self):
        pr = self._preview([['2026-05-01', '支出', 'テスト口座', 'テスト食費', '0', '', '']])
        self.assertEqual(pr[0].status, 'error_amount')

    def test_unknown_account(self):
        pr = self._preview([['2026-05-01', '支出', 'ない口座', 'テスト食費', '500', '', '']])
        self.assertEqual(pr[0].status, 'error_account')

    def test_unknown_category(self):
        pr = self._preview([['2026-05-01', '支出', 'テスト口座', 'ないカテゴリ', '500', '', '']])
        self.assertEqual(pr[0].status, 'error_category')

    def test_kind_category_mismatch(self):
        # 種別=収入 だがカテゴリは支出側
        pr = self._preview([['2026-05-01', '収入', 'テスト口座', 'テスト食費', '500', '', '']])
        self.assertEqual(pr[0].status, 'error_category')

    def test_transfer_skipped(self):
        pr = self._preview([['2026-05-01', '振替', 'テスト口座', 'テスト食費', '500', '', '']])
        self.assertEqual(pr[0].status, 'skip_transfer')

    def test_closed_month_blocked(self):
        MonthlyClosing.objects.create(
            month=date(2026, 4, 1),
            opening_carry=0, income=0, expense=0, net=0, closing_balance=0,
            account_balances=[],
        )
        pr = self._preview([['2026-04-15', '支出', 'テスト口座', 'テスト食費', '500', '', '']])
        self.assertEqual(pr[0].status, 'error_closed_month')

    def test_duplicate_detected(self):
        Transaction.objects.create(
            date=date(2026, 5, 1), account=self.account, category=self.cat_food,
            amount=500, description='既存',
        )
        pr = self._preview([['2026-05-01', '支出', 'テスト口座', 'テスト食費', '500', '別の摘要', '']])
        self.assertEqual(pr[0].status, 'warning_duplicate')
        self.assertTrue(pr[0].is_importable)

    def test_csv_injection_flag(self):
        pr = self._preview([['2026-05-01', '支出', 'テスト口座', 'テスト食費', '500', '=cmd|calc', '']])
        self.assertTrue(pr[0].csv_unsafe)

    def test_slash_date_accepted(self):
        pr = self._preview([['2026/05/01', '支出', 'テスト口座', 'テスト食費', '500', '', '']])
        self.assertEqual(pr[0].status, 'ok')


class ViewTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username='imp', password='pass')
        cls.account = Account.objects.create(name='イ口座', opening_balance=10000)
        cls.cat = Category.objects.create(
            name='イ食費', kind=Category.Kind.EXPENSE, section='food_daily',
        )

    def setUp(self):
        self.client.login(username='imp', password='pass')

    def test_get_form(self):
        resp = self.client.get(reverse('ledger:transaction_import'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'CSV インポート')

    def test_login_required(self):
        self.client.logout()
        resp = self.client.get(reverse('ledger:transaction_import'))
        self.assertEqual(resp.status_code, 302)

    def test_preview_then_confirm(self):
        csv_text = _make_csv([
            ['2026-05-01', '支出', 'イ口座', 'イ食費', '500', 'コンビニ', ''],
            ['2026-05-02', '支出', 'イ口座', 'イ食費', '700', 'スーパー', ''],
        ])
        upload = SimpleUploadedFile('test.csv', csv_text.encode('utf-8'), content_type='text/csv')
        resp = self.client.post(reverse('ledger:transaction_import'), {'csv_file': upload})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, '取込可能: 2')

        # confirm
        resp2 = self.client.post(reverse('ledger:transaction_import'), {
            'confirm': '1',
            'csv_text': csv_text,
            'filename': 'test.csv',
            'selected_lines': ['2', '3'],
        })
        self.assertEqual(resp2.status_code, 302)
        self.assertEqual(Transaction.objects.count(), 2)
        log = AuditLog.objects.filter(target_repr__contains='CSV').first()
        self.assertIsNotNone(log)
        self.assertEqual(log.metadata['count'], 2)
        self.assertEqual(len(log.metadata['created_ids']), 2)

    def test_confirm_selects_only_marked_lines(self):
        csv_text = _make_csv([
            ['2026-05-01', '支出', 'イ口座', 'イ食費', '500', 'A', ''],
            ['2026-05-02', '支出', 'イ口座', 'イ食費', '700', 'B', ''],
        ])
        # 2 行目だけ選択
        resp = self.client.post(reverse('ledger:transaction_import'), {
            'confirm': '1',
            'csv_text': csv_text,
            'filename': 'test.csv',
            'selected_lines': ['3'],
        })
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(Transaction.objects.count(), 1)
        self.assertEqual(Transaction.objects.first().description, 'B')

    def test_confirm_rolls_back_on_failure(self):
        # csv_text を不正に書き換え（パース不可）→ ロールバックされ 0 件
        resp = self.client.post(reverse('ledger:transaction_import'), {
            'confirm': '1',
            'csv_text': 'broken,header\n1,2',
            'filename': 'test.csv',
            'selected_lines': ['2'],
        })
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(Transaction.objects.count(), 0)

    def test_shift_jis_upload(self):
        csv_text = _make_csv([['2026-05-01', '支出', 'イ口座', 'イ食費', '500', 'コンビニ', '']])
        upload = SimpleUploadedFile('sjis.csv', csv_text.encode('cp932'), content_type='text/csv')
        resp = self.client.post(reverse('ledger:transaction_import'), {'csv_file': upload})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, '取込可能: 1')

    def test_wrong_extension_rejected(self):
        upload = SimpleUploadedFile('test.txt', b'foo', content_type='text/plain')
        resp = self.client.post(reverse('ledger:transaction_import'), {'csv_file': upload})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, '.csv')

    def test_dashboard_has_import_link(self):
        resp = self.client.get(reverse('ledger:dashboard'))
        self.assertIn(b'CSV', resp.content)
        self.assertIn(reverse('ledger:transaction_import').encode(), resp.content)