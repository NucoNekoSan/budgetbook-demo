from __future__ import annotations

from calendar import monthrange
from datetime import date


def parse_month(month_str: str | None) -> date:
    today = date.today()
    if not month_str:
        return date(today.year, today.month, 1)
    try:
        year, month = month_str.split('-')
        return date(int(year), int(month), 1)
    except (TypeError, ValueError):
        return date(today.year, today.month, 1)


def shift_month(target: date, offset: int) -> date:
    year = target.year + ((target.month - 1 + offset) // 12)
    month = ((target.month - 1 + offset) % 12) + 1
    return date(year, month, 1)


def month_end(target: date) -> date:
    return date(target.year, target.month, monthrange(target.year, target.month)[1])


def month_param(target: date) -> str:
    return target.strftime('%Y-%m')


def clamp_future_month(target: date) -> date:
    today = date.today()
    current_month = date(today.year, today.month, 1)
    return min(target, current_month)


def month_from_entry_date(entry_date: date) -> date:
    return clamp_future_month(date(entry_date.year, entry_date.month, 1))


def default_transaction_date(target: date) -> date:
    today = date.today()
    if today.year == target.year and today.month == target.month:
        return today
    return target


def parse_year(year_str: str | None) -> int:
    today = date.today()
    if not year_str:
        return today.year
    try:
        return int(year_str)
    except (TypeError, ValueError):
        return today.year


def clamp_future_year(year: int) -> int:
    return min(year, date.today().year)