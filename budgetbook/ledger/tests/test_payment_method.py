from __future__ import annotations

from datetime import date

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from ledger.forms import TransactionForm
from ledger.models import Account, Category, PaymentMethod, Transaction
from ledger.services.csv_import import build_preview_rows, commit_rows


class PaymentMethodModelTest(TestCase):
    def test_settlement_account_rejects_liability_account(self):
        liability = Account.objects.create(
            name='PM負債口座',
            kind=Account.Kind.LIABILITY,
            opening_balance=-1000,
        )
        with self.assertRaises(ValidationError):
            PaymentMethod.objects.create(
                name='カードA',
                kind=PaymentMethod.Kind.CREDIT_CARD,
                settlement_account=liability,
            )

    def test_day_fields_accept_zero_to_31(self):
        payment_method = PaymentMethod.objects.create(
            name='締日テスト',
            kind=PaymentMethod.Kind.CREDIT_CARD,
            closing_day=31,
            settlement_day=0,
        )
        self.assertEqual(payment_method.closing_day, 31)

    def test_day_fields_reject_over_31(self):
        with self.assertRaises(ValidationError):
            PaymentMethod.objects.create(
                name='不正日付',
                kind=PaymentMethod.Kind.CREDIT_CARD,
                closing_day=32,
            )


class PaymentMethodCrudTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username='pmcrud', password='pass')
        cls.asset_account = Account.objects.create(name='PM資産口座')
        cls.category = Category.objects.create(name='PM支出', kind=Category.Kind.EXPENSE)

    def setUp(self):
        self.client.login(username='pmcrud', password='pass')

    def test_create_payment_method(self):
        resp = self.client.post(reverse('ledger:payment_method_create'), {
            'name': '電子マネーA',
            'kind': PaymentMethod.Kind.ELECTRONIC_MONEY,
            'account': self.asset_account.pk,
            'settlement_account': '',
            'closing_day': 0,
            'settlement_day': 0,
            'notes': 'テスト',
        })
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(PaymentMethod.objects.filter(name='電子マネーA').exists())

    def test_settlement_liability_error_is_displayed(self):
        liability = Account.objects.create(
            name='PMカード負債',
            kind=Account.Kind.LIABILITY,
            opening_balance=-1000,
        )
        resp = self.client.post(reverse('ledger:payment_method_create'), {
            'name': 'カードB',
            'kind': PaymentMethod.Kind.CREDIT_CARD,
            'account': liability.pk,
            'settlement_account': liability.pk,
            'closing_day': 10,
            'settlement_day': 27,
            'notes': '',
        })
        self.assertEqual(resp.status_code, 422)
        self.assertContains(resp, '引落元口座は資産口座', status_code=422)

    def test_used_payment_method_cannot_be_deleted_and_can_be_disabled(self):
        payment_method = PaymentMethod.objects.create(
            name='使用中支払手段',
            kind=PaymentMethod.Kind.CASH,
            account=self.asset_account,
        )
        Transaction.objects.create(
            date=date(2026, 5, 1),
            account=self.asset_account,
            category=self.category,
            payment_method=payment_method,
            amount=1000,
            description='履歴',
        )
        resp = self.client.post(reverse('ledger:payment_method_delete', args=[payment_method.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(PaymentMethod.objects.filter(pk=payment_method.pk).exists())
        self.assertContains(resp, '削除できません')

        self.client.post(reverse('ledger:payment_method_toggle', args=[payment_method.pk]))
        payment_method.refresh_from_db()
        self.assertFalse(payment_method.is_active)

    def test_settings_page_contains_payment_method_section(self):
        PaymentMethod.objects.create(name='設定表示支払手段', kind=PaymentMethod.Kind.CASH)
        resp = self.client.get(reverse('ledger:settings'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, '支払手段')
        self.assertContains(resp, '設定表示支払手段')


class TransactionPaymentMethodTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username='pmtx', password='pass')
        cls.account = Account.objects.create(name='PM取引口座')
        cls.category = Category.objects.create(name='PM取引支出', kind=Category.Kind.EXPENSE)
        cls.payment_method = PaymentMethod.objects.create(
            name='取引支払手段',
            kind=PaymentMethod.Kind.CASH,
            account=cls.account,
        )

    def setUp(self):
        self.client.login(username='pmtx', password='pass')

    def _form_data(self, payment_method=''):
        return {
            'date': '2026-05-01',
            'account': self.account.pk,
            'kind': Category.Kind.EXPENSE,
            'category': self.category.pk,
            'payee': '',
            'payment_method': payment_method,
            'amount': 1000,
            'description': '支払手段テスト',
            'memo': '',
        }

    def test_transaction_form_payment_method_is_optional(self):
        form = TransactionForm(data=self._form_data())
        self.assertTrue(form.is_valid(), form.errors)
        tx = form.save()
        self.assertIsNone(tx.payment_method)

    def test_transaction_form_accepts_payment_method(self):
        form = TransactionForm(data=self._form_data(self.payment_method.pk))
        self.assertTrue(form.is_valid(), form.errors)
        tx = form.save()
        self.assertEqual(tx.payment_method, self.payment_method)

    def test_existing_transaction_can_keep_disabled_payment_method(self):
        tx = Transaction.objects.create(
            date=date(2026, 5, 1),
            account=self.account,
            category=self.category,
            payment_method=self.payment_method,
            amount=1000,
            description='履歴',
        )
        self.payment_method.is_active = False
        self.payment_method.save()
        form = TransactionForm(data=self._form_data(self.payment_method.pk), instance=tx)
        self.assertTrue(form.is_valid(), form.errors)

    def test_transaction_create_view_saves_payment_method(self):
        resp = self.client.post(
            reverse('ledger:transaction_create'),
            self._form_data(self.payment_method.pk),
        )
        self.assertEqual(resp.status_code, 302)
        tx = Transaction.objects.get(description='支払手段テスト')
        self.assertEqual(tx.payment_method, self.payment_method)

    def test_dashboard_search_matches_payment_method_name(self):
        Transaction.objects.create(
            date=date(2026, 5, 1),
            account=self.account,
            category=self.category,
            payment_method=self.payment_method,
            amount=1000,
            description='別摘要',
        )
        resp = self.client.get(reverse('ledger:dashboard'), {'month': '2026-05', 'q': '取引支払手段'})
        self.assertEqual(resp.status_code, 200)
        descriptions = [row.description for row in resp.context['page_obj']]
        self.assertIn('別摘要', descriptions)


class PaymentMethodCsvImportTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username='pmimp', password='pass')
        cls.account = Account.objects.create(name='CSVPM口座')
        cls.category = Category.objects.create(name='CSVPM支出', kind=Category.Kind.EXPENSE)
        cls.payment_method = PaymentMethod.objects.create(name='CSV支払手段', kind=PaymentMethod.Kind.CASH)

    def setUp(self):
        self.client.login(username='pmimp', password='pass')

    def test_preview_without_payment_method_column_keeps_null(self):
        preview = build_preview_rows([
            ['2026-05-01', '支出', 'CSVPM口座', 'CSVPM支出', '500', '摘要', ''],
        ])
        self.assertEqual(preview[0].status, 'ok')
        self.assertIsNone(preview[0].payment_method_id)

    def test_preview_matches_optional_payment_method_column(self):
        preview = build_preview_rows([
            ['2026-05-01', '支出', 'CSVPM口座', 'CSVPM支出', '500', '摘要', '', 'CSV支払手段'],
        ])
        self.assertEqual(preview[0].status, 'ok')
        self.assertEqual(preview[0].payment_method_id, self.payment_method.pk)
        self.assertEqual(preview[0].payment_method_name, 'CSV支払手段')

    def test_preview_unknown_payment_method_warns_but_importable(self):
        preview = build_preview_rows([
            ['2026-05-01', '支出', 'CSVPM口座', 'CSVPM支出', '500', '摘要', '', '未知手段'],
        ])
        self.assertEqual(preview[0].status, 'ok')
        self.assertTrue(preview[0].is_importable)
        self.assertIn('支払手段が見つかりません', preview[0].payment_method_warning)

    def test_commit_sets_payment_method_candidate(self):
        preview = build_preview_rows([
            ['2026-05-01', '支出', 'CSVPM口座', 'CSVPM支出', '500', '摘要', '', 'CSV支払手段'],
        ])
        created_ids = commit_rows(preview, {2})
        tx = Transaction.objects.get(pk=created_ids[0])
        self.assertEqual(tx.payment_method, self.payment_method)

    def test_preview_template_shows_payment_method_candidate(self):
        csv_text = (
            '日付,種別,口座,カテゴリ,金額,摘要,メモ,支払手段\n'
            '2026-05-01,支出,CSVPM口座,CSVPM支出,500,摘要,,CSV支払手段\n'
        )
        upload = SimpleUploadedFile('payment-method.csv', csv_text.encode('utf-8'), content_type='text/csv')
        resp = self.client.post(reverse('ledger:transaction_import'), {'csv_file': upload})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, '支払手段')
        self.assertContains(resp, 'CSV支払手段')
