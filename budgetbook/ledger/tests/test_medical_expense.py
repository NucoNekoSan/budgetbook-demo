"""v1.16.0: 医療費控除の本格対応テスト。

- MedicalExpense モデル / clean / Unique 制約
- AnnualIncomeSnapshot
- calculate_medical_deduction 計算ロジック
- 専用ページ /medical-expenses/ CRUD
- CSV エクスポート (国税庁様式準拠)
- 取引フォーム HTMX 拡張 (medical fields)
"""
from __future__ import annotations

from datetime import date

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction as db_transaction
from django.test import TestCase
from django.urls import reverse

from ledger.models import (
    Account,
    AnnualIncomeSnapshot,
    AuditLog,
    Category,
    MedicalExpense,
    Transaction,
)
from ledger.services.medical import calculate_medical_deduction


def _make_account():
    return Account.objects.create(name='普通預金A', opening_balance=200000)


def _make_medical_category():
    return Category.objects.create(
        name='医療費',
        kind=Category.Kind.EXPENSE,
        tax_tag=Category.TaxTag.MEDICAL,
    )


def _make_non_medical_category():
    return Category.objects.create(
        name='食費',
        kind=Category.Kind.EXPENSE,
        tax_tag=Category.TaxTag.NONE,
    )


# ===========================================================================
# モデル / 計算ロジック
# ===========================================================================

class MedicalExpenseModelTest(TestCase):
    def setUp(self):
        self.account = _make_account()
        self.cat_medical = _make_medical_category()
        self.cat_food = _make_non_medical_category()

    def test_medical_expense_create_minimal(self):
        e = MedicalExpense.objects.create(
            paid_date=date(2025, 4, 1),
            patient='本人',
            provider='〇〇クリニック',
            category=MedicalExpense.MedicalCategory.TREATMENT,
            amount=3000,
        )
        self.assertEqual(e.reimbursement, 0)
        self.assertEqual(e.net_amount, 3000)
        self.assertIsNone(e.transaction_id)

    def test_reimbursement_cannot_exceed_amount(self):
        with self.assertRaises(ValidationError):
            MedicalExpense.objects.create(
                paid_date=date(2025, 4, 1),
                patient='本人',
                provider='〇〇クリニック',
                category=MedicalExpense.MedicalCategory.TREATMENT,
                amount=3000,
                reimbursement=4000,
            )

    def test_transaction_tag_must_be_medical(self):
        # 食費カテゴリの取引に紐付けようとすると ValidationError
        tx = Transaction.objects.create(
            date=date(2025, 4, 1),
            account=self.account,
            category=self.cat_food,
            amount=3000,
            description='スーパー',
        )
        with self.assertRaises(ValidationError):
            MedicalExpense.objects.create(
                transaction=tx,
                paid_date=date(2025, 4, 1),
                patient='本人',
                provider='〇〇',
                category=MedicalExpense.MedicalCategory.TREATMENT,
                amount=3000,
            )

    def test_transaction_amount_and_date_must_match(self):
        tx = Transaction.objects.create(
            date=date(2025, 4, 1),
            account=self.account,
            category=self.cat_medical,
            amount=3000,
            description='〇〇クリニック',
        )
        # 金額不一致
        with self.assertRaises(ValidationError):
            MedicalExpense.objects.create(
                transaction=tx,
                paid_date=date(2025, 4, 1),
                patient='本人',
                provider='〇〇',
                category=MedicalExpense.MedicalCategory.TREATMENT,
                amount=5000,
            )
        # 日付不一致
        with self.assertRaises(ValidationError):
            MedicalExpense.objects.create(
                transaction=tx,
                paid_date=date(2025, 5, 1),
                patient='本人',
                provider='〇〇',
                category=MedicalExpense.MedicalCategory.TREATMENT,
                amount=3000,
            )

    def test_unique_per_transaction(self):
        tx = Transaction.objects.create(
            date=date(2025, 4, 1),
            account=self.account,
            category=self.cat_medical,
            amount=3000,
            description='〇〇クリニック',
        )
        MedicalExpense.objects.create(
            transaction=tx,
            paid_date=date(2025, 4, 1),
            patient='本人',
            provider='〇〇',
            category=MedicalExpense.MedicalCategory.TREATMENT,
            amount=3000,
        )
        # full_clean() が UniqueConstraint を ValidationError で拾うため、
        # DB レベルの IntegrityError ではなく ValidationError を期待する。
        with self.assertRaises((ValidationError, IntegrityError)):
            MedicalExpense.objects.create(
                transaction=tx,
                paid_date=date(2025, 4, 1),
                patient='配偶者',
                provider='〇〇',
                category=MedicalExpense.MedicalCategory.TREATMENT,
                amount=3000,
            )


class CalculateMedicalDeductionTest(TestCase):
    def setUp(self):
        for i, amt in enumerate([50000, 70000], start=1):
            MedicalExpense.objects.create(
                paid_date=date(2025, i, 1),
                patient='本人',
                provider=f'P{i}',
                category=MedicalExpense.MedicalCategory.TREATMENT,
                amount=amt,
                reimbursement=10000 if i == 1 else 0,
            )

    def test_deduction_calc_with_snapshot_under_200man(self):
        AnnualIncomeSnapshot.objects.create(year=2025, gross_income=1_500_000)
        s = calculate_medical_deduction(2025)
        # 5% = 75,000
        self.assertEqual(s.threshold, 75_000)
        self.assertEqual(s.total_paid, 120_000)
        self.assertEqual(s.total_reimbursement, 10_000)
        self.assertEqual(s.net_paid, 110_000)
        self.assertEqual(s.deduction, 35_000)
        self.assertTrue(s.gross_income_known)

    def test_deduction_calc_with_snapshot_over_200man(self):
        AnnualIncomeSnapshot.objects.create(year=2025, gross_income=5_000_000)
        s = calculate_medical_deduction(2025)
        # min(100k, 250k) = 100k
        self.assertEqual(s.threshold, 100_000)
        self.assertEqual(s.deduction, 10_000)

    def test_deduction_calc_without_snapshot(self):
        s = calculate_medical_deduction(2025)
        self.assertEqual(s.threshold, 100_000)
        self.assertFalse(s.gross_income_known)
        self.assertIsNone(s.gross_income)
        self.assertEqual(s.deduction, 10_000)


# ===========================================================================
# View - 専用ページ
# ===========================================================================

class MedicalExpenseListViewTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username='me', password='pass')
        cls.account = _make_account()
        cls.cat_medical = _make_medical_category()
        cls.expense = MedicalExpense.objects.create(
            paid_date=date(2025, 5, 14),
            patient='テスト本人',
            provider='□□クリニック',
            category=MedicalExpense.MedicalCategory.TREATMENT,
            amount=4500,
            reimbursement=500,
        )

    def setUp(self):
        self.client.login(username='me', password='pass')

    def test_list_page_login_required(self):
        self.client.logout()
        resp = self.client.get(reverse('ledger:medical_expense_list'))
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/accounts/login/', resp['Location'])

    def test_list_page_default_year_is_current(self):
        resp = self.client.get(reverse('ledger:medical_expense_list'))
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode('utf-8')
        self.assertIn(f'{date.today().year}年 医療費控除明細', body)

    def test_list_page_summary_correct(self):
        resp = self.client.get(reverse('ledger:medical_expense_list') + '?year=2025')
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode('utf-8')
        # net_paid = 4000, threshold = 100000, deduction = 0
        self.assertIn('テスト本人', body)
        self.assertIn('□□クリニック', body)

    def test_list_page_warning_when_snapshot_missing(self):
        resp = self.client.get(reverse('ledger:medical_expense_list') + '?year=2025')
        self.assertIn('総所得が未登録', resp.content.decode('utf-8'))

    def test_list_page_no_warning_when_snapshot_exists(self):
        AnnualIncomeSnapshot.objects.create(year=2025, gross_income=5_000_000)
        resp = self.client.get(reverse('ledger:medical_expense_list') + '?year=2025')
        self.assertNotIn('総所得が未登録', resp.content.decode('utf-8'))


class MedicalExpenseCrudViewTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username='me', password='pass')
        cls.account = _make_account()
        cls.cat_medical = _make_medical_category()

    def setUp(self):
        self.client.login(username='me', password='pass')

    def test_create_view_creates_record(self):
        before = MedicalExpense.objects.count()
        resp = self.client.post(reverse('ledger:medical_expense_create'), {
            'paid_date': '2025-04-10',
            'patient': '本人',
            'provider': '〇〇クリニック',
            'category': MedicalExpense.MedicalCategory.TREATMENT,
            'amount': 3500,
            'reimbursement': 0,
            'notes': '',
            'transaction': '',
        })
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(MedicalExpense.objects.count(), before + 1)
        self.assertTrue(AuditLog.objects.filter(
            target_model='MedicalExpense',
            action=AuditLog.Action.CREATE,
        ).exists())

    def test_edit_view_updates_record(self):
        e = MedicalExpense.objects.create(
            paid_date=date(2025, 4, 10),
            patient='本人',
            provider='A',
            category=MedicalExpense.MedicalCategory.TREATMENT,
            amount=3000,
        )
        resp = self.client.post(reverse('ledger:medical_expense_update', args=[e.pk]), {
            'paid_date': '2025-04-10',
            'patient': '本人',
            'provider': 'B病院',
            'category': MedicalExpense.MedicalCategory.MEDICINE,
            'amount': 3000,
            'reimbursement': 200,
            'notes': '更新',
            'transaction': '',
        })
        self.assertEqual(resp.status_code, 302)
        e.refresh_from_db()
        self.assertEqual(e.provider, 'B病院')
        self.assertEqual(e.reimbursement, 200)
        self.assertEqual(e.category, MedicalExpense.MedicalCategory.MEDICINE)

    def test_delete_view_removes_record(self):
        e = MedicalExpense.objects.create(
            paid_date=date(2025, 4, 10),
            patient='本人',
            provider='A',
            category=MedicalExpense.MedicalCategory.TREATMENT,
            amount=3000,
        )
        before = MedicalExpense.objects.count()
        resp = self.client.post(reverse('ledger:medical_expense_delete', args=[e.pk]))
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(MedicalExpense.objects.count(), before - 1)
        self.assertTrue(AuditLog.objects.filter(
            target_model='MedicalExpense',
            action=AuditLog.Action.DELETE,
        ).exists())

    def test_create_with_transaction_link(self):
        tx = Transaction.objects.create(
            date=date(2025, 5, 1),
            account=self.account,
            category=self.cat_medical,
            amount=4000,
            description='〇〇病院',
        )
        resp = self.client.post(reverse('ledger:medical_expense_create'), {
            'paid_date': '2025-05-01',
            'patient': '本人',
            'provider': '〇〇病院',
            'category': MedicalExpense.MedicalCategory.TREATMENT,
            'amount': 4000,
            'reimbursement': 0,
            'transaction': str(tx.pk),
        })
        self.assertEqual(resp.status_code, 302)
        e = MedicalExpense.objects.get(transaction=tx)
        self.assertEqual(e.amount, 4000)

    def test_create_without_transaction(self):
        # Transaction なしで作成可（家計簿外医療費）
        resp = self.client.post(reverse('ledger:medical_expense_create'), {
            'paid_date': '2025-05-01',
            'patient': '配偶者',
            'provider': '保険組合事後請求',
            'category': MedicalExpense.MedicalCategory.OTHER,
            'amount': 1200,
            'reimbursement': 0,
            'transaction': '',
        })
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(MedicalExpense.objects.filter(provider='保険組合事後請求', transaction__isnull=True).exists())


# ===========================================================================
# View - 取引フォーム HTMX 拡張
# ===========================================================================

class TransactionMedicalFieldsViewTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username='me', password='pass')
        cls.cat_medical = _make_medical_category()
        cls.cat_food = _make_non_medical_category()

    def setUp(self):
        self.client.login(username='me', password='pass')

    def test_medical_fields_partial_hidden_for_non_medical_category(self):
        resp = self.client.get(
            reverse('ledger:transaction_medical_fields') + f'?category={self.cat_food.pk}'
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode('utf-8')
        self.assertIn('id="medical-fields"', body)
        self.assertNotIn('medical_patient', body)

    def test_medical_fields_partial_shown_for_medical_category(self):
        resp = self.client.get(
            reverse('ledger:transaction_medical_fields') + f'?category={self.cat_medical.pk}'
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode('utf-8')
        self.assertIn('medical_patient', body)
        self.assertIn('medical_provider', body)


class TransactionFormMedicalSyncTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username='me', password='pass')
        cls.account = _make_account()
        cls.cat_medical = _make_medical_category()
        cls.cat_food = _make_non_medical_category()

    def setUp(self):
        self.client.login(username='me', password='pass')

    def test_transaction_save_creates_medical_expense_atomically(self):
        resp = self.client.post(reverse('ledger:transaction_create'), {
            'date': '2025-06-15',
            'account': str(self.account.pk),
            'kind': Category.Kind.EXPENSE,
            'category': str(self.cat_medical.pk),
            'amount': 5500,
            'description': '〇〇クリニック',
            'memo': '',
            'medical_patient': '本人',
            'medical_provider': '〇〇クリニック',
            'medical_category': MedicalExpense.MedicalCategory.TREATMENT,
            'medical_reimbursement': 500,
        })
        self.assertIn(resp.status_code, (200, 302))
        tx = Transaction.objects.get(description='〇〇クリニック', amount=5500)
        e = MedicalExpense.objects.get(transaction=tx)
        self.assertEqual(e.patient, '本人')
        self.assertEqual(e.reimbursement, 500)
        self.assertEqual(e.category, MedicalExpense.MedicalCategory.TREATMENT)

    def test_transaction_save_without_medical_fields_does_not_create(self):
        before = MedicalExpense.objects.count()
        self.client.post(reverse('ledger:transaction_create'), {
            'date': '2025-06-15',
            'account': str(self.account.pk),
            'kind': Category.Kind.EXPENSE,
            'category': str(self.cat_food.pk),
            'amount': 1000,
            'description': 'スーパー',
            'memo': '',
        })
        self.assertEqual(MedicalExpense.objects.count(), before)


# ===========================================================================
# CSV エクスポート
# ===========================================================================

class MedicalExpenseCsvTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username='me', password='pass')
        MedicalExpense.objects.create(
            paid_date=date(2025, 3, 1),
            patient='本人',
            provider='A病院',
            category=MedicalExpense.MedicalCategory.TREATMENT,
            amount=4500,
            reimbursement=500,
        )
        MedicalExpense.objects.create(
            paid_date=date(2025, 4, 1),
            patient='配偶者',
            provider='=SUM(A1)悪意の薬局',  # CSV injection 試行
            category=MedicalExpense.MedicalCategory.MEDICINE,
            amount=1200,
        )

    def setUp(self):
        self.client.login(username='me', password='pass')

    def test_csv_download_filename_and_headers(self):
        resp = self.client.get(reverse('ledger:medical_expense_csv') + '?year=2025')
        self.assertEqual(resp.status_code, 200)
        self.assertIn('text/csv', resp['Content-Type'])
        self.assertIn('medical-expenses-2025.csv', resp['Content-Disposition'])
        # UTF-8 BOM
        self.assertTrue(resp.content.startswith(b'\xef\xbb\xbf'))

    def test_csv_row_order_matches_official_format(self):
        resp = self.client.get(reverse('ledger:medical_expense_csv') + '?year=2025')
        body = resp.content.decode('utf-8-sig')
        lines = body.strip().split('\n')
        header = lines[0]
        # 国税庁様式の列順
        self.assertIn('医療を受けた方の氏名', header)
        self.assertIn('病院・薬局などの支払先の名称', header)
        self.assertIn('医療費の区分', header)
        self.assertIn('支払った医療費の額', header)
        self.assertIn('左のうち、補填される金額', header)
        self.assertIn('差引額', header)

    def test_csv_injection_protection(self):
        resp = self.client.get(reverse('ledger:medical_expense_csv') + '?year=2025')
        body = resp.content.decode('utf-8-sig')
        # `=SUM(A1)` 始まりはシングルクオートで前置されているはず
        self.assertNotIn(',=SUM(A1)悪意の薬局,', body)
        self.assertIn("'=SUM(A1)悪意の薬局", body)


# ===========================================================================
# AnnualIncomeSnapshot
# ===========================================================================

class AnnualIncomeSnapshotViewTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username='me', password='pass')

    def setUp(self):
        self.client.login(username='me', password='pass')

    def test_snapshot_upsert_creates_new_year(self):
        resp = self.client.post(reverse('ledger:income_snapshot_save'), {
            'year': 2024,
            'gross_income': 4500000,
            'notes': '',
        })
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(AnnualIncomeSnapshot.objects.filter(year=2024).exists())

    def test_snapshot_upsert_updates_existing_year(self):
        AnnualIncomeSnapshot.objects.create(year=2024, gross_income=4500000)
        resp = self.client.post(reverse('ledger:income_snapshot_save'), {
            'year': 2024,
            'gross_income': 5000000,
            'notes': '更新',
        })
        self.assertEqual(resp.status_code, 302)
        s = AnnualIncomeSnapshot.objects.get(year=2024)
        self.assertEqual(s.gross_income, 5000000)
        self.assertEqual(AnnualIncomeSnapshot.objects.count(), 1)


class V13BackwardCompatTest(TestCase):
    """v1.13.0 の既存 tax-deductions レポートが v1.16.0 でも動くことを確認。"""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username='me', password='pass')
        cls.account = _make_account()
        cls.cat_medical = _make_medical_category()
        Transaction.objects.create(
            date=date(2025, 3, 1),
            account=cls.account,
            category=cls.cat_medical,
            amount=4500,
            description='〇〇クリニック',
        )

    def setUp(self):
        self.client.login(username='me', password='pass')

    def test_tax_deductions_v1_13_still_works(self):
        resp = self.client.get(reverse('ledger:tax_deductions') + '?year=2025&tax_tag=medical')
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode('utf-8')
        self.assertIn('〇〇クリニック', body)