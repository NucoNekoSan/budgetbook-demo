from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from ..forms import TransactionForm
from ..models import AuditLog, Transaction
from ..services.balance import is_month_closed
from ..services.medical import sync_medical_expense_from_post
from ..services.dates import (
    clamp_future_month,
    month_from_entry_date,
    month_param,
    parse_month,
)
from ..services.filters import parse_filters, parse_preserved_filters
from .helpers import (
    build_form_context,
    closed_month_response,
    inline_form_context,
    record_audit,
    render_dashboard_bundle,
    render_dashboard_oob,
    render_dashboard_section,
    resolve_target_month_for_obj,
)


@login_required
@require_http_methods(['GET', 'POST'])
def transaction_create(request: HttpRequest) -> HttpResponse:
    target_month = clamp_future_month(parse_month(request.GET.get('month') or request.POST.get('month')))
    if request.method == 'POST':
        form = TransactionForm(request.POST)
        if form.is_valid():
            entry_date = form.cleaned_data['date']
            if is_month_closed(entry_date):
                return closed_month_response(
                    request,
                    month_from_entry_date(entry_date),
                    '締め済み月のため、取引を追加できません。',
                )
            transaction = form.save()
            sync_medical_expense_from_post(transaction, request.POST)
            record_audit(
                request,
                AuditLog.Action.CREATE,
                transaction,
                '取引を保存しました。',
                {'date': transaction.date.isoformat(), 'amount': transaction.amount},
            )
            target_month = month_from_entry_date(transaction.date)
            if request.htmx:
                return render_dashboard_bundle(request, target_month, '取引を保存しました。')
            return redirect(f"{reverse('ledger:dashboard')}?month={month_param(target_month)}")
        status = 422 if request.htmx else 200
        context = build_form_context(target_month, form=form)
        return render(request, 'ledger/partials/transaction_form_panel.html', context, status=status)

    context = build_form_context(target_month)
    return render(request, 'ledger/partials/transaction_form_panel.html', context)


@login_required
@require_http_methods(['GET', 'POST'])
def transaction_update(request: HttpRequest, pk: int) -> HttpResponse:
    transaction = get_object_or_404(Transaction.objects.select_related('category'), pk=pk)
    target_month = clamp_future_month(parse_month(request.GET.get('month') or request.POST.get('month') or month_param(transaction.date.replace(day=1))))

    if request.method == 'POST':
        form = TransactionForm(request.POST, instance=transaction)
        if form.is_valid():
            entry_date = form.cleaned_data['date']
            if is_month_closed(transaction.date) or is_month_closed(entry_date):
                return closed_month_response(
                    request,
                    target_month,
                    '締め済み月のため、取引を更新できません。',
                )
            transaction = form.save()
            sync_medical_expense_from_post(transaction, request.POST)
            record_audit(
                request,
                AuditLog.Action.UPDATE,
                transaction,
                '取引を更新しました。',
                {'date': transaction.date.isoformat(), 'amount': transaction.amount},
            )
            target_month = month_from_entry_date(transaction.date)
            if request.htmx:
                return render_dashboard_bundle(request, target_month, '取引を更新しました。')
            return redirect(f"{reverse('ledger:dashboard')}?month={month_param(target_month)}")
        status = 422 if request.htmx else 200
        context = build_form_context(target_month, form=form, transaction=transaction)
        return render(request, 'ledger/partials/transaction_form_panel.html', context, status=status)

    context = build_form_context(target_month, transaction=transaction)
    return render(request, 'ledger/partials/transaction_form_panel.html', context)


@login_required
@require_http_methods(['GET', 'POST'])
def transaction_delete(request: HttpRequest, pk: int) -> HttpResponse:
    transaction = get_object_or_404(Transaction.objects.select_related('account', 'category'), pk=pk)
    target_month = clamp_future_month(parse_month(request.GET.get('month') or request.POST.get('month') or month_param(transaction.date.replace(day=1))))
    filters = parse_filters(request.GET)
    page = request.GET.get('page') or request.POST.get('page') or 1

    if request.method == 'POST':
        if is_month_closed(transaction.date):
            return closed_month_response(
                request,
                target_month,
                '締め済み月のため、取引を削除できません。',
            )
        record_audit(
            request,
            AuditLog.Action.DELETE,
            transaction,
            '取引を削除しました。',
            {'date': transaction.date.isoformat(), 'amount': transaction.amount},
        )
        transaction.delete()
        if request.htmx:
            return render_dashboard_oob(request, target_month, '取引を削除しました。', filters=filters, page=page)
        return redirect(f"{reverse('ledger:dashboard')}?month={month_param(target_month)}")

    return render(
        request,
        'ledger/partials/transaction_delete_confirm.html',
        {
            'transaction': transaction,
            'month_param': month_param(target_month),
            'delete_action': f"{reverse('ledger:transaction_delete', args=[transaction.pk])}?month={month_param(target_month)}",
            'cancel_url': f"{reverse('ledger:transaction_create')}?month={month_param(target_month)}",
        },
    )


@login_required
@require_http_methods(['GET', 'POST'])
def transaction_inline_update(request: HttpRequest, pk: int) -> HttpResponse:
    transaction = get_object_or_404(Transaction.objects.select_related('category'), pk=pk)
    target_month = resolve_target_month_for_obj(request, transaction.date)
    filters = parse_filters(request.GET) if request.method == 'GET' else parse_preserved_filters(request.POST)
    page = request.GET.get('page') or request.POST.get('page') or 1

    if request.method == 'POST':
        form = TransactionForm(request.POST, instance=transaction)
        if form.is_valid():
            entry_date = form.cleaned_data['date']
            if is_month_closed(transaction.date) or is_month_closed(entry_date):
                return closed_month_response(
                    request,
                    target_month,
                    '締め済み月のため、取引を更新できません。',
                )
            updated = form.save()
            record_audit(
                request,
                AuditLog.Action.UPDATE,
                updated,
                '取引を更新しました。',
                {'date': updated.date.isoformat(), 'amount': updated.amount, 'inline': True},
            )
            if request.htmx:
                return render_dashboard_section(
                    request, target_month, '取引を更新しました。',
                    row_id=f'inline-edit-tx-{transaction.pk}', filters=filters,
                    page=page, scroll_to='transaction-list-panel',
                )
            return redirect(f"{reverse('ledger:dashboard')}?month={month_param(target_month)}")
        status = 422 if request.htmx else 200
        ctx = inline_form_context(
            mode='transaction', instance=transaction, form=form,
            target_month=target_month, filters=filters, page=page,
        )
        return render(request, 'ledger/partials/inline_edit_row.html', ctx, status=status)

    form = TransactionForm(instance=transaction)
    ctx = inline_form_context(
        mode='transaction', instance=transaction, form=form,
        target_month=target_month, filters=filters, page=page,
    )
    return render(request, 'ledger/partials/inline_edit_row.html', ctx)


@login_required
@require_http_methods(['GET'])
def transaction_inline_cancel(request: HttpRequest, pk: int) -> HttpResponse:
    return render(
        request,
        'ledger/partials/inline_edit_placeholder.html',
        {'row_id': f'inline-edit-tx-{pk}'},
    )