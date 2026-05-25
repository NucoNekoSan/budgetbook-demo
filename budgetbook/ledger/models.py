import hashlib
import json

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.conf import settings
from django.db import models


def normalize_master_name(value: str) -> str:
    return ' '.join((value or '').strip().casefold().split())


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField('作成日時', auto_now_add=True)
    updated_at = models.DateTimeField('更新日時', auto_now=True)

    class Meta:
        abstract = True


class Account(TimeStampedModel):
    class Kind(models.TextChoices):
        """会計区分。
        - ASSET: 資産（現金・銀行・電子マネーなど、自分の財産）
        - LIABILITY: 負債（クレジットカード未払い・ローンなど、将来の支払義務）
        個人 B/S では「資産 − 負債 = 正味財産」となる。
        """
        ASSET = 'asset', '資産'
        LIABILITY = 'liability', '負債'

    name = models.CharField('口座名', max_length=100, unique=True)
    kind = models.CharField(
        '会計区分',
        max_length=10,
        choices=Kind.choices,
        default=Kind.ASSET,
        db_index=True,
    )
    opening_balance = models.IntegerField(
        '初期残高',
        default=0,
        # 負債口座は負の値を許容するため、kind=asset でのみ正値制約を効かせる
    )
    is_active = models.BooleanField('有効', default=True)
    notes = models.TextField('メモ', blank=True)

    class Meta:
        verbose_name = '口座'
        verbose_name_plural = '口座'
        ordering = ['name']

    def __str__(self) -> str:
        return self.name

    def clean(self) -> None:
        super().clean()
        # 資産口座の初期残高は 0 以上 (現金がマイナスはあり得ない)
        if self.kind == self.Kind.ASSET and self.opening_balance < 0:
            raise ValidationError({
                'opening_balance': '資産口座の初期残高は 0 以上で入力してください。',
            })
        if not self.pk:
            return
        original = type(self).objects.filter(pk=self.pk).values('opening_balance').first()
        if (
            original
            and original['opening_balance'] != self.opening_balance
            and MonthlyClosing.objects.exists()
        ):
            raise ValidationError({
                'opening_balance': '月次締めが存在するため、初期残高は変更できません。',
            })

    def save(self, *args, **kwargs):
        update_fields = kwargs.get('update_fields')
        if update_fields is None or 'opening_balance' in update_fields:
            self.full_clean()
        super().save(*args, **kwargs)


class LoanProfile(TimeStampedModel):
    """負債口座（kind=LIABILITY）の付帯情報。

    自動計算はしない。利率・月次返済額・引落日などを記録専用フィールドで持ち、
    B/S 画面で「年間想定利息」を表示するために使う。
    Account との関係は OneToOne。なくても動く（任意）。
    """

    class Method(models.TextChoices):
        REVOLVING = 'revolving', 'リボ払い'
        EQUAL_PRINCIPAL_INTEREST = 'eq_pi', '元利均等'
        EQUAL_PRINCIPAL = 'eq_p', '元金均等'
        FIXED_MONTHLY = 'fixed', '定額分割'
        OTHER = 'other', 'その他'

    account = models.OneToOneField(
        'Account',
        on_delete=models.CASCADE,
        related_name='loan_profile',
        verbose_name='負債口座',
    )
    annual_rate_bp = models.IntegerField(
        '年利 (bp)',
        default=0,
        help_text='basis point で入力。15.00% なら 1500、0.5% なら 50。',
    )
    method = models.CharField(
        '返済方式',
        max_length=20,
        choices=Method.choices,
        default=Method.OTHER,
    )
    monthly_payment = models.IntegerField(
        '月次返済額（目安）',
        default=0,
        help_text='実額が変動する場合は目安値で OK。0 なら未設定として扱う。',
    )
    payment_day = models.IntegerField(
        '引落日',
        default=0,
        help_text='1〜31 の範囲。0 は未設定。',
    )
    payoff_date = models.DateField('完済予定日', null=True, blank=True)
    source_account = models.ForeignKey(
        'Account',
        on_delete=models.SET_NULL,
        related_name='loan_payments_from',
        null=True,
        blank=True,
        verbose_name='引落元口座',
        help_text='毎月の返済を自動生成する場合に指定。資産口座のみ。',
    )
    notes = models.TextField('備考', blank=True, help_text='契約日・引落口座・契約番号など。')

    class Meta:
        verbose_name = '負債プロファイル'
        verbose_name_plural = '負債プロファイル'

    def __str__(self) -> str:
        return f'{self.account.name} ローン情報'

    def clean(self) -> None:
        super().clean()
        if self.account_id and self.account.kind != Account.Kind.LIABILITY:
            raise ValidationError({
                'account': 'LoanProfile は負債口座にのみ登録できます。',
            })
        if self.annual_rate_bp < 0:
            raise ValidationError({'annual_rate_bp': '年利は 0 以上で入力してください。'})
        if self.payment_day < 0 or self.payment_day > 31:
            raise ValidationError({'payment_day': '引落日は 0〜31 の範囲で入力してください。'})
        if self.source_account_id and self.source_account.kind != Account.Kind.ASSET:
            raise ValidationError({
                'source_account': '引落元口座は資産口座を指定してください。',
            })

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    @property
    def annual_rate_pct(self) -> float:
        """年利を % で返す（例: 1500bp → 15.0）。"""
        return self.annual_rate_bp / 100.0


class Category(TimeStampedModel):
    class Kind(models.TextChoices):
        INCOME = 'income', '収入'
        EXPENSE = 'expense', '支出'

    class Section(models.TextChoices):
        """支出の大分類（家計簿の標準区分）。kind=income の場合は OTHER 推奨。"""
        FOOD_DAILY = 'food_daily', '食品・日用品'
        DINING_OUT = 'dining_out', '外食'
        HOUSING = 'housing', '住居費'
        HOUSING_MISC = 'housing_misc', '住居関連'
        UTILITY = 'utility', '光熱・通信'
        TRANSPORT = 'transport', '交通'
        MEDICAL = 'medical', '医療・健康'
        EDU_LEISURE = 'edu_leisure', '教養・娯楽'
        APPAREL_BEAUTY = 'apparel_beauty', '衣料・美容'
        SOCIAL = 'social', '交際・贈答'
        INSURANCE_TAX = 'insurance_tax', '保険・税'
        SAVING_INVEST = 'saving_invest', '貯蓄・投資'
        OTHER = 'other', 'その他'

    class TaxTag(models.TextChoices):
        """確定申告連携用の控除タグ。年末に集計レポート出力に使う。"""
        NONE = 'none', '対象外'
        MEDICAL = 'medical', '医療費控除'
        DONATION = 'donation', '寄附金（ふるさと納税等）'
        BUSINESS = 'business', '事業経費'
        OTHER_DEDUCTIBLE = 'other', 'その他控除'

    name = models.CharField('カテゴリ名', max_length=100, unique=True)
    kind = models.CharField('区分', max_length=10, choices=Kind.choices)
    section = models.CharField(
        '大分類',
        max_length=20,
        choices=Section.choices,
        default=Section.OTHER,
        db_index=True,
    )
    tax_tag = models.CharField(
        '税控除タグ',
        max_length=20,
        choices=TaxTag.choices,
        default=TaxTag.NONE,
        db_index=True,
    )
    is_active = models.BooleanField('有効', default=True)
    notes = models.TextField('メモ', blank=True)

    class Meta:
        verbose_name = 'カテゴリ'
        verbose_name_plural = 'カテゴリ'
        ordering = ['kind', 'name']

    def __str__(self) -> str:
        return f'{self.get_kind_display()} | {self.name}'

    def clean(self) -> None:
        super().clean()
        if not self.pk:
            return
        original = type(self).objects.filter(pk=self.pk).values('kind').first()
        if (
            original
            and original['kind'] != self.kind
            and Transaction.objects.filter(category_id=self.pk).exists()
        ):
            raise ValidationError({
                'kind': '使用済みカテゴリの区分は変更できません。新カテゴリを作成し、必要な取引を再分類してください。',
            })

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class CategoryChangeLog(TimeStampedModel):
    class Action(models.TextChoices):
        UPDATE = 'update', 'カテゴリ編集'
        RECLASSIFY = 'reclassify', '取引再分類'
        DEACTIVATE = 'deactivate', '無効化'
        REACTIVATE = 'reactivate', '有効化'

    category = models.ForeignKey(
        Category,
        on_delete=models.PROTECT,
        related_name='change_logs',
        verbose_name='対象カテゴリ',
    )
    action = models.CharField('操作', max_length=20, choices=Action.choices, db_index=True)
    before = models.JSONField('変更前', default=dict, blank=True)
    after = models.JSONField('変更後', default=dict, blank=True)
    affected_transaction_count = models.PositiveIntegerField('対象取引数', default=0)
    includes_closed_month = models.BooleanField('締め済み月を含む', default=False)
    reason = models.TextField('理由', blank=True)
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name='操作ユーザー',
    )

    class Meta:
        verbose_name = 'カテゴリ変更履歴'
        verbose_name_plural = 'カテゴリ変更履歴'
        ordering = ['-created_at', '-id']
        indexes = [
            models.Index(fields=['action']),
            models.Index(fields=['created_at']),
        ]

    def __str__(self) -> str:
        return f'{self.created_at:%Y-%m-%d %H:%M:%S} {self.get_action_display()} {self.category.name}'


class Payee(TimeStampedModel):
    name = models.CharField('支払先名', max_length=120, unique=True)
    normalized_name = models.CharField('正規化支払先名', max_length=120, unique=True, editable=False)
    is_active = models.BooleanField('有効', default=True)
    notes = models.TextField('メモ', blank=True)

    class Meta:
        verbose_name = '支払先'
        verbose_name_plural = '支払先'
        ordering = ['name']

    def __str__(self) -> str:
        return self.name

    def clean(self) -> None:
        super().clean()
        self.normalized_name = normalize_master_name(self.name)
        if not self.normalized_name:
            raise ValidationError({'name': '支払先名を入力してください。'})
        alias_qs = PayeeAlias.objects.filter(normalized_alias=self.normalized_name)
        if self.pk:
            alias_qs = alias_qs.exclude(payee_id=self.pk)
        if alias_qs.exists():
            raise ValidationError({'name': '同じ表記が支払先別名として既に使われています。'})

    def save(self, *args, **kwargs):
        self.normalized_name = normalize_master_name(self.name)
        self.full_clean()
        super().save(*args, **kwargs)


class PayeeAlias(TimeStampedModel):
    payee = models.ForeignKey(
        Payee,
        on_delete=models.CASCADE,
        related_name='aliases',
        verbose_name='支払先',
    )
    alias = models.CharField('別名', max_length=120)
    normalized_alias = models.CharField('正規化別名', max_length=120, unique=True, editable=False)

    class Meta:
        verbose_name = '支払先別名'
        verbose_name_plural = '支払先別名'
        ordering = ['alias']

    def __str__(self) -> str:
        return f'{self.alias} → {self.payee.name}'

    def clean(self) -> None:
        super().clean()
        self.normalized_alias = normalize_master_name(self.alias)
        if not self.normalized_alias:
            raise ValidationError({'alias': '別名を入力してください。'})
        if self.payee_id and self.payee.normalized_name == self.normalized_alias:
            raise ValidationError({'alias': '支払先名と同じ別名は登録できません。'})
        payee_qs = Payee.objects.filter(normalized_name=self.normalized_alias)
        if self.payee_id:
            payee_qs = payee_qs.exclude(pk=self.payee_id)
        if payee_qs.exists():
            raise ValidationError({'alias': '同じ表記が支払先名として既に使われています。'})

    def save(self, *args, **kwargs):
        self.normalized_alias = normalize_master_name(self.alias)
        self.full_clean()
        super().save(*args, **kwargs)


class PaymentMethod(TimeStampedModel):
    class Kind(models.TextChoices):
        CASH = 'cash', '現金'
        BANK = 'bank', '銀行口座'
        CREDIT_CARD = 'credit_card', 'クレジットカード'
        DEBIT_CARD = 'debit_card', 'デビットカード'
        ELECTRONIC_MONEY = 'electronic_money', '電子マネー'
        QR = 'qr', 'QR決済'
        OTHER = 'other', 'その他'

    name = models.CharField('支払手段名', max_length=100, unique=True)
    kind = models.CharField('種別', max_length=30, choices=Kind.choices, db_index=True)
    account = models.ForeignKey(
        Account,
        on_delete=models.PROTECT,
        related_name='payment_methods',
        null=True,
        blank=True,
        verbose_name='通常利用口座',
        help_text='この支払手段で通常残高が動く口座。クレジットカードなら負債口座。',
    )
    settlement_account = models.ForeignKey(
        Account,
        on_delete=models.PROTECT,
        related_name='settlement_payment_methods',
        null=True,
        blank=True,
        verbose_name='引落元口座',
        help_text='クレジットカード等の引落元となる資産口座。',
    )
    closing_day = models.PositiveSmallIntegerField('締日', default=0)
    settlement_day = models.PositiveSmallIntegerField('引落日', default=0)
    is_active = models.BooleanField('有効', default=True)
    notes = models.TextField('メモ', blank=True)

    class Meta:
        verbose_name = '支払手段'
        verbose_name_plural = '支払手段'
        ordering = ['name']

    def __str__(self) -> str:
        return self.name

    def clean(self) -> None:
        super().clean()
        errors = {}
        if self.closing_day < 0 or self.closing_day > 31:
            errors['closing_day'] = '締日は 0〜31 の範囲で入力してください。'
        if self.settlement_day < 0 or self.settlement_day > 31:
            errors['settlement_day'] = '引落日は 0〜31 の範囲で入力してください。'
        if self.settlement_account_id and self.settlement_account.kind != Account.Kind.ASSET:
            errors['settlement_account'] = '引落元口座は資産口座を指定してください。'
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class Transaction(TimeStampedModel):
    date = models.DateField('日付')
    account = models.ForeignKey(Account, on_delete=models.PROTECT, verbose_name='口座')
    category = models.ForeignKey(Category, on_delete=models.PROTECT, verbose_name='カテゴリ')
    payee = models.ForeignKey(
        Payee,
        on_delete=models.PROTECT,
        related_name='transactions',
        null=True,
        blank=True,
        verbose_name='支払先',
    )
    payment_method = models.ForeignKey(
        PaymentMethod,
        on_delete=models.PROTECT,
        related_name='transactions',
        null=True,
        blank=True,
        verbose_name='支払手段',
    )
    amount = models.IntegerField(
        '金額',
        validators=[MinValueValidator(1)],
    )
    description = models.CharField('摘要', max_length=120)
    memo = models.TextField('メモ', blank=True)

    class Meta:
        verbose_name = '取引'
        verbose_name_plural = '取引'
        ordering = ['-date', '-id']
        indexes = [
            models.Index(fields=['date', 'id'], name='ledger_tx_date_id_idx'),
            models.Index(fields=['account', 'date'], name='ledger_tx_acct_date_idx'),
            models.Index(fields=['category', 'date'], name='ledger_tx_cat_date_idx'),
            models.Index(fields=['payee', 'date'], name='ledger_tx_payee_date_idx'),
            models.Index(fields=['payment_method', 'date'], name='ledger_tx_pm_date_idx'),
        ]

    def __str__(self) -> str:
        return f'{self.date} {self.description} {self.amount}'

    @property
    def kind(self) -> str:
        return self.category.kind


class Transfer(TimeStampedModel):
    date = models.DateField('日付')
    from_account = models.ForeignKey(
        Account,
        on_delete=models.PROTECT,
        related_name='transfers_out',
        verbose_name='出金元口座',
    )
    to_account = models.ForeignKey(
        Account,
        on_delete=models.PROTECT,
        related_name='transfers_in',
        verbose_name='入金先口座',
    )
    amount = models.IntegerField(
        '金額',
        validators=[MinValueValidator(1)],
    )
    description = models.CharField('摘要', max_length=120)
    memo = models.TextField('メモ', blank=True)

    class Meta:
        verbose_name = '振替'
        verbose_name_plural = '振替'
        ordering = ['-date', '-id']
        indexes = [
            models.Index(fields=['date', 'id'], name='ledger_transfer_date_id_idx'),
            models.Index(fields=['from_account', 'date'], name='ledger_transfer_from_date_idx'),
            models.Index(fields=['to_account', 'date'], name='ledger_transfer_to_date_idx'),
        ]

    def __str__(self) -> str:
        return f'{self.date} {self.description} {self.amount}'

    def clean(self) -> None:
        super().clean()
        if self.from_account_id and self.to_account_id and self.from_account_id == self.to_account_id:
            raise ValidationError({
                'to_account': '出金元口座と入金先口座は別の口座を指定してください。',
            })

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class MonthlyClosing(models.Model):
    month = models.DateField('対象月', unique=True)
    closed_at = models.DateTimeField('締め日時', auto_now_add=True)
    closed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name='締め処理者',
    )
    opening_carry = models.IntegerField('月初繰越')
    income = models.IntegerField('収入')
    expense = models.IntegerField('支出')
    net = models.IntegerField('当月収支')
    closing_balance = models.IntegerField('月末残高')
    account_balances = models.JSONField('口座別残高スナップショット', blank=True)
    notes = models.TextField('メモ', blank=True)

    class Meta:
        verbose_name = '月次締め'
        verbose_name_plural = '月次締め'
        ordering = ['-month']

    def __str__(self) -> str:
        return f'{self.month:%Y-%m} 月次締め'

    def clean(self) -> None:
        super().clean()
        if self.month and self.month.day != 1:
            raise ValidationError({'month': '対象月は月初日を指定してください。'})

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class AccountReconciliation(TimeStampedModel):
    account = models.ForeignKey(Account, on_delete=models.PROTECT, verbose_name='口座')
    reconciled_on = models.DateField('照合日')
    book_balance = models.IntegerField('帳簿残高')
    actual_balance = models.IntegerField('実残高')
    difference = models.IntegerField('差額')
    notes = models.TextField('メモ', blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name='登録者',
    )

    class Meta:
        verbose_name = '口座残高照合'
        verbose_name_plural = '口座残高照合'
        ordering = ['-reconciled_on', 'account__name']
        indexes = [
            models.Index(fields=['-reconciled_on', 'account'], name='ledger_recon_date_acct_idx'),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['account', 'reconciled_on'],
                name='unique_reconciliation_account_date',
            ),
        ]

    def __str__(self) -> str:
        return f'{self.reconciled_on} {self.account.name} 照合'

    def save(self, *args, **kwargs):
        self.difference = self.actual_balance - self.book_balance
        super().save(*args, **kwargs)


class AuditLog(models.Model):
    class Action(models.TextChoices):
        CREATE = 'create', '作成'
        UPDATE = 'update', '更新'
        DELETE = 'delete', '削除'
        DEACTIVATE = 'deactivate', '無効化'
        CLOSE = 'close', '締め'
        RECONCILE = 'reconcile', '照合'

    created_at = models.DateTimeField('記録日時', auto_now_add=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name='操作ユーザー',
    )
    action = models.CharField('操作', max_length=20, choices=Action.choices)
    target_model = models.CharField('対象モデル', max_length=80)
    target_id = models.CharField('対象ID', max_length=80, blank=True)
    target_repr = models.CharField('対象表示名', max_length=200)
    summary = models.CharField('概要', max_length=200, blank=True)
    metadata = models.JSONField('補足情報', default=dict, blank=True)
    prev_hash = models.CharField('前監査ログハッシュ', max_length=64, blank=True, editable=False)
    row_hash = models.CharField('監査ログハッシュ', max_length=64, blank=True, editable=False, db_index=True)

    class Meta:
        verbose_name = '監査ログ'
        verbose_name_plural = '監査ログ'
        ordering = ['-created_at', '-id']
        indexes = [
            models.Index(fields=['created_at']),
            models.Index(fields=['target_model', 'target_id']),
            models.Index(fields=['action']),
        ]

    def __str__(self) -> str:
        return f'{self.created_at:%Y-%m-%d %H:%M:%S} {self.get_action_display()} {self.target_model}#{self.target_id}'

    def hash_payload(self) -> dict:
        return {
            'created_at': self.created_at.isoformat() if self.created_at else '',
            'user_id': self.user_id,
            'action': self.action,
            'target_model': self.target_model,
            'target_id': self.target_id,
            'target_repr': self.target_repr,
            'summary': self.summary,
            'metadata': self.metadata,
            'prev_hash': self.prev_hash,
        }

    def compute_row_hash(self) -> str:
        payload = json.dumps(
            self.hash_payload(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(',', ':'),
            default=str,
        )
        return hashlib.sha256(payload.encode('utf-8')).hexdigest()

    def save(self, *args, **kwargs):
        is_new = self._state.adding
        if is_new and not self.prev_hash:
            previous = type(self).objects.exclude(row_hash='').order_by('-id').only('row_hash').first()
            self.prev_hash = previous.row_hash if previous else ''
        super().save(*args, **kwargs)
        if is_new and not self.row_hash:
            self.row_hash = self.compute_row_hash()
            type(self).objects.filter(pk=self.pk).update(
                prev_hash=self.prev_hash,
                row_hash=self.row_hash,
            )


class SectionBudget(TimeStampedModel):
    """大分類 (Category.Section) 単位の月次予算。

    - 月 (month): YYYY-MM-01 で保持
    - section: Category.Section の値
    - amount: 円整数

    粒度: section 単位。category ごとの細かい予算管理は持たない。
    家計診断は「食品・日用品 ¥X / 住居 ¥Y」のレベルで十分という設計判断。
    """
    month = models.DateField('対象月', db_index=True)
    section = models.CharField(
        '大分類',
        max_length=20,
        choices=Category.Section.choices,
        db_index=True,
    )
    amount = models.IntegerField('予算額', validators=[MinValueValidator(0)])
    notes = models.TextField('メモ', blank=True)

    class Meta:
        verbose_name = '月次予算（大分類）'
        verbose_name_plural = '月次予算（大分類）'
        ordering = ['-month', 'section']
        constraints = [
            models.UniqueConstraint(
                fields=['month', 'section'],
                name='unique_section_budget_month',
            ),
        ]

    def __str__(self) -> str:
        return f'{self.month:%Y-%m} {self.get_section_display()} ¥{self.amount:,}'

    def clean(self) -> None:
        super().clean()
        if self.month and self.month.day != 1:
            raise ValidationError({'month': '対象月は月初日を指定してください。'})

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class ExpenseGroup(TimeStampedModel):
    name = models.CharField('グループ名', max_length=100, unique=True)
    is_active = models.BooleanField('有効', default=True)
    sort_order = models.IntegerField('表示順', default=0)
    notes = models.TextField('メモ', blank=True)

    class Meta:
        verbose_name = '支出カテゴリグループ'
        verbose_name_plural = '支出カテゴリグループ'
        ordering = ['sort_order', 'name']

    def __str__(self) -> str:
        return self.name


class ExpenseGroupCategory(TimeStampedModel):
    group = models.ForeignKey(
        ExpenseGroup,
        on_delete=models.CASCADE,
        related_name='memberships',
        verbose_name='グループ',
    )
    category = models.OneToOneField(
        Category,
        on_delete=models.CASCADE,
        related_name='expense_group_membership',
        verbose_name='カテゴリ',
    )

    class Meta:
        verbose_name = 'グループ所属カテゴリ'
        verbose_name_plural = 'グループ所属カテゴリ'
        ordering = ['group__sort_order', 'category__name']

    def __str__(self) -> str:
        return f'{self.group.name} | {self.category.name}'

    def clean(self) -> None:
        super().clean()
        if self.category_id and self.category.kind != Category.Kind.EXPENSE:
            raise ValidationError({
                'category': 'グループには支出カテゴリのみ登録できます。',
            })

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class MedicalExpense(TimeStampedModel):
    """医療費控除明細（v1.16.0）。

    Transaction とは独立のテーブル。家計簿に載った医療費は nullable FK で紐付け、
    家計簿に載らない医療費（保険組合事後請求等）は transaction=NULL で登録する。
    国税庁「医療費控除の明細書」様式に準拠した区分・列構成。
    """

    class MedicalCategory(models.TextChoices):
        TREATMENT = 'treatment', '診療・治療（病院・歯科）'
        MEDICINE = 'medicine', '医薬品（処方薬・市販薬）'
        CARE_INSURANCE = 'care_insurance', '介護保険サービス'
        OTHER = 'other', 'その他（通院交通費 等）'

    transaction = models.ForeignKey(
        'Transaction',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='medical_expense_set',
        verbose_name='紐付け取引',
    )
    paid_date = models.DateField('支払日', db_index=True)
    patient = models.CharField('受診者', max_length=50)
    provider = models.CharField('医療機関・薬局名', max_length=120)
    category = models.CharField(
        '区分',
        max_length=20,
        choices=MedicalCategory.choices,
        db_index=True,
    )
    amount = models.IntegerField(
        '支払額',
        validators=[MinValueValidator(1)],
    )
    reimbursement = models.IntegerField(
        '補填額',
        default=0,
        validators=[MinValueValidator(0)],
        help_text='保険金・出産育児一時金・高額療養費等で補填された金額',
    )
    notes = models.TextField('メモ', blank=True)

    class Meta:
        verbose_name = '医療費'
        verbose_name_plural = '医療費'
        ordering = ['-paid_date', '-id']
        constraints = [
            models.UniqueConstraint(
                fields=['transaction'],
                condition=models.Q(transaction__isnull=False),
                name='uniq_medical_expense_per_transaction',
            ),
        ]

    def __str__(self) -> str:
        return f'{self.paid_date} {self.patient} {self.provider} {self.amount}'

    @property
    def net_amount(self) -> int:
        return self.amount - self.reimbursement

    def clean(self) -> None:
        super().clean()
        if self.reimbursement is not None and self.amount is not None:
            if self.reimbursement > self.amount:
                raise ValidationError({
                    'reimbursement': '補填額は支払額以下で入力してください。',
                })
        if self.transaction_id:
            tx = self.transaction
            if tx.category.tax_tag != Category.TaxTag.MEDICAL:
                raise ValidationError({
                    'transaction': '紐付け先取引のカテゴリは「医療費控除」タグである必要があります。',
                })
            if tx.amount != self.amount:
                raise ValidationError({
                    'amount': '紐付け取引の金額と支払額が一致していません。',
                })
            if tx.date != self.paid_date:
                raise ValidationError({
                    'paid_date': '紐付け取引の日付と支払日が一致していません。',
                })

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class AnnualIncomeSnapshot(TimeStampedModel):
    """年次総所得スナップショット（v1.16.0）。

    医療費控除額計算で使用する「総所得金額」を年単位で保存する。
    源泉徴収票の「給与所得控除後の金額」欄を入力する想定。
    """

    year = models.PositiveIntegerField('対象年', unique=True, db_index=True)
    gross_income = models.IntegerField(
        '総所得金額',
        validators=[MinValueValidator(0)],
        help_text='給与所得控除後の金額（源泉徴収票の該当欄）',
    )
    notes = models.TextField('メモ', blank=True)

    class Meta:
        verbose_name = '年次所得スナップショット'
        verbose_name_plural = '年次所得スナップショット'
        ordering = ['-year']

    def __str__(self) -> str:
        return f'{self.year} 年: ¥{self.gross_income:,}'

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class InsurancePremium(TimeStampedModel):
    """保険料控除明細（v1.17.0）。

    保険会社から届く「生命保険料控除証明書」「地震保険料控除証明書」の数値を
    年単位で記録し、国税庁公式式で控除額を自動計算する。

    Transaction とは紐付けない（保険料の引落取引は年払い/前納で総額一致しない）。
    """

    class InsuranceCategory(models.TextChoices):
        LIFE_GENERAL = 'life_general', '一般生命保険料'
        LIFE_CARE_MEDICAL = 'life_care_medical', '介護医療保険料'
        LIFE_ANNUITY = 'life_annuity', '個人年金保険料'
        EARTHQUAKE = 'earthquake', '地震保険料'

    class ContractType(models.TextChoices):
        NEW = 'new', '新契約（2012/1/1 以降）'
        OLD = 'old', '旧契約（2011/12/31 以前）'

    year = models.PositiveIntegerField('対象年', db_index=True)
    category = models.CharField(
        '区分',
        max_length=20,
        choices=InsuranceCategory.choices,
        db_index=True,
    )
    contract_type = models.CharField(
        '契約区分',
        max_length=10,
        choices=ContractType.choices,
        default=ContractType.NEW,
    )
    insurer = models.CharField('保険会社名', max_length=120)
    policy_number = models.CharField(
        '証券番号',
        max_length=60,
        blank=True,
        help_text='控除証明書の証券番号（任意、本人識別用）',
    )
    annual_amount = models.IntegerField(
        '年間支払保険料',
        validators=[MinValueValidator(1)],
        help_text='控除証明書の「申告額」または「年間払込予定額」',
    )
    submitted_in_year_end_adjustment = models.BooleanField(
        '年末調整で提出済',
        default=False,
        help_text='ON にすると確定申告レポートでは除外される',
    )
    notes = models.TextField('メモ', blank=True)

    class Meta:
        verbose_name = '保険料控除'
        verbose_name_plural = '保険料控除'
        ordering = ['-year', 'category', '-id']
        indexes = [
            models.Index(fields=['year', 'category']),
        ]

    def __str__(self) -> str:
        return f'{self.year} {self.get_category_display()} {self.insurer} ¥{self.annual_amount:,}'

    def clean(self) -> None:
        super().clean()
        # 介護医療保険料は新契約のみ存在（2012/1/1 新設）
        if (
            self.category == self.InsuranceCategory.LIFE_CARE_MEDICAL
            and self.contract_type == self.ContractType.OLD
        ):
            raise ValidationError({
                'contract_type': '介護医療保険料は新契約のみが対象です（2012/1/1 新設）。',
            })
        # 地震保険料は新旧区分の意味なし → NEW に正規化
        if self.category == self.InsuranceCategory.EARTHQUAKE:
            self.contract_type = self.ContractType.NEW

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)
