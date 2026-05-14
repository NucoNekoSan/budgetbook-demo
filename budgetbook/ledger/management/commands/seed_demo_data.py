"""Public demo / portfolio 用のデモデータを生成する management command。

一般的な 4 人家族（夫・妻・子 2 人想定）の家計をモデルにしたダミーデータ。
実在の人物・口座・金融機関を一切含まない。

Usage:
    python manage.py seed_demo_data --reset

`--reset` は既存の demo データだけを削除して再投入する（既存 user / superuser は残す）。
"""
from __future__ import annotations

import random
from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction as db_transaction

from ledger.models import (
    Account,
    AnnualIncomeSnapshot,
    Category,
    InsurancePremium,
    LoanProfile,
    MedicalExpense,
    SectionBudget,
    Transaction,
    Transfer,
)


# ---------------------------------------------------------------------------
# Master data (一般家庭向け)
# ---------------------------------------------------------------------------

ASSET_ACCOUNTS = [
    ('現金', 30_000),
    ('普通預金', 800_000),
    ('貯蓄預金', 1_500_000),
    ('証券口座', 500_000),
    ('電子マネー', 8_000),
]

LIABILITY_ACCOUNTS = [
    # (name, kind, opening_balance_negative_or_zero)
    ('住宅ローン', -25_000_000),
    ('自動車ローン', -1_200_000),
    ('クレジットカード', 0),
]

LOAN_PROFILES = [
    # (account_name, annual_rate_bp, monthly_payment, payment_day, source_account_name, method)
    ('住宅ローン', 130, 85_000, 27, '普通預金', LoanProfile.Method.EQUAL_PRINCIPAL_INTEREST),
    ('自動車ローン', 290, 35_000, 27, '普通預金', LoanProfile.Method.EQUAL_PRINCIPAL_INTEREST),
]

INCOME_CATEGORIES = [
    ('給与', Category.Section.OTHER, Category.TaxTag.NONE),
    ('ボーナス', Category.Section.OTHER, Category.TaxTag.NONE),
    ('副収入', Category.Section.OTHER, Category.TaxTag.NONE),
]

EXPENSE_CATEGORIES = [
    # (name, section, tax_tag)
    ('家賃・住宅ローン', Category.Section.HOUSING, Category.TaxTag.NONE),
    ('水道光熱費', Category.Section.UTILITY, Category.TaxTag.NONE),
    ('通信費', Category.Section.UTILITY, Category.TaxTag.NONE),
    ('食費', Category.Section.FOOD_DAILY, Category.TaxTag.NONE),
    ('日用品', Category.Section.FOOD_DAILY, Category.TaxTag.NONE),
    ('外食', Category.Section.DINING_OUT, Category.TaxTag.NONE),
    ('交通費', Category.Section.TRANSPORT, Category.TaxTag.NONE),
    ('医療費', Category.Section.MEDICAL, Category.TaxTag.MEDICAL),
    ('教育費', Category.Section.EDU_LEISURE, Category.TaxTag.NONE),
    ('娯楽', Category.Section.EDU_LEISURE, Category.TaxTag.NONE),
    ('衣料・美容', Category.Section.APPAREL_BEAUTY, Category.TaxTag.NONE),
    ('交際費', Category.Section.SOCIAL, Category.TaxTag.NONE),
    ('保険料', Category.Section.INSURANCE_TAX, Category.TaxTag.NONE),
    ('税金', Category.Section.INSURANCE_TAX, Category.TaxTag.NONE),
    ('ふるさと納税', Category.Section.SOCIAL, Category.TaxTag.DONATION),
    ('サブスク', Category.Section.UTILITY, Category.TaxTag.NONE),
    ('金利・手数料', Category.Section.OTHER, Category.TaxTag.NONE),
    ('その他', Category.Section.OTHER, Category.TaxTag.NONE),
]


def _months_back(today: date, n: int) -> date:
    y = today.year
    m = today.month - n
    while m <= 0:
        y -= 1
        m += 12
    return date(y, m, 1)


class Command(BaseCommand):
    help = 'Public demo / portfolio 用の家計サンプルデータを投入します。'

    def add_arguments(self, parser):
        parser.add_argument(
            '--reset',
            action='store_true',
            help='既存の取引/振替/医療費/保険料/口座/カテゴリ/予算/LoanProfile/AnnualIncomeSnapshot を全削除してから投入する',
        )
        parser.add_argument(
            '--seed',
            type=int,
            default=42,
            help='ランダム seed（再現性確保用、デフォルト 42）',
        )

    @db_transaction.atomic
    def handle(self, *args, **options):
        random.seed(options['seed'])

        if options['reset']:
            self._reset()

        self._create_demo_user()
        accounts = self._create_accounts()
        categories = self._create_categories()
        self._create_loan_profiles(accounts)
        self._create_transactions(accounts, categories)
        self._create_transfers(accounts)
        self._create_section_budgets()
        self._create_medical_expenses()
        self._create_insurance_premiums()
        self._create_income_snapshot()

        self.stdout.write(self.style.SUCCESS(
            'Demo data seeded. ログイン: demo / demo / 管理者ログイン admin / admin (本番では使わないこと)'
        ))

    # ----- reset --------------------------------------------------------

    def _reset(self):
        self.stdout.write('Resetting demo data...')
        # 順序重要: 子テーブルから削除
        MedicalExpense.objects.all().delete()
        InsurancePremium.objects.all().delete()
        AnnualIncomeSnapshot.objects.all().delete()
        SectionBudget.objects.all().delete()
        Transaction.objects.all().delete()
        Transfer.objects.all().delete()
        LoanProfile.objects.all().delete()
        Category.objects.all().delete()
        Account.objects.all().delete()

    # ----- users --------------------------------------------------------

    def _create_demo_user(self):
        User = get_user_model()
        for username, password, is_super in [
            ('demo', 'demo', False),
            ('admin', 'admin', True),
        ]:
            user, created = User.objects.get_or_create(
                username=username,
                defaults={'is_staff': is_super, 'is_superuser': is_super},
            )
            if created:
                user.set_password(password)
                user.save()

    # ----- master -------------------------------------------------------

    def _create_accounts(self) -> dict[str, Account]:
        accounts: dict[str, Account] = {}
        for name, opening_balance in ASSET_ACCOUNTS:
            acc, _ = Account.objects.update_or_create(
                name=name,
                defaults={
                    'kind': Account.Kind.ASSET,
                    'opening_balance': opening_balance,
                    'is_active': True,
                },
            )
            accounts[name] = acc
        for name, opening_balance in LIABILITY_ACCOUNTS:
            acc, _ = Account.objects.update_or_create(
                name=name,
                defaults={
                    'kind': Account.Kind.LIABILITY,
                    'opening_balance': opening_balance,
                    'is_active': True,
                },
            )
            accounts[name] = acc
        return accounts

    def _create_categories(self) -> dict[str, Category]:
        cats: dict[str, Category] = {}
        for name, section, tax_tag in INCOME_CATEGORIES:
            cat, _ = Category.objects.update_or_create(
                name=name,
                defaults={
                    'kind': Category.Kind.INCOME,
                    'section': section,
                    'tax_tag': tax_tag,
                    'is_active': True,
                },
            )
            cats[name] = cat
        for name, section, tax_tag in EXPENSE_CATEGORIES:
            cat, _ = Category.objects.update_or_create(
                name=name,
                defaults={
                    'kind': Category.Kind.EXPENSE,
                    'section': section,
                    'tax_tag': tax_tag,
                    'is_active': True,
                },
            )
            cats[name] = cat
        return cats

    def _create_loan_profiles(self, accounts: dict[str, Account]):
        for name, rate_bp, monthly, day, source_name, method in LOAN_PROFILES:
            LoanProfile.objects.update_or_create(
                account=accounts[name],
                defaults={
                    'annual_rate_bp': rate_bp,
                    'monthly_payment': monthly,
                    'payment_day': day,
                    'source_account': accounts[source_name],
                    'method': method,
                },
            )

    # ----- transactions -------------------------------------------------

    def _create_transactions(self, accounts: dict[str, Account], categories: dict[str, Category]):
        today = date.today()
        # 過去 3 ヶ月分の取引を生成
        start_month = _months_back(today, 2)
        # 各月の典型的なパターン
        for i in range(3):
            y, m = self._add_months(start_month, i)
            month_start = date(y, m, 1)
            # 月初: 給与（口座: 普通預金）
            Transaction.objects.create(
                date=date(y, m, 25),
                account=accounts['普通預金'],
                category=categories['給与'],
                amount=380_000,
                description='給与振込',
            )
            # 月末: 副収入（小額）
            Transaction.objects.create(
                date=date(y, m, 28),
                account=accounts['普通預金'],
                category=categories['副収入'],
                amount=random.randint(5_000, 20_000),
                description='ポイント還元',
            )
            # 家賃・住宅ローン (月 1 件)
            Transaction.objects.create(
                date=date(y, m, 27),
                account=accounts['普通預金'],
                category=categories['家賃・住宅ローン'],
                amount=120_000,
                description='住宅ローン返済',
            )
            # 水道光熱費
            Transaction.objects.create(
                date=date(y, m, 15),
                account=accounts['普通預金'],
                category=categories['水道光熱費'],
                amount=random.randint(18_000, 25_000),
                description='電気・ガス・水道',
            )
            # 通信費
            Transaction.objects.create(
                date=date(y, m, 10),
                account=accounts['普通預金'],
                category=categories['通信費'],
                amount=random.randint(12_000, 15_000),
                description='携帯・インターネット',
            )
            # サブスク
            Transaction.objects.create(
                date=date(y, m, 5),
                account=accounts['クレジットカード'],
                category=categories['サブスク'],
                amount=2_500,
                description='動画配信サービス',
            )
            # 食費 (週次レベルで複数)
            for week_day in [3, 10, 17, 24]:
                if week_day > 28:
                    continue
                Transaction.objects.create(
                    date=date(y, m, week_day),
                    account=accounts['現金'] if random.random() < 0.3 else accounts['クレジットカード'],
                    category=categories['食費'],
                    amount=random.randint(6_000, 12_000),
                    description=random.choice(['スーパー', '食材まとめ買い', '生協']),
                )
            # 外食 (月 2-3 件)
            for d in random.sample(range(2, 29), 3):
                Transaction.objects.create(
                    date=date(y, m, d),
                    account=accounts['クレジットカード'],
                    category=categories['外食'],
                    amount=random.randint(2_500, 6_500),
                    description=random.choice(['ランチ', 'ファミレス', 'カフェ']),
                )
            # 日用品
            for d in random.sample(range(2, 29), 2):
                Transaction.objects.create(
                    date=date(y, m, d),
                    account=accounts['クレジットカード'],
                    category=categories['日用品'],
                    amount=random.randint(1_500, 4_000),
                    description='ドラッグストア',
                )
            # 交通費
            Transaction.objects.create(
                date=date(y, m, 8),
                account=accounts['電子マネー'],
                category=categories['交通費'],
                amount=random.randint(8_000, 12_000),
                description='定期券チャージ',
            )
            # 医療費 (一部の月のみ)
            if i % 2 == 0:
                Transaction.objects.create(
                    date=date(y, m, 12),
                    account=accounts['現金'],
                    category=categories['医療費'],
                    amount=random.randint(1_500, 6_000),
                    description='病院・薬局',
                )
            # 教育費 (中月のみ)
            if i == 1:
                Transaction.objects.create(
                    date=date(y, m, 6),
                    account=accounts['普通預金'],
                    category=categories['教育費'],
                    amount=22_000,
                    description='習い事月謝',
                )
            # 娯楽
            Transaction.objects.create(
                date=date(y, m, 22),
                account=accounts['クレジットカード'],
                category=categories['娯楽'],
                amount=random.randint(3_000, 8_000),
                description='書籍・動画',
            )
            # ふるさと納税 (最後の月の年末想定)
            if i == 2:
                Transaction.objects.create(
                    date=date(y, m, 20),
                    account=accounts['クレジットカード'],
                    category=categories['ふるさと納税'],
                    amount=30_000,
                    description='ふるさと納税 (返礼品)',
                )

    @staticmethod
    def _add_months(d: date, n: int) -> tuple[int, int]:
        m = d.month + n
        y = d.year
        while m > 12:
            y += 1
            m -= 12
        return y, m

    # ----- transfers ----------------------------------------------------

    def _create_transfers(self, accounts: dict[str, Account]):
        today = date.today()
        # 月次のクレジット引き落とし振替（最近 1 件）
        last_month = _months_back(today, 1)
        Transfer.objects.create(
            date=date(last_month.year, last_month.month, 27),
            from_account=accounts['普通預金'],
            to_account=accounts['クレジットカード'],
            amount=45_000,
            description='クレジットカード引落',
        )
        # 普通預金 → 貯蓄預金 (積立)
        Transfer.objects.create(
            date=date(last_month.year, last_month.month, 25),
            from_account=accounts['普通預金'],
            to_account=accounts['貯蓄預金'],
            amount=50_000,
            description='積立貯蓄',
        )

    # ----- budgets ------------------------------------------------------

    def _create_section_budgets(self):
        today = date.today()
        month_start = date(today.year, today.month, 1)
        section_budgets = [
            (Category.Section.HOUSING, 130_000),
            (Category.Section.UTILITY, 30_000),
            (Category.Section.FOOD_DAILY, 55_000),
            (Category.Section.DINING_OUT, 15_000),
            (Category.Section.TRANSPORT, 12_000),
            (Category.Section.MEDICAL, 10_000),
            (Category.Section.EDU_LEISURE, 35_000),
            (Category.Section.APPAREL_BEAUTY, 10_000),
            (Category.Section.SOCIAL, 8_000),
            (Category.Section.INSURANCE_TAX, 20_000),
        ]
        for section, amount in section_budgets:
            SectionBudget.objects.update_or_create(
                month=month_start,
                section=section,
                defaults={'amount': amount},
            )

    # ----- 医療費控除明細 (v1.16.0) -----------------------------------

    def _create_medical_expenses(self):
        today = date.today()
        last_year = today.year - 1
        samples = [
            (date(last_year, 3, 5), '本人', '〇〇クリニック',
             MedicalExpense.MedicalCategory.TREATMENT, 4_200, 0, '風邪'),
            (date(last_year, 6, 12), '配偶者', '△△内科',
             MedicalExpense.MedicalCategory.TREATMENT, 6_800, 0, '健康診断後の精密検査'),
            (date(last_year, 7, 20), '子A', '□□小児科',
             MedicalExpense.MedicalCategory.TREATMENT, 3_500, 0, ''),
            (date(last_year, 8, 5), '本人', '◇◇薬局',
             MedicalExpense.MedicalCategory.MEDICINE, 1_800, 0, '処方薬'),
            (date(last_year, 9, 18), '配偶者', '◎◎薬局',
             MedicalExpense.MedicalCategory.MEDICINE, 2_400, 1_200, '保険適用の処方薬、組合より一部補填'),
            (date(last_year, 11, 10), '本人', '☆☆歯科クリニック',
             MedicalExpense.MedicalCategory.TREATMENT, 8_500, 0, '虫歯治療'),
        ]
        for paid_date, patient, provider, category, amount, reimbursement, notes in samples:
            MedicalExpense.objects.create(
                paid_date=paid_date,
                patient=patient,
                provider=provider,
                category=category,
                amount=amount,
                reimbursement=reimbursement,
                notes=notes,
            )

    # ----- 保険料控除 (v1.17.0) ------------------------------------------

    def _create_insurance_premiums(self):
        today = date.today()
        last_year = today.year - 1
        samples = [
            (last_year, InsurancePremium.InsuranceCategory.LIFE_GENERAL,
             InsurancePremium.ContractType.NEW, '〇〇生命', 'A-1234', 96_000, False),
            (last_year, InsurancePremium.InsuranceCategory.LIFE_CARE_MEDICAL,
             InsurancePremium.ContractType.NEW, '△△生命', 'B-5678', 48_000, False),
            (last_year, InsurancePremium.InsuranceCategory.LIFE_ANNUITY,
             InsurancePremium.ContractType.OLD, '◇◇共済', 'C-9012', 80_000, False),
            (last_year, InsurancePremium.InsuranceCategory.EARTHQUAKE,
             InsurancePremium.ContractType.NEW, '□□損保', 'D-3456', 32_000, False),
        ]
        for year, category, contract_type, insurer, policy, amount, year_end in samples:
            InsurancePremium.objects.create(
                year=year,
                category=category,
                contract_type=contract_type,
                insurer=insurer,
                policy_number=policy,
                annual_amount=amount,
                submitted_in_year_end_adjustment=year_end,
            )

    # ----- 年次総所得 ---------------------------------------------------

    def _create_income_snapshot(self):
        today = date.today()
        last_year = today.year - 1
        AnnualIncomeSnapshot.objects.update_or_create(
            year=last_year,
            defaults={
                'gross_income': 4_500_000,
                'notes': 'デモ用サンプル（源泉徴収票の「給与所得控除後の金額」想定）',
            },
        )
