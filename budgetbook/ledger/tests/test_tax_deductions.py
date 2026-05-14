"""v1.13.0: 確定申告レポート (税控除タグ集計) のテスト。"""
from datetime import date

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from ledger.models import Account, Category, Transaction


class TaxDeductionsViewTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username='td', password='pass')
        cls.account = Account.objects.create(name='普通預金A', opening_balance=100000)
        cls.cat_medical = Category.objects.create(
            name='医療費', kind=Category.Kind.EXPENSE, tax_tag=Category.TaxTag.MEDICAL,
        )
        cls.cat_donation = Category.objects.create(
            name='ふるさと納税', kind=Category.Kind.EXPENSE, tax_tag=Category.TaxTag.DONATION,
        )
        cls.cat_other_expense = Category.objects.create(
            name='食費', kind=Category.Kind.EXPENSE, tax_tag=Category.TaxTag.NONE,
        )
        cls.cat_income_medical = Category.objects.create(
            name='医療保険金', kind=Category.Kind.INCOME, tax_tag=Category.TaxTag.MEDICAL,
        )
        # 2025 年の医療費取引
        Transaction.objects.create(
            date=date(2025, 3, 12), account=cls.account, category=cls.cat_medical,
            amount=4200, description='◯◯病院', memo='風邪',
        )
        Transaction.objects.create(
            date=date(2025, 6, 22), account=cls.account, category=cls.cat_medical,
            amount=9500, description='△△クリニック', memo='健診',
        )
        # 2025 年のふるさと納税
        Transaction.objects.create(
            date=date(2025, 12, 25), account=cls.account, category=cls.cat_donation,
            amount=30000, description='○○市ふるさと納税', memo='',
        )
        # 2025 年の食費（tax_tag=none、出ない）
        Transaction.objects.create(
            date=date(2025, 5, 1), account=cls.account, category=cls.cat_other_expense,
            amount=5000, description='スーパー', memo='',
        )
        # 2024 年の医療費（年違い、出ない）
        Transaction.objects.create(
            date=date(2024, 8, 1), account=cls.account, category=cls.cat_medical,
            amount=8000, description='昨年の病院', memo='',
        )
        # 収入の医療保険金（出ない、支出のみ集計）
        Transaction.objects.create(
            date=date(2025, 7, 1), account=cls.account, category=cls.cat_income_medical,
            amount=20000, description='保険金', memo='',
        )

    def setUp(self):
        self.client.login(username='td', password='pass')

    def test_html_default_year_and_tag(self):
        resp = self.client.get(reverse('ledger:tax_deductions'))
        self.assertEqual(resp.status_code, 200)
        # デフォルトは medical
        body = resp.content.decode('utf-8')
        self.assertIn('医療費控除', body)

    def test_html_lists_matching_transactions(self):
        resp = self.client.get(reverse('ledger:tax_deductions') + '?year=2025&tax_tag=medical')
        body = resp.content.decode('utf-8')
        self.assertIn('◯◯病院', body)
        self.assertIn('△△クリニック', body)

    def test_html_excludes_other_tags(self):
        resp = self.client.get(reverse('ledger:tax_deductions') + '?year=2025&tax_tag=medical')
        body = resp.content.decode('utf-8')
        # 取引の摘要は table に出ない（カテゴリ名はプルダウンに出るので除外検査しない）
        self.assertNotIn('○○市ふるさと納税', body)

    def test_html_excludes_income(self):
        # 収入カテゴリは tax_tag=medical でも対象外
        resp = self.client.get(reverse('ledger:tax_deductions') + '?year=2025&tax_tag=medical')
        body = resp.content.decode('utf-8')
        self.assertNotIn('保険金', body)

    def test_html_excludes_other_year(self):
        resp = self.client.get(reverse('ledger:tax_deductions') + '?year=2025&tax_tag=medical')
        body = resp.content.decode('utf-8')
        self.assertNotIn('昨年の病院', body)

    def test_html_total_correct(self):
        resp = self.client.get(reverse('ledger:tax_deductions') + '?year=2025&tax_tag=medical')
        self.assertEqual(resp.context['total'], 4200 + 9500)
        self.assertEqual(resp.context['count'], 2)

    def test_html_medical_remaining(self):
        resp = self.client.get(reverse('ledger:tax_deductions') + '?year=2025&tax_tag=medical')
        # 4200+9500=13700, 100000 - 13700 = 86300
        self.assertEqual(resp.context['medical_remaining'], 86300)

    def test_html_donation_no_medical_remaining(self):
        resp = self.client.get(reverse('ledger:tax_deductions') + '?year=2025&tax_tag=donation')
        self.assertIsNone(resp.context['medical_remaining'])

    def test_html_empty_state(self):
        resp = self.client.get(reverse('ledger:tax_deductions') + '?year=2020&tax_tag=medical')
        body = resp.content.decode('utf-8')
        self.assertIn('取引はありません', body)

    def test_csv_download_content_type_and_filename(self):
        resp = self.client.get(reverse('ledger:tax_deductions_csv') + '?year=2025&tax_tag=medical')
        self.assertEqual(resp.status_code, 200)
        self.assertIn('text/csv', resp['Content-Type'])
        self.assertIn('tax-medical-2025.csv', resp['Content-Disposition'])

    def test_csv_content_rows(self):
        resp = self.client.get(reverse('ledger:tax_deductions_csv') + '?year=2025&tax_tag=medical')
        body = resp.content.decode('utf-8-sig')  # BOM 込みで decode
        lines = body.strip().split('\r\n')
        # header + 2 行
        self.assertEqual(len(lines), 3)
        self.assertIn('日付', lines[0])
        self.assertIn('2025-03-12', lines[1])  # 日付昇順
        self.assertIn('◯◯病院', lines[1])
        self.assertIn('2025-06-22', lines[2])

    def test_csv_bom_for_excel(self):
        resp = self.client.get(reverse('ledger:tax_deductions_csv') + '?year=2025&tax_tag=medical')
        self.assertTrue(resp.content.startswith('﻿'.encode('utf-8')))

    def test_csv_injection_protection(self):
        Transaction.objects.create(
            date=date(2025, 9, 1), account=self.account, category=self.cat_medical,
            amount=1000, description='=SUM(A1:A10)', memo='',
        )
        resp = self.client.get(reverse('ledger:tax_deductions_csv') + '?year=2025&tax_tag=medical')
        body = resp.content.decode('utf-8-sig')
        # =SUM(...) はシングルクオート前置されている
        self.assertIn("'=SUM(A1:A10)", body)

    def test_invalid_year_falls_back_to_current(self):
        resp = self.client.get(reverse('ledger:tax_deductions') + '?year=abc')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context['year'], date.today().year)

    def test_invalid_tax_tag_falls_back_to_medical(self):
        resp = self.client.get(reverse('ledger:tax_deductions') + '?tax_tag=foo')
        self.assertEqual(resp.context['tax_tag'], Category.TaxTag.MEDICAL)

    def test_login_required_redirect(self):
        self.client.logout()
        resp = self.client.get(reverse('ledger:tax_deductions'))
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/accounts/login/', resp['Location'])

    def test_csv_login_required_redirect(self):
        self.client.logout()
        resp = self.client.get(reverse('ledger:tax_deductions_csv'))
        self.assertEqual(resp.status_code, 302)


class SettingsPageTaxLinkTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username='sp2', password='pass')

    def setUp(self):
        self.client.login(username='sp2', password='pass')

    def test_settings_has_tax_report_link(self):
        resp = self.client.get(reverse('ledger:settings'))
        body = resp.content.decode('utf-8')
        self.assertIn(reverse('ledger:tax_deductions'), body)
