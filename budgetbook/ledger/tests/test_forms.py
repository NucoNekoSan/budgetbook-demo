from datetime import date

from django.test import TestCase

from ledger.models import Account, Category, Transaction
from ledger.forms import TransactionForm


class TransactionFormKindCategoryTest(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.account = Account.objects.create(name='テスト口座')
        cls.cat_income = Category.objects.create(name='給与', kind=Category.Kind.INCOME)
        cls.cat_expense = Category.objects.create(name='食費', kind=Category.Kind.EXPENSE)

    def _form_data(self, kind, category):
        return {
            'date': '2026-04-01',
            'account': self.account.pk,
            'kind': kind,
            'category': category.pk,
            'amount': 1000,
            'description': 'テスト',
        }

    def test_expense_kind_with_expense_category_valid(self):
        form = TransactionForm(data=self._form_data('expense', self.cat_expense))
        self.assertTrue(form.is_valid(), form.errors)

    def test_income_kind_with_income_category_valid(self):
        form = TransactionForm(data=self._form_data('income', self.cat_income))
        self.assertTrue(form.is_valid(), form.errors)

    def test_expense_kind_with_income_category_rejected(self):
        form = TransactionForm(data=self._form_data('expense', self.cat_income))
        self.assertFalse(form.is_valid())

    def test_income_kind_with_expense_category_rejected(self):
        form = TransactionForm(data=self._form_data('income', self.cat_expense))
        self.assertFalse(form.is_valid())
