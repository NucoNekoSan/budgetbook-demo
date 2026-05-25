from django.test import SimpleTestCase

from ledger.models import AccountReconciliation, Transaction, Transfer


class PerformanceIndexMetadataTest(SimpleTestCase):
    def test_hot_path_indexes_are_declared(self):
        expected = {
            Transaction: {
                'ledger_tx_date_id_idx',
                'ledger_tx_acct_date_idx',
                'ledger_tx_cat_date_idx',
                'ledger_tx_payee_date_idx',
                'ledger_tx_pm_date_idx',
            },
            Transfer: {
                'ledger_transfer_date_id_idx',
                'ledger_transfer_from_date_idx',
                'ledger_transfer_to_date_idx',
            },
            AccountReconciliation: {
                'ledger_recon_date_acct_idx',
            },
        }

        for model, names in expected.items():
            with self.subTest(model=model.__name__):
                actual = {index.name for index in model._meta.indexes}
                self.assertTrue(names <= actual)
