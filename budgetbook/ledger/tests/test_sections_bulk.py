"""大分類一括編集ビューのテスト。"""
from __future__ import annotations

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from ledger.models import AuditLog, Category


class SectionsBulkEditTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username='secbulk', password='pass')
        cls.cat_a = Category.objects.create(
            name='B食費A', kind=Category.Kind.EXPENSE, section=Category.Section.OTHER,
        )
        cls.cat_b = Category.objects.create(
            name='B交通A', kind=Category.Kind.EXPENSE, section=Category.Section.OTHER,
        )
        cls.cat_in = Category.objects.create(
            name='B給与', kind=Category.Kind.INCOME,
        )

    def setUp(self):
        self.client.login(username='secbulk', password='pass')

    def test_get_renders_grouped(self):
        resp = self.client.get(reverse('ledger:sections_bulk_edit'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, '大分類の一括編集')
        self.assertContains(resp, 'B食費A')

    def test_post_updates_sections(self):
        resp = self.client.post(reverse('ledger:sections_bulk_edit'), {
            f'section_{self.cat_a.pk}': 'food_daily',
            f'tax_tag_{self.cat_a.pk}': 'none',
            f'section_{self.cat_b.pk}': 'transport',
            f'tax_tag_{self.cat_b.pk}': 'none',
            f'tax_tag_{self.cat_in.pk}': 'none',
        })
        self.assertEqual(resp.status_code, 200)
        self.cat_a.refresh_from_db()
        self.cat_b.refresh_from_db()
        self.assertEqual(self.cat_a.section, 'food_daily')
        self.assertEqual(self.cat_b.section, 'transport')
        # 監査ログが 1 件出ている
        self.assertTrue(AuditLog.objects.filter(target_id='bulk').exists())

    def test_post_with_no_changes(self):
        resp = self.client.post(reverse('ledger:sections_bulk_edit'), {
            f'section_{self.cat_a.pk}': self.cat_a.section,
            f'tax_tag_{self.cat_a.pk}': self.cat_a.tax_tag,
            f'section_{self.cat_b.pk}': self.cat_b.section,
            f'tax_tag_{self.cat_b.pk}': self.cat_b.tax_tag,
            f'tax_tag_{self.cat_in.pk}': self.cat_in.tax_tag,
        })
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, '変更はありませんでした')

    def test_invalid_section_ignored(self):
        resp = self.client.post(reverse('ledger:sections_bulk_edit'), {
            f'section_{self.cat_a.pk}': 'INVALID_SECTION',
            f'tax_tag_{self.cat_a.pk}': 'none',
            f'section_{self.cat_b.pk}': 'transport',
            f'tax_tag_{self.cat_b.pk}': 'none',
            f'tax_tag_{self.cat_in.pk}': 'none',
        })
        self.assertEqual(resp.status_code, 200)
        self.cat_a.refresh_from_db()
        # 不正値は無視され、もとのまま
        self.assertEqual(self.cat_a.section, Category.Section.OTHER)