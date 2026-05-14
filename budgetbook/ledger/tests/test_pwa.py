"""v1.9.0 PWA テスト。"""
from __future__ import annotations

import json

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse


class ManifestTest(TestCase):
    def test_manifest_status_and_content_type(self):
        resp = self.client.get('/manifest.webmanifest')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp['Content-Type'], 'application/manifest+json')

    def test_manifest_no_login_required(self):
        # 未ログインでもアクセス可能であること
        resp = self.client.get('/manifest.webmanifest')
        self.assertEqual(resp.status_code, 200)

    def test_manifest_required_fields(self):
        resp = self.client.get('/manifest.webmanifest')
        data = json.loads(resp.content)
        self.assertEqual(data['name'], 'BudgetBook')
        self.assertEqual(data['start_url'], '/')
        self.assertEqual(data['scope'], '/')
        self.assertEqual(data['display'], 'standalone')
        # icons: SVG + 192 + 512 + maskable
        sizes = [i['sizes'] for i in data['icons']]
        self.assertIn('192x192', sizes)
        self.assertIn('512x512', sizes)
        purposes = [i.get('purpose') for i in data['icons']]
        self.assertIn('maskable', purposes)

    def test_manifest_via_reverse(self):
        resp = self.client.get(reverse('ledger:pwa_manifest'))
        self.assertEqual(resp.status_code, 200)


class ServiceWorkerTest(TestCase):
    def test_sw_status_and_content_type(self):
        resp = self.client.get('/sw.js')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp['Content-Type'], 'application/javascript')

    def test_sw_no_login_required(self):
        resp = self.client.get('/sw.js')
        self.assertEqual(resp.status_code, 200)

    def test_sw_allowed_header(self):
        resp = self.client.get('/sw.js')
        self.assertEqual(resp.get('Service-Worker-Allowed'), '/')

    def test_sw_body_has_cache_version(self):
        resp = self.client.get('/sw.js')
        body = resp.content.decode('utf-8')
        self.assertIn('CACHE_VERSION', body)
        self.assertIn("'install'", body)
        self.assertIn("'fetch'", body)


class OfflineTest(TestCase):
    def test_offline_status(self):
        resp = self.client.get('/offline')
        self.assertEqual(resp.status_code, 200)

    def test_offline_no_login_required(self):
        resp = self.client.get('/offline')
        self.assertEqual(resp.status_code, 200)

    def test_offline_has_csp(self):
        resp = self.client.get('/offline')
        self.assertIn('Content-Security-Policy', resp)


class BaseHtmlPwaTagsTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username='pwa', password='pass')

    def setUp(self):
        self.client.login(username='pwa', password='pass')

    def test_dashboard_has_pwa_tags(self):
        resp = self.client.get(reverse('ledger:dashboard'))
        body = resp.content.decode('utf-8')
        # manifest link
        self.assertIn('rel="manifest"', body)
        self.assertIn('/manifest.webmanifest', body)
        # theme color
        self.assertIn('name="theme-color"', body)
        # apple-touch-icon
        self.assertIn('rel="apple-touch-icon"', body)
        # apple meta
        self.assertIn('apple-mobile-web-app-capable', body)
        self.assertIn('apple-mobile-web-app-title', body)
        # SW register script (with nonce, served from /static/)
        self.assertIn('pwa_register.js', body)

    def test_offline_page_has_pwa_tags(self):
        # 未ログインでも base.html 経由でタグが入る
        self.client.logout()
        resp = self.client.get('/offline')
        body = resp.content.decode('utf-8')
        self.assertIn('/manifest.webmanifest', body)


class IconsAvailableTest(TestCase):
    """生成済み PNG / SVG が staticfiles 経由で配信されることを確認。

    runserver / 本番ともに同じ URL でアクセスできる前提。
    Django のテストランナーは whitenoise を介さないため、ここでは
    ファイル存在のみ確認する。
    """

    def test_icon_files_exist(self):
        from django.conf import settings
        from pathlib import Path
        icons_dir = Path(settings.BASE_DIR) / 'static' / 'icons'
        for fname in ('icon.svg', 'icon-192.png', 'icon-512.png', 'icon-mask-512.png', 'apple-touch-icon.png'):
            self.assertTrue((icons_dir / fname).exists(), f'{fname} not found')