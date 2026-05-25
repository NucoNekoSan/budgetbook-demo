from __future__ import annotations

from datetime import date

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from ledger.models import (
    Account,
    AuditLog,
    Category,
    CategoryChangeLog,
    MonthlyClosing,
    Transaction,
)
from ledger.services.category_history import (
    build_reclassification_plan,
    reclassify_transactions,
)


class CategoryChangeLogViewTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username='category-history', password='pass')
        cls.account = Account.objects.create(name='履歴口座')

    def setUp(self):
        self.client.login(username='category-history', password='pass')

    def test_category_update_creates_change_log_with_before_after_and_reason(self):
        category = Category.objects.create(
            name='履歴食費',
            kind=Category.Kind.EXPENSE,
            section=Category.Section.FOOD_DAILY,
            tax_tag=Category.TaxTag.NONE,
        )
        resp = self.client.post(reverse('ledger:category_update', args=[category.pk]), {
            'name': '履歴食品',
            'kind': Category.Kind.EXPENSE,
            'section': Category.Section.MEDICAL,
            'tax_tag': Category.TaxTag.MEDICAL,
            'notes': '',
            'change_reason': '分類方針の見直し',
        })
        self.assertEqual(resp.status_code, 200)
        log = CategoryChangeLog.objects.get(category=category)
        self.assertEqual(log.action, CategoryChangeLog.Action.UPDATE)
        self.assertEqual(log.before['name'], '履歴食費')
        self.assertEqual(log.after['name'], '履歴食品')
        self.assertEqual(log.before['section'], Category.Section.FOOD_DAILY)
        self.assertEqual(log.after['section'], Category.Section.MEDICAL)
        self.assertEqual(log.after['tax_tag'], Category.TaxTag.MEDICAL)
        self.assertEqual(log.reason, '分類方針の見直し')
        self.assertEqual(log.changed_by, self.user)

    def test_used_category_kind_change_is_rejected(self):
        category = Category.objects.create(name='使用済み費', kind=Category.Kind.EXPENSE)
        Transaction.objects.create(
            date=date(2026, 5, 1),
            account=self.account,
            category=category,
            amount=1000,
            description='履歴',
        )
        resp = self.client.post(reverse('ledger:category_update', args=[category.pk]), {
            'name': '使用済み費',
            'kind': Category.Kind.INCOME,
            'section': Category.Section.OTHER,
            'tax_tag': Category.TaxTag.NONE,
            'notes': '',
            'change_reason': '不正変更',
        })
        self.assertEqual(resp.status_code, 422)
        category.refresh_from_db()
        self.assertEqual(category.kind, Category.Kind.EXPENSE)
        self.assertFalse(CategoryChangeLog.objects.filter(category=category).exists())

    def test_unused_category_kind_change_is_allowed(self):
        category = Category.objects.create(name='未使用費', kind=Category.Kind.EXPENSE)
        resp = self.client.post(reverse('ledger:category_update', args=[category.pk]), {
            'name': '未使用収入',
            'kind': Category.Kind.INCOME,
            'section': Category.Section.OTHER,
            'tax_tag': Category.TaxTag.NONE,
            'notes': '',
            'change_reason': '未使用カテゴリの整理',
        })
        self.assertEqual(resp.status_code, 200)
        category.refresh_from_db()
        self.assertEqual(category.kind, Category.Kind.INCOME)
        self.assertEqual(CategoryChangeLog.objects.get(category=category).after['kind'], Category.Kind.INCOME)

    def test_toggle_category_creates_deactivate_and_reactivate_logs(self):
        category = Category.objects.create(name='停止履歴', kind=Category.Kind.EXPENSE)
        self.client.post(reverse('ledger:category_toggle', args=[category.pk]))
        category.refresh_from_db()
        self.assertFalse(category.is_active)
        self.client.post(reverse('ledger:category_toggle', args=[category.pk]))
        actions = list(CategoryChangeLog.objects.filter(category=category).order_by('id').values_list('action', flat=True))
        self.assertEqual(actions, [
            CategoryChangeLog.Action.DEACTIVATE,
            CategoryChangeLog.Action.REACTIVATE,
        ])

    def test_category_log_prevents_complete_delete(self):
        category = Category.objects.create(name='履歴あり削除不可', kind=Category.Kind.EXPENSE)
        self.client.post(reverse('ledger:category_update', args=[category.pk]), {
            'name': '履歴あり削除不可2',
            'kind': Category.Kind.EXPENSE,
            'section': Category.Section.OTHER,
            'tax_tag': Category.TaxTag.NONE,
            'notes': '',
            'change_reason': '削除不可確認',
        })
        resp = self.client.get(reverse('ledger:settings'))
        self.assertContains(resp, '履歴 1')
        self.assertNotContains(resp, 'aria-label="履歴あり削除不可2 を削除"')


class CategoryReclassificationServiceTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username='reclassifier', password='pass')
        cls.account = Account.objects.create(name='再分類口座')
        cls.from_category = Category.objects.create(name='再分類元', kind=Category.Kind.EXPENSE)
        cls.to_category = Category.objects.create(name='再分類先', kind=Category.Kind.EXPENSE)
        cls.income_category = Category.objects.create(name='再分類収入', kind=Category.Kind.INCOME)

    def test_dry_run_counts_target_transactions(self):
        Transaction.objects.create(
            date=date(2026, 5, 1),
            account=self.account,
            category=self.from_category,
            amount=1000,
            description='対象',
        )
        plan = build_reclassification_plan(
            from_category=self.from_category,
            to_category=self.to_category,
        )
        self.assertEqual(plan.affected_transaction_count, 1)
        self.assertFalse(plan.includes_closed_month)

    def test_reclassification_rejects_kind_mismatch(self):
        with self.assertRaises(ValidationError):
            build_reclassification_plan(
                from_category=self.from_category,
                to_category=self.income_category,
            )

    def test_reclassification_rejects_closed_month(self):
        Transaction.objects.create(
            date=date(2026, 4, 20),
            account=self.account,
            category=self.from_category,
            amount=1000,
            description='締め済み',
        )
        MonthlyClosing.objects.create(
            month=date(2026, 4, 1),
            opening_carry=0,
            income=0,
            expense=1000,
            net=-1000,
            closing_balance=-1000,
            account_balances=[],
        )
        plan = build_reclassification_plan(
            from_category=self.from_category,
            to_category=self.to_category,
        )
        self.assertTrue(plan.includes_closed_month)
        with self.assertRaises(ValidationError):
            reclassify_transactions(
                from_category=self.from_category,
                to_category=self.to_category,
                reason='締め済み拒否',
                changed_by=self.user,
            )

    def test_reclassification_updates_unclosed_transactions_and_logs(self):
        tx = Transaction.objects.create(
            date=date(2026, 5, 20),
            account=self.account,
            category=self.from_category,
            amount=1000,
            description='未締め',
        )
        plan = reclassify_transactions(
            from_category=self.from_category,
            to_category=self.to_category,
            reason='カテゴリ整理',
            changed_by=self.user,
        )
        self.assertEqual(plan.affected_transaction_count, 1)
        tx.refresh_from_db()
        self.assertEqual(tx.category, self.to_category)
        change_log = CategoryChangeLog.objects.get(category=self.from_category)
        self.assertEqual(change_log.action, CategoryChangeLog.Action.RECLASSIFY)
        self.assertEqual(change_log.reason, 'カテゴリ整理')
        self.assertEqual(change_log.affected_transaction_count, 1)
        self.assertTrue(AuditLog.objects.filter(target_model='Category', target_id=str(self.from_category.pk)).exists())

    def test_reclassification_requires_reason(self):
        with self.assertRaises(ValidationError):
            reclassify_transactions(
                from_category=self.from_category,
                to_category=self.to_category,
                reason='',
                changed_by=self.user,
            )


class CategoryHistoryCompatibilityTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username='compat', password='pass')
        cls.account = Account.objects.create(name='互換口座')

    def setUp(self):
        self.client.login(username='compat', password='pass')

    def test_csv_import_does_not_resolve_old_category_name_from_history(self):
        category = Category.objects.create(name='旧カテゴリ', kind=Category.Kind.EXPENSE)
        self.client.post(reverse('ledger:category_update', args=[category.pk]), {
            'name': '新カテゴリ',
            'kind': Category.Kind.EXPENSE,
            'section': Category.Section.OTHER,
            'tax_tag': Category.TaxTag.NONE,
            'notes': '',
            'change_reason': '名称変更',
        })
        from ledger.services.csv_import import build_preview_rows
        preview = build_preview_rows([
            ['2026-05-01', '支出', '互換口座', '旧カテゴリ', '500', '摘要', ''],
        ])
        self.assertEqual(preview[0].status, 'error_category')

    def test_monthly_closing_amount_snapshot_unchanged_by_category_edit(self):
        category = Category.objects.create(name='締めカテゴリ', kind=Category.Kind.EXPENSE)
        Transaction.objects.create(
            date=date(2026, 5, 1),
            account=self.account,
            category=category,
            amount=1000,
            description='締め対象',
        )
        closing = MonthlyClosing.objects.create(
            month=date(2026, 5, 1),
            opening_carry=0,
            income=0,
            expense=1000,
            net=-1000,
            closing_balance=-1000,
            account_balances=[],
        )
        self.client.post(reverse('ledger:category_update', args=[category.pk]), {
            'name': '締めカテゴリ改名',
            'kind': Category.Kind.EXPENSE,
            'section': Category.Section.MEDICAL,
            'tax_tag': Category.TaxTag.MEDICAL,
            'notes': '',
            'change_reason': '締め後分類見直し',
        })
        closing.refresh_from_db()
        self.assertEqual(closing.expense, 1000)
        self.assertEqual(closing.net, -1000)
        log = CategoryChangeLog.objects.get(category=category)
        self.assertTrue(log.includes_closed_month)
