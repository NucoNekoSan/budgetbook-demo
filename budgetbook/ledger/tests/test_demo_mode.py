"""v1.18.5: DEMO_MODE middleware + seed_demo_data command のテスト。"""
from __future__ import annotations

from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse

from ledger.models import (
    Account,
    AnnualIncomeSnapshot,
    Category,
    InsurancePremium,
    LoanProfile,
    MedicalExpense,
    SectionBudget,
    Transaction,
    Transfer,
)


# ===========================================================================
# DemoModeWriteBlockMiddleware
# ===========================================================================

class DemoModeMiddlewareTest(TestCase):
    """DEMO_MODE 環境で mutation がブロックされることの検証。"""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username='demo', password='demo')
        cls.account = Account.objects.create(name='テスト口座', opening_balance=10000)
        cls.cat = Category.objects.create(name='テスト食費', kind=Category.Kind.EXPENSE)

    def setUp(self):
        self.client.login(username='demo', password='demo')

    @override_settings(DEMO_MODE=False)
    def test_normal_mode_allows_post(self):
        """通常モード（DEMO_MODE=False）では POST が通る。"""
        resp = self.client.post(reverse('ledger:transaction_create'), {
            'date': '2025-06-01',
            'account': str(self.account.pk),
            'kind': Category.Kind.EXPENSE,
            'category': str(self.cat.pk),
            'amount': 1000,
            'description': 'テスト',
            'memo': '',
        })
        # 302 redirect (success) or 200 (form error) — どちらも 403 ではない
        self.assertNotEqual(resp.status_code, 403)

    @override_settings(DEMO_MODE=True, DEMO_ALLOW_WRITES=False)
    def test_demo_mode_blocks_post(self):
        """DEMO_MODE=True かつ DEMO_ALLOW_WRITES=False で POST が 403。"""
        resp = self.client.post(reverse('ledger:transaction_create'), {
            'date': '2025-06-01',
            'account': str(self.account.pk),
            'kind': Category.Kind.EXPENSE,
            'category': str(self.cat.pk),
            'amount': 1000,
            'description': 'テスト',
            'memo': '',
        })
        self.assertEqual(resp.status_code, 403)
        self.assertIn('demo_blocked', resp.content.decode('utf-8'))

    @override_settings(DEMO_MODE=True, DEMO_ALLOW_WRITES=False)
    def test_demo_mode_allows_get(self):
        """DEMO_MODE でも GET は通る（読み取り専用）。"""
        resp = self.client.get(reverse('ledger:dashboard'))
        self.assertNotEqual(resp.status_code, 403)

    @override_settings(DEMO_MODE=True, DEMO_ALLOW_WRITES=True)
    def test_demo_mode_with_allow_writes_allows_post(self):
        """DEMO_ALLOW_WRITES=True なら DEMO_MODE 中でも POST が通る。"""
        resp = self.client.post(reverse('ledger:transaction_create'), {
            'date': '2025-06-01',
            'account': str(self.account.pk),
            'kind': Category.Kind.EXPENSE,
            'category': str(self.cat.pk),
            'amount': 1000,
            'description': 'テスト',
            'memo': '',
        })
        self.assertNotEqual(resp.status_code, 403)

    @override_settings(DEMO_MODE=True, DEMO_ALLOW_WRITES=False)
    def test_demo_mode_allows_login_logout(self):
        """ログイン flow は DEMO_MODE でも通す（bypass 対象）。"""
        self.client.logout()
        # ログイン POST は許可される
        resp = self.client.post(reverse('login'), {
            'username': 'demo',
            'password': 'demo',
        })
        # 302 (success) or 200 (failure) どちらでもよいが 403 ではないこと
        self.assertNotEqual(resp.status_code, 403)


class DemoAutoLoginMiddlewareTest(TestCase):
    """DEMO_AUTO_LOGIN=1 で未認証訪問者を demo ユーザーとして自動ログイン。"""

    @classmethod
    def setUpTestData(cls):
        cls.demo_user = User.objects.create_user(username='demo', password='demo')

    @override_settings(DEMO_MODE=True, DEMO_AUTO_LOGIN=True)
    def test_anonymous_visitor_auto_logged_in(self):
        """未ログインで dashboard アクセス → demo ユーザーで自動ログイン → 200。"""
        resp = self.client.get(reverse('ledger:dashboard'))
        self.assertEqual(resp.status_code, 200)
        # template に user.username が出るはず
        body = resp.content.decode('utf-8')
        self.assertIn('demo', body)

    @override_settings(DEMO_MODE=True, DEMO_AUTO_LOGIN=False)
    def test_auto_login_disabled_redirects_to_login(self):
        """DEMO_AUTO_LOGIN=False では従来通り login_required redirect。"""
        resp = self.client.get(reverse('ledger:dashboard'))
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/accounts/login/', resp['Location'])

    @override_settings(DEMO_MODE=False, DEMO_AUTO_LOGIN=True)
    def test_auto_login_inert_when_demo_mode_off(self):
        """DEMO_MODE=False なら DEMO_AUTO_LOGIN=True でも自動ログインしない。"""
        resp = self.client.get(reverse('ledger:dashboard'))
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/accounts/login/', resp['Location'])

    @override_settings(DEMO_MODE=True, DEMO_AUTO_LOGIN=True)
    def test_existing_session_not_overridden(self):
        """既に他ユーザーで認証済みなら自動ログインで上書きしない。"""
        other = User.objects.create_user(username='other', password='other')
        self.client.login(username='other', password='other')
        resp = self.client.get(reverse('ledger:dashboard'))
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode('utf-8')
        self.assertIn('other', body)


class DemoModeContextProcessorTest(TestCase):
    """context processor が template に DEMO_MODE フラグを渡す。"""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username='demo', password='demo')

    def setUp(self):
        self.client.login(username='demo', password='demo')

    @override_settings(DEMO_MODE=True)
    def test_demo_banner_appears_in_template(self):
        resp = self.client.get(reverse('ledger:dashboard'))
        body = resp.content.decode('utf-8')
        self.assertIn('demo-banner', body)
        self.assertIn('デモデータです', body)

    @override_settings(DEMO_MODE=False)
    def test_demo_banner_hidden_when_off(self):
        resp = self.client.get(reverse('ledger:dashboard'))
        body = resp.content.decode('utf-8')
        self.assertNotIn('demo-banner', body)


# ===========================================================================
# seed_demo_data コマンド
# ===========================================================================

class SeedDemoDataCommandTest(TestCase):
    def test_seed_creates_expected_records(self):
        call_command('seed_demo_data', '--reset')
        self.assertEqual(Account.objects.count(), 8)
        # 収入 3 + 支出 18 = 21
        self.assertEqual(Category.objects.count(), 21)
        self.assertEqual(Category.objects.filter(kind=Category.Kind.INCOME).count(), 3)
        self.assertEqual(Category.objects.filter(kind=Category.Kind.EXPENSE).count(), 18)
        # 取引: 3 年分（前々年・前年フル + 当年部分）。前 2 年 600 件以上 + 当年で 600+
        self.assertGreater(Transaction.objects.count(), 500)
        # 振替: 月 2 件 × (24 前年 + 当年 1〜12 月) で年初でも 48 + 2 = 50 件以上
        self.assertGreaterEqual(Transfer.objects.count(), 50)
        self.assertEqual(LoanProfile.objects.count(), 2)
        # 医療費: 各年 10-12 件 × 2 年 = 20+ 件
        self.assertGreater(MedicalExpense.objects.count(), 15)
        # 保険料: 各年 4 件 × 3 年 = 12 件
        self.assertEqual(InsurancePremium.objects.count(), 12)
        # 所得スナップショット: 3 年分
        self.assertEqual(AnnualIncomeSnapshot.objects.count(), 3)
        # 予算: 当月 + 前月 × 10 セクション = 20 件
        self.assertEqual(SectionBudget.objects.count(), 20)

    def test_seed_is_idempotent_with_reset(self):
        call_command('seed_demo_data', '--reset')
        first_tx_count = Transaction.objects.count()
        call_command('seed_demo_data', '--reset', '--seed', '42')
        second_tx_count = Transaction.objects.count()
        # 同じ seed で同じ件数（再現性）
        self.assertEqual(first_tx_count, second_tx_count)

    def test_seed_creates_demo_user(self):
        from django.contrib.auth import get_user_model
        User = get_user_model()
        call_command('seed_demo_data', '--reset')
        self.assertTrue(User.objects.filter(username='demo').exists())
        self.assertTrue(User.objects.filter(username='admin', is_superuser=True).exists())

    def test_seed_does_not_use_real_personal_categories(self):
        """seed したカテゴリ名に private repo の実カテゴリ名が含まれていないこと。"""
        call_command('seed_demo_data', '--reset')
        forbidden = ['クレカリボ', '返還金', '<your-city>', '普通預金A', 'ショッピングローン']
        all_names = ' '.join(
            list(Account.objects.values_list('name', flat=True))
            + list(Category.objects.values_list('name', flat=True))
        )
        for word in forbidden:
            self.assertNotIn(word, all_names, f'Forbidden word in seed: {word}')

    def test_seed_medical_categories_use_official_choices(self):
        call_command('seed_demo_data', '--reset')
        valid_choices = {v for v, _ in MedicalExpense.MedicalCategory.choices}
        for e in MedicalExpense.objects.all():
            self.assertIn(e.category, valid_choices)

    def test_seed_insurance_premium_constraints(self):
        """seed で介護医療×旧契約の不正組合せが入っていないこと。"""
        call_command('seed_demo_data', '--reset')
        for ip in InsurancePremium.objects.filter(
            category=InsurancePremium.InsuranceCategory.LIFE_CARE_MEDICAL
        ):
            self.assertEqual(ip.contract_type, InsurancePremium.ContractType.NEW)
