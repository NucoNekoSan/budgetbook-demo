from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.db.models import Count
from django.db.models.deletion import ProtectedError
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_http_methods

from ..forms import AccountForm, CategoryForm, LoanProfileForm
from ..models import Account, AuditLog, Category, ExpenseGroupCategory, LoanProfile, Transaction, Transfer
from .helpers import record_audit


def _accounts_for_settings() -> list[Account]:
    accounts = list(Account.objects.order_by('-is_active', 'name'))
    tx_counts = dict(
        Transaction.objects.values('account_id')
        .annotate(count=Count('id'))
        .values_list('account_id', 'count')
    )
    transfer_out_counts = dict(
        Transfer.objects.values('from_account_id')
        .annotate(count=Count('id'))
        .values_list('from_account_id', 'count')
    )
    transfer_in_counts = dict(
        Transfer.objects.values('to_account_id')
        .annotate(count=Count('id'))
        .values_list('to_account_id', 'count')
    )
    for account in accounts:
        transaction_count = tx_counts.get(account.pk, 0)
        transfer_count = transfer_out_counts.get(account.pk, 0) + transfer_in_counts.get(account.pk, 0)
        account.transaction_count = transaction_count
        account.transfer_count = transfer_count
        account.usage_count = transaction_count + transfer_count
        account.can_delete = account.usage_count == 0
    return accounts


def _categories_for_settings() -> list[Category]:
    categories = list(Category.objects.order_by('-is_active', 'kind', 'name'))
    tx_counts = dict(
        Transaction.objects.values('category_id')
        .annotate(count=Count('id'))
        .values_list('category_id', 'count')
    )
    group_counts = dict(
        ExpenseGroupCategory.objects.values('category_id')
        .annotate(count=Count('id'))
        .values_list('category_id', 'count')
    )
    for category in categories:
        transaction_count = tx_counts.get(category.pk, 0)
        group_count = group_counts.get(category.pk, 0)
        category.transaction_count = transaction_count
        category.group_count = group_count
        category.can_delete = transaction_count == 0
    return categories


def _settings_context() -> dict:
    return {
        'accounts': _accounts_for_settings(),
        'categories': _categories_for_settings(),
    }


@login_required
@require_http_methods(['GET'])
def settings_page(request: HttpRequest) -> HttpResponse:
    context = _settings_context()
    context['account_form'] = AccountForm()
    context['category_form'] = CategoryForm()
    return render(request, 'ledger/settings.html', context)


def _render_account_list(request: HttpRequest, flash: str = '') -> HttpResponse:
    context = {
        'accounts': _accounts_for_settings(),
        'account_form': AccountForm(),
        'flash_message': flash,
    }
    return render(request, 'ledger/partials/account_list.html', context)


@login_required
@require_http_methods(['GET', 'POST'])
def account_create(request: HttpRequest) -> HttpResponse:
    if request.method == 'POST':
        form = AccountForm(request.POST)
        if form.is_valid():
            account = form.save()
            record_audit(request, AuditLog.Action.CREATE, account, '口座を追加しました。')
            return _render_account_list(request, '口座を追加しました。')
        context = {
            'accounts': _accounts_for_settings(),
            'account_form': form,
            'show_account_form': True,
        }
        return render(request, 'ledger/partials/account_list.html', context, status=422)
    if request.GET.get('close'):
        return _render_account_list(request)
    context = {
        'accounts': _accounts_for_settings(),
        'account_form': AccountForm(),
        'show_account_form': True,
    }
    return render(request, 'ledger/partials/account_list.html', context)


@login_required
@require_http_methods(['GET', 'POST'])
def account_update(request: HttpRequest, pk: int) -> HttpResponse:
    account = get_object_or_404(Account, pk=pk)
    inline = request.GET.get('inline') == '1' or request.POST.get('inline') == '1'
    # インライン編集のキャンセル: プレースホルダ tr のみ返す
    if inline and request.method == 'GET' and request.GET.get('close') == '1':
        return render(request, 'ledger/partials/account_inline_placeholder.html', {
            'account': account,
        })
    # 負債口座は LoanProfile も同時編集
    is_liability_post = (
        account.kind == Account.Kind.LIABILITY
        or request.POST.get('kind') == Account.Kind.LIABILITY
    )
    profile_instance = getattr(account, 'loan_profile', None)
    if request.method == 'POST':
        form = AccountForm(request.POST, instance=account)
        loan_form = None
        if is_liability_post:
            loan_form = LoanProfileForm(
                request.POST,
                instance=profile_instance or LoanProfile(account=account),
            )
        if form.is_valid() and (loan_form is None or loan_form.is_valid()):
            account = form.save()
            if loan_form is not None and account.kind == Account.Kind.LIABILITY:
                loan_form.instance.account = account
                loan_form.save()
            record_audit(request, AuditLog.Action.UPDATE, account, f'「{account.name}」を更新しました。')
            response = _render_account_list(request, f'「{account.name}」を更新しました。')
            if inline:
                response['HX-Retarget'] = '#account-list'
                response['HX-Reswap'] = 'innerHTML'
            return response
        if inline:
            return render(request, 'ledger/partials/account_inline_edit.html', {
                'form': form, 'loan_form': loan_form, 'account': account,
            }, status=422)
        context = {
            'accounts': _accounts_for_settings(),
            'account_form': AccountForm(),
            'edit_account_form': form,
            'edit_account_loan_form': loan_form,
            'edit_account_pk': pk,
        }
        return render(request, 'ledger/partials/account_list.html', context, status=422)
    # GET
    loan_form = None
    if account.kind == Account.Kind.LIABILITY:
        loan_form = LoanProfileForm(instance=profile_instance or LoanProfile(account=account))
    if inline:
        return render(request, 'ledger/partials/account_inline_edit.html', {
            'form': AccountForm(instance=account),
            'loan_form': loan_form,
            'account': account,
        })
    context = {
        'accounts': _accounts_for_settings(),
        'account_form': AccountForm(),
        'edit_account_form': AccountForm(instance=account),
        'edit_account_loan_form': loan_form,
        'edit_account_pk': pk,
    }
    return render(request, 'ledger/partials/account_list.html', context)


@login_required
@require_http_methods(['POST'])
def account_toggle(request: HttpRequest, pk: int) -> HttpResponse:
    account = get_object_or_404(Account, pk=pk)
    account.is_active = not account.is_active
    account.save(update_fields=['is_active'])
    label = '有効' if account.is_active else '無効'
    action = AuditLog.Action.UPDATE if account.is_active else AuditLog.Action.DEACTIVATE
    record_audit(request, action, account, f'「{account.name}」を{label}にしました。', {'is_active': account.is_active})
    return _render_account_list(request, f'「{account.name}」を{label}にしました。')


@login_required
@require_http_methods(['POST'])
def account_delete(request: HttpRequest, pk: int) -> HttpResponse:
    account = get_object_or_404(Account, pk=pk)
    name = account.name
    target_id = str(account.pk)
    target_repr = str(account)
    try:
        account.delete()
    except ProtectedError:
        return _render_account_list(
            request,
            f'「{name}」には取引または振替が紐づいているため削除できません。先に「停止」で無効化してください。',
        )
    record_audit(
        request, AuditLog.Action.DELETE, account, f'「{name}」を削除しました。',
        target_id=target_id, target_repr=target_repr,
    )
    return _render_account_list(request, f'「{name}」を削除しました。')


def _render_category_list(request: HttpRequest, flash: str = '') -> HttpResponse:
    context = {
        'categories': _categories_for_settings(),
        'category_form': CategoryForm(),
        'flash_message': flash,
    }
    return render(request, 'ledger/partials/category_list.html', context)


@login_required
@require_http_methods(['GET', 'POST'])
def category_create(request: HttpRequest) -> HttpResponse:
    if request.method == 'POST':
        form = CategoryForm(request.POST)
        if form.is_valid():
            category = form.save()
            record_audit(request, AuditLog.Action.CREATE, category, 'カテゴリを追加しました。')
            return _render_category_list(request, 'カテゴリを追加しました。')
        context = {
            'categories': _categories_for_settings(),
            'category_form': form,
            'show_category_form': True,
        }
        return render(request, 'ledger/partials/category_list.html', context, status=422)
    if request.GET.get('close'):
        return _render_category_list(request)
    context = {
        'categories': _categories_for_settings(),
        'category_form': CategoryForm(),
        'show_category_form': True,
    }
    return render(request, 'ledger/partials/category_list.html', context)


@login_required
@require_http_methods(['GET', 'POST'])
def category_update(request: HttpRequest, pk: int) -> HttpResponse:
    category = get_object_or_404(Category, pk=pk)
    inline = request.GET.get('inline') == '1' or request.POST.get('inline') == '1'
    if inline and request.method == 'GET' and request.GET.get('close') == '1':
        return render(request, 'ledger/partials/category_inline_placeholder.html', {
            'category': category,
        })
    if request.method == 'POST':
        form = CategoryForm(request.POST, instance=category)
        if form.is_valid():
            category = form.save()
            record_audit(request, AuditLog.Action.UPDATE, category, f'「{category.name}」を更新しました。')
            response = _render_category_list(request, f'「{category.name}」を更新しました。')
            if inline:
                response['HX-Retarget'] = '#category-list'
                response['HX-Reswap'] = 'innerHTML'
            return response
        if inline:
            return render(request, 'ledger/partials/category_inline_edit.html', {
                'form': form, 'category': category,
            }, status=422)
        context = {
            'categories': _categories_for_settings(),
            'category_form': CategoryForm(),
            'edit_category_form': form,
            'edit_category_pk': pk,
        }
        return render(request, 'ledger/partials/category_list.html', context, status=422)
    if inline:
        return render(request, 'ledger/partials/category_inline_edit.html', {
            'form': CategoryForm(instance=category), 'category': category,
        })
    context = {
        'categories': _categories_for_settings(),
        'category_form': CategoryForm(),
        'edit_category_form': CategoryForm(instance=category),
        'edit_category_pk': pk,
    }
    return render(request, 'ledger/partials/category_list.html', context)


@login_required
@require_http_methods(['POST'])
def category_toggle(request: HttpRequest, pk: int) -> HttpResponse:
    category = get_object_or_404(Category, pk=pk)
    category.is_active = not category.is_active
    category.save(update_fields=['is_active'])
    label = '有効' if category.is_active else '無効'
    action = AuditLog.Action.UPDATE if category.is_active else AuditLog.Action.DEACTIVATE
    record_audit(request, action, category, f'「{category.name}」を{label}にしました。', {'is_active': category.is_active})
    return _render_category_list(request, f'「{category.name}」を{label}にしました。')


@login_required
@require_http_methods(['POST'])
def category_delete(request: HttpRequest, pk: int) -> HttpResponse:
    category = get_object_or_404(Category, pk=pk)
    name = category.name
    target_id = str(category.pk)
    target_repr = str(category)
    try:
        category.delete()
    except ProtectedError:
        return _render_category_list(
            request,
            f'「{name}」には取引が紐づいているため削除できません。先に取引を削除するか、無効化してください。',
        )
    record_audit(
        request, AuditLog.Action.DELETE, category, f'「{name}」を削除しました。',
        target_id=target_id, target_repr=target_repr,
    )
    return _render_category_list(request, f'「{name}」を削除しました。')