from __future__ import annotations

import csv

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_http_methods

from ..models import Category, Transaction, Transfer
from ..services.csv_safe import csv_safe_row
from ..services.dashboard import get_dashboard_context
from ..services.dates import clamp_future_month, month_param, parse_month, shift_month
from ..services.filters import parse_filters
from .helpers import build_form_context


@login_required
@require_http_methods(['GET'])
def dashboard(request: HttpRequest) -> HttpResponse:
    target_month = clamp_future_month(parse_month(request.GET.get('month')))
    page = request.GET.get('page', 1)
    filters = parse_filters(request.GET)
    context = get_dashboard_context(target_month, page=page, filters=filters)
    if request.htmx:
        return render(request, 'ledger/partials/dashboard_content.html', context)
    context.update(build_form_context(target_month))
    return render(request, 'ledger/dashboard.html', context)


@login_required
@require_http_methods(['GET'])
def category_options(request: HttpRequest) -> HttpResponse:
    kind = request.GET.get('kind', Category.Kind.EXPENSE)
    if kind not in Category.Kind.values:
        kind = Category.Kind.EXPENSE
    categories = Category.objects.filter(is_active=True, kind=kind).order_by('name')
    return render(request, 'ledger/partials/category_options.html', {'categories': categories})


@login_required
@require_http_methods(['GET'])
def transaction_export(request: HttpRequest) -> HttpResponse:
    target_month = clamp_future_month(parse_month(request.GET.get('month')))
    start = target_month
    end = shift_month(target_month, 1)

    transactions = list(
        Transaction.objects.select_related('account', 'category')
        .filter(date__gte=start, date__lt=end)
    )
    transfers = list(
        Transfer.objects.select_related('from_account', 'to_account')
        .filter(date__gte=start, date__lt=end)
    )

    rows = []
    for tx in transactions:
        rows.append((tx.date, tx.id, 'tx', tx))
    for tr in transfers:
        rows.append((tr.date, tr.id, 'tr', tr))
    rows.sort(key=lambda r: (r[0], r[1]))

    filename = f'kakeibo-{month_param(target_month)}.csv'
    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    response.write('﻿')  # UTF-8 BOM (Excel で開いたとき文字化けしない)

    writer = csv.writer(response)
    writer.writerow(csv_safe_row(['日付', '種別', '口座', 'カテゴリ', '金額', '摘要', 'メモ']))
    for _d, _id, kind, obj in rows:
        if kind == 'tx':
            writer.writerow(csv_safe_row([
                obj.date.strftime('%Y-%m-%d'),
                obj.category.get_kind_display(),
                obj.account.name,
                obj.category.name,
                obj.amount,
                obj.description,
                obj.memo,
            ]))
        else:
            writer.writerow(csv_safe_row([
                obj.date.strftime('%Y-%m-%d'),
                '振替',
                f'{obj.from_account.name} → {obj.to_account.name}',
                '振替',
                obj.amount,
                obj.description,
                obj.memo,
            ]))

    return response