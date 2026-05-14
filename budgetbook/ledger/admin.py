from django.contrib import admin

from .models import (
    Account,
    AccountReconciliation,
    AnnualIncomeSnapshot,
    AuditLog,
    Category,
    ExpenseGroup,
    ExpenseGroupCategory,
    InsurancePremium,
    LoanProfile,
    MedicalExpense,
    MonthlyClosing,
    Transaction,
    Transfer,
)


@admin.register(Account)
class AccountAdmin(admin.ModelAdmin):
    list_display = ('name', 'kind', 'opening_balance', 'is_active', 'updated_at')
    list_filter = ('kind', 'is_active')
    search_fields = ('name',)


@admin.register(LoanProfile)
class LoanProfileAdmin(admin.ModelAdmin):
    list_display = ('account', 'method', 'annual_rate_bp', 'monthly_payment', 'payment_day', 'payoff_date')
    list_filter = ('method',)
    search_fields = ('account__name',)
    autocomplete_fields = ('account',)


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'kind', 'section', 'is_active', 'updated_at')
    list_filter = ('kind', 'section', 'is_active')
    search_fields = ('name',)
    list_editable = ('section',)


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ('date', 'description', 'account', 'category', 'amount')
    list_filter = ('category__kind', 'account', 'category', 'date')
    search_fields = ('description', 'memo')
    autocomplete_fields = ('account', 'category')
    date_hierarchy = 'date'


class ExpenseGroupCategoryInline(admin.TabularInline):
    model = ExpenseGroupCategory
    extra = 1
    autocomplete_fields = ('category',)


@admin.register(ExpenseGroup)
class ExpenseGroupAdmin(admin.ModelAdmin):
    list_display = ('name', 'is_active', 'sort_order', 'updated_at')
    list_filter = ('is_active',)
    search_fields = ('name',)
    ordering = ('sort_order', 'name')
    inlines = [ExpenseGroupCategoryInline]


@admin.register(ExpenseGroupCategory)
class ExpenseGroupCategoryAdmin(admin.ModelAdmin):
    list_display = ('group', 'category')
    list_filter = ('group',)
    autocomplete_fields = ('group', 'category')


@admin.register(Transfer)
class TransferAdmin(admin.ModelAdmin):
    list_display = ('date', 'description', 'from_account', 'to_account', 'amount')
    list_filter = ('from_account', 'to_account', 'date')
    search_fields = ('description', 'memo')
    autocomplete_fields = ('from_account', 'to_account')
    date_hierarchy = 'date'


@admin.register(MonthlyClosing)
class MonthlyClosingAdmin(admin.ModelAdmin):
    list_display = ('month', 'closing_balance', 'income', 'expense', 'net', 'closed_at', 'closed_by')
    list_filter = ('month', 'closed_by')
    readonly_fields = (
        'closed_at', 'opening_carry', 'income', 'expense', 'net',
        'closing_balance', 'account_balances',
    )
    date_hierarchy = 'month'


@admin.register(AccountReconciliation)
class AccountReconciliationAdmin(admin.ModelAdmin):
    list_display = ('reconciled_on', 'account', 'book_balance', 'actual_balance', 'difference', 'created_by')
    list_filter = ('account', 'reconciled_on')
    readonly_fields = ('book_balance', 'difference', 'created_by')
    autocomplete_fields = ('account',)
    date_hierarchy = 'reconciled_on'


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ('created_at', 'user', 'action', 'target_model', 'target_id', 'target_repr', 'summary')
    list_filter = ('action', 'target_model', 'user', 'created_at')
    search_fields = ('target_model', 'target_id', 'target_repr', 'summary')
    readonly_fields = (
        'created_at', 'user', 'action', 'target_model', 'target_id',
        'target_repr', 'summary', 'metadata',
    )
    date_hierarchy = 'created_at'

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_view_permission(self, request, obj=None):
        return request.user.is_active and request.user.is_staff


@admin.register(MedicalExpense)
class MedicalExpenseAdmin(admin.ModelAdmin):
    list_display = ('paid_date', 'patient', 'provider', 'category', 'amount', 'reimbursement', 'transaction')
    list_filter = ('category', 'paid_date')
    search_fields = ('patient', 'provider', 'notes')
    autocomplete_fields = ('transaction',)
    date_hierarchy = 'paid_date'


@admin.register(AnnualIncomeSnapshot)
class AnnualIncomeSnapshotAdmin(admin.ModelAdmin):
    list_display = ('year', 'gross_income', 'updated_at')
    search_fields = ('year', 'notes')
    ordering = ('-year',)


@admin.register(InsurancePremium)
class InsurancePremiumAdmin(admin.ModelAdmin):
    list_display = (
        'year', 'category', 'contract_type', 'insurer',
        'annual_amount', 'submitted_in_year_end_adjustment',
    )
    list_filter = ('year', 'category', 'contract_type', 'submitted_in_year_end_adjustment')
    search_fields = ('insurer', 'policy_number', 'notes')
    ordering = ('-year', 'category')
