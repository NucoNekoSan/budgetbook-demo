from datetime import date

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from ledger.models import Account, Category, Transaction, Transfer


class AuthRequiredEndpointTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.account_a = Account.objects.create(name='普通預金A')
        cls.account_b = Account.objects.create(name='普通預金B')
        cls.category = Category.objects.create(name='食費', kind=Category.Kind.EXPENSE)
        cls.transaction = Transaction.objects.create(
            date=date.today(),
            account=cls.account_a,
            category=cls.category,
            amount=1000,
            description='スーパー',
        )
        cls.transfer = Transfer.objects.create(
            date=date.today(),
            from_account=cls.account_a,
            to_account=cls.account_b,
            amount=5000,
            description='資金移動',
        )

    def assertLoginRequired(self, url, method='get'):
        request_method = getattr(self.client, method)
        resp = request_method(url)
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/accounts/login/', resp.url)

    def test_read_pages_require_login(self):
        for url in [
            reverse('ledger:dashboard'),
            reverse('ledger:annual'),
            reverse('ledger:expense_breakdown'),
            reverse('ledger:accounting'),
            reverse('ledger:settings'),
            reverse('ledger:transaction_export'),
        ]:
            with self.subTest(url=url):
                self.assertLoginRequired(url)

    def test_mutation_endpoints_require_login(self):
        urls = [
            reverse('ledger:transaction_create'),
            reverse('ledger:transaction_update', args=[self.transaction.pk]),
            reverse('ledger:transaction_delete', args=[self.transaction.pk]),
            reverse('ledger:transaction_inline_update', args=[self.transaction.pk]),
            reverse('ledger:transfer_create'),
            reverse('ledger:transfer_update', args=[self.transfer.pk]),
            reverse('ledger:transfer_delete', args=[self.transfer.pk]),
            reverse('ledger:transfer_inline_update', args=[self.transfer.pk]),
            reverse('ledger:monthly_closing_create'),
            reverse('ledger:reconciliation_create'),
            reverse('ledger:account_create'),
            reverse('ledger:account_update', args=[self.account_a.pk]),
            reverse('ledger:account_toggle', args=[self.account_a.pk]),
            reverse('ledger:account_delete', args=[self.account_a.pk]),
            reverse('ledger:category_create'),
            reverse('ledger:category_update', args=[self.category.pk]),
            reverse('ledger:category_toggle', args=[self.category.pk]),
            reverse('ledger:category_delete', args=[self.category.pk]),
        ]
        for url in urls:
            with self.subTest(url=url):
                self.assertLoginRequired(url, method='post')

    def test_inline_cancel_endpoints_require_login(self):
        for url in [
            reverse('ledger:transaction_inline_cancel', args=[self.transaction.pk]),
            reverse('ledger:transfer_inline_cancel', args=[self.transfer.pk]),
        ]:
            with self.subTest(url=url):
                self.assertLoginRequired(url)


class LoginLogoutSecurityTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username='testuser', password='testpass123')

    def test_login_page_accessible(self):
        resp = self.client.get('/accounts/login/')
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'ログイン')

    def test_login_success_redirects_to_dashboard(self):
        resp = self.client.post('/accounts/login/', {
            'username': 'testuser',
            'password': 'testpass123',
        })
        self.assertRedirects(resp, '/')

    def test_login_failure_does_not_authenticate(self):
        resp = self.client.post('/accounts/login/', {
            'username': 'testuser',
            'password': 'wrongpass',
        })
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_authenticated_user_redirected_from_login_page(self):
        self.client.login(username='testuser', password='testpass123')
        resp = self.client.get('/accounts/login/')
        self.assertRedirects(resp, '/')

    def test_logout_requires_post_and_redirects_to_login(self):
        self.client.login(username='testuser', password='testpass123')
        get_resp = self.client.get('/accounts/logout/')
        self.assertEqual(get_resp.status_code, 405)
        post_resp = self.client.post('/accounts/logout/')
        self.assertRedirects(post_resp, '/accounts/login/')

    def test_disabled_password_management_urls_are_not_exposed(self):
        for path in ['/accounts/password_change/', '/accounts/password_reset/']:
            with self.subTest(path=path):
                resp = self.client.get(path)
                self.assertEqual(resp.status_code, 404)


class SecurityHeaderTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username='testuser', password='testpass123')

    def test_authenticated_response_has_security_headers(self):
        self.client.login(username='testuser', password='testpass123')
        resp = self.client.get(reverse('ledger:dashboard'))
        self.assertEqual(resp.headers['X-Frame-Options'], 'DENY')
        self.assertEqual(resp.headers['X-Content-Type-Options'], 'nosniff')
        self.assertEqual(resp.headers['Referrer-Policy'], 'same-origin')
        csp = resp.headers['Content-Security-Policy']
        self.assertIn("default-src 'self'", csp)
        self.assertIn("object-src 'none'", csp)
        self.assertIn("frame-ancestors 'none'", csp)
        self.assertIn("form-action 'self'", csp)
