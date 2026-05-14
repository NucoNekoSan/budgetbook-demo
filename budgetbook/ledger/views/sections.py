"""カテゴリの大分類 (section) 一括編集ビュー。"""
from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_http_methods

from ..models import AuditLog, Category
from .helpers import record_audit


@login_required
@require_http_methods(['GET', 'POST'])
def sections_bulk_edit(request: HttpRequest) -> HttpResponse:
    if request.method == 'POST':
        valid_sections = {v for v, _ in Category.Section.choices}
        valid_tags = {v for v, _ in Category.TaxTag.choices}
        changes = []
        with transaction.atomic():
            for cat in Category.objects.filter(is_active=True):
                section_key = f'section_{cat.pk}'
                tag_key = f'tax_tag_{cat.pk}'
                new_section = request.POST.get(section_key)
                new_tag = request.POST.get(tag_key)
                changed = False
                if new_section in valid_sections and new_section != cat.section:
                    old_section = cat.section
                    cat.section = new_section
                    changed = True
                    changes.append(f'{cat.name}: section {old_section} → {new_section}')
                if new_tag in valid_tags and new_tag != cat.tax_tag:
                    old_tag = cat.tax_tag
                    cat.tax_tag = new_tag
                    changed = True
                    changes.append(f'{cat.name}: tax_tag {old_tag} → {new_tag}')
                if changed:
                    cat.save()
        if changes:
            # 一括変更を 1 件の AuditLog にまとめる
            placeholder = Category(name='一括', kind='expense')
            record_audit(
                request,
                AuditLog.Action.UPDATE,
                placeholder,
                f'カテゴリの大分類/税タグを一括更新（{len(changes)} 件）',
                {'changes': changes[:50]},  # 大量の場合は最初の 50 件のみ
                target_id='bulk', target_repr='カテゴリ大分類一括更新',
            )
        flash = f'{len(changes)} 件の変更を保存しました。' if changes else '変更はありませんでした。'
        return _render(request, flash=flash)
    return _render(request)


def _render(request: HttpRequest, flash: str = '') -> HttpResponse:
    expense_categories = (
        Category.objects.filter(is_active=True, kind=Category.Kind.EXPENSE)
        .order_by('section', 'name')
    )
    income_categories = (
        Category.objects.filter(is_active=True, kind=Category.Kind.INCOME)
        .order_by('name')
    )
    section_choices = Category.Section.choices
    tax_choices = Category.TaxTag.choices

    # section ごとにグルーピング表示
    grouped = {}
    section_label = dict(section_choices)
    for cat in expense_categories:
        grouped.setdefault(cat.section, []).append(cat)
    grouped_rows = []
    # 整列: choices の順番で
    for sec_value, sec_label in section_choices:
        if sec_value in grouped:
            grouped_rows.append({
                'section': sec_value,
                'label': sec_label,
                'categories': grouped[sec_value],
            })

    return render(request, 'ledger/sections_edit.html', {
        'grouped_rows': grouped_rows,
        'income_categories': income_categories,
        'section_choices': section_choices,
        'tax_choices': tax_choices,
        'flash': flash,
    })