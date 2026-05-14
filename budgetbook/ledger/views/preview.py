"""取引フォーム入力中の即時プレビュー API。
HTMX が金額・カテゴリ入力に応じて呼び出し、
「保存後の今月の支出/収入合計」「重複候補の警告」を返す。
"""
from __future__ import annotations

from datetime import date, datetime

from django.contrib.auth.decorators import login_required
from django.db.models import Sum
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_http_methods

from ..models import Category, Transaction
from ..services.dates import shift_month


@login_required
@require_http_methods(['POST'])
def transaction_preview(request: HttpRequest) -> HttpResponse:
    """フォーム入力値から、保存した場合の月次合計と重複警告を返す。"""
    raw_amount = (request.POST.get('amount') or '').strip()
    raw_date = (request.POST.get('date') or '').strip()
    raw_category = (request.POST.get('category') or '').strip()
    raw_account = (request.POST.get('account') or '').strip()
    raw_description = (request.POST.get('description') or '').strip()

    # 入力値の正規化
    try:
        amount = int(raw_amount) if raw_amount else 0
    except (TypeError, ValueError):
        amount = 0
    try:
        entry_date = datetime.strptime(raw_date, '%Y-%m-%d').date() if raw_date else date.today()
    except (TypeError, ValueError):
        entry_date = date.today()
    try:
        category_id = int(raw_category) if raw_category else None
    except (TypeError, ValueError):
        category_id = None

    category = Category.objects.filter(pk=category_id).first() if category_id else None
    kind = category.kind if category else 'expense'

    # 当月の現状合計
    month_start = entry_date.replace(day=1)
    month_end = shift_month(month_start, 1)
    monthly_qs = Transaction.objects.filter(date__gte=month_start, date__lt=month_end)
    current_income = monthly_qs.filter(category__kind=Category.Kind.INCOME).aggregate(
        total=Sum('amount')
    )['total'] or 0
    current_expense = monthly_qs.filter(category__kind=Category.Kind.EXPENSE).aggregate(
        total=Sum('amount')
    )['total'] or 0

    new_income = current_income + (amount if kind == 'income' and amount > 0 else 0)
    new_expense = current_expense + (amount if kind == 'expense' and amount > 0 else 0)
    new_net = new_income - new_expense

    # 重複候補検出: 同日 + 同金額 + 同カテゴリ
    duplicates = []
    if amount > 0 and category_id:
        duplicates = list(
            Transaction.objects.filter(
                date=entry_date,
                amount=amount,
                category_id=category_id,
            ).select_related('category', 'account')[:3]
        )

    return render(request, 'ledger/partials/transaction_preview.html', {
        'amount': amount,
        'kind': kind,
        'category': category,
        'entry_date': entry_date,
        'month_label': month_start,
        'current_income': current_income,
        'current_expense': current_expense,
        'new_income': new_income,
        'new_expense': new_expense,
        'new_net': new_net,
        'duplicates': duplicates,
        'has_input': amount > 0 and category_id is not None,
    })