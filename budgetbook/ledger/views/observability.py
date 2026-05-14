"""観測性: /metrics JSON + /settings/login-history/ ビュー。

v1.10.0 仕様: docs/specs/v1.10.0_observability.md
"""
from __future__ import annotations

import json
from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from ..services.metrics import build_metrics

LOGIN_HISTORY_DAYS = 30
LOGIN_HISTORY_PER_PAGE = 50


@login_required
@require_GET
@never_cache
def metrics(request: HttpRequest) -> HttpResponse:
    body = json.dumps(build_metrics(), ensure_ascii=False)
    return HttpResponse(body, content_type='application/json; charset=utf-8')


@login_required
@require_GET
def login_history(request: HttpRequest) -> HttpResponse:
    try:
        from axes.models import AccessAttempt, AccessLog
    except Exception:
        return render(request, 'ledger/login_history.html', {
            'rows': [],
            'unavailable': True,
        })

    cutoff = timezone.now() - timedelta(days=LOGIN_HISTORY_DAYS)
    successes = AccessLog.objects.filter(attempt_time__gte=cutoff)
    failures = AccessAttempt.objects.filter(attempt_time__gte=cutoff)

    rows = []
    for s in successes:
        rows.append({
            'when': s.attempt_time,
            'kind': 'success',
            'username': s.username or '',
            'ip': s.ip_address or '',
            'user_agent': (s.user_agent or '')[:80],
            'path': (s.path_info or '')[:100],
            'failures': 0,
        })
    for f in failures:
        rows.append({
            'when': f.attempt_time,
            'kind': 'failure',
            'username': f.username or '',
            'ip': f.ip_address or '',
            'user_agent': (f.user_agent or '')[:80],
            'path': (f.path_info or '')[:100],
            'failures': f.failures_since_start,
        })
    rows.sort(key=lambda r: r['when'], reverse=True)

    page = request.GET.get('page', 1)
    paginator = Paginator(rows, LOGIN_HISTORY_PER_PAGE)
    page_obj = paginator.get_page(page)
    return render(request, 'ledger/login_history.html', {
        'page_obj': page_obj,
        'days': LOGIN_HISTORY_DAYS,
        'unavailable': False,
    })