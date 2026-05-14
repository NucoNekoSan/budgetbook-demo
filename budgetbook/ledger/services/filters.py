from __future__ import annotations

from urllib.parse import quote


def parse_filters(params: dict) -> dict:
    filters = {}
    q = params.get('q', '').strip()
    if q:
        filters['q'] = q
    account = params.get('account', '').strip()
    if account:
        try:
            filters['account'] = int(account)
        except (TypeError, ValueError):
            pass
    category = params.get('category', '').strip()
    if category:
        try:
            filters['category'] = int(category)
        except (TypeError, ValueError):
            pass
    return filters


def parse_preserved_filters(params: dict) -> dict:
    filters = {}
    q = params.get('filter_q', '').strip()
    if q:
        filters['q'] = q
    account = params.get('filter_account', '').strip()
    if account:
        try:
            filters['account'] = int(account)
        except (TypeError, ValueError):
            pass
    category = params.get('filter_category', '').strip()
    if category:
        try:
            filters['category'] = int(category)
        except (TypeError, ValueError):
            pass
    return filters


def build_filter_query_string(filters: dict) -> str:
    parts = []
    if filters.get('q'):
        parts.append(f"q={quote(filters['q'])}")
    if filters.get('account'):
        parts.append(f"account={filters['account']}")
    if filters.get('category'):
        parts.append(f"category={filters['category']}")
    return '&'.join(parts)