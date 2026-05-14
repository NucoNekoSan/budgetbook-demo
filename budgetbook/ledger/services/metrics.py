"""観測メトリクス集計サービス。

/metrics エンドポイント用。生取引データは扱わず集計値のみ返す。
v1.10.0 仕様: docs/specs/v1.10.0_observability.md
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from django.db.models import Count, Q
from django.utils import timezone

from ..models import (
    Account,
    AccountReconciliation,
    AuditLog,
    Category,
    MonthlyClosing,
    Transaction,
    Transfer,
)
from .balance import all_account_balances
from .dates import month_end

METRICS_VERSION = '1.10.0'


def _safe_axes_counts() -> dict[str, int]:
    """axes が無効化されている場合でも壊れないように。"""
    try:
        from axes.models import AccessAttempt, AccessLog  # noqa: F401
    except Exception:
        return {'recent_failed_logins_24h': 0, 'currently_locked_usernames': 0}
    now = timezone.now()
    cutoff = now - timedelta(hours=24)
    try:
        failed = AccessAttempt.objects.filter(attempt_time__gte=cutoff).count()
    except Exception:
        failed = 0
    try:
        # axes 5.x+ では AccessAttempt 行があれば locked と見なせる
        locked = AccessAttempt.objects.filter(failures_since_start__gt=0).values('username').distinct().count()
    except Exception:
        locked = 0
    return {'recent_failed_logins_24h': failed, 'currently_locked_usernames': locked}


def build_metrics(now: date | None = None) -> dict[str, Any]:
    today = now or timezone.localdate()
    month_start = today.replace(day=1)
    m_end = month_end(month_start)

    acct_agg = Account.objects.aggregate(
        total=Count('pk'),
        asset=Count('pk', filter=Q(kind=Account.Kind.ASSET)),
        liability=Count('pk', filter=Q(kind=Account.Kind.LIABILITY)),
        active=Count('pk', filter=Q(is_active=True)),
    )
    cat_agg = Category.objects.aggregate(
        total=Count('pk'),
        expense=Count('pk', filter=Q(kind=Category.Kind.EXPENSE)),
        income=Count('pk', filter=Q(kind=Category.Kind.INCOME)),
        active=Count('pk', filter=Q(is_active=True)),
    )

    tx_total = Transaction.objects.count()
    tx_this_month = Transaction.objects.filter(
        date__gte=month_start, date__lte=m_end,
    ).count()
    tr_total = Transfer.objects.count()
    tr_this_month = Transfer.objects.filter(
        date__gte=month_start, date__lte=m_end,
    ).count()

    audit_cutoff = timezone.now() - timedelta(days=7)
    audit_total = AuditLog.objects.count()
    audit_recent = AuditLog.objects.filter(created_at__gte=audit_cutoff).count()

    balances = all_account_balances(today)
    asset_pks = set(
        Account.objects.filter(kind=Account.Kind.ASSET).values_list('pk', flat=True)
    )
    asset_total = sum(b for pk, b in balances.items() if pk in asset_pks)
    liability_total = sum(b for pk, b in balances.items() if pk not in asset_pks)

    return {
        'version': METRICS_VERSION,
        'generated_at': timezone.now().isoformat(),
        'counts': {
            'accounts': acct_agg,
            'categories': cat_agg,
            'transactions': {'total': tx_total, 'this_month': tx_this_month},
            'transfers': {'total': tr_total, 'this_month': tr_this_month},
            'monthly_closings': MonthlyClosing.objects.count(),
            'reconciliations': AccountReconciliation.objects.count(),
            'audit_logs': {'total': audit_total, 'last_7_days': audit_recent},
        },
        'balances': {
            'asset_total': int(asset_total),
            'liability_total': int(liability_total),
            'net_worth': int(asset_total + liability_total),
        },
        'axes': _safe_axes_counts(),
    }