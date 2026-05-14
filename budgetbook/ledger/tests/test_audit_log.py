from datetime import date

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from ledger.models import Account, AccountReconciliation, AuditLog, Category, MonthlyClosing, Transaction


class AuditLogTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username='test', password='pass')
        cls.account = Account.objects.create(name='監査口座', opening_balance=10000)
        cls.category = Category.objects.create(name='監査食費', kind=Category.Kind.EXPENSE)

    def setUp(self):
        self.client.login(username='test', password='pass')

    def test_transaction_create_writes_audit_log(self):
        resp = self.client.post(reverse('ledger:transaction_create'), {
            'date': '2026-04-01',
            'account': self.account.pk,
            'kind': Category.Kind.EXPENSE,
            'category': self.category.pk,
            'amount': 1000,
            'description': '監査作成',
            'memo': '',
            'month': '2026-04',
        })
        self.assertEqual(resp.status_code, 302)
        log = AuditLog.objects.get(action=AuditLog.Action.CREATE, target_model='Transaction')
        self.assertEqual(log.user, self.user)
        self.assertIn('取引を保存', log.summary)
        self.assertEqual(log.metadata['amount'], 1000)

    def test_transaction_update_writes_audit_log(self):
        tx = Transaction.objects.create(
            date=date(2026, 4, 1),
            account=self.account,
            category=self.category,
            amount=1000,
            description='監査更新前',
        )
        resp = self.client.post(reverse('ledger:transaction_update', args=[tx.pk]), {
            'date': '2026-04-02',
            'account': self.account.pk,
            'kind': Category.Kind.EXPENSE,
            'category': self.category.pk,
            'amount': 1200,
            'description': '監査更新後',
            'memo': '',
            'month': '2026-04',
        })
        self.assertEqual(resp.status_code, 302)
        log = AuditLog.objects.get(action=AuditLog.Action.UPDATE, target_model='Transaction')
        self.assertEqual(log.target_id, str(tx.pk))
        self.assertEqual(log.metadata['amount'], 1200)

    def test_transaction_delete_keeps_target_id_in_audit_log(self):
        tx = Transaction.objects.create(
            date=date(2026, 4, 1),
            account=self.account,
            category=self.category,
            amount=1000,
            description='監査削除',
        )
        tx_id = str(tx.pk)
        resp = self.client.post(reverse('ledger:transaction_delete', args=[tx.pk]) + '?month=2026-04')
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(Transaction.objects.filter(pk=tx_id).exists())
        log = AuditLog.objects.get(action=AuditLog.Action.DELETE, target_model='Transaction')
        self.assertEqual(log.target_id, tx_id)
        self.assertIn('監査削除', log.target_repr)

    def test_invalid_transaction_does_not_write_audit_log(self):
        resp = self.client.post(reverse('ledger:transaction_create'), {
            'date': '2026-04-01',
            'account': self.account.pk,
            'kind': Category.Kind.EXPENSE,
            'category': self.category.pk,
            'amount': 0,
            'description': '不正',
            'memo': '',
            'month': '2026-04',
        })
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(AuditLog.objects.exists())

    def test_monthly_closing_writes_audit_log(self):
        resp = self.client.post(reverse('ledger:monthly_closing_create'), {
            'month': '2026-04-01',
            'notes': '',
        })
        self.assertEqual(resp.status_code, 200)
        closing = MonthlyClosing.objects.get(month=date(2026, 4, 1))
        log = AuditLog.objects.get(action=AuditLog.Action.CLOSE, target_model='MonthlyClosing')
        self.assertEqual(log.target_id, str(closing.pk))
        self.assertEqual(log.metadata['month'], '2026-04')

    def test_reconciliation_writes_audit_log(self):
        resp = self.client.post(reverse('ledger:reconciliation_create'), {
            'account': self.account.pk,
            'reconciled_on': '2026-04-30',
            'actual_balance': 9800,
            'notes': '',
        })
        self.assertEqual(resp.status_code, 200)
        item = AccountReconciliation.objects.get(account=self.account, reconciled_on=date(2026, 4, 30))
        log = AuditLog.objects.get(action=AuditLog.Action.RECONCILE, target_model='AccountReconciliation')
        self.assertEqual(log.target_id, str(item.pk))
        self.assertEqual(log.metadata['difference'], item.difference)

    def test_audit_log_records_ip_and_user_agent(self):
        resp = self.client.post(
            reverse('ledger:transaction_create'),
            {
                'date': '2026-04-05',
                'account': self.account.pk,
                'kind': Category.Kind.EXPENSE,
                'category': self.category.pk,
                'amount': 500,
                'description': 'IP/UA テスト',
                'memo': '',
                'month': '2026-04',
            },
            HTTP_USER_AGENT='penTest/1.0',
            REMOTE_ADDR='10.0.0.99',
        )
        self.assertEqual(resp.status_code, 302)
        log = AuditLog.objects.get(action=AuditLog.Action.CREATE, target_model='Transaction')
        self.assertEqual(log.metadata.get('ip'), '10.0.0.99')
        self.assertEqual(log.metadata.get('user_agent'), 'penTest/1.0')

    def test_account_protected_delete_is_rejected_without_audit(self):
        """責務分離後: 関連取引のある口座 delete は拒否され、副作用なし。"""
        Transaction.objects.create(
            date=date(2026, 4, 1),
            account=self.account,
            category=self.category,
            amount=1000,
            description='保護',
        )
        resp = self.client.post(reverse('ledger:account_delete', args=[self.account.pk]))
        self.assertEqual(resp.status_code, 200)
        self.account.refresh_from_db()
        # 自動無効化はしない (責務は account_toggle に委ねる)
        self.assertTrue(self.account.is_active)
        # 拒否なので DEACTIVATE / DELETE どちらの監査も書かれない
        self.assertFalse(AuditLog.objects.filter(target_model='Account', target_id=str(self.account.pk)).exists())

    def test_account_toggle_to_inactive_writes_audit_log(self):
        """責務分離後: 無効化は account_toggle が DEACTIVATE 監査を残す。"""
        self.client.post(reverse('ledger:account_toggle', args=[self.account.pk]))
        self.account.refresh_from_db()
        self.assertFalse(self.account.is_active)
        log = AuditLog.objects.get(action=AuditLog.Action.DEACTIVATE, target_model='Account')
        self.assertEqual(log.target_id, str(self.account.pk))
