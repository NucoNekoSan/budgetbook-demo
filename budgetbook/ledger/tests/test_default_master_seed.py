from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from ledger.models import Account, Category, ExpenseGroup, PaymentMethod, Transaction


class SeedDefaultMasterDataTest(TestCase):
    def test_seed_default_master_data_is_idempotent_and_empty_of_transactions(self):
        out = StringIO()
        call_command('seed_default_master_data', stdout=out)
        call_command('seed_default_master_data', stdout=StringIO())

        self.assertIn('標準マスタの投入が完了しました。', out.getvalue())
        self.assertTrue(Account.objects.filter(name='普通預金').exists())
        self.assertTrue(Category.objects.filter(name='給与', kind=Category.Kind.INCOME).exists())
        self.assertTrue(Category.objects.filter(name='医療費', tax_tag=Category.TaxTag.MEDICAL).exists())
        self.assertTrue(PaymentMethod.objects.filter(name='クレジットカード').exists())
        self.assertTrue(ExpenseGroup.objects.filter(name='日常支出').exists())
        self.assertEqual(Transaction.objects.count(), 0)