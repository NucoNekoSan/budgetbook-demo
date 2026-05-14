from django.core.management.base import BaseCommand

from ledger.models import Account, Category


class Command(BaseCommand):
    help = '家計簿アプリ向けの初期口座・カテゴリを投入します。'

    def handle(self, *args, **options):
        accounts = ['現金', '普通預金']
        income_categories = ['給与', '副収入', '臨時収入']
        expense_categories = ['食費', '日用品', '住居費', '水道光熱費', '通信費', '交通費', '医療費', '娯楽費', '教育費', '雑費']

        for name in accounts:
            Account.objects.get_or_create(name=name)

        for name in income_categories:
            Category.objects.get_or_create(name=name, defaults={'kind': Category.Kind.INCOME})

        for name in expense_categories:
            Category.objects.get_or_create(name=name, defaults={'kind': Category.Kind.EXPENSE})

        self.stdout.write(self.style.SUCCESS('初期データの投入が完了しました。'))
