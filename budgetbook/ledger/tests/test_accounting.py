from datetime import date

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from ledger.models import Account, AccountReconciliation, Category, MonthlyClosing, Transaction, Transfer
from ledger.views import calculate_account_balance, month_end


class MonthlyClosingTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username='test', password='pass')
        cls.account = Account.objects.create(name='普通預金A', opening_balance=10000)
        cls.account_b = Account.objects.create(name='北海道銀行', opening_balance=20000)
        cls.income = Category.objects.create(name='給与', kind=Category.Kind.INCOME)
        cls.expense = Category.objects.create(name='食費', kind=Category.Kind.EXPENSE)

    def setUp(self):
        self.client.login(username='test', password='pass')

    def test_accounting_page_loads(self):
        resp = self.client.get(reverse('ledger:accounting'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, '締め・照合')
        self.assertContains(resp, '月次締め')
        self.assertContains(resp, '口座残高照合')
        self.assertContains(resp, '締め前チェック')
        self.assertContains(resp, 'バックアップ取得と会計整合性チェック')
        self.assertContains(resp, 'status-pill')
        self.assertNotContains(resp, 'style="margin-top:18px"')

    def test_accounting_preflight_warns_unreconciled_accounts(self):
        resp = self.client.get(reverse('ledger:accounting'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, '照合が未登録の口座')
        self.assertContains(resp, '普通預金A')
        self.assertContains(resp, '北海道銀行')

    def test_accounting_preflight_marks_month_end_reconciled_accounts(self):
        today = date.today()
        target_month = date(today.year, today.month, 1)
        closing_day = month_end(target_month)
        AccountReconciliation.objects.create(
            account=self.account,
            reconciled_on=closing_day,
            book_balance=calculate_account_balance(self.account, closing_day),
            actual_balance=calculate_account_balance(self.account, closing_day),
            difference=0,
        )
        AccountReconciliation.objects.create(
            account=self.account_b,
            reconciled_on=closing_day,
            book_balance=calculate_account_balance(self.account_b, closing_day),
            actual_balance=calculate_account_balance(self.account_b, closing_day),
            difference=0,
        )

        resp = self.client.get(reverse('ledger:accounting'))

        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, '有効口座は月末日で照合済みです')
        self.assertContains(resp, '登録済みの月末照合に差額はありません')
        self.assertNotContains(resp, '照合が未登録の口座')

    def test_accounting_preflight_warns_reconciliation_difference(self):
        today = date.today()
        target_month = date(today.year, today.month, 1)
        closing_day = month_end(target_month)
        AccountReconciliation.objects.create(
            account=self.account,
            reconciled_on=closing_day,
            book_balance=calculate_account_balance(self.account, closing_day),
            actual_balance=calculate_account_balance(self.account, closing_day) + 100,
            difference=100,
        )

        resp = self.client.get(reverse('ledger:accounting'))

        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, '月末照合に差額があります')
        self.assertContains(resp, '普通預金A')

    def test_create_monthly_closing_snapshot(self):
        Transaction.objects.create(
            date=date(2026, 4, 10), account=self.account, category=self.income,
            amount=5000, description='収入',
        )
        Transaction.objects.create(
            date=date(2026, 4, 11), account=self.account, category=self.expense,
            amount=1200, description='支出',
        )
        Transfer.objects.create(
            date=date(2026, 4, 12), from_account=self.account_b, to_account=self.account,
            amount=3000, description='資金移動',
        )

        resp = self.client.post(reverse('ledger:monthly_closing_create'), {
            'month': '2026-04-01',
            'notes': '4月締め',
        })
        self.assertEqual(resp.status_code, 200)
        closing = MonthlyClosing.objects.get(month=date(2026, 4, 1))
        self.assertEqual(closing.opening_carry, 30000)
        self.assertEqual(closing.income, 5000)
        self.assertEqual(closing.expense, 1200)
        self.assertEqual(closing.net, 3800)
        self.assertEqual(closing.closing_balance, 33800)
        self.assertEqual(closing.closed_by, self.user)
        self.assertEqual(len(closing.account_balances), 2)

    def test_delete_closing_unlocks_month(self):
        """誤って締めた月を取消できる。取消後は対象月の取引追加が可能になる。"""
        closing = MonthlyClosing.objects.create(
            month=date(2026, 4, 1),
            opening_carry=0, income=0, expense=0, net=0,
            closing_balance=0, account_balances=[],
        )
        resp = self.client.post(reverse('ledger:monthly_closing_delete', args=[closing.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(MonthlyClosing.objects.filter(pk=closing.pk).exists())
        # 取消後は対象月の取引追加が可能
        Transaction.objects.create(
            date=date(2026, 4, 15), account=self.account, category=self.income,
            amount=1000, description='取消後',
        )

    def test_delete_closing_writes_audit_log(self):
        from ledger.models import AuditLog
        closing = MonthlyClosing.objects.create(
            month=date(2026, 4, 1),
            opening_carry=0, income=0, expense=0, net=0,
            closing_balance=0, account_balances=[],
        )
        self.client.post(reverse('ledger:monthly_closing_delete', args=[closing.pk]))
        self.assertTrue(AuditLog.objects.filter(
            action=AuditLog.Action.DELETE, target_model='MonthlyClosing',
            target_id=str(closing.pk),
        ).exists())

    def test_resnapshot_recomputes_totals(self):
        """締めた後で過去の取引を訂正 → 再計算で drift が解消される。"""
        Transaction.objects.create(
            date=date(2026, 4, 10), account=self.account, category=self.income,
            amount=5000, description='初期収入',
        )
        # 締める (snapshot=5000)
        self.client.post(reverse('ledger:monthly_closing_create'), {
            'month': '2026-04-01', 'notes': '',
        })
        closing = MonthlyClosing.objects.get(month=date(2026, 4, 1))
        old_income = closing.income
        # 締めた後で取引を追加するのは禁止されているので、いったん取消してから追加
        self.client.post(reverse('ledger:monthly_closing_delete', args=[closing.pk]))
        Transaction.objects.create(
            date=date(2026, 4, 11), account=self.account, category=self.income,
            amount=3000, description='追加収入',
        )
        # 再度締めずに、別シナリオ: drift シミュレーションは別テストで。
        # ここでは resnapshot エンドポイント自体の動作のみ確認
        closing2 = MonthlyClosing.objects.create(
            month=date(2026, 4, 1),
            opening_carry=0, income=old_income, expense=0, net=old_income,
            closing_balance=old_income + 30000,
            account_balances=[],
        )
        resp = self.client.post(reverse('ledger:monthly_closing_resnapshot', args=[closing2.pk]))
        self.assertEqual(resp.status_code, 200)
        closing2.refresh_from_db()
        # 現在帳簿: 5000 + 3000 = 8000
        self.assertEqual(closing2.income, 8000)

    def test_delete_reconciliation(self):
        item = AccountReconciliation.objects.create(
            account=self.account,
            reconciled_on=date(2026, 4, 30),
            book_balance=10000,
            actual_balance=10000,
            difference=0,
        )
        resp = self.client.post(reverse('ledger:reconciliation_delete', args=[item.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(AccountReconciliation.objects.filter(pk=item.pk).exists())

    def test_help_panel_renders(self):
        resp = self.client.get(reverse('ledger:accounting'))
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode('utf-8')
        self.assertIn('この画面の使い方', body)
        self.assertIn('推奨フロー', body)
        self.assertIn('誤って締めた', body)

    def test_future_month_closing_rejected(self):
        today = date.today()
        future = (date(today.year, today.month, 1).replace(day=1))
        # 1か月先
        future_year = future.year + (1 if future.month == 12 else 0)
        future_month = 1 if future.month == 12 else future.month + 1
        future_label = f'{future_year}-{future_month:02d}-01'
        resp = self.client.post(reverse('ledger:monthly_closing_create'), {
            'month': future_label,
            'notes': '',
        })
        self.assertEqual(resp.status_code, 422)
        self.assertFalse(MonthlyClosing.objects.filter(
            month=date(future_year, future_month, 1)
        ).exists())

    def test_duplicate_monthly_closing_rejected(self):
        MonthlyClosing.objects.create(
            month=date(2026, 4, 1),
            opening_carry=0,
            income=0,
            expense=0,
            net=0,
            closing_balance=0,
            account_balances=[],
        )
        resp = self.client.post(reverse('ledger:monthly_closing_create'), {
            'month': '2026-04-01',
            'notes': '',
        })
        self.assertEqual(resp.status_code, 409)
        self.assertEqual(MonthlyClosing.objects.filter(month=date(2026, 4, 1)).count(), 1)

    def test_closed_month_blocks_transaction_create(self):
        MonthlyClosing.objects.create(
            month=date(2026, 4, 1),
            opening_carry=0,
            income=0,
            expense=0,
            net=0,
            closing_balance=0,
            account_balances=[],
        )
        resp = self.client.post(reverse('ledger:transaction_create') + '?month=2026-04', {
            'date': '2026-04-15',
            'account': self.account.pk,
            'kind': 'expense',
            'category': self.expense.pk,
            'amount': 1000,
            'description': '締め済み',
            'memo': '',
            'month': '2026-04',
        })
        self.assertEqual(resp.status_code, 409)
        self.assertFalse(Transaction.objects.filter(description='締め済み').exists())

    def test_closed_month_blocks_transfer_delete(self):
        transfer = Transfer.objects.create(
            date=date(2026, 4, 15),
            from_account=self.account,
            to_account=self.account_b,
            amount=1000,
            description='締め済み振替',
        )
        MonthlyClosing.objects.create(
            month=date(2026, 4, 1),
            opening_carry=0,
            income=0,
            expense=0,
            net=0,
            closing_balance=0,
            account_balances=[],
        )
        resp = self.client.post(reverse('ledger:transfer_delete', args=[transfer.pk]) + '?month=2026-04')
        self.assertEqual(resp.status_code, 409)
        self.assertTrue(Transfer.objects.filter(pk=transfer.pk).exists())

    def test_dashboard_marks_closed_month(self):
        MonthlyClosing.objects.create(
            month=date(2026, 4, 1),
            opening_carry=0,
            income=0,
            expense=0,
            net=0,
            closing_balance=0,
            account_balances=[],
        )
        resp = self.client.get(reverse('ledger:dashboard') + '?month=2026-04')
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, '締め済みです')

    def test_closed_month_dashboard_hides_edit_and_delete_actions(self):
        tx = Transaction.objects.create(
            date=date(2026, 4, 15),
            account=self.account,
            category=self.expense,
            amount=1200,
            description='締め済み取引',
        )
        transfer = Transfer.objects.create(
            date=date(2026, 4, 16),
            from_account=self.account,
            to_account=self.account_b,
            amount=3000,
            description='締め済み振替',
        )
        MonthlyClosing.objects.create(
            month=date(2026, 4, 1),
            opening_carry=0,
            income=0,
            expense=0,
            net=0,
            closing_balance=0,
            account_balances=[],
        )

        resp = self.client.get(reverse('ledger:dashboard') + '?month=2026-04')

        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, '閲覧のみ可能です')
        self.assertContains(resp, '締め済み取引')
        self.assertContains(resp, '締め済み振替')
        self.assertNotContains(resp, reverse('ledger:transaction_inline_update', args=[tx.pk]))
        self.assertNotContains(resp, reverse('ledger:transaction_delete', args=[tx.pk]))
        self.assertNotContains(resp, reverse('ledger:transfer_inline_update', args=[transfer.pk]))
        self.assertNotContains(resp, reverse('ledger:transfer_delete', args=[transfer.pk]))

    def test_closed_month_transaction_form_is_read_only(self):
        MonthlyClosing.objects.create(
            month=date(2026, 4, 1),
            opening_carry=0,
            income=0,
            expense=0,
            net=0,
            closing_balance=0,
            account_balances=[],
        )

        resp = self.client.get(reverse('ledger:transaction_create') + '?month=2026-04')

        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, '通常取引・振替の追加や編集はできません')
        self.assertNotContains(resp, 'type="submit"')
        self.assertNotContains(resp, '保存する')

    def test_closed_month_transfer_form_is_read_only(self):
        MonthlyClosing.objects.create(
            month=date(2026, 4, 1),
            opening_carry=0,
            income=0,
            expense=0,
            net=0,
            closing_balance=0,
            account_balances=[],
        )

        resp = self.client.get(reverse('ledger:transfer_create') + '?month=2026-04')

        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, '通常取引・振替の追加や編集はできません')
        self.assertNotContains(resp, 'type="submit"')
        self.assertNotContains(resp, '保存する')

    def test_accounting_page_marks_matching_closing_as_consistent(self):
        self.client.post(reverse('ledger:monthly_closing_create'), {
            'month': '2026-04-01',
            'notes': '',
        })

        resp = self.client.get(reverse('ledger:accounting'))

        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, '一致')
        self.assertNotContains(resp, '現在の帳簿と差異があります。')

    def test_accounting_page_warns_when_closed_month_snapshot_drifts(self):
        self.client.post(reverse('ledger:monthly_closing_create'), {
            'month': '2026-04-01',
            'notes': '',
        })
        Transaction.objects.create(
            date=date(2026, 4, 20),
            account=self.account,
            category=self.income,
            amount=5000,
            description='締め後追加',
        )

        resp = self.client.get(reverse('ledger:accounting'))

        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, '現在の帳簿と差異があります。')
        self.assertContains(resp, '収入差')
        self.assertContains(resp, '月末残高差')
        self.assertContains(resp, '普通預金A')


class AccountReconciliationTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username='test', password='pass')
        cls.account = Account.objects.create(name='現金', opening_balance=10000)
        cls.expense = Category.objects.create(name='食費', kind=Category.Kind.EXPENSE)

    def setUp(self):
        self.client.login(username='test', password='pass')

    def test_create_reconciliation_uses_server_side_book_balance(self):
        Transaction.objects.create(
            date=date(2026, 4, 10),
            account=self.account,
            category=self.expense,
            amount=1200,
            description='支出',
        )
        resp = self.client.post(reverse('ledger:reconciliation_create'), {
            'account': self.account.pk,
            'reconciled_on': '2026-04-30',
            'actual_balance': 9000,
            'notes': '手元現金確認',
        })
        self.assertEqual(resp.status_code, 200)
        item = AccountReconciliation.objects.get(account=self.account, reconciled_on=date(2026, 4, 30))
        self.assertEqual(item.book_balance, calculate_account_balance(self.account, date(2026, 4, 30)))
        self.assertEqual(item.book_balance, 8800)
        self.assertEqual(item.actual_balance, 9000)
        self.assertEqual(item.difference, 200)
        self.assertEqual(item.created_by, self.user)

    def test_duplicate_reconciliation_rejected(self):
        AccountReconciliation.objects.create(
            account=self.account,
            reconciled_on=date(2026, 4, 30),
            book_balance=10000,
            actual_balance=10000,
            difference=0,
        )
        resp = self.client.post(reverse('ledger:reconciliation_create'), {
            'account': self.account.pk,
            'reconciled_on': '2026-04-30',
            'actual_balance': 10000,
            'notes': '',
        })
        self.assertEqual(resp.status_code, 409)
        self.assertEqual(AccountReconciliation.objects.count(), 1)
