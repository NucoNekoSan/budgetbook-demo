from __future__ import annotations

import csv
from datetime import date

from django.contrib.auth.decorators import login_required
from django.db.models import IntegerField, Q, Sum, Value
from django.db.models.functions import Coalesce, TruncMonth
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_http_methods

from ..models import Category, InsurancePremium, Transaction
from ..services.csv_safe import csv_safe_row
from ..services.dates import (
    clamp_future_month,
    clamp_future_year,
    month_param,
    parse_month,
    parse_year,
    shift_month,
)
from ..services.groups import aggregate_with_groups, build_conic_gradient
from ..services.tax_report_v2 import build_tax_report_v2


def _build_annual_summary(year: int) -> list[dict]:
    start = date(year, 1, 1)
    end = date(year + 1, 1, 1)

    rows = (
        Transaction.objects
        .filter(date__gte=start, date__lt=end)
        .annotate(month=TruncMonth('date'))
        .values('month')
        .annotate(
            income=Coalesce(
                Sum('amount', filter=Q(category__kind=Category.Kind.INCOME)),
                Value(0, output_field=IntegerField()),
            ),
            expense=Coalesce(
                Sum('amount', filter=Q(category__kind=Category.Kind.EXPENSE)),
                Value(0, output_field=IntegerField()),
            ),
        )
        .order_by('month')
    )

    by_month = {row['month']: row for row in rows}
    result = []
    for m in range(1, 13):
        key = date(year, m, 1)
        row = by_month.get(key)
        inc = row['income'] if row else 0
        exp = row['expense'] if row else 0
        result.append({
            'month': m,
            'month_param': f'{year}-{m:02d}',
            'label': f'{m}月',
            'income': inc,
            'expense': exp,
            'net': inc - exp,
        })
    return result


@login_required
@require_http_methods(['GET'])
def expense_breakdown(request: HttpRequest) -> HttpResponse:
    today = date.today()
    year = clamp_future_year(parse_year(request.GET.get('year')))
    target_month = clamp_future_month(parse_month(request.GET.get('month')))

    expense_qs = Transaction.objects.filter(category__kind=Category.Kind.EXPENSE)

    m_start = target_month
    m_end = shift_month(target_month, 1)
    monthly_category_rows = list(
        expense_qs.filter(date__gte=m_start, date__lt=m_end)
        .values('category_id', 'category__name')
        .annotate(total=Sum('amount'))
        .order_by('-total')
    )
    monthly_rows = aggregate_with_groups(monthly_category_rows)
    monthly_total = sum(r['total'] for r in monthly_rows)

    y_start = date(year, 1, 1)
    y_end = date(year + 1, 1, 1)
    yearly_category_rows = list(
        expense_qs.filter(date__gte=y_start, date__lt=y_end)
        .values('category_id', 'category__name')
        .annotate(total=Sum('amount'))
        .order_by('-total')
    )
    yearly_rows = aggregate_with_groups(yearly_category_rows)
    yearly_total = sum(r['total'] for r in yearly_rows)

    # Section (大分類) 集計 — 月間
    section_rows_raw = list(
        expense_qs.filter(date__gte=m_start, date__lt=m_end)
        .values('category__section')
        .annotate(total=Sum('amount'))
        .order_by('-total')
    )
    section_label_map = dict(Category.Section.choices)
    section_rows = []
    section_total = sum((r['total'] or 0) for r in section_rows_raw)
    for row in section_rows_raw:
        key = row['category__section'] or 'other'
        amount = row['total'] or 0
        section_rows.append({
            'section': key,
            'label': section_label_map.get(key, key),
            'total': amount,
            'pct': round(amount / section_total * 100, 1) if section_total else 0,
        })

    monthly_income = (
        Transaction.objects.filter(
            category__kind=Category.Kind.INCOME,
            date__gte=m_start, date__lt=m_end,
        ).aggregate(total=Coalesce(Sum('amount'), Value(0, output_field=IntegerField())))['total']
    )
    income_ratio_rows = []
    income_ratio_chart = []
    has_income = monthly_income > 0
    is_over_spent = False
    overspent_amount = 0
    remainder = 0
    remainder_pct = 0

    if has_income:
        for r in monthly_rows:
            pct = round(r['total'] / monthly_income * 100, 1) if monthly_income else 0
            income_ratio_rows.append({
                'label': r['label'],
                'category__name': r['label'],
                'total': r['total'],
                'pct': pct,
                'kind': r['kind'],
            })
        if monthly_total > monthly_income:
            is_over_spent = True
            overspent_amount = monthly_total - monthly_income
            for r in monthly_rows:
                income_ratio_chart.append({
                    'label': r['label'],
                    'category__name': r['label'],
                    'total': r['total'],
                })
        else:
            remainder = monthly_income - monthly_total
            remainder_pct = round(remainder / monthly_income * 100, 1) if monthly_income else 0
            for r in monthly_rows:
                income_ratio_chart.append({
                    'label': r['label'],
                    'category__name': r['label'],
                    'total': r['total'],
                })
            if remainder > 0:
                income_ratio_chart.append({
                    'label': '残額',
                    'category__name': '残額',
                    'total': remainder,
                })

    next_month = shift_month(target_month, 1)
    return render(request, 'ledger/expense_breakdown.html', {
        'year': year,
        'target_month': target_month,
        'month_param': month_param(target_month),
        'prev_month_param': month_param(shift_month(target_month, -1)),
        'next_month_param': month_param(next_month) if target_month < clamp_future_month(next_month) else None,
        'prev_year': year - 1,
        'next_year': year + 1 if year < today.year else None,
        'monthly_rows': monthly_rows,
        'monthly_total': monthly_total,
        'section_rows': section_rows,
        'yearly_rows': yearly_rows,
        'yearly_total': yearly_total,
        'monthly_income': monthly_income,
        'has_income': has_income,
        'income_ratio_rows': income_ratio_rows,
        'income_ratio_chart': income_ratio_chart,
        'income_ratio_pie_style': build_conic_gradient(income_ratio_chart),
        'is_over_spent': is_over_spent,
        'overspent_amount': overspent_amount,
        'remainder': remainder,
        'remainder_pct': remainder_pct,
    })


@login_required
@require_http_methods(['GET'])
def annual(request: HttpRequest) -> HttpResponse:
    year = clamp_future_year(parse_year(request.GET.get('year')))
    months = _build_annual_summary(year)

    total_income = sum(m['income'] for m in months)
    total_expense = sum(m['expense'] for m in months)
    total_net = total_income - total_expense

    # Section (大分類) 年間集計
    y_start = date(year, 1, 1)
    y_end = date(year + 1, 1, 1)
    annual_section_raw = list(
        Transaction.objects.filter(
            category__kind=Category.Kind.EXPENSE,
            date__gte=y_start, date__lt=y_end,
        )
        .values('category__section')
        .annotate(total=Sum('amount'))
        .order_by('-total')
    )
    section_label_map = dict(Category.Section.choices)
    section_total = sum((r['total'] or 0) for r in annual_section_raw)
    annual_section_rows = []
    for row in annual_section_raw:
        key = row['category__section'] or 'other'
        amount = row['total'] or 0
        annual_section_rows.append({
            'section': key,
            'label': section_label_map.get(key, key),
            'total': amount,
            'pct': round(amount / section_total * 100, 1) if section_total else 0,
        })

    today = date.today()
    prev_year = year - 1
    next_year = year + 1 if year < today.year else None

    return render(request, 'ledger/annual.html', {
        'year': year,
        'months': months,
        'total_income': total_income,
        'total_expense': total_expense,
        'total_net': total_net,
        'prev_year': prev_year,
        'next_year': next_year,
        'annual_trend': months,
        'annual_section_rows': annual_section_rows,
    })


# v1.13.0: 確定申告レポート（税控除タグ集計）
_TAX_TAG_LABEL = dict(Category.TaxTag.choices)
_VALID_TAX_TAGS = {value for value, _label in Category.TaxTag.choices if value != Category.TaxTag.NONE}
_MEDICAL_DEDUCTION_THRESHOLD = 100000  # 医療費控除の最低ライン（10 万円 or 所得 5%）


def _resolve_tax_tag(raw: str | None) -> str:
    if raw in _VALID_TAX_TAGS:
        return raw
    return Category.TaxTag.MEDICAL


def _resolve_year(raw: str | None) -> int:
    today = date.today()
    if not raw:
        return today.year
    try:
        return int(raw)
    except (TypeError, ValueError):
        return today.year


def _query_tax_transactions(year: int, tax_tag: str):
    return (
        Transaction.objects
        .select_related('category', 'account')
        .filter(
            date__year=year,
            category__tax_tag=tax_tag,
            category__kind=Category.Kind.EXPENSE,
        )
        .order_by('date', 'id')
    )


@login_required
@require_http_methods(['GET'])
def tax_deductions(request: HttpRequest) -> HttpResponse:
    year = _resolve_year(request.GET.get('year'))
    tax_tag = _resolve_tax_tag(request.GET.get('tax_tag'))
    transactions = list(_query_tax_transactions(year, tax_tag))
    total = sum(t.amount for t in transactions)

    medical_remaining = None
    if tax_tag == Category.TaxTag.MEDICAL:
        medical_remaining = max(0, _MEDICAL_DEDUCTION_THRESHOLD - total)

    today = date.today()
    return render(request, 'ledger/tax_deductions.html', {
        'year': year,
        'tax_tag': tax_tag,
        'tax_tag_label': _TAX_TAG_LABEL.get(tax_tag, tax_tag),
        'tax_tag_choices': [
            (value, label) for value, label in Category.TaxTag.choices
            if value != Category.TaxTag.NONE
        ],
        'transactions': transactions,
        'count': len(transactions),
        'total': total,
        'medical_remaining': medical_remaining,
        'medical_threshold': _MEDICAL_DEDUCTION_THRESHOLD,
        'prev_year': year - 1,
        'next_year': year + 1 if year < today.year else None,
        'csv_url': f'/reports/tax-deductions.csv?year={year}&tax_tag={tax_tag}',
    })


@login_required
@require_http_methods(['GET'])
def tax_deductions_csv(request: HttpRequest) -> HttpResponse:
    year = _resolve_year(request.GET.get('year'))
    tax_tag = _resolve_tax_tag(request.GET.get('tax_tag'))
    transactions = list(_query_tax_transactions(year, tax_tag))

    filename = f'tax-{tax_tag}-{year}.csv'
    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    response.write('﻿')  # UTF-8 BOM

    writer = csv.writer(response)
    writer.writerow(csv_safe_row(['日付', '支払先', 'カテゴリ', '金額', 'メモ']))
    for tx in transactions:
        writer.writerow(csv_safe_row([
            tx.date.strftime('%Y-%m-%d'),
            tx.description,
            tx.category.name,
            tx.amount,
            tx.memo,
        ]))
    return response


# ---------------------------------------------------------------------------
# v1.18.0: 確定申告レポート v2（医療費 + 生保 + 地震 + 寄附金 統合）
# ---------------------------------------------------------------------------

_MEDICAL_CATEGORY_LABEL = None  # 遅延 import: 循環参照回避


def _life_per_category_rows(insurance_summary):
    """生命保険料 3 枠の表示用行を組み立てる。"""
    cat_label = dict(InsurancePremium.InsuranceCategory.choices)
    rows = []
    for cat in [
        InsurancePremium.InsuranceCategory.LIFE_GENERAL,
        InsurancePremium.InsuranceCategory.LIFE_CARE_MEDICAL,
        InsurancePremium.InsuranceCategory.LIFE_ANNUITY,
    ]:
        row = insurance_summary.life['per_category'].get(cat, {})
        rows.append({
            'label': cat_label[cat],
            'new_paid': row.get('new_paid', 0),
            'old_paid': row.get('old_paid', 0),
            'deduction': row.get('deduction', 0),
        })
    return rows


@login_required
@require_http_methods(['GET'])
def tax_deductions_v2(request: HttpRequest) -> HttpResponse:
    year = _resolve_year(request.GET.get('year'))
    exclude_year_end = request.GET.get('exclude_year_end', '1') == '1'
    summary = build_tax_report_v2(year, exclude_year_end_adjusted=exclude_year_end)

    today = date.today()
    return render(request, 'ledger/tax_deductions_v2.html', {
        'year': year,
        'exclude_year_end': exclude_year_end,
        'summary': summary,
        'life_rows': _life_per_category_rows(summary.insurance),
        'prev_year': year - 1,
        'next_year': year + 1 if year < today.year else None,
        'csv_url': (
            f'/reports/tax-deductions/v2.csv'
            f'?year={year}&exclude_year_end={"1" if exclude_year_end else "0"}'
        ),
    })


@login_required
@require_http_methods(['GET'])
def tax_deductions_v2_csv(request: HttpRequest) -> HttpResponse:
    year = _resolve_year(request.GET.get('year'))
    exclude_year_end = request.GET.get('exclude_year_end', '1') == '1'
    summary = build_tax_report_v2(year, exclude_year_end_adjusted=exclude_year_end)

    # 遅延 import で循環参照回避
    from ..models import MedicalExpense
    medical_category_label = dict(MedicalExpense.MedicalCategory.choices)
    ins_cat_label = dict(InsurancePremium.InsuranceCategory.choices)
    ins_contract_label = dict(InsurancePremium.ContractType.choices)

    filename = f'tax-report-v2-{year}.csv'
    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    response.write('﻿')

    writer = csv.writer(response)

    # ---- 医療費控除 ----
    writer.writerow(csv_safe_row(['【医療費控除】']))
    writer.writerow(csv_safe_row(['支払日', '受診者', '医療機関', '区分', '支払額', '補填額', '差引']))
    medical_qs = MedicalExpense.objects.filter(paid_date__year=year).order_by('paid_date', 'id')
    for e in medical_qs:
        writer.writerow(csv_safe_row([
            e.paid_date.strftime('%Y-%m-%d'),
            e.patient,
            e.provider,
            medical_category_label.get(e.category, e.category),
            e.amount,
            e.reimbursement,
            e.net_amount,
        ]))
    writer.writerow(csv_safe_row(['【医療費控除 支払合計】', '', '', '', summary.medical.total_paid, '', '']))
    writer.writerow(csv_safe_row(['【医療費控除 補填合計】', '', '', '', '', summary.medical.total_reimbursement, '']))
    writer.writerow(csv_safe_row(['【医療費控除 控除基準額】', '', '', '', '', '', summary.medical.threshold]))
    writer.writerow(csv_safe_row(['【医療費控除 控除額（申告書 第二表 ⑩）】', '', '', '', '', '', summary.medical.deduction]))
    writer.writerow([])

    # ---- 生命保険料控除 ----
    writer.writerow(csv_safe_row(['【生命保険料控除】（年調済除外: ' + ('はい' if exclude_year_end else 'いいえ') + '）']))
    writer.writerow(csv_safe_row(['枠', '新契約支払', '旧契約支払', '控除額']))
    for row in _life_per_category_rows(summary.insurance):
        writer.writerow(csv_safe_row([row['label'], row['new_paid'], row['old_paid'], row['deduction']]))
    writer.writerow(csv_safe_row(['【3 枠合計（上限前）】', '', '', summary.insurance.life['raw_sum']]))
    writer.writerow(csv_safe_row(['【生命保険料控除 合計（申告書 第二表 ⑮）】', '', '', summary.insurance.life['total']]))
    writer.writerow([])

    # ---- 地震保険料控除 ----
    writer.writerow(csv_safe_row(['【地震保険料控除】']))
    writer.writerow(csv_safe_row(['保険会社', '年間支払額', '控除額（行単位）']))
    eq_qs = InsurancePremium.objects.filter(
        year=year,
        category=InsurancePremium.InsuranceCategory.EARTHQUAKE,
    )
    if exclude_year_end:
        eq_qs = eq_qs.filter(submitted_in_year_end_adjustment=False)
    for ip in eq_qs:
        writer.writerow(csv_safe_row([ip.insurer, ip.annual_amount, min(ip.annual_amount, 50_000)]))
    writer.writerow(csv_safe_row(['【地震保険料控除 支払合計】', summary.insurance.earthquake['paid'], '']))
    writer.writerow(csv_safe_row(['【地震保険料控除 合計（申告書 第二表 ⑯）】', '', summary.insurance.earthquake['deduction']]))
    writer.writerow([])

    # ---- 寄附金（参考） ----
    writer.writerow(csv_safe_row(['【寄附金（参考、控除額は別途計算）】']))
    writer.writerow(csv_safe_row(['日付', '支払先', 'カテゴリ', '金額']))
    for tx in summary.donation['transactions']:
        writer.writerow(csv_safe_row([
            tx.date.strftime('%Y-%m-%d'),
            tx.description,
            tx.category.name,
            tx.amount,
        ]))
    writer.writerow(csv_safe_row(['【寄附金 年間支払合計（参考、申告書 ⑲は別途計算）】', '', '', summary.donation['total']]))
    writer.writerow([])

    # ---- 総計 ----
    writer.writerow(csv_safe_row(['【総控除額（医療費 + 生保 + 地震、寄附金除く）】', '', '', summary.grand_deduction_total]))

    return response