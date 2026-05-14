"""月次予算 vs 実績の集計。"""
from __future__ import annotations

from datetime import date

from django.db.models import Sum

from ..models import Category, SectionBudget, Transaction
from .dates import shift_month


def _previous_month_section_budgets(target_month: date) -> dict[str, int]:
    """前月の予算を引継ぎ用に取得。"""
    prev = shift_month(target_month, -1)
    return {
        b.section: b.amount
        for b in SectionBudget.objects.filter(month=prev)
    }


def section_budget_summary(target_month: date) -> dict:
    """対象月の section 別予算と実績、超過率を集計。

    返り値:
      {
        'rows': [{
          'section': 'food_daily',
          'label': '食品・日用品',
          'budget': 50000,    # 0 なら未設定
          'spent': 32500,
          'remaining': 17500,
          'pct': 65,           # 0 なら未設定なので bar 出さない
          'over': False,
          'has_budget': True,
        }, ...],
        'total_budget': int,
        'total_spent': int,
        'total_remaining': int,
        'total_pct': int,
        'over_sections': int,  # 超過してる section 数
        'unset_sections': [labels],  # 予算未設定の section
      }
    """
    start = target_month
    end = shift_month(target_month, 1)
    label_map = dict(Category.Section.choices)

    # 当月の予算
    budgets = {b.section: b for b in SectionBudget.objects.filter(month=target_month)}

    # 当月の section 別支出
    spent_raw = (
        Transaction.objects.filter(
            category__kind=Category.Kind.EXPENSE,
            date__gte=start, date__lt=end,
        )
        .values('category__section')
        .annotate(total=Sum('amount'))
    )
    spent_map = {row['category__section'] or 'other': int(row['total'] or 0) for row in spent_raw}

    rows = []
    total_budget = 0
    total_spent = 0
    over_count = 0
    unset = []
    for section_value, section_label in Category.Section.choices:
        budget_obj = budgets.get(section_value)
        budget = budget_obj.amount if budget_obj else 0
        spent = spent_map.get(section_value, 0)
        has_budget = budget > 0
        if has_budget:
            pct = int(spent / budget * 100) if budget else 0
            remaining = budget - spent
            over = spent > budget
            if over:
                over_count += 1
        else:
            pct = 0
            remaining = -spent
            over = False
            if spent > 0:
                # 予算未設定なのに支出が出ている section は注意喚起対象
                unset.append(section_label)
        # spent==0 かつ予算未設定の section は表示しない (ノイズ削減)
        if not has_budget and spent == 0:
            continue
        rows.append({
            'section': section_value,
            'label': section_label,
            'budget': budget,
            'spent': spent,
            'remaining': remaining,
            'pct': min(pct, 200),  # bar の最大は 200% で打切り
            'pct_for_display': pct,
            'over': over,
            'has_budget': has_budget,
        })
        total_budget += budget
        total_spent += spent

    total_remaining = total_budget - total_spent
    total_pct = int(total_spent / total_budget * 100) if total_budget else 0

    return {
        'rows': rows,
        'total_budget': total_budget,
        'total_spent': total_spent,
        'total_remaining': total_remaining,
        'total_pct': total_pct,
        'over_sections': over_count,
        'unset_sections': unset,
        'has_any_budget': total_budget > 0,
    }