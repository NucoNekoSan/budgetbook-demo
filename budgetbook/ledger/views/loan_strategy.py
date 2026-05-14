"""返済戦略ビュー。"""
from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_http_methods

from ..services.loan_strategy import compare_strategies


@login_required
@require_http_methods(['GET'])
def loan_strategy_view(request: HttpRequest) -> HttpResponse:
    try:
        monthly_extra = int(request.GET.get('extra', '0'))
    except (TypeError, ValueError):
        monthly_extra = 0
    monthly_extra = max(0, min(monthly_extra, 1_000_000))

    base = compare_strategies(monthly_extra=0)
    if monthly_extra > 0:
        boosted = compare_strategies(monthly_extra=monthly_extra)
    else:
        boosted = None

    return render(request, 'ledger/loan_strategy.html', {
        'base': base,
        'boosted': boosted,
        'monthly_extra': monthly_extra,
    })