"""負債返済戦略のシミュレーション。

戦略:
- avalanche (雪崩法): 高金利から優先返済 (数学的最適 = 総利息最小)
- snowball (雪だるま法): 小残高から優先返済 (心理効果が大きい)

シミュレーションの簡略化:
- 月利 = 年利 / 12
- 各月: (残債 × 月利) を利息として加算 → 月次返済額を「最低支払」として全口座に当て、
  さらに extra 分を「優先口座」に集中投下
- 優先口座は戦略に応じて決定
- 残債 0 になったらその口座の最低支払額分を、次の優先口座に上乗せ（rolling）
- 上限 600 ヶ月 (50 年) で打切り
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Iterable

from ..models import Account, LoanProfile
from .balance import all_account_balances


MAX_MONTHS = 600


@dataclass
class LoanState:
    name: str
    owed: int
    annual_rate_bp: int
    monthly_minimum: int

    @property
    def monthly_rate(self) -> float:
        return self.annual_rate_bp / 10000 / 12


@dataclass
class SimulationResult:
    strategy: str
    months_to_payoff: int
    total_interest: int
    monthly_total_payment: int     # 各月の合計支払額（最低支払 + extra）
    extra: int                      # 月次の繰上返済額
    per_loan: dict[str, dict]       # 口座別の累計利息と完済月
    timeline: list[dict] = field(default_factory=list)  # 任意: グラフ用

    def to_dict(self) -> dict:
        return {
            'strategy': self.strategy,
            'months_to_payoff': self.months_to_payoff,
            'total_interest': self.total_interest,
            'monthly_total_payment': self.monthly_total_payment,
            'extra': self.extra,
            'per_loan': self.per_loan,
            'years': round(self.months_to_payoff / 12, 1),
        }


def collect_loan_states(as_of: date | None = None) -> list[LoanState]:
    """現在の負債口座 + LoanProfile からシミュレーション用状態を作る。

    as_of で指定された日付（既定: 今日）時点の **実残高** を使う。
    取引・振替（v1.11/12 自動生成分含む）が反映される。
    """
    if as_of is None:
        as_of = date.today()
    balances = all_account_balances(as_of)
    states = []
    for account in Account.objects.filter(kind=Account.Kind.LIABILITY, is_active=True):
        current = balances.get(account.pk, account.opening_balance)
        owed = -current  # 負債残高（正値）
        if owed <= 0:
            continue
        profile = getattr(account, 'loan_profile', None)
        rate_bp = profile.annual_rate_bp if profile else 0
        min_pay = profile.monthly_payment if profile and profile.monthly_payment > 0 else max(int(owed * 0.03), 1000)
        states.append(LoanState(
            name=account.name,
            owed=owed,
            annual_rate_bp=rate_bp,
            monthly_minimum=min_pay,
        ))
    return states


def _sort_priority(states: list[LoanState], strategy: str) -> list[LoanState]:
    if strategy == 'avalanche':
        # 高金利 → 高残高 の順
        return sorted(states, key=lambda s: (-s.annual_rate_bp, -s.owed))
    elif strategy == 'snowball':
        # 低残高 → 高金利 の順
        return sorted(states, key=lambda s: (s.owed, -s.annual_rate_bp))
    else:
        raise ValueError(f'unknown strategy: {strategy}')


def simulate_payoff(
    states: list[LoanState],
    monthly_extra: int = 0,
    strategy: str = 'avalanche',
) -> SimulationResult:
    """月次シミュレーション。states の owed を非破壊的にコピーして実行。"""
    # ディープコピー
    work = [LoanState(name=s.name, owed=s.owed, annual_rate_bp=s.annual_rate_bp,
                      monthly_minimum=s.monthly_minimum) for s in states]
    per_loan = {s.name: {'interest_paid': 0, 'months': 0, 'minimum': s.monthly_minimum} for s in states}
    total_interest = 0
    months = 0
    base_monthly_min = sum(s.monthly_minimum for s in work)

    while any(s.owed > 0 for s in work):
        if months >= MAX_MONTHS:
            break
        months += 1

        # 1) 利息計上
        for s in work:
            if s.owed <= 0:
                continue
            interest = int(s.owed * s.monthly_rate)
            s.owed += interest
            total_interest += interest
            per_loan[s.name]['interest_paid'] += interest

        # 2) 各口座に最低支払額を当てる
        rolling_extra = monthly_extra
        for s in work:
            if s.owed <= 0:
                # 既に完済 → その口座の最低支払を rolling 原資へ
                rolling_extra += s.monthly_minimum
                continue
            pay = min(s.monthly_minimum, s.owed)
            s.owed -= pay
            if s.owed <= 0 and per_loan[s.name]['months'] == 0:
                per_loan[s.name]['months'] = months

        # 3) extra + rolling を優先口座に投下
        priority = _sort_priority([s for s in work if s.owed > 0], strategy)
        remaining_extra = rolling_extra
        for s in priority:
            if remaining_extra <= 0:
                break
            pay = min(remaining_extra, s.owed)
            s.owed -= pay
            remaining_extra -= pay
            if s.owed <= 0 and per_loan[s.name]['months'] == 0:
                per_loan[s.name]['months'] = months

    return SimulationResult(
        strategy=strategy,
        months_to_payoff=months,
        total_interest=total_interest,
        monthly_total_payment=base_monthly_min + monthly_extra,
        extra=monthly_extra,
        per_loan=per_loan,
    )


def compare_strategies(monthly_extra: int = 0, as_of: date | None = None) -> dict:
    """avalanche / snowball を比較。as_of の実残高ベース。"""
    states = collect_loan_states(as_of=as_of)
    if not states:
        return {'states': [], 'avalanche': None, 'snowball': None, 'savings': 0}
    av = simulate_payoff(states, monthly_extra=monthly_extra, strategy='avalanche')
    sb = simulate_payoff(states, monthly_extra=monthly_extra, strategy='snowball')
    savings = sb.total_interest - av.total_interest
    return {
        'states': states,
        'avalanche': av.to_dict(),
        'snowball': sb.to_dict(),
        'savings': savings,
        'monthly_minimum_total': sum(s.monthly_minimum for s in states),
    }