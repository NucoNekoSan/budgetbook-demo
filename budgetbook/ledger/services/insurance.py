"""生命保険料控除・地震保険料控除（v1.17.0）の計算ロジック。

国税庁公式式を整数除算で 1:1 実装する。
- 各枠（一般生命/介護医療/個人年金）の控除額 → 合算上限 12 万円
- 地震保険料控除 上限 5 万円
- 新旧契約混在時は 3 方式の最大値を自動選択（国税庁ルール）
"""
from __future__ import annotations

from dataclasses import dataclass

from django.db.models import Sum

from ..models import InsurancePremium


# ---------------------------------------------------------------------------
# 各枠 1 件分の控除額（純粋関数）
# ---------------------------------------------------------------------------

def calc_life_new(amount: int) -> int:
    """新契約 (2012/1/1 以降) の 1 枠分の控除額。上限 4 万円。"""
    if amount <= 0:
        return 0
    if amount <= 20_000:
        return amount
    if amount <= 40_000:
        return amount // 2 + 10_000
    if amount <= 80_000:
        return amount // 4 + 20_000
    return 40_000


def calc_life_old(amount: int) -> int:
    """旧契約 (2011/12/31 以前) の 1 枠分の控除額。上限 5 万円。"""
    if amount <= 0:
        return 0
    if amount <= 25_000:
        return amount
    if amount <= 50_000:
        return amount // 2 + 12_500
    if amount <= 100_000:
        return amount // 4 + 25_000
    return 50_000


def calc_life_category(new_total: int, old_total: int) -> int:
    """1 枠（一般 / 介護医療 / 個人年金）の控除額。

    新旧両方ある場合は 3 方式の最大値を選ぶ（国税庁ルール）:
    1. 新契約のみで計算（上限 4 万円）
    2. 旧契約のみで計算（上限 5 万円）
    3. 新旧合算を新契約ルールで計算（上限 4 万円）
    """
    if new_total <= 0 and old_total <= 0:
        return 0
    if new_total <= 0:
        return calc_life_old(old_total)
    if old_total <= 0:
        return calc_life_new(new_total)
    return max(
        calc_life_new(new_total),
        calc_life_old(old_total),
        calc_life_new(new_total + old_total),
    )


# ---------------------------------------------------------------------------
# 集計
# ---------------------------------------------------------------------------

@dataclass
class InsuranceDeductionSummary:
    year: int
    life: dict
    earthquake: dict
    grand_total: int
    exclude_year_end_adjusted: bool


def _filter_qs(year: int, exclude_year_end_adjusted: bool):
    qs = InsurancePremium.objects.filter(year=year)
    if exclude_year_end_adjusted:
        qs = qs.filter(submitted_in_year_end_adjustment=False)
    return qs


def calc_life_total(year: int, exclude_year_end_adjusted: bool = False) -> dict:
    """生命保険料控除合計（上限 12 万円）と内訳。"""
    qs = _filter_qs(year, exclude_year_end_adjusted).exclude(
        category=InsurancePremium.InsuranceCategory.EARTHQUAKE,
    )

    def sum_by(cat, contract):
        return qs.filter(category=cat, contract_type=contract).aggregate(
            s=Sum('annual_amount'),
        )['s'] or 0

    cats = [
        InsurancePremium.InsuranceCategory.LIFE_GENERAL,
        InsurancePremium.InsuranceCategory.LIFE_CARE_MEDICAL,
        InsurancePremium.InsuranceCategory.LIFE_ANNUITY,
    ]
    per_category = {}
    raw_sum = 0
    for cat in cats:
        new_total = sum_by(cat, InsurancePremium.ContractType.NEW)
        old_total = sum_by(cat, InsurancePremium.ContractType.OLD)
        deduction = calc_life_category(new_total, old_total)
        per_category[cat] = {
            'new_paid': new_total,
            'old_paid': old_total,
            'deduction': deduction,
        }
        raw_sum += deduction

    return {
        'per_category': per_category,
        'raw_sum': raw_sum,
        'total': min(raw_sum, 120_000),
    }


def calc_earthquake_total(year: int, exclude_year_end_adjusted: bool = False) -> dict:
    """地震保険料控除（上限 5 万円）。"""
    qs = _filter_qs(year, exclude_year_end_adjusted).filter(
        category=InsurancePremium.InsuranceCategory.EARTHQUAKE,
    )
    paid = qs.aggregate(s=Sum('annual_amount'))['s'] or 0
    return {
        'paid': paid,
        'deduction': min(paid, 50_000),
    }


def calculate_insurance_deduction(
    year: int,
    exclude_year_end_adjusted: bool = False,
) -> InsuranceDeductionSummary:
    """生命保険料控除 + 地震保険料控除のまとめ計算。"""
    life = calc_life_total(year, exclude_year_end_adjusted)
    earthquake = calc_earthquake_total(year, exclude_year_end_adjusted)
    return InsuranceDeductionSummary(
        year=year,
        life=life,
        earthquake=earthquake,
        grand_total=life['total'] + earthquake['deduction'],
        exclude_year_end_adjusted=exclude_year_end_adjusted,
    )