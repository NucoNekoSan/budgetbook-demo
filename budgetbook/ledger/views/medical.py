"""医療費控除関連 view (v1.16.0)。

- /medical-expenses/ 一覧 + 集計
- /medical-expenses/new/ 追加
- /medical-expenses/<pk>/edit/ 編集
- /medical-expenses/<pk>/delete/ 削除
- /medical-expenses.csv CSV エクスポート（国税庁様式準拠）
- /settings/income-snapshots/ 年次総所得 upsert
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

from ..forms import AnnualIncomeSnapshotForm, MedicalExpenseForm
from ..models import AnnualIncomeSnapshot, MedicalExpense
from ..services.csv_safe import csv_safe_row
from ..services.dates import clamp_future_year, parse_year
from ..services.medical import (
    calculate_medical_deduction,
    group_by_patient,
    group_by_provider,
)
from .helpers import record_audit


# ---------------------------------------------------------------------------
# 一覧 / CRUD
# ---------------------------------------------------------------------------

def _resolve_year(raw: str | None) -> int:
    return clamp_future_year(parse_year(raw))


def _patient_suggestions(year: int) -> list[str]:
    """直近年の受診者値を distinct で取得（入力補完用）。"""
    return list(
        MedicalExpense.objects
        .filter(paid_date__year__gte=year - 1)
        .order_by()
        .values_list('patient', flat=True)
        .distinct()[:30]
    )


@login_required
@require_http_methods(['GET'])
def medical_expense_list(request: HttpRequest) -> HttpResponse:
    year = _resolve_year(request.GET.get('year'))
    expenses = list(
        MedicalExpense.objects
        .select_related('transaction', 'transaction__category')
        .filter(paid_date__year=year)
        .order_by('paid_date', 'id')
    )
    summary = calculate_medical_deduction(year)
    today = date.today()
    return render(request, 'ledger/medical_expense_list.html', {
        'year': year,
        'expenses': expenses,
        'summary': summary,
        'patient_rows': group_by_patient(expenses),
        'provider_rows': group_by_provider(expenses),
        'prev_year': year - 1,
        'next_year': year + 1 if year < today.year else None,
        'csv_url': f'{reverse("ledger:medical_expense_csv")}?year={year}',
    })


@login_required
@require_http_methods(['GET', 'POST'])
def medical_expense_create(request: HttpRequest) -> HttpResponse:
    year = _resolve_year(request.GET.get('year'))
    if request.method == 'POST':
        form = MedicalExpenseForm(request.POST)
        if form.is_valid():
            with db_transaction.atomic():
                instance = form.save()
                record_audit(
                    request,
                    'create',
                    instance,
                    summary=f'医療費を登録: {instance.patient} / {instance.provider} ¥{instance.amount:,}',
                    metadata={'source': 'medical_expense_create'},
                )
            return HttpResponseRedirect(f'{reverse("ledger:medical_expense_list")}?year={instance.paid_date.year}')
    else:
        form = MedicalExpenseForm(initial={'paid_date': date(year, date.today().month, date.today().day) if year == date.today().year else date(year, 12, 31)})
    return render(request, 'ledger/medical_expense_form.html', {
        'form': form,
        'mode': 'create',
        'year': year,
        'patient_suggestions': _patient_suggestions(year),
        'form_action': reverse('ledger:medical_expense_create'),
        'cancel_url': f'{reverse("ledger:medical_expense_list")}?year={year}',
    })


@login_required
@require_http_methods(['GET', 'POST'])
def medical_expense_update(request: HttpRequest, pk: int) -> HttpResponse:
    instance = get_object_or_404(MedicalExpense, pk=pk)
    year = instance.paid_date.year
    if request.method == 'POST':
        form = MedicalExpenseForm(request.POST, instance=instance)
        if form.is_valid():
            with db_transaction.atomic():
                updated = form.save()
                record_audit(
                    request,
                    'update',
                    updated,
                    summary=f'医療費を更新: {updated.patient} / {updated.provider} ¥{updated.amount:,}',
                    metadata={'source': 'medical_expense_update'},
                )
            return HttpResponseRedirect(f'{reverse("ledger:medical_expense_list")}?year={updated.paid_date.year}')
    else:
        form = MedicalExpenseForm(instance=instance)
    return render(request, 'ledger/medical_expense_form.html', {
        'form': form,
        'mode': 'edit',
        'year': year,
        'instance': instance,
        'patient_suggestions': _patient_suggestions(year),
        'form_action': reverse('ledger:medical_expense_update', args=[pk]),
        'cancel_url': f'{reverse("ledger:medical_expense_list")}?year={year}',
    })


@login_required
@require_http_methods(['POST'])
def medical_expense_delete(request: HttpRequest, pk: int) -> HttpResponse:
    instance = get_object_or_404(MedicalExpense, pk=pk)
    year = instance.paid_date.year
    repr_str = str(instance)
    instance_id = instance.pk
    with db_transaction.atomic():
        instance.delete()
        record_audit(
            request,
            'delete',
            instance,
            summary=f'医療費を削除: {repr_str}',
            target_id=str(instance_id),
            target_repr=repr_str,
            metadata={'source': 'medical_expense_delete'},
        )
    return HttpResponseRedirect(f'{reverse("ledger:medical_expense_list")}?year={year}')


# ---------------------------------------------------------------------------
# CSV エクスポート
# ---------------------------------------------------------------------------

_CATEGORY_LABEL = dict(MedicalExpense.MedicalCategory.choices)


@login_required
@require_http_methods(['GET'])
def medical_expense_csv(request: HttpRequest) -> HttpResponse:
    year = _resolve_year(request.GET.get('year'))
    expenses = list(
        MedicalExpense.objects
        .filter(paid_date__year=year)
        .order_by('paid_date', 'id')
    )
    summary = calculate_medical_deduction(year)

    filename = f'medical-expenses-{year}.csv'
    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    response.write('﻿')  # UTF-8 BOM

    writer = csv.writer(response)
    # 国税庁「医療費控除の明細書」様式準拠の列順
    writer.writerow(csv_safe_row([
        '医療を受けた方の氏名',
        '病院・薬局などの支払先の名称',
        '医療費の区分',
        '支払った医療費の額',
        '左のうち、補填される金額',
        '差引額',
        '支払日',
    ]))
    for e in expenses:
        writer.writerow(csv_safe_row([
            e.patient,
            e.provider,
            _CATEGORY_LABEL.get(e.category, e.category),
            e.amount,
            e.reimbursement,
            e.net_amount,
            e.paid_date.strftime('%Y-%m-%d'),
        ]))

    # フッター: 合計 + 控除額
    writer.writerow([])
    writer.writerow(csv_safe_row(['【合計】', '', '', summary.total_paid, summary.total_reimbursement, summary.net_paid, '']))
    writer.writerow(csv_safe_row(['【控除基準額】', '', '', '', '', summary.threshold, '']))
    writer.writerow(csv_safe_row(['【医療費控除額】', '', '', '', '', summary.deduction, '']))
    return response


# ---------------------------------------------------------------------------
# AnnualIncomeSnapshot
# ---------------------------------------------------------------------------

@login_required
@require_http_methods(['GET'])
def income_snapshot_list(request: HttpRequest) -> HttpResponse:
    snapshots = list(AnnualIncomeSnapshot.objects.order_by('-year'))
    form = AnnualIncomeSnapshotForm(initial={'year': date.today().year})
    return render(request, 'ledger/income_snapshot.html', {
        'snapshots': snapshots,
        'form': form,
    })


@login_required
@require_http_methods(['POST'])
def income_snapshot_save(request: HttpRequest) -> HttpResponse:
    year_raw = request.POST.get('year', '').strip()
    try:
        year_value = int(year_raw)
    except (TypeError, ValueError):
        return HttpResponseRedirect(reverse('ledger:income_snapshot_list'))

    existing = AnnualIncomeSnapshot.objects.filter(year=year_value).first()
    form = AnnualIncomeSnapshotForm(request.POST, instance=existing)
    if form.is_valid():
        with db_transaction.atomic():
            instance = form.save()
            record_audit(
                request,
                'update' if existing else 'create',
                instance,
                summary=f'年次所得を{"更新" if existing else "登録"}: {instance.year}年 ¥{instance.gross_income:,}',
                metadata={'source': 'income_snapshot_save'},
            )
        return HttpResponseRedirect(reverse('ledger:income_snapshot_list'))

    snapshots = list(AnnualIncomeSnapshot.objects.order_by('-year'))
    return render(request, 'ledger/income_snapshot.html', {
        'snapshots': snapshots,
        'form': form,
    })


@login_required
@require_http_methods(['POST'])
def income_snapshot_delete(request: HttpRequest, pk: int) -> HttpResponse:
    instance = get_object_or_404(AnnualIncomeSnapshot, pk=pk)
    repr_str = str(instance)
    instance_id = instance.pk
    with db_transaction.atomic():
        instance.delete()
        record_audit(
            request,
            'delete',
            instance,
            summary=f'年次所得を削除: {repr_str}',
            target_id=str(instance_id),
            target_repr=repr_str,
            metadata={'source': 'income_snapshot_delete'},
        )
    return HttpResponseRedirect(reverse('ledger:income_snapshot_list'))


# ---------------------------------------------------------------------------
# 取引フォーム HTMX 拡張用 partial
# ---------------------------------------------------------------------------

@login_required
@require_http_methods(['GET'])
def transaction_medical_fields(request: HttpRequest) -> HttpResponse:
    """取引フォームでカテゴリが tax_tag=MEDICAL の場合に展開する partial。

    tax_tag != MEDICAL の場合は空の div を返す（フィールド非表示）。
    """
    from ..models import Category
    cat_id = (request.GET.get('category') or request.GET.get('category_id') or '').strip()
    show = False
    if cat_id:
        try:
            cat = Category.objects.filter(pk=int(cat_id)).first()
        except (TypeError, ValueError):
            cat = None
        if cat and cat.tax_tag == Category.TaxTag.MEDICAL:
            show = True
    return render(request, 'ledger/partials/medical_fields.html', {
        'show': show,
        'category_choices': MedicalExpense.MedicalCategory.choices,
    })