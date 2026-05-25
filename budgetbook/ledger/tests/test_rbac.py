from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse


@override_settings(LEDGER_STAFF_ONLY=True)
class StaffOnlyLedgerModeTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.staff = User.objects.create_user(
            username='staff',
            password='pass',
            is_staff=True,
        )
        cls.member = User.objects.create_user(
            username='member',
            password='pass',
            is_staff=False,
        )

    def test_anonymous_user_still_redirects_to_login(self):
        resp = self.client.get(reverse('ledger:dashboard'))
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/accounts/login/', resp.url)

    def test_non_staff_user_is_forbidden_from_private_ledger(self):
        self.client.login(username='member', password='pass')
        for url in [
            reverse('ledger:dashboard'),
            reverse('ledger:settings'),
            reverse('ledger:metrics'),
            reverse('ledger:transaction_export'),
        ]:
            with self.subTest(url=url):
                resp = self.client.get(url)
                self.assertEqual(resp.status_code, 403)

    def test_staff_user_can_access_private_ledger(self):
        self.client.login(username='staff', password='pass')
        resp = self.client.get(reverse('ledger:dashboard'))
        self.assertEqual(resp.status_code, 200)

    def test_public_operational_and_pwa_paths_are_exempt(self):
        self.client.login(username='member', password='pass')
        for url in [
            reverse('ledger:healthz'),
            reverse('ledger:pwa_manifest'),
            reverse('ledger:pwa_service_worker'),
            reverse('ledger:pwa_offline'),
        ]:
            with self.subTest(url=url):
                resp = self.client.get(url)
                self.assertNotEqual(resp.status_code, 403)
