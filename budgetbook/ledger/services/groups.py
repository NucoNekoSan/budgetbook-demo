from __future__ import annotations

from ..models import ExpenseGroupCategory


def build_category_membership_map() -> dict:
    """category_id -> {'group_id', 'group_name', 'sort_order'} (active group のみ)。"""
    mapping = {}
    qs = ExpenseGroupCategory.objects.select_related('group').filter(group__is_active=True)
    for m in qs:
        mapping[m.category_id] = {
            'group_id': m.group_id,
            'group_name': m.group.name,
            'sort_order': m.group.sort_order,
        }
    return mapping


def aggregate_with_groups(category_rows: list) -> list:
    """category_id, category__name, total を持つ行を、active group で合算する。"""
    membership = build_category_membership_map()
    groups: dict = {}
    individuals = []
    for row in category_rows:
        info = membership.get(row['category_id'])
        if info:
            g = groups.setdefault(info['group_id'], {
                'label': info['group_name'],
                'category__name': info['group_name'],
                'total': 0,
                'kind': 'group',
                'sort_order': info['sort_order'],
                'members': [],
            })
            g['total'] += row['total']
            g['members'].append({
                'category_id': row['category_id'],
                'category__name': row['category__name'],
                'total': row['total'],
            })
        else:
            individuals.append({
                'label': row['category__name'],
                'category__name': row['category__name'],
                'category_id': row['category_id'],
                'total': row['total'],
                'kind': 'category',
            })

    combined = list(groups.values()) + individuals
    combined.sort(key=lambda r: r['total'], reverse=True)
    total = sum(r['total'] for r in combined)
    for r in combined:
        r['pct'] = round(r['total'] / total * 100, 1) if total else 0
    return combined


def build_conic_gradient(rows: list[dict]) -> str:
    PIE_COLORS = [
        '#ef4444', '#f97316', '#eab308', '#22c55e', '#14b8a6',
        '#3b82f6', '#8b5cf6', '#ec4899', '#6366f1', '#0ea5e9',
        '#f43f5e', '#a855f7', '#84cc16', '#06b6d4', '#d946ef',
    ]
    total = sum(int(row.get('total') or 0) for row in rows)
    if total <= 0:
        return 'conic-gradient(#e5e7eb 0% 100%)'

    parts = []
    cursor = 0.0
    last_index = len(rows) - 1
    for i, row in enumerate(rows):
        amount = int(row.get('total') or 0)
        if amount <= 0:
            continue
        start = cursor
        end = 100.0 if i == last_index else cursor + (amount / total * 100)
        color = PIE_COLORS[i % len(PIE_COLORS)]
        parts.append(f'{color} {start:.4f}% {end:.4f}%')
        cursor = end
    return f"conic-gradient({', '.join(parts)})" if parts else 'conic-gradient(#e5e7eb 0% 100%)'