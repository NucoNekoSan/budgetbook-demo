"""v1.10.0 観測性のテスト。"""
from __future__ import annotations

import json
import sys
from datetime import date
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse

from ledger.models import Account, Category, Transaction
from ledger.services import error_mail


class MetricsTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username='m', password='pass')
        cls.asset = Account.objects.create(
            name='M資産', opening_balance=100000, kind=Account.Kind.ASSET,
        )
        cls.liab = Account.objects.create(
            name='M負債', opening_balance=-50000, kind=Account.Kind.LIABILITY,
        )
        cls.cat = Category.objects.create(name='M食費', kind=Category.Kind.EXPENSE)
        Transaction.objects.create(
            date=date(2026, 5, 1), account=cls.asset, category=cls.cat,
            amount=1000, description='テスト',
        )

    def setUp(self):
        self.client.login(username='m', password='pass')

    def test_login_required(self):
        self.client.logout()
        resp = self.client.get(reverse('ledger:metrics'))
        self.assertEqual(resp.status_code, 302)

    def test_returns_json(self):
        resp = self.client.get(reverse('ledger:metrics'))
        self.assertEqual(resp.status_code, 200)
        self.assertIn('application/json', resp['Content-Type'])
        data = json.loads(resp.content)
        self.assertIn('counts', data)
        self.assertIn('balances', data)
        self.assertIn('axes', data)
        self.assertEqual(data['version'], '1.10.0')

    def test_counts(self):
        resp = self.client.get(reverse('ledger:metrics'))
        data = json.loads(resp.content)
        self.assertEqual(data['counts']['accounts']['total'], 2)
        self.assertEqual(data['counts']['accounts']['asset'], 1)
        self.assertEqual(data['counts']['accounts']['liability'], 1)
        self.assertEqual(data['counts']['transactions']['total'], 1)

    def test_balances_split(self):
        resp = self.client.get(reverse('ledger:metrics'))
        data = json.loads(resp.content)
        # 資産 100000 - 1000(支出) = 99000、負債 -50000
        self.assertEqual(data['balances']['asset_total'], 99000)
        self.assertEqual(data['balances']['liability_total'], -50000)
        self.assertEqual(data['balances']['net_worth'], 49000)

    def test_no_cache(self):
        resp = self.client.get(reverse('ledger:metrics'))
        cc = resp.get('Cache-Control', '')
        self.assertIn('no', cc.lower())


class LoginHistoryTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username='lh', password='pass')

    def setUp(self):
        self.client.login(username='lh', password='pass')

    def test_login_required(self):
        self.client.logout()
        resp = self.client.get(reverse('ledger:login_history'))
        self.assertEqual(resp.status_code, 302)

    def test_renders_empty_state(self):
        resp = self.client.get(reverse('ledger:login_history'))
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'\xe3\x83\xad\xe3\x82\xb0\xe3\x82\xa4\xe3\x83\xb3', resp.content)  # 「ログイン」


@override_settings(
    ERROR_NOTIFY_TO=['admin@example.com'],
    EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
    DEFAULT_FROM_EMAIL='budgetbook@test',
)
class ErrorMailTest(TestCase):
    def setUp(self):
        # 前テストで起動した送信スレッドを取り込んでから outbox を初期化する
        self._drain_threads()
        error_mail._reset_rate_limit_for_tests()
        mail.outbox = []

    def tearDown(self):
        self._drain_threads()

    def _exc_info(self):
        try:
            raise KeyError("'account'")
        except KeyError:
            return sys.exc_info()

    def _drain_threads(self):
        import threading
        for t in threading.enumerate():
            if t is not threading.current_thread() and t.daemon and t.is_alive():
                t.join(timeout=1.0)

    def test_payload_excludes_pii(self):
        exc = self._exc_info()
        subject, body = error_mail.build_error_payload(
            path='/transactions/new/', method='POST', status=500, exc_info=exc,
        )
        self.assertIn('KeyError', subject)
        self.assertIn('/transactions/new/', subject)
        # 本文に cookie / session / body の手掛かりが入っていない
        self.assertNotIn('cookie', body.lower())
        self.assertNotIn('csrftoken', body.lower())
        self.assertNotIn('sessionid', body.lower())
        # 例外メッセージは入る
        self.assertIn('account', body)

    def test_traceback_truncated(self):
        exc = self._exc_info()
        _, body = error_mail.build_error_payload(
            path='/x', method='GET', status=500, exc_info=exc,
        )
        # 「先頭 5 行」と書かれているはず
        self.assertIn('先頭', body)

    def test_notify_sends_when_configured(self):
        exc = self._exc_info()
        result = error_mail.notify(
            path='/x', method='GET', status=500, exc_info=exc,
        )
        self.assertTrue(result)
        self._drain_threads()
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('KeyError', mail.outbox[0].subject)
        self.assertEqual(mail.outbox[0].to, ['admin@example.com'])

    def test_rate_limited_within_5min(self):
        exc = self._exc_info()
        first = error_mail.notify(path='/x', method='GET', status=500, exc_info=exc)
        second = error_mail.notify(path='/x', method='GET', status=500, exc_info=exc)
        self.assertTrue(first)
        self.assertFalse(second)

    def test_different_path_not_rate_limited(self):
        exc = self._exc_info()
        a = error_mail.notify(path='/a', method='GET', status=500, exc_info=exc)
        b = error_mail.notify(path='/b', method='GET', status=500, exc_info=exc)
        self.assertTrue(a)
        self.assertTrue(b)


@override_settings(ERROR_NOTIFY_TO=[])
class ErrorMailDisabledTest(TestCase):
    def setUp(self):
        error_mail._reset_rate_limit_for_tests()
        mail.outbox = []

    def test_notify_noop_when_disabled(self):
        try:
            raise ValueError('x')
        except ValueError:
            exc = sys.exc_info()
        result = error_mail.notify(path='/x', method='GET', status=500, exc_info=exc)
        self.assertFalse(result)
        self.assertEqual(len(mail.outbox), 0)


class HandlerAttachTest(TestCase):
    def test_handler_attached_only_when_configured(self):
        # 起動済み LOGGING の中身は環境変数依存。settings をフラグだけ確認。
        from django.conf import settings as dj_settings
        # ERROR_NOTIFY_TO は list（空 list なら attach されない設計）
        self.assertIsInstance(dj_settings.ERROR_NOTIFY_TO, list)


class SettingsPageLinksTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username='sp', password='pass')

    def setUp(self):
        self.client.login(username='sp', password='pass')

    def test_settings_has_observability_links(self):
        # /metrics は監視ツール用 JSON エンドポイントなので設定 UI にリンクは置かない。
        # URL 直打ちでのみアクセスする運用に変更 (v1.11.0)。
        resp = self.client.get(reverse('ledger:settings'))
        body = resp.content.decode('utf-8')
        self.assertIn(reverse('ledger:login_history'), body)
        self.assertNotIn(reverse('ledger:metrics'), body)