from __future__ import annotations

from datetime import date

from django import forms
from django.urls import reverse_lazy

from .models import (
    Account,
    AnnualIncomeSnapshot,
    Category,
    InsurancePremium,
    LoanProfile,
    MedicalExpense,
    MonthlyClosing,
    Transaction,
    Transfer,
)


class DateInput(forms.DateInput):
    input_type = 'date'


class TransactionForm(forms.ModelForm):
    kind = forms.ChoiceField(
        choices=Category.Kind.choices,
        label='種別',
        widget=forms.Select(attrs={
            'class': 'form-input',
            'hx-get': reverse_lazy('ledger:category_options'),
            'hx-target': '#id_category',
            'hx-swap': 'innerHTML',
            'hx-trigger': 'change',
        }),
    )

    field_order = ['date', 'account', 'kind', 'category', 'amount', 'description', 'memo']

    class Meta:
        model = Transaction
        fields = ['date', 'account', 'category', 'amount', 'description', 'memo']
        widgets = {
            'date': DateInput(attrs={'class': 'form-input', 'enterkeyhint': 'next', 'autocomplete': 'off'}),
            'account': forms.Select(attrs={'class': 'form-input'}),
            'category': forms.Select(attrs={'class': 'form-input'}),
            'amount': forms.NumberInput(attrs={
                'class': 'form-input', 'step': '1', 'min': '1',
                'inputmode': 'numeric', 'enterkeyhint': 'next', 'autocomplete': 'off',
            }),
            'description': forms.TextInput(attrs={
                'class': 'form-input', 'placeholder': '例: スーパー、給与、電気代',
                'enterkeyhint': 'next', 'autocomplete': 'off',
            }),
            'memo': forms.Textarea(attrs={
                'class': 'form-input', 'rows': 4, 'placeholder': '任意メモ',
                'enterkeyhint': 'done', 'autocomplete': 'off',
            }),
        }
        labels = {
            'date': '日付',
            'account': '口座',
            'category': 'カテゴリ',
            'amount': '金額',
            'description': '摘要',
            'memo': 'メモ',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        account_qs = Account.objects.filter(is_active=True)
        if self.instance and self.instance.pk:
            account_qs = account_qs | Account.objects.filter(pk=self.instance.account_id)
        self.fields['account'].queryset = account_qs.distinct().order_by('name')
        for field in self.fields.values():
            field.help_text = ''

        # POST データ → 既存インスタンスの種別 → デフォルト（支出）の優先順で kind を決定
        if self.data.get('kind') in Category.Kind.values:
            kind = self.data['kind']
        elif self.instance and self.instance.pk:
            kind = self.instance.category.kind
        else:
            kind = Category.Kind.EXPENSE

        self.fields['kind'].initial = kind
        category_qs = Category.objects.filter(is_active=True, kind=kind)
        if self.instance and self.instance.pk:
            category_qs = category_qs | Category.objects.filter(pk=self.instance.category_id)
        self.fields['category'].queryset = category_qs.distinct().order_by('name')

    def clean(self):
        cleaned = super().clean()
        kind = cleaned.get('kind')
        category = cleaned.get('category')
        if kind and category and category.kind != kind:
            raise forms.ValidationError(
                '種別とカテゴリが一致しません。種別を変更したときはカテゴリを再選択してください。'
            )
        return cleaned


class TransferForm(forms.ModelForm):
    class Meta:
        model = Transfer
        fields = ['date', 'from_account', 'to_account', 'amount', 'description', 'memo']
        widgets = {
            'date': DateInput(attrs={'class': 'form-input', 'enterkeyhint': 'next', 'autocomplete': 'off'}),
            'from_account': forms.Select(attrs={'class': 'form-input'}),
            'to_account': forms.Select(attrs={'class': 'form-input'}),
            'amount': forms.NumberInput(attrs={
                'class': 'form-input', 'step': '1', 'min': '1',
                'inputmode': 'numeric', 'enterkeyhint': 'next', 'autocomplete': 'off',
            }),
            'description': forms.TextInput(attrs={
                'class': 'form-input', 'placeholder': '例: 普通預金A → 普通預金B',
                'enterkeyhint': 'next', 'autocomplete': 'off',
            }),
            'memo': forms.Textarea(attrs={
                'class': 'form-input', 'rows': 4, 'placeholder': '任意メモ',
                'enterkeyhint': 'done', 'autocomplete': 'off',
            }),
        }
        labels = {
            'date': '日付',
            'from_account': '出金元口座',
            'to_account': '入金先口座',
            'amount': '金額',
            'description': '摘要',
            'memo': 'メモ',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        active_accounts = Account.objects.filter(is_active=True)
        from_accounts = active_accounts
        to_accounts = active_accounts
        if self.instance and self.instance.pk:
            from_accounts = from_accounts | Account.objects.filter(pk=self.instance.from_account_id)
            to_accounts = to_accounts | Account.objects.filter(pk=self.instance.to_account_id)
        self.fields['from_account'].queryset = from_accounts.distinct().order_by('name')
        self.fields['to_account'].queryset = to_accounts.distinct().order_by('name')
        active_accounts = active_accounts.order_by('name')
        if not self.is_bound and not self.instance.pk:
            account_ids = list(active_accounts.values_list('pk', flat=True)[:2])
            if len(account_ids) >= 2:
                self.fields['from_account'].initial = account_ids[0]
                self.fields['to_account'].initial = account_ids[1]
        for field in self.fields.values():
            field.help_text = ''

    def clean(self):
        cleaned = super().clean()
        from_account = cleaned.get('from_account')
        to_account = cleaned.get('to_account')
        if from_account and to_account and from_account == to_account:
            raise forms.ValidationError(
                '出金元口座と入金先口座は別の口座を指定してください。'
            )
        return cleaned


class MonthlyClosingForm(forms.Form):
    month = forms.DateField(
        label='対象月',
        widget=DateInput(attrs={'class': 'form-input'}),
    )
    notes = forms.CharField(
        label='メモ',
        required=False,
        widget=forms.Textarea(attrs={'class': 'form-input', 'rows': 3, 'placeholder': '任意メモ'}),
    )

    def clean_month(self):
        value = self.cleaned_data['month'].replace(day=1)
        today = date.today()
        if value > date(today.year, today.month, 1):
            raise forms.ValidationError('未来の月は締められません。当月以前を指定してください。')
        return value


class AccountReconciliationForm(forms.Form):
    account = forms.ModelChoiceField(
        label='口座',
        queryset=Account.objects.none(),
        widget=forms.Select(attrs={'class': 'form-input'}),
    )
    reconciled_on = forms.DateField(
        label='照合日',
        widget=DateInput(attrs={'class': 'form-input'}),
    )
    actual_balance = forms.IntegerField(
        label='実残高',
        widget=forms.NumberInput(attrs={'class': 'form-input', 'step': '1'}),
    )
    notes = forms.CharField(
        label='メモ',
        required=False,
        widget=forms.Textarea(attrs={'class': 'form-input', 'rows': 3, 'placeholder': '残高確認元や差額理由など'}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['account'].queryset = Account.objects.filter(is_active=True).order_by('name')


class AccountForm(forms.ModelForm):
    class Meta:
        model = Account
        fields = ['name', 'kind', 'opening_balance', 'notes']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-input', 'placeholder': '例: 普通預金A、現金、クレジットカードA'}),
            'kind': forms.Select(attrs={'class': 'form-input'}),
            'opening_balance': forms.NumberInput(attrs={'class': 'form-input', 'step': '1'}),
            'notes': forms.Textarea(attrs={'class': 'form-input', 'rows': 2, 'placeholder': '任意メモ'}),
        }
        labels = {
            'name': '口座名',
            'kind': '会計区分',
            'opening_balance': '初期残高',
            'notes': 'メモ',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.help_text = ''
        # kind による初期残高ヘルプの切替
        is_liability = (
            (self.is_bound and self.data.get('kind') == Account.Kind.LIABILITY)
            or (self.instance and self.instance.pk and self.instance.kind == Account.Kind.LIABILITY)
        )
        if is_liability:
            self.fields['opening_balance'].help_text = (
                '負債口座は借入残高を「マイナス値」で入力してください。'
                '例: 残債 100 万円 → -1000000'
            )
        else:
            self.fields['opening_balance'].help_text = (
                '資産口座は 0 円以上で入力してください。'
            )
        if self._has_balance_history():
            self.fields['opening_balance'].help_text += (
                ' 取引/振替が登録済みのため、変更すると過去残高が再計算されます。'
            )
        if MonthlyClosing.objects.exists():
            self.fields['opening_balance'].help_text = (
                '月次締めが存在するため、初期残高は変更できません。'
            )

    def _has_balance_history(self) -> bool:
        if not self.instance or not self.instance.pk:
            return False
        return (
            self.instance.transaction_set.exists()
            or self.instance.transfers_out.exists()
            or self.instance.transfers_in.exists()
        )

    def clean_name(self):
        name = self.cleaned_data['name']
        qs = Account.objects.filter(name=name)
        if self.instance and self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError(f'「{name}」は既に使われています。別の名前を入力してください。')
        return name

    def clean_opening_balance(self):
        return self.cleaned_data['opening_balance']


class LoanProfileForm(forms.ModelForm):
    """負債口座の付帯情報。account は親ビューで埋め込む前提。"""

    annual_rate_pct_input = forms.DecimalField(
        label='年利 (%)',
        required=False,
        min_value=0,
        max_value=100,
        decimal_places=2,
        widget=forms.NumberInput(attrs={
            'class': 'form-input', 'step': '0.01',
            'placeholder': '例: 15.00',
        }),
        help_text='%表記で入力（内部では bp 換算で保持）。',
    )

    class Meta:
        model = LoanProfile
        fields = ['method', 'monthly_payment', 'payment_day', 'payoff_date', 'source_account', 'notes']
        widgets = {
            'method': forms.Select(attrs={'class': 'form-input'}),
            'monthly_payment': forms.NumberInput(attrs={
                'class': 'form-input', 'step': '1', 'min': '0',
                'placeholder': '例: 10000',
            }),
            'payment_day': forms.NumberInput(attrs={
                'class': 'form-input', 'step': '1', 'min': '0', 'max': '31',
                'placeholder': '例: 27',
            }),
            'payoff_date': DateInput(attrs={'class': 'form-input'}),
            'source_account': forms.Select(attrs={'class': 'form-input'}),
            'notes': forms.Textarea(attrs={
                'class': 'form-input', 'rows': 2,
                'placeholder': '契約番号 / 引落口座 / 補足など',
            }),
        }
        labels = {
            'method': '返済方式',
            'monthly_payment': '月次返済額（目安）',
            'payment_day': '引落日',
            'payoff_date': '完済予定日',
            'source_account': '引落元口座',
            'notes': '備考',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # 既存データから %初期値を計算
        if self.instance and self.instance.pk:
            self.fields['annual_rate_pct_input'].initial = self.instance.annual_rate_pct
        # 引落元は資産口座のみ
        self.fields['source_account'].queryset = (
            Account.objects.filter(kind=Account.Kind.ASSET, is_active=True).order_by('name')
        )
        self.fields['source_account'].empty_label = '（自動返済を使わない）'
        # 並び順: 年利 -> その他
        self.order_fields(['annual_rate_pct_input', 'method', 'monthly_payment',
                           'payment_day', 'payoff_date', 'source_account', 'notes'])

    def save(self, *args, **kwargs):
        # %入力を bp に変換
        pct = self.cleaned_data.get('annual_rate_pct_input') or 0
        self.instance.annual_rate_bp = int(round(float(pct) * 100))
        return super().save(*args, **kwargs)


class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = ['name', 'kind', 'section', 'tax_tag', 'notes']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-input', 'placeholder': '例: 食費、交通費、給与'}),
            'kind': forms.Select(attrs={'class': 'form-input'}),
            'section': forms.Select(attrs={'class': 'form-input'}),
            'tax_tag': forms.Select(attrs={'class': 'form-input'}),
            'notes': forms.Textarea(attrs={'class': 'form-input', 'rows': 2, 'placeholder': '任意メモ'}),
        }
        labels = {
            'name': 'カテゴリ名',
            'kind': '区分',
            'section': '大分類',
            'tax_tag': '税控除タグ',
            'notes': 'メモ',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.help_text = ''
        if self.instance and self.instance.pk:
            self.fields['kind'].disabled = True

    def clean_name(self):
        name = self.cleaned_data['name']
        qs = Category.objects.filter(name=name)
        if self.instance and self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError(f'「{name}」は既に使われています。別の名前を入力してください。')
        return name

    def clean_kind(self):
        if self.instance and self.instance.pk:
            return self.instance.kind
        return self.cleaned_data['kind']


class CsvImportForm(forms.Form):
    csv_file = forms.FileField(
        label='CSV ファイル',
        widget=forms.ClearableFileInput(attrs={'class': 'form-input', 'accept': '.csv,text/csv'}),
        help_text='エクスポートと同じ書式の CSV を選択してください（最大 1 MiB / 1000 行）。',
    )

    def clean_csv_file(self):
        f = self.cleaned_data['csv_file']
        name = (getattr(f, 'name', '') or '').lower()
        if not name.endswith('.csv'):
            raise forms.ValidationError('拡張子が .csv のファイルを選択してください。')
        size = getattr(f, 'size', 0) or 0
        if size > 1 * 1024 * 1024:
            raise forms.ValidationError('ファイルサイズが 1 MiB を超えています。')
        return f


class MedicalExpenseForm(forms.ModelForm):
    """医療費控除明細（v1.16.0）入力フォーム。

    取引フォームから来た場合は transaction フィールドが hidden で来る。
    専用ページから来た場合は transaction なしで作成可能。
    """

    class Meta:
        model = MedicalExpense
        fields = ['paid_date', 'patient', 'provider', 'category', 'amount', 'reimbursement', 'notes', 'transaction']
        widgets = {
            'paid_date': DateInput(attrs={'class': 'form-input', 'autocomplete': 'off'}),
            'patient': forms.TextInput(attrs={
                'class': 'form-input', 'placeholder': '例: 受診者A / 受診者B / 子供A',
                'list': 'medical-patient-suggestions',
                'autocomplete': 'off',
            }),
            'provider': forms.TextInput(attrs={
                'class': 'form-input', 'placeholder': '例: 〇〇クリニック / △△薬局',
                'autocomplete': 'off',
            }),
            'category': forms.Select(attrs={'class': 'form-input'}),
            'amount': forms.NumberInput(attrs={
                'class': 'form-input', 'step': '1', 'min': '1',
                'inputmode': 'numeric', 'autocomplete': 'off',
            }),
            'reimbursement': forms.NumberInput(attrs={
                'class': 'form-input', 'step': '1', 'min': '0',
                'inputmode': 'numeric', 'autocomplete': 'off',
            }),
            'notes': forms.Textarea(attrs={
                'class': 'form-input', 'rows': 3, 'placeholder': '任意メモ',
                'autocomplete': 'off',
            }),
            'transaction': forms.HiddenInput(),
        }
        labels = {
            'paid_date': '支払日',
            'patient': '受診者',
            'provider': '医療機関・薬局名',
            'category': '区分',
            'amount': '支払額',
            'reimbursement': '補填額',
            'notes': 'メモ',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.help_text = ''
        self.fields['transaction'].required = False
        self.fields['notes'].required = False
        self.fields['reimbursement'].required = False


class AnnualIncomeSnapshotForm(forms.ModelForm):
    """年次総所得スナップショット（v1.16.0）入力フォーム。"""

    class Meta:
        model = AnnualIncomeSnapshot
        fields = ['year', 'gross_income', 'notes']
        widgets = {
            'year': forms.NumberInput(attrs={
                'class': 'form-input', 'step': '1', 'min': '1900', 'max': '2999',
                'inputmode': 'numeric', 'autocomplete': 'off',
            }),
            'gross_income': forms.NumberInput(attrs={
                'class': 'form-input', 'step': '1', 'min': '0',
                'inputmode': 'numeric', 'autocomplete': 'off',
                'placeholder': '例: 4500000',
            }),
            'notes': forms.Textarea(attrs={
                'class': 'form-input', 'rows': 2, 'placeholder': '任意メモ',
                'autocomplete': 'off',
            }),
        }
        labels = {
            'year': '対象年',
            'gross_income': '総所得金額',
            'notes': 'メモ',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['notes'].required = False
        self.fields['gross_income'].help_text = '給与所得控除後の金額（源泉徴収票の該当欄）'


class InsurancePremiumForm(forms.ModelForm):
    """生命保険料控除・地震保険料控除（v1.17.0）入力フォーム。"""

    class Meta:
        model = InsurancePremium
        fields = [
            'year',
            'category',
            'contract_type',
            'insurer',
            'policy_number',
            'annual_amount',
            'submitted_in_year_end_adjustment',
            'notes',
        ]
        widgets = {
            'year': forms.NumberInput(attrs={
                'class': 'form-input', 'step': '1', 'min': '1900', 'max': '2999',
                'inputmode': 'numeric', 'autocomplete': 'off',
            }),
            'category': forms.Select(attrs={'class': 'form-input'}),
            'contract_type': forms.Select(attrs={'class': 'form-input'}),
            'insurer': forms.TextInput(attrs={
                'class': 'form-input', 'placeholder': '例: 〇〇生命 / 〇〇共済',
                'list': 'insurance-insurer-suggestions',
                'autocomplete': 'off',
            }),
            'policy_number': forms.TextInput(attrs={
                'class': 'form-input', 'placeholder': '例: 1234-5678 (任意)',
                'autocomplete': 'off',
            }),
            'annual_amount': forms.NumberInput(attrs={
                'class': 'form-input', 'step': '1', 'min': '1',
                'inputmode': 'numeric', 'autocomplete': 'off',
                'placeholder': '控除証明書の申告額（円単位）',
            }),
            'submitted_in_year_end_adjustment': forms.CheckboxInput(attrs={
                'class': 'form-check',
            }),
            'notes': forms.Textarea(attrs={
                'class': 'form-input', 'rows': 2, 'autocomplete': 'off',
            }),
        }
        labels = {
            'year': '対象年',
            'category': '区分',
            'contract_type': '契約区分',
            'insurer': '保険会社名',
            'policy_number': '証券番号',
            'annual_amount': '年間支払保険料',
            'submitted_in_year_end_adjustment': '年末調整で提出済',
            'notes': 'メモ',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['policy_number'].required = False
        self.fields['notes'].required = False
        self.fields['submitted_in_year_end_adjustment'].required = False
        self.fields['annual_amount'].help_text = '控除証明書記載の「申告額」または「年間払込予定額」'

    def clean(self):
        cleaned = super().clean()
        category = cleaned.get('category')
        contract_type = cleaned.get('contract_type')
        if (
            category == InsurancePremium.InsuranceCategory.LIFE_CARE_MEDICAL
            and contract_type == InsurancePremium.ContractType.OLD
        ):
            raise forms.ValidationError(
                '介護医療保険料は新契約のみが対象です（2012/1/1 新設）。'
            )
        return cleaned
