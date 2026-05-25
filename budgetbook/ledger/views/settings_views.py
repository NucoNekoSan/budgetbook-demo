from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.db.models import Count
from django.db.models.deletion import ProtectedError
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_http_methods

from ..forms import AccountForm, CategoryForm, LoanProfileForm, PayeeForm, PaymentMethodForm
from ..models import (
    Account,
    AuditLog,
    Category,
    CategoryChangeLog,
    ExpenseGroupCategory,
    LoanProfile,
    Payee,
    PaymentMethod,
    Transaction,
    Transfer,
)
from ..services.category_history import (
    category_snapshot,
    create_category_change_log,
)
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
    log_counts = dict(
        CategoryChangeLog.objects.values('category_id')
        .annotate(count=Count('id'))
        .values_list('category_id', 'count')
    )
    for category in categories:
        transaction_count = tx_counts.get(category.pk, 0)
        group_count = group_counts.get(category.pk, 0)
        change_log_count = log_counts.get(category.pk, 0)
        category.transaction_count = transaction_count
        category.group_count = group_count
        category.change_log_count = change_log_count
        category.can_delete = transaction_count == 0 and change_log_count == 0
    return categories


def _payees_for_settings() -> list[Payee]:
    payees = list(Payee.objects.prefetch_related('aliases').order_by('-is_active', 'name'))
    tx_counts = dict(
        Transaction.objects.values('payee_id')
        .annotate(count=Count('id'))
        .values_list('payee_id', 'count')
    )
    for payee in payees:
        payee.transaction_count = tx_counts.get(payee.pk, 0)
        payee.can_delete = payee.transaction_count == 0
    return payees


def _payment_methods_for_settings() -> list[PaymentMethod]:
    payment_methods = list(
        PaymentMethod.objects
        .select_related('account', 'settlement_account')
        .order_by('-is_active', 'kind', 'name')
    )
    tx_counts = dict(
        Transaction.objects.values('payment_method_id')
        .annotate(count=Count('id'))
        .values_list('payment_method_id', 'count')
    )
    for payment_method in payment_methods:
        payment_method.transaction_count = tx_counts.get(payment_method.pk, 0)
        payment_method.can_delete = payment_method.transaction_count == 0
    return payment_methods


def _settings_context() -> dict:
    return {
        'accounts': _accounts_for_settings(),
        'categories': _categories_for_settings(),
        'payees': _payees_for_settings(),
        'payment_methods': _payment_methods_for_settings(),
    }


@login_required
@require_http_methods(['GET'])
def settings_page(request: HttpRequest) -> HttpResponse:
    context = _settings_context()
    context['account_form'] = AccountForm()
    context['category_form'] = CategoryForm()
    context['payee_form'] = PayeeForm()
    context['payment_method_form'] = PaymentMethodForm()
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
        before = category_snapshot(category)
        form = CategoryForm(request.POST, instance=category, include_change_reason=True)
        if form.is_valid():
            category = form.save()
            after = category_snapshot(category)
            if before != after:
                create_category_change_log(
                    category=category,
                    action=CategoryChangeLog.Action.UPDATE,
                    before=before,
                    after=after,
                    reason=form.cleaned_data.get('change_reason', ''),
                    changed_by=request.user,
                )
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
            'form': CategoryForm(instance=category, include_change_reason=True), 'category': category,
        })
    context = {
        'categories': _categories_for_settings(),
        'category_form': CategoryForm(),
        'edit_category_form': CategoryForm(instance=category, include_change_reason=True),
        'edit_category_pk': pk,
    }
    return render(request, 'ledger/partials/category_list.html', context)


@login_required
@require_http_methods(['POST'])
def category_toggle(request: HttpRequest, pk: int) -> HttpResponse:
    category = get_object_or_404(Category, pk=pk)
    before = category_snapshot(category)
    category.is_active = not category.is_active
    category.save(update_fields=['is_active'])
    after = category_snapshot(category)
    label = '有効' if category.is_active else '無効'
    action = AuditLog.Action.UPDATE if category.is_active else AuditLog.Action.DEACTIVATE
    history_action = (
        CategoryChangeLog.Action.REACTIVATE
        if category.is_active
        else CategoryChangeLog.Action.DEACTIVATE
    )
    create_category_change_log(
        category=category,
        action=history_action,
        before=before,
        after=after,
        changed_by=request.user,
    )
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
            f'「{name}」には取引・分析グループ・変更履歴のいずれかが紐づいているため削除できません。必要なら無効化してください。',
        )
    record_audit(
        request, AuditLog.Action.DELETE, category, f'「{name}」を削除しました。',
        target_id=target_id, target_repr=target_repr,
    )
    return _render_category_list(request, f'「{name}」を削除しました。')


def _render_payee_list(request: HttpRequest, flash: str = '') -> HttpResponse:
    context = {
        'payees': _payees_for_settings(),
        'payee_form': PayeeForm(),
        'flash_message': flash,
    }
    return render(request, 'ledger/partials/payee_list.html', context)


@login_required
@require_http_methods(['GET', 'POST'])
def payee_create(request: HttpRequest) -> HttpResponse:
    if request.method == 'POST':
        form = PayeeForm(request.POST)
        if form.is_valid():
            payee = form.save()
            record_audit(request, AuditLog.Action.CREATE, payee, '支払先を追加しました。')
            return _render_payee_list(request, '支払先を追加しました。')
        context = {
            'payees': _payees_for_settings(),
            'payee_form': form,
            'show_payee_form': True,
        }
        return render(request, 'ledger/partials/payee_list.html', context, status=422)
    if request.GET.get('close'):
        return _render_payee_list(request)
    context = {
        'payees': _payees_for_settings(),
        'payee_form': PayeeForm(),
        'show_payee_form': True,
    }
    return render(request, 'ledger/partials/payee_list.html', context)


@login_required
@require_http_methods(['GET', 'POST'])
def payee_update(request: HttpRequest, pk: int) -> HttpResponse:
    payee = get_object_or_404(Payee, pk=pk)
    inline = request.GET.get('inline') == '1' or request.POST.get('inline') == '1'
    if inline and request.method == 'GET' and request.GET.get('close') == '1':
        return render(request, 'ledger/partials/payee_inline_placeholder.html', {
            'payee': payee,
        })
    if request.method == 'POST':
        form = PayeeForm(request.POST, instance=payee)
        if form.is_valid():
            payee = form.save()
            record_audit(request, AuditLog.Action.UPDATE, payee, f'「{payee.name}」を更新しました。')
            response = _render_payee_list(request, f'「{payee.name}」を更新しました。')
            if inline:
                response['HX-Retarget'] = '#payee-list'
                response['HX-Reswap'] = 'innerHTML'
            return response
        if inline:
            return render(request, 'ledger/partials/payee_inline_edit.html', {
                'form': form, 'payee': payee,
            }, status=422)
        context = {
            'payees': _payees_for_settings(),
            'payee_form': PayeeForm(),
            'edit_payee_form': form,
            'edit_payee_pk': pk,
        }
        return render(request, 'ledger/partials/payee_list.html', context, status=422)
    if inline:
        return render(request, 'ledger/partials/payee_inline_edit.html', {
            'form': PayeeForm(instance=payee), 'payee': payee,
        })
    context = {
        'payees': _payees_for_settings(),
        'payee_form': PayeeForm(),
        'edit_payee_form': PayeeForm(instance=payee),
        'edit_payee_pk': pk,
    }
    return render(request, 'ledger/partials/payee_list.html', context)


@login_required
@require_http_methods(['POST'])
def payee_toggle(request: HttpRequest, pk: int) -> HttpResponse:
    payee = get_object_or_404(Payee, pk=pk)
    payee.is_active = not payee.is_active
    payee.save(update_fields=['is_active'])
    label = '有効' if payee.is_active else '無効'
    action = AuditLog.Action.UPDATE if payee.is_active else AuditLog.Action.DEACTIVATE
    record_audit(request, action, payee, f'「{payee.name}」を{label}にしました。', {'is_active': payee.is_active})
    return _render_payee_list(request, f'「{payee.name}」を{label}にしました。')


@login_required
@require_http_methods(['POST'])
def payee_delete(request: HttpRequest, pk: int) -> HttpResponse:
    payee = get_object_or_404(Payee, pk=pk)
    name = payee.name
    target_id = str(payee.pk)
    target_repr = str(payee)
    try:
        payee.delete()
    except ProtectedError:
        return _render_payee_list(
            request,
            f'「{name}」には取引が紐づいているため削除できません。先に「停止」で無効化してください。',
        )
    record_audit(
        request, AuditLog.Action.DELETE, payee, f'「{name}」を削除しました。',
        target_id=target_id, target_repr=target_repr,
    )
    return _render_payee_list(request, f'「{name}」を削除しました。')


def _render_payment_method_list(request: HttpRequest, flash: str = '') -> HttpResponse:
    context = {
        'payment_methods': _payment_methods_for_settings(),
        'payment_method_form': PaymentMethodForm(),
        'flash_message': flash,
    }
    return render(request, 'ledger/partials/payment_method_list.html', context)


@login_required
@require_http_methods(['GET', 'POST'])
def payment_method_create(request: HttpRequest) -> HttpResponse:
    if request.method == 'POST':
        form = PaymentMethodForm(request.POST)
        if form.is_valid():
            payment_method = form.save()
            record_audit(request, AuditLog.Action.CREATE, payment_method, '支払手段を追加しました。')
            return _render_payment_method_list(request, '支払手段を追加しました。')
        context = {
            'payment_methods': _payment_methods_for_settings(),
            'payment_method_form': form,
            'show_payment_method_form': True,
        }
        return render(request, 'ledger/partials/payment_method_list.html', context, status=422)
    if request.GET.get('close'):
        return _render_payment_method_list(request)
    context = {
        'payment_methods': _payment_methods_for_settings(),
        'payment_method_form': PaymentMethodForm(),
        'show_payment_method_form': True,
    }
    return render(request, 'ledger/partials/payment_method_list.html', context)


@login_required
@require_http_methods(['GET', 'POST'])
def payment_method_update(request: HttpRequest, pk: int) -> HttpResponse:
    payment_method = get_object_or_404(PaymentMethod, pk=pk)
    inline = request.GET.get('inline') == '1' or request.POST.get('inline') == '1'
    if inline and request.method == 'GET' and request.GET.get('close') == '1':
        return render(request, 'ledger/partials/payment_method_inline_placeholder.html', {
            'payment_method': payment_method,
        })
    if request.method == 'POST':
        form = PaymentMethodForm(request.POST, instance=payment_method)
        if form.is_valid():
            payment_method = form.save()
            record_audit(
                request,
                AuditLog.Action.UPDATE,
                payment_method,
                f'「{payment_method.name}」を更新しました。',
            )
            response = _render_payment_method_list(request, f'「{payment_method.name}」を更新しました。')
            if inline:
                response['HX-Retarget'] = '#payment-method-list'
                response['HX-Reswap'] = 'innerHTML'
            return response
        if inline:
            return render(request, 'ledger/partials/payment_method_inline_edit.html', {
                'form': form, 'payment_method': payment_method,
            }, status=422)
        context = {
            'payment_methods': _payment_methods_for_settings(),
            'payment_method_form': PaymentMethodForm(),
            'edit_payment_method_form': form,
            'edit_payment_method_pk': pk,
        }
        return render(request, 'ledger/partials/payment_method_list.html', context, status=422)
    if inline:
        return render(request, 'ledger/partials/payment_method_inline_edit.html', {
            'form': PaymentMethodForm(instance=payment_method),
            'payment_method': payment_method,
        })
    context = {
        'payment_methods': _payment_methods_for_settings(),
        'payment_method_form': PaymentMethodForm(),
        'edit_payment_method_form': PaymentMethodForm(instance=payment_method),
        'edit_payment_method_pk': pk,
    }
    return render(request, 'ledger/partials/payment_method_list.html', context)


@login_required
@require_http_methods(['POST'])
def payment_method_toggle(request: HttpRequest, pk: int) -> HttpResponse:
    payment_method = get_object_or_404(PaymentMethod, pk=pk)
    payment_method.is_active = not payment_method.is_active
    payment_method.save(update_fields=['is_active'])
    label = '有効' if payment_method.is_active else '無効'
    action = AuditLog.Action.UPDATE if payment_method.is_active else AuditLog.Action.DEACTIVATE
    record_audit(
        request,
        action,
        payment_method,
        f'「{payment_method.name}」を{label}にしました。',
        {'is_active': payment_method.is_active},
    )
    return _render_payment_method_list(request, f'「{payment_method.name}」を{label}にしました。')


@login_required
@require_http_methods(['POST'])
def payment_method_delete(request: HttpRequest, pk: int) -> HttpResponse:
    payment_method = get_object_or_404(PaymentMethod, pk=pk)
    name = payment_method.name
    target_id = str(payment_method.pk)
    target_repr = str(payment_method)
    try:
        payment_method.delete()
    except ProtectedError:
        return _render_payment_method_list(
            request,
            f'「{name}」には取引が紐づいているため削除できません。先に「停止」で無効化してください。',
        )
    record_audit(
        request, AuditLog.Action.DELETE, payment_method, f'「{name}」を削除しました。',
        target_id=target_id, target_repr=target_repr,
    )
    return _render_payment_method_list(request, f'「{name}」を削除しました。')
