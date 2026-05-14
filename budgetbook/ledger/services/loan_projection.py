"""単一負債口座の完済予測 (auto payoff projection)。

`/loan-strategy/` が複数ローン横断の戦略比較を扱うのに対し、本サービスは
口座 1 つを単独でシミュレーションし、現在の monthly_payment を維持した
場合に「あと N ヶ月で完済 / 想定総利息」を計算する。

v1.15.0 (spec: docs/specs/v1.15.0_auto_payoff_projection.md)
"""
from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date
from typing import Optional

from ..models import Account, LoanProfile
from .balance import all_account_balances


MAX_MONTHS = 600


@dataclass
class _ProjectionInput:
    owed: int
    annual_rate_bp: int
    monthly_payment: int
    payment_day: int | None


def _next_payment_date(as_of: date, payment_day: int) -> date:
    """as_of 以後で最も近い payment_day。payment_day=0 は月末。

    as_of 当日が payment_day なら as_of を返す。
    """
    if payment_day == 0:
        end = _month_end(as_of)
        if as_of <= end:
            return end
        # 通常通らないが念のため
        return _month_end(_add_months(as_of, 1))
    # payment_day in 1..31
    target_day = min(payment_day, _days_in_month(as_of))
    if as_of.day <= target_day:
        return as_of.replace(day=target_day)
    nm = _add_months(as_of, 1)
    return nm.replace(day=min(payment_day, _days_in_month(nm)))


def _payoff_date(start: date, months_remaining: int, payment_day: int | None) -> date | None:
    if months_remaining is None or months_remaining <= 0:
        return None
    if payment_day is None:
        return None
    # 1 回目の引落日を求め、そこから (months_remaining - 1) ヶ月進める
    first = _next_payment_date(start, payment_day)
    final = _add_months(first, months_remaining - 1)
    if payment_day == 0:
        return _month_end(final)
    return final.replace(day=min(payment_day, _days_in_month(final)))


def _days_in_month(d: date) -> int:
    return calendar.monthrange(d.year, d.month)[1]


def _month_end(d: date) -> date:
    return d.replace(day=_days_in_month(d))


def _add_months(d: date, months: int) -> date:
    total = d.month - 1 + months
    y = d.year + total // 12
    m = total % 12 + 1
    return date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


def project_fixed_principal_payoff(
    account: Account,
    as_of: date | None = None,
    owed: int | None = None,
    profile: LoanProfile | None = None,
) -> Optional[dict]:
    """単一負債口座の完済予測。

    Args:
        account: 対象口座 (kind=LIABILITY 想定)
        as_of: 残高基準日。既定: 今日
        owed: 既知の残債 (正値)。None なら all_account_balances から計算
        profile: 既知の LoanProfile。None なら account.loan_profile を取得

    Returns:
        dict (キー: owed, annual_rate_bp, monthly_payment, months_remaining,
              payoff_date, total_interest, total_paid, next_interest,
              next_principal, next_payment_date, warning)
        投影不能な場合は None。

    投影不能の条件:
        - profile が無い
        - monthly_payment <= 0
        - owed <= 0 (既に完済 / 資産化)
    """
    if as_of is None:
        as_of = date.today()

    if profile is None:
        profile = getattr(account, 'loan_profile', None)
    if profile is None:
        return None
    if profile.monthly_payment is None or profile.monthly_payment <= 0:
        return None

    if owed is None:
        balances = all_account_balances(as_of)
        b = balances.get(account.pk, account.opening_balance)
        owed = -b
    if owed <= 0:
        return None

    annual_rate_bp = profile.annual_rate_bp or 0
    payment = profile.monthly_payment
    payment_day = profile.payment_day if profile.payment_day is not None else None

    next_interest = 0
    if annual_rate_bp > 0:
        monthly_rate = annual_rate_bp / 10000 / 12
        next_interest = int(owed * monthly_rate)

    next_principal = max(payment - next_interest, 0)

    npd = _next_payment_date(as_of, payment_day) if payment_day is not None else None

    base = {
        'owed': owed,
        'annual_rate_bp': annual_rate_bp,
        'monthly_payment': payment,
        'next_interest': next_interest,
        'next_principal': next_principal,
        'next_payment_date': npd,
    }

    if annual_rate_bp == 0:
        # 利息ゼロ: 単純割り算 + 端数月
        months = (owed + payment - 1) // payment  # ceil
        return {
            **base,
            'months_remaining': months,
            'total_interest': 0,
            'total_paid': owed,
            'payoff_date': _payoff_date(as_of, months, payment_day),
            'warning': None,
        }

    monthly_rate = annual_rate_bp / 10000 / 12

    # 利息より小さい payment は永遠に減らない
    if payment <= next_interest:
        return {
            **base,
            'months_remaining': None,
            'total_interest': None,
            'total_paid': None,
            'payoff_date': None,
            'warning': 'payment_below_interest',
        }

    remaining = owed
    total_interest = 0
    total_paid = 0
    months = 0
    while remaining > 0 and months < MAX_MONTHS:
        months += 1
        interest = int(remaining * monthly_rate)
        remaining += interest
        total_interest += interest
        pay = min(payment, remaining)
        remaining -= pay
        total_paid += pay

    warning = None
    if months >= MAX_MONTHS and remaining > 0:
        warning = 'max_months_exceeded'

    return {
        **base,
        'months_remaining': months,
        'total_interest': total_interest,
        'total_paid': total_paid,
        'payoff_date': _payoff_date(as_of, months, payment_day),
        'warning': warning,
    }