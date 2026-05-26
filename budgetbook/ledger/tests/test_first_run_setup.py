from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse

from ledger.models import Account, Category, PaymentMethod


@override_settings(FIRST_RUN_SETUP_ENABLED=True)
class FirstRunSetupTest(TestCase):
    def test_no_users_redirects_dashboard_to_setup(self):
        resp = self.client.get(reverse('ledger:dashboard'))
        self.assertRedirects(resp, reverse('ledger:first_run_setup'), fetch_redirect_response=False)

    def test_setup_creates_first_admin_and_default_masters(self):
        resp = self.client.post(reverse('ledger:first_run_setup'), {
            'username': 'owner',
            'display_name': 'Owner',
            'password': 'secure-passphrase-123',
            'create_default_masters': 'on',
        })

        self.assertRedirects(resp, reverse('ledger:dashboard'), fetch_redirect_response=False)
        user = User.objects.get(username='owner')
        self.assertTrue(user.is_staff)
        self.assertTrue(user.is_superuser)
        self.assertEqual(user.first_name, 'Owner')
        self.assertTrue(Account.objects.filter(name='普通預金').exists())
        self.assertTrue(Category.objects.filter(name='食費', kind=Category.Kind.EXPENSE).exists())
        self.assertTrue(PaymentMethod.objects.filter(name='現金').exists())

    def test_setup_is_closed_after_user_exists(self):
        User.objects.create_user(username='existing', password='pass')
        resp = self.client.get(reverse('ledger:first_run_setup'))
        self.assertRedirects(resp, reverse('ledger:dashboard'), fetch_redirect_response=False)

    def test_setup_post_is_closed_after_user_exists(self):
        User.objects.create_user(username='existing', password='pass')
        resp = self.client.post(reverse('ledger:first_run_setup'), {
            'username': 'second',
            'password': 'secure-passphrase-123',
        })
        self.assertRedirects(resp, reverse('ledger:dashboard'), fetch_redirect_response=False)
        self.assertFalse(User.objects.filter(username='second').exists())


class FirstRunSetupDisabledTest(TestCase):
    def test_default_behavior_keeps_existing_login_redirect(self):
        resp = self.client.get(reverse('ledger:dashboard'))
        self.assertIn('/accounts/login/', resp.url)