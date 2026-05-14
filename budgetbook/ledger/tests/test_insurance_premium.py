"""v1.17.0: 生命保険料控除・地震保険料控除のテスト。

- InsurancePremium モデル / バリデーション
- 国税庁式の計算ロジック（純粋関数）
- 集計 + 年調除外
- View CRUD
- CSV
"""
from __future__ import annotations

from datetime import date

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from ledger.models import AuditLog, InsurancePremium
from ledger.services.insurance import (
    calc_earthquake_total,
    calc_life_category,
    calc_life_new,
    calc_life_old,
    calc_life_total,
    calculate_insurance_deduction,
)


# ===========================================================================
# モデル / バリデーション
# ===========================================================================

class InsurancePremiumModelTest(TestCase):
    def test_insurance_premium_create_minimal(self):
        ip = InsurancePremium.objects.create(
            year=2025,
            category=InsurancePremium.InsuranceCategory.LIFE_GENERAL,
            contract_type=InsurancePremium.ContractType.NEW,
            insurer='〇〇生命',
            annual_amount=40_000,
        )
        self.assertEqual(ip.annual_amount, 40_000)
        self.assertEqual(ip.policy_number, '')
        self.assertFalse(ip.submitted_in_year_end_adjustment)

    def test_care_medical_old_contract_rejected(self):
        with self.assertRaises(ValidationError):
            InsurancePremium.objects.create(
                year=2025,
                category=InsurancePremium.InsuranceCategory.LIFE_CARE_MEDICAL,
                contract_type=InsurancePremium.ContractType.OLD,
                insurer='〇〇生命',
                annual_amount=30_000,
            )

    def test_earthquake_contract_type_normalized_to_new(self):
        ip = InsurancePremium.objects.create(
            year=2025,
            category=InsurancePremium.InsuranceCategory.EARTHQUAKE,
            contract_type=InsurancePremium.ContractType.OLD,
            insurer='〇〇損保',
            annual_amount=30_000,
        )
        self.assertEqual(ip.contract_type, InsurancePremium.ContractType.NEW)

    def test_annual_amount_must_be_positive(self):
        with self.assertRaises(ValidationError):
            InsurancePremium.objects.create(
                year=2025,
                category=InsurancePremium.InsuranceCategory.LIFE_GENERAL,
                insurer='X',
                annual_amount=0,
            )

    def test_str_representation(self):
        ip = InsurancePremium.objects.create(
            year=2025,
            category=InsurancePremium.InsuranceCategory.LIFE_GENERAL,
            insurer='テスト生命',
            annual_amount=10_000,
        )
        self.assertIn('2025', str(ip))
        self.assertIn('テスト生命', str(ip))


# ===========================================================================
# 計算ロジック (純粋関数)
# ===========================================================================

class CalcLifeNewTest(TestCase):
    def test_under_20k(self):
        self.assertEqual(calc_life_new(15_000), 15_000)
        self.assertEqual(calc_life_new(20_000), 20_000)

    def test_20k_to_40k(self):
        # 30000 // 2 + 10000 = 25000
        self.assertEqual(calc_life_new(30_000), 25_000)
        self.assertEqual(calc_life_new(40_000), 30_000)

    def test_40k_to_80k(self):
        # 60000 // 4 + 20000 = 35000
        self.assertEqual(calc_life_new(60_000), 35_000)
        self.assertEqual(calc_life_new(80_000), 40_000)

    def test_over_80k(self):
        self.assertEqual(calc_life_new(80_001), 40_000)
        self.assertEqual(calc_life_new(200_000), 40_000)


class CalcLifeOldTest(TestCase):
    def test_under_25k(self):
        self.assertEqual(calc_life_old(20_000), 20_000)
        self.assertEqual(calc_life_old(25_000), 25_000)

    def test_25k_to_50k(self):
        # 40000 // 2 + 12500 = 32500
        self.assertEqual(calc_life_old(40_000), 32_500)
        self.assertEqual(calc_life_old(50_000), 37_500)

    def test_50k_to_100k(self):
        # 80000 // 4 + 25000 = 45000
        self.assertEqual(calc_life_old(80_000), 45_000)
        self.assertEqual(calc_life_old(100_000), 50_000)

    def test_over_100k(self):
        self.assertEqual(calc_life_old(100_001), 50_000)
        self.assertEqual(calc_life_old(300_000), 50_000)


class CalcLifeCategoryTest(TestCase):
    def test_new_only(self):
        self.assertEqual(calc_life_category(new_total=30_000, old_total=0), 25_000)

    def test_old_only(self):
        self.assertEqual(calc_life_category(new_total=0, old_total=40_000), 32_500)

    def test_mixed_new_advantage(self):
        # 新 80k のみで 40k、旧 25k のみで 25k、合算 105k は新ルールで 40k → max(40k, 25k, 40k) = 40k
        result = calc_life_category(new_total=80_000, old_total=25_000)
        self.assertEqual(result, 40_000)

    def test_mixed_old_advantage(self):
        # 新 0 想定外なので新 1k + 旧 100k: 新 1k(1000) / 旧 100k(50000) / 合算 101k 新ルール (40000)
        # max(1000, 50000, 40000) = 50000
        result = calc_life_category(new_total=1_000, old_total=100_000)
        self.assertEqual(result, 50_000)

    def test_mixed_combined_advantage(self):
        # 新 5k + 旧 5k: 新 5k(5000) / 旧 5k(5000) / 合算 10k 新ルール (10000)
        # max(5000, 5000, 10000) = 10000
        result = calc_life_category(new_total=5_000, old_total=5_000)
        self.assertEqual(result, 10_000)

    def test_both_zero(self):
        self.assertEqual(calc_life_category(new_total=0, old_total=0), 0)


# ===========================================================================
# 集計 + 年調除外
# ===========================================================================

class CalcLifeTotalTest(TestCase):
    def setUp(self):
        # 3 枠各 40k 新契約 → 各枠 30k 控除 → 合計 90k （上限 120k 未満）
        for cat in [
            InsurancePremium.InsuranceCategory.LIFE_GENERAL,
            InsurancePremium.InsuranceCategory.LIFE_CARE_MEDICAL,
            InsurancePremium.InsuranceCategory.LIFE_ANNUITY,
        ]:
            InsurancePremium.objects.create(
                year=2025,
                category=cat,
                contract_type=InsurancePremium.ContractType.NEW,
                insurer=f'{cat} 保険',
                annual_amount=40_000,
            )

    def test_three_categories_sum(self):
        result = calc_life_total(2025)
        self.assertEqual(result['raw_sum'], 90_000)
        self.assertEqual(result['total'], 90_000)
        # 各枠の控除額 = 30k
        for cat_row in result['per_category'].values():
            self.assertEqual(cat_row['deduction'], 30_000)

    def test_capped_at_120000(self):
        # 各枠 80k に増額: 各枠 40k 上限 → 合計 120k 上限
        InsurancePremium.objects.filter(year=2025).update(annual_amount=80_000)
        result = calc_life_total(2025)
        self.assertEqual(result['raw_sum'], 120_000)
        self.assertEqual(result['total'], 120_000)

    def test_capped_above_120000(self):
        # 各枠 80k 新 + 同枠 100k 旧 を一般生命に追加
        InsurancePremium.objects.filter(year=2025).update(annual_amount=80_000)
        InsurancePremium.objects.create(
            year=2025,
            category=InsurancePremium.InsuranceCategory.LIFE_GENERAL,
            contract_type=InsurancePremium.ContractType.OLD,
            insurer='旧生命',
            annual_amount=100_000,
        )
        result = calc_life_total(2025)
        # raw_sum > 120k だが total は 120k に capped
        self.assertEqual(result['total'], 120_000)
        self.assertGreaterEqual(result['raw_sum'], 120_000)


class CalcEarthquakeTotalTest(TestCase):
    def test_under_50000(self):
        InsurancePremium.objects.create(
            year=2025,
            category=InsurancePremium.InsuranceCategory.EARTHQUAKE,
            insurer='損保',
            annual_amount=30_000,
        )
        result = calc_earthquake_total(2025)
        self.assertEqual(result['paid'], 30_000)
        self.assertEqual(result['deduction'], 30_000)

    def test_capped_at_50000(self):
        InsurancePremium.objects.create(
            year=2025,
            category=InsurancePremium.InsuranceCategory.EARTHQUAKE,
            insurer='損保',
            annual_amount=80_000,
        )
        result = calc_earthquake_total(2025)
        self.assertEqual(result['deduction'], 50_000)


class ExcludeYearEndAdjustedTest(TestCase):
    def setUp(self):
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
            insurer='年調未提出',
            annual_amount=40_000,
            submitted_in_year_end_adjustment=False,
        )

    def test_exclude_year_end_adjusted_filters_out(self):
        result_include = calculate_insurance_deduction(2025, exclude_year_end_adjusted=False)
        result_exclude = calculate_insurance_deduction(2025, exclude_year_end_adjusted=True)
        # include: 80k → 新ルール 40k 上限
        self.assertEqual(result_include.life['total'], 40_000)
        # exclude: 40k → 30k
        self.assertEqual(result_exclude.life['total'], 30_000)


# ===========================================================================
# View
# ===========================================================================

class InsurancePremiumListViewTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username='ip', password='pass')

    def setUp(self):
        self.client.login(username='ip', password='pass')

    def test_list_page_login_required(self):
        self.client.logout()
        resp = self.client.get(reverse('ledger:insurance_premium_list'))
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/accounts/login/', resp['Location'])

    def test_list_page_default_year_is_current(self):
        resp = self.client.get(reverse('ledger:insurance_premium_list'))
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode('utf-8')
        self.assertIn(f'{date.today().year}年 保険料控除明細', body)

    def test_list_page_summary_matches_service(self):
        InsurancePremium.objects.create(
            year=2025,
            category=InsurancePremium.InsuranceCategory.LIFE_GENERAL,
            insurer='〇〇生命',
            annual_amount=40_000,
        )
        resp = self.client.get(reverse('ledger:insurance_premium_list') + '?year=2025')
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode('utf-8')
        self.assertIn('〇〇生命', body)


class InsurancePremiumCrudViewTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username='ip', password='pass')

    def setUp(self):
        self.client.login(username='ip', password='pass')

    def test_create_view_creates_record(self):
        before = InsurancePremium.objects.count()
        resp = self.client.post(reverse('ledger:insurance_premium_create'), {
            'year': 2025,
            'category': InsurancePremium.InsuranceCategory.LIFE_GENERAL,
            'contract_type': InsurancePremium.ContractType.NEW,
            'insurer': '〇〇生命',
            'policy_number': '',
            'annual_amount': 40000,
            'notes': '',
        })
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(InsurancePremium.objects.count(), before + 1)
        self.assertTrue(AuditLog.objects.filter(
            target_model='InsurancePremium',
            action='create',
        ).exists())

    def test_edit_view_updates_record(self):
        ip = InsurancePremium.objects.create(
            year=2025,
            category=InsurancePremium.InsuranceCategory.LIFE_GENERAL,
            insurer='A',
            annual_amount=10000,
        )
        resp = self.client.post(reverse('ledger:insurance_premium_update', args=[ip.pk]), {
            'year': 2025,
            'category': InsurancePremium.InsuranceCategory.LIFE_GENERAL,
            'contract_type': InsurancePremium.ContractType.NEW,
            'insurer': 'B生命',
            'policy_number': '',
            'annual_amount': 50000,
            'notes': '更新',
        })
        self.assertEqual(resp.status_code, 302)
        ip.refresh_from_db()
        self.assertEqual(ip.insurer, 'B生命')
        self.assertEqual(ip.annual_amount, 50000)

    def test_delete_view_removes_record(self):
        ip = InsurancePremium.objects.create(
            year=2025,
            category=InsurancePremium.InsuranceCategory.LIFE_GENERAL,
            insurer='A',
            annual_amount=10000,
        )
        before = InsurancePremium.objects.count()
        resp = self.client.post(reverse('ledger:insurance_premium_delete', args=[ip.pk]))
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(InsurancePremium.objects.count(), before - 1)

    def test_form_rejects_care_medical_old(self):
        resp = self.client.post(reverse('ledger:insurance_premium_create'), {
            'year': 2025,
            'category': InsurancePremium.InsuranceCategory.LIFE_CARE_MEDICAL,
            'contract_type': InsurancePremium.ContractType.OLD,
            'insurer': '〇〇生命',
            'policy_number': '',
            'annual_amount': 30000,
            'notes': '',
        })
        # フォームでエラー → 再表示 (200) or redirect しないこと
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(InsurancePremium.objects.filter(insurer='〇〇生命').exists())


# ===========================================================================
# CSV
# ===========================================================================

class InsurancePremiumCsvTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username='ip', password='pass')
        InsurancePremium.objects.create(
            year=2025,
            category=InsurancePremium.InsuranceCategory.LIFE_GENERAL,
            insurer='=SUM(A1)悪意生命',  # CSV injection 試行
            annual_amount=40_000,
        )

    def setUp(self):
        self.client.login(username='ip', password='pass')

    def test_csv_download_filename_and_headers(self):
        resp = self.client.get(reverse('ledger:insurance_premium_csv') + '?year=2025')
        self.assertEqual(resp.status_code, 200)
        self.assertIn('text/csv', resp['Content-Type'])
        self.assertIn('insurance-premiums-2025.csv', resp['Content-Disposition'])
        # UTF-8 BOM
        self.assertTrue(resp.content.startswith(b'\xef\xbb\xbf'))

    def test_csv_injection_protection(self):
        resp = self.client.get(reverse('ledger:insurance_premium_csv') + '?year=2025')
        body = resp.content.decode('utf-8-sig')
        self.assertNotIn(',=SUM(A1)悪意生命,', body)
        self.assertIn("'=SUM(A1)悪意生命", body)