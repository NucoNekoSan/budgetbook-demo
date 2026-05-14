from __future__ import annotations

from datetime import date

from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_http_methods

from ..forms import AccountReconciliationForm, MonthlyClosingForm
from ..models import AccountReconciliation, AuditLog, MonthlyClosing
from ..services.balance import calculate_account_balance
from ..services.closing import (
    build_monthly_closing_preflight,
    build_monthly_closing_snapshot,
    enrich_monthly_closings_with_drift,
)
from ..services.dates import month_param
from .helpers import record_audit


def _month_from_closing_form(closing_form: MonthlyClosingForm | None) -> date:
    today_month = date.today().replace(day=1)
    if closing_form is None:
        return today_month
    raw_value = ''
    if closing_form.is_bound:
        raw_value = closing_form.data.get('month', '')
    else:
        raw_value = closing_form.initial.get('month', '')
    if isinstance(raw_value, date):
        return raw_value.replace(day=1)
    try:
        return date.fromisoformat(str(raw_value)).replace(day=1)
    except (TypeError, ValueError):
        return today_month


def _accounting_context(
    *,
    closing_form: MonthlyClosingForm | None = None,
    reconciliation_form: AccountReconciliationForm | None = None,
    flash_message: str = '',
    error_message: str = '',
) -> dict:
    closings = MonthlyClosing.objects.select_related('closed_by').order_by('-month')[:12]
    closing_form = closing_form or MonthlyClosingForm(initial={'month': date.today().replace(day=1)})
    closing_preflight = build_monthly_closing_preflight(_month_from_closing_form(closing_form))
    return {
        'closing_form': closing_form,
        'closing_preflight': closing_preflight,
        'reconciliation_form': reconciliation_form or AccountReconciliationForm(initial={'reconciled_on': date.today()}),
        'closings': enrich_monthly_closings_with_drift(closings),
        'reconciliations': AccountReconciliation.objects.select_related('account', 'created_by').order_by('-reconciled_on', 'account__name')[:20],
        'flash_message': flash_message,
        'error_message': error_message,
    }


@login_required
@require_http_methods(['GET'])
def accounting(request: HttpRequest) -> HttpResponse:
    return render(request, 'ledger/accounting.html', _accounting_context())


@login_required
@require_http_methods(['POST'])
def monthly_closing_create(request: HttpRequest) -> HttpResponse:
    form = MonthlyClosingForm(request.POST)
    if not form.is_valid():
        return render(
            request,
            'ledger/accounting.html',
            _accounting_context(closing_form=form, error_message='月次締めの入力内容を確認してください。'),
            status=422,
        )

    target_month = form.cleaned_data['month']
    snapshot = build_monthly_closing_snapshot(target_month)
    try:
        with transaction.atomic():
            closing = MonthlyClosing.objects.create(
                month=target_month,
                closed_by=request.user,
                opening_carry=snapshot['opening_carry'],
                income=snapshot['income'],
                expense=snapshot['expense'],
                net=snapshot['net'],
                closing_balance=snapshot['closing_balance'],
                account_balances=snapshot['account_balances'],
                notes=form.cleaned_data.get('notes', ''),
            )
            record_audit(
                request,
                AuditLog.Action.CLOSE,
                closing,
                f'{month_param(target_month)} を月次締めしました。',
                {'month': month_param(target_month), 'closing_balance': snapshot['closing_balance']},
            )
    except (IntegrityError, ValidationError):
        return render(
            request,
            'ledger/accounting.html',
            _accounting_context(error_message=f'{month_param(target_month)} は既に締め済みです。'),
            status=409,
        )

    return render(
        request,
        'ledger/accounting.html',
        _accounting_context(flash_message=f'{month_param(target_month)} を締めました。'),
    )


@login_required
@require_http_methods(['POST'])
def reconciliation_create(request: HttpRequest) -> HttpResponse:
    form = AccountReconciliationForm(request.POST)
    if not form.is_valid():
        return render(
            request,
            'ledger/accounting.html',
            _accounting_context(reconciliation_form=form, error_message='口座照合の入力内容を確認してください。'),
            status=422,
        )

    account = form.cleaned_data['account']
    reconciled_on = form.cleaned_data['reconciled_on']
    book_balance = calculate_account_balance(account, reconciled_on)
    try:
        with transaction.atomic():
            item = AccountReconciliation.objects.create(
                account=account,
                reconciled_on=reconciled_on,
                book_balance=book_balance,
                actual_balance=form.cleaned_data['actual_balance'],
                notes=form.cleaned_data.get('notes', ''),
                created_by=request.user,
            )
            record_audit(
                request,
                AuditLog.Action.RECONCILE,
                item,
                f'{account.name} の残高照合を登録しました。',
                {'book_balance': book_balance, 'actual_balance': item.actual_balance, 'difference': item.difference},
            )
    except IntegrityError:
        return render(
            request,
            'ledger/accounting.html',
            _accounting_context(error_message=f'{account.name} の {reconciled_on:%Y-%m-%d} 照合は既に登録済みです。'),
            status=409,
        )

    return render(
        request,
        'ledger/accounting.html',
        _accounting_context(flash_message=f'{account.name} の残高照合を登録しました。'),
    )


@login_required
@require_http_methods(['POST'])
def monthly_closing_delete(request: HttpRequest, pk: int) -> HttpResponse:
    """月次締めを取り消す（誤って締めた場合の救済）。
    削除は物理削除。AuditLog に必ず DELETE を残す。
    """
    closing = get_object_or_404(MonthlyClosing, pk=pk)
    month_label = month_param(closing.month)
    target_id = str(closing.pk)
    target_repr = str(closing)
    closing_balance = closing.closing_balance
    closing.delete()
    # delete 後の record_audit (target_id を保持)
    record_audit(
        request,
        AuditLog.Action.DELETE,
        closing,
        f'{month_label} の月次締めを取消しました。',
        {'month': month_label, 'closing_balance': closing_balance, 'reason': 'manual_unlock'},
        target_id=target_id, target_repr=target_repr,
    )
    return render(
        request,
        'ledger/accounting.html',
        _accounting_context(flash_message=f'{month_label} の月次締めを取消しました。再度締め直すか、当月の取引を編集できます。'),
    )


@login_required
@require_http_methods(['POST'])
def monthly_closing_resnapshot(request: HttpRequest, pk: int) -> HttpResponse:
    """既存の月次締めを現在の帳簿で再スナップショット（drift 解消）。
    対象月の現在の集計値で opening_carry / income / expense / net /
    closing_balance / account_balances を上書きする。
    """
    closing = get_object_or_404(MonthlyClosing, pk=pk)
    month_label = month_param(closing.month)
    snapshot = build_monthly_closing_snapshot(closing.month)
    closing.opening_carry = snapshot['opening_carry']
    closing.income = snapshot['income']
    closing.expense = snapshot['expense']
    closing.net = snapshot['net']
    closing.closing_balance = snapshot['closing_balance']
    closing.account_balances = snapshot['account_balances']
    closing.save()
    record_audit(
        request,
        AuditLog.Action.UPDATE,
        closing,
        f'{month_label} の月次締めを再スナップショットしました。',
        {'month': month_label, 'closing_balance': snapshot['closing_balance'], 'reason': 'resnapshot'},
    )
    return render(
        request,
        'ledger/accounting.html',
        _accounting_context(flash_message=f'{month_label} の月次締めを再計算しました。'),
    )


@login_required
@require_http_methods(['POST'])
def reconciliation_delete(request: HttpRequest, pk: int) -> HttpResponse:
    """口座残高照合を取り消す（誤入力時の救済）。"""
    item = get_object_or_404(AccountReconciliation, pk=pk)
    target_id = str(item.pk)
    target_repr = str(item)
    label = f'{item.reconciled_on:%Y-%m-%d} {item.account.name}'
    item.delete()
    record_audit(
        request,
        AuditLog.Action.DELETE,
        item,
        f'{label} の照合を取消しました。',
        {'reason': 'manual_unlock'},
        target_id=target_id, target_repr=target_repr,
    )
    return render(
        request,
        'ledger/accounting.html',
        _accounting_context(flash_message=f'{label} の照合を取消しました。'),
    )