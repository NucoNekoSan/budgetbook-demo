from __future__ import annotations

from calendar import monthrange
from datetime import date, timedelta

from django.core.paginator import Paginator
from django.db.models import IntegerField, Q, Sum, Value
from django.db.models.functions import Coalesce

from ..models import Account, Category, MonthlyClosing, Transaction, Transfer
from .balance import all_account_balances
from .budget import section_budget_summary
from .dates import clamp_future_month, month_end, month_param, shift_month
from .filters import build_filter_query_string

TRANSACTIONS_PER_PAGE = 20


def _merge_rows(tx_qs, transfer_qs) -> list:
    rows = []
    for tx in tx_qs:
        tx.row_type = 'transaction'
        rows.append(tx)
    for tr in transfer_qs:
        tr.row_type = 'transfer'
        rows.append(tr)
    rows.sort(key=lambda r: (r.date, r.id), reverse=True)
    return rows


def _build_daily_trend(target_month: date) -> list[dict]:
    start = target_month
    end = shift_month(target_month, 1)
    num_days = monthrange(target_month.year, target_month.month)[1]

    rows = (
        Transaction.objects
        .filter(date__gte=start, date__lt=end)
        .values('date')
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
        .order_by('date')
    )

    by_day = {row['date']: row for row in rows}
    result = []
    for d in range(1, num_days + 1):
        key = date(target_month.year, target_month.month, d)
        row = by_day.get(key)
        inc = row['income'] if row else 0
        exp = row['expense'] if row else 0
        result.append({
            'label': f'{d}日',
            'income': inc,
            'expense': exp,
            'net': inc - exp,
        })
    return result


def get_dashboard_context(target_month: date, page: int = 1, filters: dict | None = None) -> dict:
    start = target_month
    end = shift_month(target_month, 1)

    base_qs = Transaction.objects.select_related('account', 'category')
    monthly_qs = base_qs.filter(date__gte=start, date__lt=end)

    income = monthly_qs.filter(category__kind=Category.Kind.INCOME).aggregate(
        total=Coalesce(Sum('amount'), Value(0, output_field=IntegerField()))
    )['total']
    expense = monthly_qs.filter(category__kind=Category.Kind.EXPENSE).aggregate(
        total=Coalesce(Sum('amount'), Value(0, output_field=IntegerField()))
    )['total']
    net = income - expense

    expense_by_category = list(
        monthly_qs.filter(category__kind=Category.Kind.EXPENSE)
        .values('category__name')
        .annotate(total=Sum('amount'))
        .order_by('-total', 'category__name')[:8]
    )

    section_label_map = dict(Category.Section.choices)
    expense_by_section = []
    section_total = 0
    for row in (
        monthly_qs.filter(category__kind=Category.Kind.EXPENSE)
        .values('category__section')
        .annotate(total=Sum('amount'))
        .order_by('-total')
    ):
        amount = int(row['total'] or 0)
        key = row['category__section'] or 'other'
        expense_by_section.append({
            'section': key,
            'label': section_label_map.get(key, key),
            'total': amount,
        })
        section_total += amount
    for r in expense_by_section:
        r['pct'] = round(r['total'] / section_total * 100, 1) if section_total else 0

    m_end = month_end(target_month)
    prev_day = start - timedelta(days=1)
    has_accounts = Account.objects.exists()
    opening_balances = all_account_balances(prev_day) if has_accounts else {}
    closing_balances = all_account_balances(m_end) if has_accounts else {}
    # 家計簿ページの「月末残高」「月初繰越」は手元現金感を優先して資産口座のみで集計。
    # 負債（クレジットカード・ローン等）は /balance-sheet/ で確認する役割分離。
    asset_pks = set(
        Account.objects.filter(kind=Account.Kind.ASSET).values_list('pk', flat=True)
    )
    opening_carry = sum(b for pk, b in opening_balances.items() if pk in asset_pks)
    closing_balance = sum(b for pk, b in closing_balances.items() if pk in asset_pks)
    has_liabilities = Account.objects.filter(kind=Account.Kind.LIABILITY).exists()

    account_balances = []
    for acct in Account.objects.filter(is_active=True, kind=Account.Kind.ASSET).order_by('name'):
        acct.current_balance = closing_balances.get(acct.pk, acct.opening_balance)
        account_balances.append(acct)

    all_accounts = list(Account.objects.filter(is_active=True).order_by('name'))
    all_categories = list(Category.objects.filter(is_active=True).order_by('kind', 'name'))

    if not filters:
        filters = {}

    transfer_qs = Transfer.objects.select_related('from_account', 'to_account').filter(
        date__gte=start, date__lt=end,
    )
    filtered_tx_qs = monthly_qs
    if filters.get('q'):
        filtered_tx_qs = filtered_tx_qs.filter(description__icontains=filters['q'])
        transfer_qs = transfer_qs.filter(description__icontains=filters['q'])
    if filters.get('account'):
        filtered_tx_qs = filtered_tx_qs.filter(account_id=filters['account'])
        transfer_qs = transfer_qs.filter(
            Q(from_account_id=filters['account']) | Q(to_account_id=filters['account'])
        )
    if filters.get('category'):
        filtered_tx_qs = filtered_tx_qs.filter(category_id=filters['category'])
        transfer_qs = transfer_qs.none()

    combined_rows = _merge_rows(filtered_tx_qs, transfer_qs)

    is_filtered = bool(filters)
    filter_qs = build_filter_query_string(filters)

    paginator = Paginator(combined_rows, TRANSACTIONS_PER_PAGE)
    page_obj = paginator.get_page(page)

    next_month = shift_month(target_month, 1)
    prev_month_param = month_param(shift_month(target_month, -1))
    next_month_param_val = None if target_month >= clamp_future_month(next_month) else month_param(next_month)

    prev_month_url = f"month={prev_month_param}"
    if filter_qs:
        prev_month_url += f"&{filter_qs}"
    next_month_url = None
    if next_month_param_val:
        next_month_url = f"month={next_month_param_val}"
        if filter_qs:
            next_month_url += f"&{filter_qs}"

    return {
        'target_month': target_month,
        'month_param': month_param(target_month),
        'previous_month_query': prev_month_url,
        'next_month_query': next_month_url,
        'income': income,
        'expense': expense,
        'net': net,
        'page_obj': page_obj,
        'expense_by_category': expense_by_category,
        'expense_by_section': expense_by_section,
        'budget_summary': section_budget_summary(target_month),
        'account_balances': account_balances,
        'has_accounts': bool(all_accounts),
        'has_categories': bool(all_categories),
        'filter_q': filters.get('q', ''),
        'filter_account': filters.get('account', ''),
        'filter_category': filters.get('category', ''),
        'filter_qs': filter_qs,
        'is_filtered': is_filtered,
        'all_accounts': all_accounts,
        'all_categories': all_categories,
        'daily_trend': _build_daily_trend(target_month),
        'opening_carry': opening_carry,
        'closing_balance': closing_balance,
        'has_liabilities': has_liabilities,
        'monthly_closing': MonthlyClosing.objects.filter(month=target_month).first(),
    }