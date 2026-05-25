from __future__ import annotations

from datetime import date

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from ledger.forms import TransactionForm
from ledger.models import Account, Category, Payee, PayeeAlias, Transaction
from ledger.services.csv_import import build_preview_rows, commit_rows


class PayeeModelTest(TestCase):
    def test_normalized_name_is_unique(self):
        Payee.objects.create(name='店舗 A')
        with self.assertRaises(ValidationError):
            Payee.objects.create(name='  店舗   a  ')

    def test_alias_cannot_conflict_with_other_payee_name(self):
        Payee.objects.create(name='店舗A')
        other = Payee.objects.create(name='店舗B')
        with self.assertRaises(ValidationError):
            PayeeAlias.objects.create(payee=other, alias='店舗A')

    def test_alias_cannot_conflict_with_other_alias(self):
        payee = Payee.objects.create(name='店舗A')
        other = Payee.objects.create(name='店舗B')
        PayeeAlias.objects.create(payee=payee, alias='明細A')
        with self.assertRaises(ValidationError):
            PayeeAlias.objects.create(payee=other, alias=' 明細a ')


class PayeeCrudTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username='payee', password='pass')
        cls.account = Account.objects.create(name='Payeeテスト口座')
        cls.category = Category.objects.create(name='Payeeテスト支出', kind=Category.Kind.EXPENSE)

    def setUp(self):
        self.client.login(username='payee', password='pass')

    def test_create_payee_with_aliases(self):
        resp = self.client.post(reverse('ledger:payee_create'), {
            'name': '店舗A',
            'aliases_text': '明細A\n店舗Ａ',
            'notes': 'テスト',
        })
        self.assertEqual(resp.status_code, 200)
        payee = Payee.objects.get(name='店舗A')
        self.assertEqual(payee.aliases.count(), 2)

    def test_duplicate_payee_name_shows_friendly_error(self):
        Payee.objects.create(name='店舗A')
        resp = self.client.post(reverse('ledger:payee_create'), {
            'name': ' 店舗a ',
            'aliases_text': '',
            'notes': '',
        })
        self.assertEqual(resp.status_code, 422)
        self.assertContains(resp, '既に使われています', status_code=422)

    def test_used_payee_cannot_be_deleted_and_can_be_disabled(self):
        payee = Payee.objects.create(name='使用中支払先')
        Transaction.objects.create(
            date=date(2026, 5, 1),
            account=self.account,
            category=self.category,
            payee=payee,
            amount=1000,
            description='履歴',
        )
        resp = self.client.post(reverse('ledger:payee_delete', args=[payee.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(Payee.objects.filter(pk=payee.pk).exists())
        self.assertContains(resp, '削除できません')

        self.client.post(reverse('ledger:payee_toggle', args=[payee.pk]))
        payee.refresh_from_db()
        self.assertFalse(payee.is_active)

    def test_settings_page_contains_payee_section(self):
        Payee.objects.create(name='設定表示支払先')
        resp = self.client.get(reverse('ledger:settings'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, '支払先')
        self.assertContains(resp, '設定表示支払先')


class TransactionPayeeTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username='txpayee', password='pass')
        cls.account = Account.objects.create(name='取引Payee口座')
        cls.category = Category.objects.create(name='取引Payee支出', kind=Category.Kind.EXPENSE)
        cls.payee = Payee.objects.create(name='取引支払先')

    def setUp(self):
        self.client.login(username='txpayee', password='pass')

    def _form_data(self, payee=''):
        return {
            'date': '2026-05-01',
            'account': self.account.pk,
            'kind': Category.Kind.EXPENSE,
            'category': self.category.pk,
            'payee': payee,
            'amount': 1000,
            'description': '摘要は維持',
            'memo': '',
        }

    def test_transaction_form_payee_is_optional(self):
        form = TransactionForm(data=self._form_data())
        self.assertTrue(form.is_valid(), form.errors)
        tx = form.save()
        self.assertIsNone(tx.payee)

    def test_transaction_form_accepts_payee(self):
        form = TransactionForm(data=self._form_data(self.payee.pk))
        self.assertTrue(form.is_valid(), form.errors)
        tx = form.save()
        self.assertEqual(tx.payee, self.payee)

    def test_existing_transaction_can_keep_disabled_payee(self):
        tx = Transaction.objects.create(
            date=date(2026, 5, 1),
            account=self.account,
            category=self.category,
            payee=self.payee,
            amount=1000,
            description='履歴',
        )
        self.payee.is_active = False
        self.payee.save()
        form = TransactionForm(data=self._form_data(self.payee.pk), instance=tx)
        self.assertTrue(form.is_valid(), form.errors)

    def test_transaction_create_view_saves_payee(self):
        resp = self.client.post(reverse('ledger:transaction_create'), self._form_data(self.payee.pk))
        self.assertEqual(resp.status_code, 302)
        tx = Transaction.objects.get(description='摘要は維持')
        self.assertEqual(tx.payee, self.payee)

    def test_dashboard_search_matches_payee_name(self):
        Transaction.objects.create(
            date=date(2026, 5, 1),
            account=self.account,
            category=self.category,
            payee=self.payee,
            amount=1000,
            description='別摘要',
        )
        resp = self.client.get(reverse('ledger:dashboard'), {'month': '2026-05', 'q': '取引支払先'})
        self.assertEqual(resp.status_code, 200)
        descriptions = [row.description for row in resp.context['page_obj']]
        self.assertIn('別摘要', descriptions)


class PayeeCsvImportTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username='payeeimp', password='pass')
        cls.account = Account.objects.create(name='CSVPayee口座')
        cls.category = Category.objects.create(name='CSVPayee支出', kind=Category.Kind.EXPENSE)
        cls.payee = Payee.objects.create(name='CSV支払先')
        PayeeAlias.objects.create(payee=cls.payee, alias='CSV明細')

    def setUp(self):
        self.client.login(username='payeeimp', password='pass')

    def test_preview_matches_payee_alias_from_description(self):
        preview = build_preview_rows([
            ['2026-05-01', '支出', 'CSVPayee口座', 'CSVPayee支出', '500', 'CSV明細', ''],
        ])
        self.assertEqual(preview[0].status, 'ok')
        self.assertEqual(preview[0].payee_id, self.payee.pk)
        self.assertEqual(preview[0].payee_name, 'CSV支払先')

    def test_commit_sets_payee_candidate(self):
        preview = build_preview_rows([
            ['2026-05-01', '支出', 'CSVPayee口座', 'CSVPayee支出', '500', 'CSV明細', ''],
        ])
        created_ids = commit_rows(preview, {2})
        tx = Transaction.objects.get(pk=created_ids[0])
        self.assertEqual(tx.payee, self.payee)
        self.assertEqual(tx.description, 'CSV明細')

    def test_preview_template_shows_payee_candidate(self):
        csv_text = '日付,種別,口座,カテゴリ,金額,摘要,メモ\n2026-05-01,支出,CSVPayee口座,CSVPayee支出,500,CSV明細,\n'
        upload = SimpleUploadedFile('payee.csv', csv_text.encode('utf-8'), content_type='text/csv')
        resp = self.client.post(reverse('ledger:transaction_import'), {'csv_file': upload})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, '支払先候補')
        self.assertContains(resp, 'CSV支払先')
