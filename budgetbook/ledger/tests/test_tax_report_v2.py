"""v1.18.0: 確定申告レポート v2（医療費+生保+地震+寄附金 統合）のテスト。"""
from __future__ import annotations

from datetime import date

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from ledger.models import (
    Account,
    AnnualIncomeSnapshot,
    Category,
    InsurancePremium,
    MedicalExpense,
    Transaction,
)
from ledger.services.tax_report_v2 import build_tax_report_v2


def _make_account():
    return Account.objects.create(name='普通預金A', opening_balance=500_000)


def _make_donation_category():
    return Category.objects.create(
        name='ふるさと納税',
        kind=Category.Kind.EXPENSE,
        tax_tag=Category.TaxTag.DONATION,
    )


# ===========================================================================
# 集計サービス
# ===========================================================================

class BuildTaxReportV2Test(TestCase):
    def test_build_empty_year(self):
        s = build_tax_report_v2(2025)
        self.assertEqual(s.year, 2025)
        self.assertEqual(s.medical.total_paid, 0)
        self.assertEqual(s.medical.deduction, 0)
        self.assertEqual(s.insurance.life['total'], 0)
        self.assertEqual(s.insurance.earthquake['deduction'], 0)
        self.assertEqual(s.donation['total'], 0)
        self.assertEqual(s.grand_deduction_total, 0)

    def test_build_medical_only(self):
        MedicalExpense.objects.create(
            paid_date=date(2025, 4, 1),
            patient='本人',
            provider='〇〇クリニック',
            category=MedicalExpense.MedicalCategory.TREATMENT,
            amount=200_000,
        )
        AnnualIncomeSnapshot.objects.create(year=2025, gross_income=5_000_000)
        s = build_tax_report_v2(2025)
        # 200,000 - 100,000(基準) = 100,000
        self.assertEqual(s.medical.deduction, 100_000)
        self.assertEqual(s.insurance.life['total'], 0)
        self.assertEqual(s.donation['total'], 0)
        self.assertEqual(s.grand_deduction_total, 100_000)

    def test_build_insurance_only(self):
        InsurancePremium.objects.create(
            year=2025,
            category=InsurancePremium.InsuranceCategory.LIFE_GENERAL,
            insurer='〇〇生命',
            annual_amount=80_000,  # 上限 4 万円
        )
        InsurancePremium.objects.create(
            year=2025,
            category=InsurancePremium.InsuranceCategory.EARTHQUAKE,
            insurer='〇〇損保',
            annual_amount=30_000,
        )
        s = build_tax_report_v2(2025)
        self.assertEqual(s.insurance.life['total'], 40_000)
        self.assertEqual(s.insurance.earthquake['deduction'], 30_000)
        self.assertEqual(s.grand_deduction_total, 70_000)

    def test_build_donation_only(self):
        account = _make_account()
        cat = _make_donation_category()
        Transaction.objects.create(
            date=date(2025, 12, 15),
            account=account,
            category=cat,
            amount=30_000,
            description='〇〇市ふるさと納税',
        )
        s = build_tax_report_v2(2025)
        self.assertEqual(s.donation['total'], 30_000)
        self.assertEqual(s.donation['count'], 1)
        # 寄附金は grand_total に加算されない
        self.assertEqual(s.grand_deduction_total, 0)

    def test_exclude_year_end_default_true(self):
        # 年調済が 1 件、年調未提出が 1 件
        InsurancePremium.objects.create(
            year=2025,
            category=InsurancePremium.InsuranceCategory.LIFE_GENERAL,
            insurer='年調済',
            annual_amount=40_000,
            submitted_in_year_end_adjustment=True,
        )
        InsurancePremium.objects.create(
            year=2025,
            category=InsurancePremium.InsuranceCategory.LIFE_GENERAL,
            insurer='未提出',
            annual_amount=40_000,
            submitted_in_year_end_adjustment=False,
        )
        s_default = build_tax_report_v2(2025)  # exclude_year_end_adjusted=True
        s_include = build_tax_report_v2(2025, exclude_year_end_adjusted=False)
        # exclude=True: 40k のみ → 30k 控除
        self.assertEqual(s_default.insurance.life['total'], 30_000)
        # exclude=False: 80k 合算 → 40k 控除
        self.assertEqual(s_include.insurance.life['total'], 40_000)

    def test_grand_total_excludes_donation(self):
        # 医療費・生保・地震・寄附金それぞれ計上
        AnnualIncomeSnapshot.objects.create(year=2025, gross_income=5_000_000)
        MedicalExpense.objects.create(
            paid_date=date(2025, 4, 1),
            patient='本人',
            provider='A',
            category=MedicalExpense.MedicalCategory.TREATMENT,
            amount=150_000,
        )
        InsurancePremium.objects.create(
            year=2025,
            category=InsurancePremium.InsuranceCategory.LIFE_GENERAL,
            insurer='B',
            annual_amount=80_000,
        )
        InsurancePremium.objects.create(
            year=2025,
            category=InsurancePremium.InsuranceCategory.EARTHQUAKE,
            insurer='C',
            annual_amount=30_000,
        )
        account = _make_account()
        cat = _make_donation_category()
        Transaction.objects.create(
            date=date(2025, 12, 15),
            account=account,
            category=cat,
            amount=100_000,
            description='寄附',
        )
        s = build_tax_report_v2(2025)
        # 医療: 50k + 生保: 40k + 地震: 30k = 120k
        self.assertEqual(s.grand_deduction_total, 120_000)
        # donation は別管理
        self.assertEqual(s.donation['total'], 100_000)


# ===========================================================================
# View - HTML
# ===========================================================================

class TaxDeductionsV2ViewTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username='td2', password='pass')

    def setUp(self):
        self.client.login(username='td2', password='pass')

    def test_v2_login_required(self):
        self.client.logout()
        resp = self.client.get(reverse('ledger:tax_deductions_v2'))
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/accounts/login/', resp['Location'])

    def test_v2_default_year_is_current(self):
        resp = self.client.get(reverse('ledger:tax_deductions_v2'))
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode('utf-8')
        self.assertIn(f'{date.today().year}年 確定申告レポート', body)

    def test_v2_renders_all_four_sections(self):
        resp = self.client.get(reverse('ledger:tax_deductions_v2') + '?year=2025')
        body = resp.content.decode('utf-8')
        self.assertIn('医療費控除', body)
        self.assertIn('生命保険料控除', body)
        self.assertIn('地震保険料控除', body)
        self.assertIn('寄附金', body)

    def test_v2_displays_transcription_hint(self):
        resp = self.client.get(reverse('ledger:tax_deductions_v2') + '?year=2025')
        body = resp.content.decode('utf-8')
        self.assertIn('第二表 ⑩医療費控除', body)
        self.assertIn('第二表 ⑮生命保険料控除', body)
        self.assertIn('第二表 ⑯地震保険料控除', body)
        self.assertIn('第二表 ⑲寄附金控除', body)

    def test_v2_toggle_changes_insurance_calculation(self):
        InsurancePremium.objects.create(
            year=2025,
            category=InsurancePremium.InsuranceCategory.LIFE_GENERAL,
            insurer='年調済',
            annual_amount=40_000,
            submitted_in_year_end_adjustment=True,
        )
        # exclude_year_end=1 (default): 年調済除外 → 控除額 0
        resp_excl = self.client.get(reverse('ledger:tax_deductions_v2') + '?year=2025&exclude_year_end=1')
        # exclude_year_end=0: 年調済含む → 控除額 30k (calc_life_new(40000)=30000)
        resp_incl = self.client.get(reverse('ledger:tax_deductions_v2') + '?year=2025&exclude_year_end=0')
        self.assertEqual(resp_excl.status_code, 200)
        self.assertEqual(resp_incl.status_code, 200)
        # response context で差分を比較できれば確実だが、テンプレ表示が変わることだけ確認
        self.assertIn('¥30,000', resp_incl.content.decode('utf-8'))


# ===========================================================================
# View - CSV
# ===========================================================================

class TaxDeductionsV2CsvTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username='td2c', password='pass')
        cls.account = _make_account()
        cls.cat_donation = _make_donation_category()
        # 寄附金で CSV injection 試行
        Transaction.objects.create(
            date=date(2025, 12, 1),
            account=cls.account,
            category=cls.cat_donation,
            amount=30_000,
            description='=SUM(A1)悪意ふるさと納税',
        )
        MedicalExpense.objects.create(
            paid_date=date(2025, 4, 1),
            patient='本人',
            provider='〇〇クリニック',
            category=MedicalExpense.MedicalCategory.TREATMENT,
            amount=4500,
        )
        InsurancePremium.objects.create(
            year=2025,
            category=InsurancePremium.InsuranceCategory.LIFE_GENERAL,
            insurer='〇〇生命',
            annual_amount=40_000,
        )
        InsurancePremium.objects.create(
            year=2025,
            category=InsurancePremium.InsuranceCategory.EARTHQUAKE,
            insurer='〇〇損保',
            annual_amount=20_000,
        )

    def setUp(self):
        self.client.login(username='td2c', password='pass')

    def test_csv_filename_and_bom(self):
        resp = self.client.get(reverse('ledger:tax_deductions_v2_csv') + '?year=2025')
        self.assertEqual(resp.status_code, 200)
        self.assertIn('text/csv', resp['Content-Type'])
        self.assertIn('tax-report-v2-2025.csv', resp['Content-Disposition'])
        self.assertTrue(resp.content.startswith(b'\xef\xbb\xbf'))

    def test_csv_contains_all_sections(self):
        resp = self.client.get(reverse('ledger:tax_deductions_v2_csv') + '?year=2025')
        body = resp.content.decode('utf-8-sig')
        self.assertIn('【医療費控除】', body)
        self.assertIn('【生命保険料控除】', body)
        self.assertIn('【地震保険料控除】', body)
        self.assertIn('【寄附金', body)
        self.assertIn('【総控除額', body)

    def test_csv_injection_protection(self):
        resp = self.client.get(reverse('ledger:tax_deductions_v2_csv') + '?year=2025')
        body = resp.content.decode('utf-8-sig')
        self.assertNotIn(',=SUM(A1)悪意ふるさと納税,', body)
        self.assertIn("'=SUM(A1)悪意ふるさと納税", body)


# ===========================================================================
# 後方互換
# ===========================================================================

class V13TaxDeductionsCompatTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username='compat', password='pass')

    def setUp(self):
        self.client.login(username='compat', password='pass')

    def test_v1_13_tax_deductions_still_works(self):
        resp = self.client.get(reverse('ledger:tax_deductions') + '?year=2025&tax_tag=medical')
        self.assertEqual(resp.status_code, 200)