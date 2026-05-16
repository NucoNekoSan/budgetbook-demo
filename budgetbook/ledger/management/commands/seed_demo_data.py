"""Public demo / portfolio 用の家計サンプルデータを生成する管理コマンド。

日本の一般 4 人家族（夫・妻・子 2 人想定）のリアルな家計を 3 年分生成する。
実在の人物・口座・金融機関を一切含まない。

データスコープ:
- **当年**: 1 月〜現在月 (部分年、ダッシュボード・予算検証用)
- **前年**: 1〜12 月フル (確定申告レポート v2 / 医療費 / 保険料 / 寄附金検証用)
- **前々年**: 1〜12 月フル (年次推移・複数年選択 UI 検証用)

Usage:
    python manage.py seed_demo_data --reset
"""
from __future__ import annotations

import calendar
import random
import secrets
from datetime import date

from django.conf import settings
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
    ('住宅ローン', -25_000_000),
    ('自動車ローン', -1_200_000),
    ('クレジットカード', 0),
]

LOAN_PROFILES = [
    ('住宅ローン', 130, 85_000, 27, '普通預金', LoanProfile.Method.EQUAL_PRINCIPAL_INTEREST),
    ('自動車ローン', 290, 35_000, 27, '普通預金', LoanProfile.Method.EQUAL_PRINCIPAL_INTEREST),
]

INCOME_CATEGORIES = [
    ('給与', Category.Section.OTHER, Category.TaxTag.NONE),
    ('ボーナス', Category.Section.OTHER, Category.TaxTag.NONE),
    ('副収入', Category.Section.OTHER, Category.TaxTag.NONE),
]

EXPENSE_CATEGORIES = [
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


# 月別の水道光熱費パターン（夏冬高、春秋低）
UTILITY_PATTERN = {
    1: 25_000, 2: 26_500, 3: 22_000, 4: 18_000, 5: 16_500, 6: 17_500,
    7: 22_000, 8: 27_000, 9: 24_000, 10: 19_500, 11: 19_000, 12: 23_500,
}


def _last_day_of_month(year: int, month: int) -> int:
    return calendar.monthrange(year, month)[1]


def _safe_date(year: int, month: int, day: int) -> date:
    """日付が月の最終日を超えた場合は月末にクランプする。"""
    last = _last_day_of_month(year, month)
    return date(year, month, min(day, last))


class Command(BaseCommand):
    help = 'Public demo / portfolio 用の家計サンプルデータ（3 年分）を投入します。'

    def add_arguments(self, parser):
        parser.add_argument(
            '--reset',
            action='store_true',
            help='既存の demo データを全削除してから投入する',
        )
        parser.add_argument(
            '--seed',
            type=int,
            default=42,
            help='ランダム seed（再現性確保用、デフォルト 42）',
        )
        parser.add_argument(
            '--create-demo-users',
            action='store_true',
            help=(
                'demo / admin ユーザーを作成する。'
                ' 本番 DB への誤実行を防ぐため、DEMO_MODE=1 のときのみ admin パスワードはランダム生成され stdout に表示される。'
                ' 既存ユーザーは触らない。'
            ),
        )

    @db_transaction.atomic
    def handle(self, *args, **options):
        random.seed(options['seed'])

        if options['reset']:
            self._reset()

        self._admin_password_for_log = None
        if options['create_demo_users']:
            self._create_demo_user()
        accounts = self._create_accounts()
        categories = self._create_categories()
        self._create_loan_profiles(accounts)

        today = date.today()
        current_year = today.year
        years_full = [current_year - 2, current_year - 1]
        # 当年は 1 月〜現在月 (部分)

        # 取引: 3 年分（前々年・前年フル + 当年部分）
        for y in years_full:
            for m in range(1, 13):
                self._create_monthly_transactions(accounts, categories, y, m)
        for m in range(1, today.month + 1):
            self._create_monthly_transactions(accounts, categories, current_year, m)

        self._create_transfers(accounts, years_full, current_year, today.month)
        self._create_section_budgets()
        self._create_medical_expenses(years_full)
        self._create_insurance_premiums(years_full + [current_year])
        self._create_income_snapshots(years_full + [current_year])

        # 集計表示用
        total_tx = Transaction.objects.count()
        total_tf = Transfer.objects.count()
        total_me = MedicalExpense.objects.count()
        total_ip = InsurancePremium.objects.count()
        summary = (
            f'Demo data seeded:\n'
            f'  Transactions: {total_tx}\n'
            f'  Transfers: {total_tf}\n'
            f'  MedicalExpense: {total_me}\n'
            f'  InsurancePremium: {total_ip}\n'
            f'  Years covered: {current_year-2}〜{current_year}'
        )
        if options['create_demo_users']:
            summary += '\n  Login: demo / demo'
            if self._admin_password_for_log:
                summary += f'\n  Admin: admin / {self._admin_password_for_log}  (一度だけ表示。記録すること)'
        self.stdout.write(self.style.SUCCESS(summary))

    # ----- reset --------------------------------------------------------

    def _reset(self):
        self.stdout.write('Resetting demo data...')
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
        """demo / admin ユーザーを作成する。

        セキュリティ:
        - demo ユーザー (一般): DEMO_AUTO_LOGIN 経由で公開デモが自動ログインするための
          read-only アカウント。password 'demo' は固定（auto-login 前提なので実質無意味）。
        - admin ユーザー (superuser):
            * DEMO_MODE=1 のときのみ作成許可。本番 DB への誤実行を防ぐ。
            * password は毎回ランダム生成し stdout に **一度だけ** 表示。
            * 既存 admin ユーザーは絶対に上書きしない（パスワードリセット事故防止）。
        """
        demo_mode = bool(getattr(settings, 'DEMO_MODE', False))
        User = get_user_model()

        demo_user, created = User.objects.get_or_create(
            username='demo',
            defaults={'is_staff': False, 'is_superuser': False},
        )
        if created:
            demo_user.set_password('demo')
            demo_user.save()

        if not demo_mode:
            self.stdout.write(self.style.WARNING(
                'DEMO_MODE=0 のため admin superuser は作成しません。'
                ' demo 用に必要なら DEMO_MODE=1 を設定して再実行するか、'
                ' `python manage.py createsuperuser` で安全に作成してください。'
            ))
            return

        existing_admin = User.objects.filter(username='admin').first()
        if existing_admin is not None:
            self.stdout.write(self.style.WARNING(
                'admin ユーザーは既に存在します。パスワードは変更しません。'
            ))
            return

        admin_password = secrets.token_urlsafe(18)
        admin = User(username='admin', is_staff=True, is_superuser=True)
        admin.set_password(admin_password)
        admin.save()
        self._admin_password_for_log = admin_password

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

    # ----- monthly transactions ----------------------------------------

    def _create_monthly_transactions(
        self,
        accounts: dict[str, Account],
        categories: dict[str, Category],
        y: int,
        m: int,
    ):
        # === 収入 ===
        Transaction.objects.create(
            date=_safe_date(y, m, 25),
            account=accounts['普通預金'],
            category=categories['給与'],
            amount=380_000,
            description='給与振込',
        )
        # ボーナス (6 月・12 月)
        if m in (6, 12):
            Transaction.objects.create(
                date=_safe_date(y, m, 10),
                account=accounts['普通預金'],
                category=categories['ボーナス'],
                amount=600_000 + random.randint(-50_000, 50_000),
                description='賞与',
            )
        # 副収入 (月による、ポイント還元など)
        if random.random() < 0.6:
            Transaction.objects.create(
                date=_safe_date(y, m, 28),
                account=accounts['普通預金'],
                category=categories['副収入'],
                amount=random.randint(3_000, 15_000),
                description='ポイント還元・キャッシュバック',
            )

        # === 固定費 ===
        Transaction.objects.create(
            date=_safe_date(y, m, 27),
            account=accounts['普通預金'],
            category=categories['家賃・住宅ローン'],
            amount=120_000,
            description='住宅ローン返済',
        )
        Transaction.objects.create(
            date=_safe_date(y, m, 15),
            account=accounts['普通預金'],
            category=categories['水道光熱費'],
            amount=UTILITY_PATTERN[m] + random.randint(-1_500, 1_500),
            description='電気・ガス・水道',
        )
        Transaction.objects.create(
            date=_safe_date(y, m, 10),
            account=accounts['普通預金'],
            category=categories['通信費'],
            amount=13_500,
            description='携帯・インターネット',
        )
        Transaction.objects.create(
            date=_safe_date(y, m, 5),
            account=accounts['クレジットカード'],
            category=categories['サブスク'],
            amount=2_500,
            description='動画配信サービス',
        )
        Transaction.objects.create(
            date=_safe_date(y, m, 27),
            account=accounts['普通預金'],
            category=categories['保険料'],
            amount=12_000,
            description='生命保険・地震保険 月払い分',
        )

        # === 食費 (週次 4 件) ===
        for week_day in [3, 10, 17, 24]:
            Transaction.objects.create(
                date=_safe_date(y, m, week_day),
                account=accounts['現金'] if random.random() < 0.3 else accounts['クレジットカード'],
                category=categories['食費'],
                amount=random.randint(6_000, 12_000),
                description=random.choice(['スーパー', '食材まとめ買い', '生協', '農協']),
            )

        # === 外食 (月 2-4 件) ===
        outing_count = random.randint(2, 4)
        for d in random.sample(range(2, 29), outing_count):
            Transaction.objects.create(
                date=_safe_date(y, m, d),
                account=accounts['クレジットカード'],
                category=categories['外食'],
                amount=random.randint(2_500, 7_500),
                description=random.choice(['ランチ', 'ファミレス', 'カフェ', '居酒屋']),
            )

        # === 日用品 (月 2-3 件) ===
        for d in random.sample(range(2, 29), random.randint(2, 3)):
            Transaction.objects.create(
                date=_safe_date(y, m, d),
                account=accounts['クレジットカード'],
                category=categories['日用品'],
                amount=random.randint(1_500, 4_500),
                description=random.choice(['ドラッグストア', 'ホームセンター', '雑貨店']),
            )

        # === 交通費 ===
        Transaction.objects.create(
            date=_safe_date(y, m, 8),
            account=accounts['電子マネー'],
            category=categories['交通費'],
            amount=random.randint(8_000, 14_000),
            description='定期券チャージ',
        )

        # === 娯楽 ===
        Transaction.objects.create(
            date=_safe_date(y, m, 22),
            account=accounts['クレジットカード'],
            category=categories['娯楽'],
            amount=random.randint(3_000, 9_000),
            description=random.choice(['書籍', '動画購入', 'ゲーム', '映画']),
        )

        # === 医療費 (年に 6-10 件、月によって発生) ===
        if random.random() < 0.7:
            Transaction.objects.create(
                date=_safe_date(y, m, random.randint(5, 25)),
                account=accounts['現金'] if random.random() < 0.5 else accounts['クレジットカード'],
                category=categories['医療費'],
                amount=random.randint(1_500, 6_500),
                description=random.choice([
                    '〇〇クリニック', '△△内科', '□□小児科',
                    '☆☆歯科', '〇〇薬局', '◇◇薬局',
                ]),
            )

        # === 衣料・美容 (季節要素、月 0-2 件) ===
        if random.random() < 0.5:
            Transaction.objects.create(
                date=_safe_date(y, m, random.randint(7, 27)),
                account=accounts['クレジットカード'],
                category=categories['衣料・美容'],
                amount=random.randint(3_500, 12_000),
                description=random.choice(['衣料品店', '美容院', 'コスメ']),
            )

        # === 交際費 (月 1 件程度) ===
        if random.random() < 0.6:
            Transaction.objects.create(
                date=_safe_date(y, m, random.randint(5, 28)),
                account=accounts['クレジットカード'],
                category=categories['交際費'],
                amount=random.randint(2_000, 8_000),
                description=random.choice(['ギフト', '飲み会', 'お祝い']),
            )

        # === 教育費 (月により) ===
        if m == 4:
            # 4 月: 入学・新学期
            Transaction.objects.create(
                date=_safe_date(y, m, 5),
                account=accounts['普通預金'],
                category=categories['教育費'],
                amount=80_000,
                description='教材・学用品',
            )
        Transaction.objects.create(
            date=_safe_date(y, m, 6),
            account=accounts['普通預金'],
            category=categories['教育費'],
            amount=22_000,
            description='習い事月謝',
        )

        # === 税金 ===
        if m == 5:
            Transaction.objects.create(
                date=_safe_date(y, m, 18),
                account=accounts['普通預金'],
                category=categories['税金'],
                amount=80_000,
                description='固定資産税',
            )
            Transaction.objects.create(
                date=_safe_date(y, m, 28),
                account=accounts['普通預金'],
                category=categories['税金'],
                amount=39_500,
                description='自動車税',
            )

        # === ふるさと納税 (10-12 月: 寄附金控除レポート検証用) ===
        if m in (10, 11, 12):
            count = 1 if m != 12 else 2
            for i in range(count):
                Transaction.objects.create(
                    date=_safe_date(y, m, random.randint(5, 28)),
                    account=accounts['クレジットカード'],
                    category=categories['ふるさと納税'],
                    amount=random.choice([10_000, 15_000, 20_000, 30_000]),
                    description=random.choice([
                        '◇◇市 ふるさと納税 (返礼品: 米)',
                        '△△町 ふるさと納税 (返礼品: 果物)',
                        '〇〇村 ふるさと納税 (返礼品: 肉)',
                        '□□市 ふるさと納税 (返礼品: 魚介)',
                    ]),
                )

        # === 金利・手数料 (月 1 件、小額) ===
        if random.random() < 0.3:
            Transaction.objects.create(
                date=_safe_date(y, m, 27),
                account=accounts['普通預金'],
                category=categories['金利・手数料'],
                amount=random.randint(220, 880),
                description='ATM 手数料',
            )

    # ----- transfers ----------------------------------------------------

    def _create_transfers(
        self,
        accounts: dict[str, Account],
        years_full: list[int],
        current_year: int,
        current_month: int,
    ):
        def add_for(y, m):
            # クレジット引落 (前月分)
            Transfer.objects.create(
                date=_safe_date(y, m, 27),
                from_account=accounts['普通預金'],
                to_account=accounts['クレジットカード'],
                amount=random.randint(40_000, 75_000),
                description='クレジットカード引落',
            )
            # 積立貯蓄
            Transfer.objects.create(
                date=_safe_date(y, m, 25),
                from_account=accounts['普通預金'],
                to_account=accounts['貯蓄預金'],
                amount=50_000,
                description='積立貯蓄',
            )

        for y in years_full:
            for m in range(1, 13):
                add_for(y, m)
        for m in range(1, current_month + 1):
            add_for(current_year, m)

    # ----- budgets ------------------------------------------------------

    def _create_section_budgets(self):
        today = date.today()
        # 当月 + 前月の予算（履歴感）
        for offset in [0, -1]:
            y = today.year
            m = today.month + offset
            if m <= 0:
                y -= 1
                m += 12
            month_start = date(y, m, 1)
            for section, amount in [
                (Category.Section.HOUSING, 130_000),
                (Category.Section.UTILITY, 30_000),
                (Category.Section.FOOD_DAILY, 60_000),
                (Category.Section.DINING_OUT, 15_000),
                (Category.Section.TRANSPORT, 12_000),
                (Category.Section.MEDICAL, 12_000),
                (Category.Section.EDU_LEISURE, 40_000),
                (Category.Section.APPAREL_BEAUTY, 12_000),
                (Category.Section.SOCIAL, 10_000),
                (Category.Section.INSURANCE_TAX, 25_000),
            ]:
                SectionBudget.objects.update_or_create(
                    month=month_start,
                    section=section,
                    defaults={'amount': amount},
                )

    # ----- 医療費控除明細 (v1.16.0) -----------------------------------

    def _create_medical_expenses(self, years: list[int]):
        """前々年・前年それぞれに 10-12 件の医療費明細を生成。"""
        patients = ['本人', '配偶者', '子A', '子B']
        providers_treatment = [
            '〇〇クリニック', '△△内科', '□□小児科', '☆☆歯科クリニック',
            '◎◎眼科', '△△整形外科', '〇〇皮膚科',
        ]
        providers_medicine = ['◇◇薬局', '〇〇薬局', '△△ドラッグ']
        providers_other = ['交通費 (通院 〇〇クリニック往復)', '交通費 (通院 △△内科)']

        for y in years:
            # 治療系 (6-8 件)
            for _ in range(random.randint(6, 8)):
                MedicalExpense.objects.create(
                    paid_date=date(y, random.randint(1, 12), random.randint(5, 28)),
                    patient=random.choice(patients),
                    provider=random.choice(providers_treatment),
                    category=MedicalExpense.MedicalCategory.TREATMENT,
                    amount=random.randint(2_500, 12_000),
                    reimbursement=0,
                    notes=random.choice(['', '風邪', '健診結果の精密検査', '虫歯治療', '定期検診']),
                )
            # 医薬品 (3-4 件)
            for _ in range(random.randint(3, 4)):
                MedicalExpense.objects.create(
                    paid_date=date(y, random.randint(1, 12), random.randint(5, 28)),
                    patient=random.choice(patients),
                    provider=random.choice(providers_medicine),
                    category=MedicalExpense.MedicalCategory.MEDICINE,
                    amount=random.randint(1_200, 4_500),
                    reimbursement=0,
                    notes='処方薬',
                )
            # 通院交通費 (1-2 件、その他区分)
            for _ in range(random.randint(1, 2)):
                MedicalExpense.objects.create(
                    paid_date=date(y, random.randint(1, 12), random.randint(5, 28)),
                    patient=random.choice(patients),
                    provider=random.choice(providers_other),
                    category=MedicalExpense.MedicalCategory.OTHER,
                    amount=random.randint(800, 3_000),
                    reimbursement=0,
                    notes='通院交通費 (公共交通機関)',
                )
            # 補填つき (出産育児一時金 / 高額療養費 / 保険組合補填) を 1 件混ぜる
            if random.random() < 0.5:
                amt = random.randint(80_000, 200_000)
                MedicalExpense.objects.create(
                    paid_date=date(y, random.randint(4, 10), random.randint(5, 28)),
                    patient=random.choice(['本人', '配偶者']),
                    provider='〇〇総合病院',
                    category=MedicalExpense.MedicalCategory.TREATMENT,
                    amount=amt,
                    reimbursement=amt // 2,
                    notes='保険組合補填あり',
                )

    # ----- 保険料控除 (v1.17.0) ------------------------------------------

    def _create_insurance_premiums(self, years: list[int]):
        """各年 4 件 (一般生命 + 介護医療 + 個人年金 + 地震) を生成。"""
        for y in years:
            InsurancePremium.objects.create(
                year=y,
                category=InsurancePremium.InsuranceCategory.LIFE_GENERAL,
                contract_type=InsurancePremium.ContractType.NEW,
                insurer='〇〇生命',
                policy_number='A-1234567',
                annual_amount=96_000,
                submitted_in_year_end_adjustment=False,
            )
            InsurancePremium.objects.create(
                year=y,
                category=InsurancePremium.InsuranceCategory.LIFE_CARE_MEDICAL,
                contract_type=InsurancePremium.ContractType.NEW,
                insurer='△△生命',
                policy_number='B-2345678',
                annual_amount=48_000,
                submitted_in_year_end_adjustment=False,
            )
            InsurancePremium.objects.create(
                year=y,
                category=InsurancePremium.InsuranceCategory.LIFE_ANNUITY,
                contract_type=InsurancePremium.ContractType.OLD,
                insurer='◇◇共済',
                policy_number='C-3456789',
                annual_amount=80_000,
                submitted_in_year_end_adjustment=False,
            )
            InsurancePremium.objects.create(
                year=y,
                category=InsurancePremium.InsuranceCategory.EARTHQUAKE,
                contract_type=InsurancePremium.ContractType.NEW,
                insurer='□□損保',
                policy_number='D-4567890',
                annual_amount=32_000,
                submitted_in_year_end_adjustment=False,
            )

    # ----- 年次総所得 ---------------------------------------------------

    def _create_income_snapshots(self, years: list[int]):
        base_income = 4_300_000
        for i, y in enumerate(sorted(years)):
            AnnualIncomeSnapshot.objects.update_or_create(
                year=y,
                defaults={
                    'gross_income': base_income + (i * 100_000),
                    'notes': 'デモ用サンプル（源泉徴収票の「給与所得控除後の金額」想定）',
                },
            )