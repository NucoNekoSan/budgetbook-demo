from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import transaction

from ledger.models import Account, Category, ExpenseGroup, ExpenseGroupCategory, PaymentMethod


ASSET_ACCOUNTS = ['現金', '普通預金', '電子マネー']
LIABILITY_ACCOUNTS = ['クレジットカード']
INCOME_CATEGORIES = [
    ('給与', Category.Section.OTHER, Category.TaxTag.NONE),
    ('副収入', Category.Section.OTHER, Category.TaxTag.NONE),
]
EXPENSE_CATEGORIES = [
    ('食費', Category.Section.FOOD_DAILY, Category.TaxTag.NONE),
    ('日用品', Category.Section.FOOD_DAILY, Category.TaxTag.NONE),
    ('外食', Category.Section.DINING_OUT, Category.TaxTag.NONE),
    ('住居費', Category.Section.HOUSING, Category.TaxTag.NONE),
    ('水道光熱費', Category.Section.UTILITY, Category.TaxTag.NONE),
    ('通信費', Category.Section.UTILITY, Category.TaxTag.NONE),
    ('交通費', Category.Section.TRANSPORT, Category.TaxTag.NONE),
    ('医療費', Category.Section.MEDICAL, Category.TaxTag.MEDICAL),
    ('教育・娯楽', Category.Section.EDU_LEISURE, Category.TaxTag.NONE),
    ('衣料・美容', Category.Section.APPAREL_BEAUTY, Category.TaxTag.NONE),
    ('交際費', Category.Section.SOCIAL, Category.TaxTag.NONE),
    ('保険・税金', Category.Section.INSURANCE_TAX, Category.TaxTag.NONE),
    ('ふるさと納税', Category.Section.SOCIAL, Category.TaxTag.DONATION),
    ('その他', Category.Section.OTHER, Category.TaxTag.NONE),
]
PAYMENT_METHODS = [
    ('現金', PaymentMethod.Kind.CASH),
    ('銀行振込', PaymentMethod.Kind.BANK),
    ('クレジットカード', PaymentMethod.Kind.CREDIT_CARD),
    ('電子マネー', PaymentMethod.Kind.ELECTRONIC_MONEY),
]
GROUPS = [
    ('生活固定費', ['住居費', '水道光熱費', '通信費', '保険・税金']),
    ('日常支出', ['食費', '日用品', '外食', '交通費']),
    ('任意支出', ['教育・娯楽', '衣料・美容', '交際費', 'その他']),
]


class Command(BaseCommand):
    help = 'Downloadable distribution 用の標準マスタだけを投入します。取引データは作成しません。'

    @transaction.atomic
    def handle(self, *args, **options):
        for name in ASSET_ACCOUNTS:
            Account.objects.get_or_create(
                name=name,
                defaults={'kind': Account.Kind.ASSET, 'opening_balance': 0},
            )
        for name in LIABILITY_ACCOUNTS:
            Account.objects.get_or_create(
                name=name,
                defaults={'kind': Account.Kind.LIABILITY, 'opening_balance': 0},
            )

        categories = {}
        for name, section, tax_tag in INCOME_CATEGORIES:
            category, _ = Category.objects.get_or_create(
                name=name,
                defaults={'kind': Category.Kind.INCOME, 'section': section, 'tax_tag': tax_tag},
            )
            categories[name] = category
        for name, section, tax_tag in EXPENSE_CATEGORIES:
            category, _ = Category.objects.get_or_create(
                name=name,
                defaults={'kind': Category.Kind.EXPENSE, 'section': section, 'tax_tag': tax_tag},
            )
            categories[name] = category

        for name, kind in PAYMENT_METHODS:
            PaymentMethod.objects.get_or_create(name=name, defaults={'kind': kind})

        for sort_order, (group_name, category_names) in enumerate(GROUPS, start=10):
            group, _ = ExpenseGroup.objects.get_or_create(
                name=group_name,
                defaults={'sort_order': sort_order},
            )
            for category_name in category_names:
                category = categories.get(category_name)
                if category is not None:
                    ExpenseGroupCategory.objects.get_or_create(group=group, category=category)

        self.stdout.write(self.style.SUCCESS('標準マスタの投入が完了しました。'))