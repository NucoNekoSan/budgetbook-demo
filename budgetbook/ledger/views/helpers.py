from __future__ import annotations

import logging
from datetime import date

from django.conf import settings
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.urls import reverse

from ..forms import TransactionForm, TransferForm
from ..models import AuditLog, MonthlyClosing, Transaction, Transfer

audit_logger = logging.getLogger('budgetbook.audit')
from ..services.dashboard import get_dashboard_context
from ..services.dates import (
    clamp_future_month,
    default_transaction_date,
    month_param,
    parse_month,
)


def _client_ip(request: HttpRequest) -> str:
    """Resolve client IP. Trust X-Forwarded-For only when proxy is trusted (TRUST_PROXY_SSL)."""
    if getattr(settings, 'SECURE_PROXY_SSL_HEADER', None):
        forwarded = request.META.get('HTTP_X_FORWARDED_FOR', '')
        if forwarded:
            return forwarded.split(',')[0].strip()[:64]
    return (request.META.get('REMOTE_ADDR') or '')[:64]


def record_audit(
    request: HttpRequest,
    action: str,
    target,
    summary: str = '',
    metadata: dict | None = None,
    target_id: str | None = None,
    target_repr: str | None = None,
) -> None:
    user = request.user if getattr(request, 'user', None) and request.user.is_authenticated else None
    audit_metadata = dict(metadata or {})
    audit_metadata.setdefault('ip', _client_ip(request))
    audit_metadata.setdefault('user_agent', (request.META.get('HTTP_USER_AGENT') or '')[:200])
    resolved_target_id = target_id if target_id is not None else str(target.pk or '')
    resolved_target_repr = (target_repr if target_repr is not None else str(target))[:200]
    AuditLog.objects.create(
        user=user,
        action=action,
        target_model=target.__class__.__name__,
        target_id=resolved_target_id,
        target_repr=resolved_target_repr,
        summary=summary[:200],
        metadata=audit_metadata,
    )
    audit_logger.info(
        'audit',
        extra={
            'event': 'audit',
            'action': action,
            'target_model': target.__class__.__name__,
            'target_id': resolved_target_id,
            'user_id': getattr(user, 'pk', None),
            'username': getattr(user, 'username', None),
            'ip': audit_metadata.get('ip'),
            'user_agent': audit_metadata.get('user_agent'),
            'summary': summary[:200],
        },
    )


def build_transaction_form_context(
    target_month: date,
    form: TransactionForm | None = None,
    transaction: Transaction | None = None,
) -> dict:
    mp = month_param(target_month)
    monthly_closing = MonthlyClosing.objects.filter(month=target_month).first()
    if transaction:
        if form is None:
            form = TransactionForm(instance=transaction)
        return {
            'form': form,
            'form_mode': 'transaction',
            'month_param': mp,
            'form_action': f"{reverse('ledger:transaction_update', args=[transaction.pk])}?month={mp}",
            'form_title': '取引を編集',
            'submit_label': '更新する',
            'cancel_url': f"{reverse('ledger:transaction_create')}?month={mp}",
            'transaction': transaction,
            'form_month_closed': monthly_closing is not None,
            'form_monthly_closing': monthly_closing,
        }
    if form is None:
        form = TransactionForm(initial={'date': default_transaction_date(target_month)})
    return {
        'form': form,
        'form_mode': 'transaction',
        'month_param': mp,
        'form_action': f"{reverse('ledger:transaction_create')}?month={mp}",
        'form_title': '取引を追加',
        'submit_label': '保存する',
        'cancel_url': f"{reverse('ledger:transaction_create')}?month={mp}",
        'form_month_closed': monthly_closing is not None,
        'form_monthly_closing': monthly_closing,
    }


def build_transfer_form_context(
    target_month: date,
    form: TransferForm | None = None,
    transfer: Transfer | None = None,
) -> dict:
    mp = month_param(target_month)
    monthly_closing = MonthlyClosing.objects.filter(month=target_month).first()
    if transfer:
        if form is None:
            form = TransferForm(instance=transfer)
        return {
            'form': form,
            'form_mode': 'transfer',
            'month_param': mp,
            'form_action': f"{reverse('ledger:transfer_update', args=[transfer.pk])}?month={mp}",
            'form_title': '振替を編集',
            'submit_label': '更新する',
            'cancel_url': f"{reverse('ledger:transaction_create')}?month={mp}",
            'transfer': transfer,
            'form_month_closed': monthly_closing is not None,
            'form_monthly_closing': monthly_closing,
        }
    if form is None:
        form = TransferForm(initial={'date': default_transaction_date(target_month)})
    return {
        'form': form,
        'form_mode': 'transfer',
        'month_param': mp,
        'form_action': f"{reverse('ledger:transfer_create')}?month={mp}",
        'form_title': '振替を追加',
        'submit_label': '保存する',
        'cancel_url': f"{reverse('ledger:transaction_create')}?month={mp}",
        'form_month_closed': monthly_closing is not None,
        'form_monthly_closing': monthly_closing,
    }


# 後方互換用エイリアス
build_form_context = build_transaction_form_context


def render_dashboard_bundle(
    request: HttpRequest,
    target_month: date,
    flash_message: str,
    form_mode: str = 'transaction',
) -> HttpResponse:
    context = get_dashboard_context(target_month, page=1)
    if form_mode == 'transfer':
        context.update(build_transfer_form_context(target_month))
    else:
        context.update(build_transaction_form_context(target_month))
    context['flash_message'] = flash_message
    return render(request, 'ledger/partials/transaction_bundle.html', context)


def render_dashboard_section(
    request: HttpRequest,
    target_month: date,
    flash_message: str,
    row_id: str,
    filters: dict | None = None,
    page: int = 1,
    scroll_to: str | None = None,
) -> HttpResponse:
    context = get_dashboard_context(target_month, page=page, filters=filters or {})
    context['flash_message'] = flash_message
    context['row_id'] = row_id
    response = render(request, 'ledger/partials/dashboard_inline_success.html', context)
    response['HX-Retarget'] = '#dashboard-content'
    if scroll_to:
        response['HX-Reswap'] = f'innerHTML show:#{scroll_to}:top'
    else:
        response['HX-Reswap'] = 'innerHTML'
    return response


def render_dashboard_oob(
    request: HttpRequest,
    target_month: date,
    flash_message: str,
    filters: dict | None = None,
    page: int = 1,
) -> HttpResponse:
    context = get_dashboard_context(target_month, page=page, filters=filters or {})
    context['flash_message'] = flash_message
    return render(request, 'ledger/partials/dashboard_content_oob.html', context)


def closed_month_response(request: HttpRequest, target_month: date, message: str, status: int = 409) -> HttpResponse:
    if request.htmx:
        context = get_dashboard_context(target_month)
        context['flash_message'] = message
        return render(request, 'ledger/partials/dashboard_content_oob.html', context, status=status)
    return render(request, 'ledger/closed_month_error.html', {'message': message}, status=status)


def resolve_target_month_for_obj(request: HttpRequest, obj_date: date) -> date:
    raw = request.GET.get('month') or request.POST.get('month')
    if raw:
        return clamp_future_month(parse_month(raw))
    return clamp_future_month(parse_month(month_param(obj_date.replace(day=1))))


def inline_form_context(*, mode: str, instance, form, target_month: date, filters: dict, page: int = 1) -> dict:
    mp = month_param(target_month)
    if mode == 'transfer':
        action = reverse('ledger:transfer_inline_update', args=[instance.pk])
        cancel = reverse('ledger:transfer_inline_cancel', args=[instance.pk])
        row_id = f'inline-edit-tr-{instance.pk}'
    else:
        action = reverse('ledger:transaction_inline_update', args=[instance.pk])
        cancel = reverse('ledger:transaction_inline_cancel', args=[instance.pk])
        row_id = f'inline-edit-tx-{instance.pk}'
    return {
        'form': form,
        'form_mode': mode,
        'month_param': mp,
        'form_action': f'{action}?month={mp}',
        'cancel_action': f'{cancel}?month={mp}',
        'row_id': row_id,
        'instance': instance,
        'filter_q': filters.get('q', ''),
        'filter_account': filters.get('account', ''),
        'filter_category': filters.get('category', ''),
        'page': page,
    }