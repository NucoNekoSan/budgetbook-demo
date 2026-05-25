"""税控除系ページの参考計算注意表示テスト。"""
from __future__ import annotations

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse


TAX_NOTICE_TEXT = '申告準備用の参考計算です'
TAX_NOTICE_CONFIRMATION_TEXT = '国税庁資料・確定申告書作成コーナー・税理士等で確認'


class TaxCalculationNoticeTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username='tax_notice', password='pass')

    def setUp(self):
        self.client.login(username='tax_notice', password='pass')

    def test_tax_related_pages_show_reference_calculation_notice(self):
        url_names = [
            'ledger:tax_deductions',
            'ledger:tax_deductions_v2',
            'ledger:medical_expense_list',
            'ledger:medical_expense_create',
            'ledger:insurance_premium_list',
            'ledger:insurance_premium_create',
            'ledger:income_snapshot_list',
        ]

        for url_name in url_names:
            with self.subTest(url_name=url_name):
                resp = self.client.get(reverse(url_name))
                self.assertEqual(resp.status_code, 200)
                body = resp.content.decode('utf-8')
                self.assertIn(TAX_NOTICE_TEXT, body)
                self.assertIn(TAX_NOTICE_CONFIRMATION_TEXT, body)

    def test_v2_copy_does_not_claim_direct_final_transcription(self):
        resp = self.client.get(reverse('ledger:tax_deductions_v2'))
        body = resp.content.decode('utf-8')
        self.assertIn('転記候補として確認できます', body)
        self.assertNotIn('そのまま確定申告書 第二表に転記できます', body)
