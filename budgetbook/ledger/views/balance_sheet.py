"""個人 B/S（貸借対照表）ビュー。

資産 − 負債 = 正味財産 を月末断面で表示する。
"""
from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.db.models import Sum
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_http_methods

from ..models import Category, Transaction
from ..services.balance import balance_sheet
from ..services.dates import (
    clamp_future_month,
    month_end,
    month_param,
    parse_month,
    shift_month,
)


@login_required
@require_http_methods(['GET'])
def balance_sheet_view(request: HttpRequest) -> HttpResponse:
    target_month = clamp_future_month(parse_month(request.GET.get('month')))
    m_end = month_end(target_month)
    bs = balance_sheet(m_end)

    # 税控除タグ別の年初〜月末集計（簡易）
    y_start = target_month.replace(month=1, day=1)
    tag_label_map = dict(Category.TaxTag.choices)
    tax_summary_raw = (
        Transaction.objects
        .filter(date__gte=y_start, date__lte=m_end)
        .exclude(category__tax_tag=Category.TaxTag.NONE)
        .values('category__tax_tag')
        .annotate(total=Sum('amount'))
        .order_by('-total')
    )
    tax_summary = [
        {
            'tag': row['category__tax_tag'],
            'label': tag_label_map.get(row['category__tax_tag'], row['category__tax_tag']),
            'total': row['total'] or 0,
        }
        for row in tax_summary_raw
    ]

    next_month = shift_month(target_month, 1)
    return render(request, 'ledger/balance_sheet.html', {
        'target_month': target_month,
        'month_param': month_param(target_month),
        'prev_month_param': month_param(shift_month(target_month, -1)),
        'next_month_param': month_param(next_month) if target_month < clamp_future_month(next_month) else None,
        'm_end': m_end,
        'bs': bs,
        'tax_summary': tax_summary,
        'year_start': y_start,
    })