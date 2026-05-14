"""月次予算 (SectionBudget) の編集ビュー。"""
from __future__ import annotations

from datetime import date

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_http_methods

from ..models import AuditLog, Category, SectionBudget
from ..services.budget import _previous_month_section_budgets, section_budget_summary
from ..services.dates import (
    clamp_future_month,
    month_param,
    parse_month,
    shift_month,
)
from .helpers import record_audit


@login_required
@require_http_methods(['GET', 'POST'])
def budget_edit(request: HttpRequest) -> HttpResponse:
    target_month = clamp_future_month(parse_month(request.GET.get('month') or request.POST.get('month')))

    if request.method == 'POST':
        # まとめて upsert: section ごとに input name="amount_<section>"
        action = request.POST.get('action', 'save')
        if action == 'copy_prev':
            prev_budgets = _previous_month_section_budgets(target_month)
            count = 0
            for section, amount in prev_budgets.items():
                obj, created = SectionBudget.objects.update_or_create(
                    month=target_month, section=section,
                    defaults={'amount': amount},
                )
                count += 1
            record_audit(
                request, AuditLog.Action.UPDATE,
                SectionBudget(month=target_month, section='all', amount=0),
                f'{month_param(target_month)} の予算を前月から複製しました（{count} 件）。',
                {'month': month_param(target_month), 'count': count, 'reason': 'copy_prev'},
                target_id=f'{month_param(target_month)}/all', target_repr=f'{month_param(target_month)} 予算 (一括)',
            )
            return _render_budget_page(request, target_month, flash=f'前月から {count} 件の予算を複製しました。')

        # 通常保存
        saved = 0
        for section_value, _ in Category.Section.choices:
            raw = request.POST.get(f'amount_{section_value}', '').strip()
            if raw == '':
                # 空入力 → 既存があれば削除
                SectionBudget.objects.filter(month=target_month, section=section_value).delete()
                continue
            try:
                amount = int(raw)
            except (TypeError, ValueError):
                continue
            if amount < 0:
                continue
            SectionBudget.objects.update_or_create(
                month=target_month, section=section_value,
                defaults={'amount': amount},
            )
            saved += 1
        record_audit(
            request, AuditLog.Action.UPDATE,
            SectionBudget(month=target_month, section='all', amount=0),
            f'{month_param(target_month)} の予算を保存しました（{saved} 件）。',
            {'month': month_param(target_month), 'saved': saved},
            target_id=f'{month_param(target_month)}/all', target_repr=f'{month_param(target_month)} 予算 (一括)',
        )
        return _render_budget_page(request, target_month, flash=f'{saved} 件の予算を保存しました。')

    return _render_budget_page(request, target_month)


def _render_budget_page(request: HttpRequest, target_month: date, flash: str = '') -> HttpResponse:
    summary = section_budget_summary(target_month)
    # 全 section をフォーム表示 (空白 input 含む)
    existing = {
        b.section: b.amount
        for b in SectionBudget.objects.filter(month=target_month)
    }
    prev_existing = _previous_month_section_budgets(target_month)
    rows = []
    for section_value, section_label in Category.Section.choices:
        rows.append({
            'section': section_value,
            'label': section_label,
            'amount': existing.get(section_value, 0),
            'has_budget': section_value in existing,
            'prev_amount': prev_existing.get(section_value, 0),
        })
    next_month = shift_month(target_month, 1)
    return render(request, 'ledger/budget_edit.html', {
        'target_month': target_month,
        'month_param': month_param(target_month),
        'prev_month_param': month_param(shift_month(target_month, -1)),
        'next_month_param': month_param(next_month) if target_month < clamp_future_month(next_month) else None,
        'rows': rows,
        'summary': summary,
        'flash': flash,
        'has_prev': bool(prev_existing),
    })