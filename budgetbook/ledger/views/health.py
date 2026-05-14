from __future__ import annotations

import logging

from django.db import DatabaseError, connection, transaction
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods

from ..models import MonthlyClosing
from ..services.closing import enrich_monthly_closings_with_drift

health_logger = logging.getLogger('budgetbook.health')


@require_http_methods(['GET'])
@never_cache
def healthz(request: HttpRequest) -> HttpResponse:
    """軽量ヘルスチェック。DB に SELECT 1 を投げて疎通だけ確認する。

    認証なし。Cloudflare Access / 内部ネットワーク前段で守る前提。
    監視ツールが頻繁に叩くため副作用なし・短時間で完結することを優先。

    `?verbose=1` で書込み試験（即ロールバック）と直近 1 件の月次締め整合性チェックを併走。
    `?verbose=1` は重いため監視ツールから叩かないこと。
    """
    try:
        with connection.cursor() as cur:
            cur.execute('SELECT 1')
            row = cur.fetchone()
        if not row or row[0] != 1:
            return JsonResponse({'status': 'error', 'detail': 'unexpected SELECT 1 result'}, status=500)
    except DatabaseError as exc:
        health_logger.error('healthz_db_select_failed', extra={'event': 'healthz', 'detail': str(exc)[:200]})
        return JsonResponse({'status': 'error', 'detail': str(exc)[:120]}, status=500)

    payload = {'status': 'ok'}

    if request.GET.get('verbose') == '1':
        # 書込み試験: TX 内で挿入し即ロールバック。データには痕跡を残さない。
        try:
            with transaction.atomic():
                with connection.cursor() as cur:
                    cur.execute('CREATE TEMP TABLE IF NOT EXISTS _healthz_probe (v INTEGER)')
                    cur.execute('INSERT INTO _healthz_probe (v) VALUES (1)')
                    cur.execute('SELECT v FROM _healthz_probe')
                    cur.fetchone()
                # ロールバックされる
                raise _Rollback()
        except _Rollback:
            payload['db_write'] = 'ok'
        except DatabaseError as exc:
            health_logger.error('healthz_db_write_failed', extra={'event': 'healthz', 'detail': str(exc)[:200]})
            return JsonResponse({'status': 'error', 'detail': f'db_write: {str(exc)[:120]}'}, status=500)

        # 会計整合性スポット: 直近 1 件のみチェック（多件は重い）
        latest = list(MonthlyClosing.objects.order_by('-month')[:1])
        if latest:
            checked = enrich_monthly_closings_with_drift(latest)
            payload['accounting'] = 'drift' if any(c.has_drift for c in checked) else 'ok'
            if payload['accounting'] == 'drift':
                health_logger.warning(
                    'healthz_accounting_drift',
                    extra={'event': 'healthz', 'month': latest[0].month.isoformat()},
                )
                return JsonResponse({**payload, 'status': 'degraded'}, status=200)
        else:
            payload['accounting'] = 'no_closings'

    return JsonResponse(payload)


class _Rollback(Exception):
    """healthz の書込み試験を強制ロールバックするための内部例外。"""
    pass