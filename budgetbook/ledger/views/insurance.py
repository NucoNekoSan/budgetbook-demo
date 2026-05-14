"""生命保険料控除・地震保険料控除関連 view (v1.17.0)。

- /insurance-premiums/?year=YYYY 一覧 + 集計
- /insurance-premiums/new/, <pk>/edit/, <pk>/delete/ CRUD
- /insurance-premiums.csv?year=YYYY CSV エクスポート
"""
from __future__ import annotations

import csv
from datetime import date

from django.contrib.auth.decorators import login_required
from django.db import transaction as db_transaction
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from ..forms import InsurancePremiumForm
from ..models import InsurancePremium
from ..services.csv_safe import csv_safe_row
from ..services.dates import clamp_future_year, parse_year
from ..services.insurance import (
    calc_life_new,
    calc_life_old,
    calculate_insurance_deduction,
)
from .helpers import record_audit


def _resolve_year(raw: str | None) -> int:
    return clamp_future_year(parse_year(raw))


def _insurer_suggestions(year: int) -> list[str]:
    """過去 3 年の保険会社名を distinct で取得（入力補完用）。"""
    return list(
        InsurancePremium.objects
        .filter(year__gte=year - 3)
        .order_by()
        .values_list('insurer', flat=True)
        .distinct()[:30]
    )


def _per_row_deduction(item: InsurancePremium) -> int:
    """1 件単独の控除額（CSV/明細表示用、合算前）。"""
    if item.category == InsurancePremium.InsuranceCategory.EARTHQUAKE:
        return min(item.annual_amount, 50_000)
    if item.contract_type == InsurancePremium.ContractType.NEW:
        return calc_life_new(item.annual_amount)
    return calc_life_old(item.annual_amount)


# ---------------------------------------------------------------------------
# 一覧 + 集計
# ---------------------------------------------------------------------------

@login_required
@require_http_methods(['GET'])
def insurance_premium_list(request: HttpRequest) -> HttpResponse:
    year = _resolve_year(request.GET.get('year'))
    exclude_year_end = request.GET.get('exclude_year_end') == '1'
    items = list(
        InsurancePremium.objects.filter(year=year).order_by('category', 'id')
    )
    for item in items:
        item.per_row_deduction = _per_row_deduction(item)

    summary = calculate_insurance_deduction(year, exclude_year_end_adjusted=exclude_year_end)
    today = date.today()

    # 区分ラベル map（template で表示用）
    cat_label_map = dict(InsurancePremium.InsuranceCategory.choices)
    life_per_category = []
    for cat in [
        InsurancePremium.InsuranceCategory.LIFE_GENERAL,
        InsurancePremium.InsuranceCategory.LIFE_CARE_MEDICAL,
        InsurancePremium.InsuranceCategory.LIFE_ANNUITY,
    ]:
        row = summary.life['per_category'].get(cat, {})
        life_per_category.append({
            'label': cat_label_map[cat],
            'new_paid': row.get('new_paid', 0),
            'old_paid': row.get('old_paid', 0),
            'deduction': row.get('deduction', 0),
        })

    return render(request, 'ledger/insurance_premium_list.html', {
        'year': year,
        'items': items,
        'summary': summary,
        'life_per_category': life_per_category,
        'exclude_year_end': exclude_year_end,
        'prev_year': year - 1,
        'next_year': year + 1 if year < today.year else None,
        'csv_url': f'{reverse("ledger:insurance_premium_csv")}?year={year}',
    })


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

@login_required
@require_http_methods(['GET', 'POST'])
def insurance_premium_create(request: HttpRequest) -> HttpResponse:
    year = _resolve_year(request.GET.get('year'))
    if request.method == 'POST':
        form = InsurancePremiumForm(request.POST)
        if form.is_valid():
            with db_transaction.atomic():
                instance = form.save()
                record_audit(
                    request,
                    'create',
                    instance,
                    summary=f'保険料控除を登録: {instance.year} {instance.get_category_display()} {instance.insurer} ¥{instance.annual_amount:,}',
                    metadata={'source': 'insurance_premium_create'},
                )
            return HttpResponseRedirect(f'{reverse("ledger:insurance_premium_list")}?year={instance.year}')
    else:
        form = InsurancePremiumForm(initial={'year': year})
    return render(request, 'ledger/insurance_premium_form.html', {
        'form': form,
        'mode': 'create',
        'year': year,
        'insurer_suggestions': _insurer_suggestions(year),
        'form_action': reverse('ledger:insurance_premium_create'),
        'cancel_url': f'{reverse("ledger:insurance_premium_list")}?year={year}',
    })


@login_required
@require_http_methods(['GET', 'POST'])
def insurance_premium_update(request: HttpRequest, pk: int) -> HttpResponse:
    instance = get_object_or_404(InsurancePremium, pk=pk)
    year = instance.year
    if request.method == 'POST':
        form = InsurancePremiumForm(request.POST, instance=instance)
        if form.is_valid():
            with db_transaction.atomic():
                updated = form.save()
                record_audit(
                    request,
                    'update',
                    updated,
                    summary=f'保険料控除を更新: {updated.year} {updated.get_category_display()} {updated.insurer} ¥{updated.annual_amount:,}',
                    metadata={'source': 'insurance_premium_update'},
                )
            return HttpResponseRedirect(f'{reverse("ledger:insurance_premium_list")}?year={updated.year}')
    else:
        form = InsurancePremiumForm(instance=instance)
    return render(request, 'ledger/insurance_premium_form.html', {
        'form': form,
        'mode': 'edit',
        'year': year,
        'instance': instance,
        'insurer_suggestions': _insurer_suggestions(year),
        'form_action': reverse('ledger:insurance_premium_update', args=[pk]),
        'cancel_url': f'{reverse("ledger:insurance_premium_list")}?year={year}',
    })


@login_required
@require_http_methods(['POST'])
def insurance_premium_delete(request: HttpRequest, pk: int) -> HttpResponse:
    instance = get_object_or_404(InsurancePremium, pk=pk)
    year = instance.year
    repr_str = str(instance)
    instance_id = instance.pk
    with db_transaction.atomic():
        instance.delete()
        record_audit(
            request,
            'delete',
            instance,
            summary=f'保険料控除を削除: {repr_str}',
            target_id=str(instance_id),
            target_repr=repr_str,
            metadata={'source': 'insurance_premium_delete'},
        )
    return HttpResponseRedirect(f'{reverse("ledger:insurance_premium_list")}?year={year}')


# ---------------------------------------------------------------------------
# CSV
# ---------------------------------------------------------------------------

_CATEGORY_LABEL = dict(InsurancePremium.InsuranceCategory.choices)
_CONTRACT_LABEL = dict(InsurancePremium.ContractType.choices)


@login_required
@require_http_methods(['GET'])
def insurance_premium_csv(request: HttpRequest) -> HttpResponse:
    year = _resolve_year(request.GET.get('year'))
    exclude_year_end = request.GET.get('exclude_year_end') == '1'
    items = list(
        InsurancePremium.objects.filter(year=year).order_by('category', 'id')
    )
    summary = calculate_insurance_deduction(year, exclude_year_end_adjusted=exclude_year_end)

    filename = f'insurance-premiums-{year}.csv'
    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    response.write('﻿')  # UTF-8 BOM

    writer = csv.writer(response)
    writer.writerow(csv_safe_row([
        '区分', '契約区分', '保険会社名', '証券番号',
        '年間支払保険料', '行単独控除額', '年末調整提出済',
    ]))
    for item in items:
        contract_label = '' if item.category == InsurancePremium.InsuranceCategory.EARTHQUAKE else _CONTRACT_LABEL.get(item.contract_type, '')
        writer.writerow(csv_safe_row([
            _CATEGORY_LABEL.get(item.category, item.category),
            contract_label,
            item.insurer,
            item.policy_number,
            item.annual_amount,
            _per_row_deduction(item),
            'Y' if item.submitted_in_year_end_adjustment else '',
        ]))

    # フッター（合算後の控除額）
    writer.writerow([])
    cat_label = dict(InsurancePremium.InsuranceCategory.choices)
    for cat_key in [
        InsurancePremium.InsuranceCategory.LIFE_GENERAL,
        InsurancePremium.InsuranceCategory.LIFE_CARE_MEDICAL,
        InsurancePremium.InsuranceCategory.LIFE_ANNUITY,
    ]:
        row = summary.life['per_category'].get(cat_key, {})
        writer.writerow(csv_safe_row([
            f'【{cat_label[cat_key]} 枠 控除額】', '', '', '', '', row.get('deduction', 0), '',
        ]))
    writer.writerow(csv_safe_row([
        '【生命保険料控除 合計（上限 12 万円）】', '', '', '', '', summary.life['total'], '',
    ]))
    writer.writerow(csv_safe_row([
        '【地震保険料控除 合計（上限 5 万円）】', '', '', '', '', summary.earthquake['deduction'], '',
    ]))
    writer.writerow(csv_safe_row([
        '【総控除額】', '', '', '', '', summary.grand_total, '',
    ]))
    return response