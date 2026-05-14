"""確定申告レポート v2（v1.18.0）の統合集計。

v1.16.0（医療費）+ v1.17.0（生保・地震）+ v1.13.0（寄附金 tax_tag）を
1 枚のレポートとして集計する。読み取り専用、DB 変更なし。
"""
from __future__ import annotations

from dataclasses import dataclass

from django.db.models import Sum

from ..models import Category, Transaction
from .insurance import calculate_insurance_deduction, InsuranceDeductionSummary
from .medical import calculate_medical_deduction, MedicalDeductionSummary


@dataclass
class TaxReportV2Summary:
    year: int
    exclude_year_end_adjusted: bool
    medical: MedicalDeductionSummary
    insurance: InsuranceDeductionSummary
    donation: dict
    # 控除額の総計（医療費 + 生保 + 地震）。
    # 寄附金は控除額計算ロジック未実装のため除外。
    grand_deduction_total: int


def _aggregate_donation(year: int) -> dict:
    """寄附金（tax_tag=donation）の年間取引集計。

    控除額は計算しない（ふるさと納税ワンストップ特例運用 or 別途申告書計算欄で対応）。
    支払合計と取引一覧のみ返す。
    """
    qs = (
        Transaction.objects
        .select_related('category', 'account')
        .filter(
            date__year=year,
            category__tax_tag=Category.TaxTag.DONATION,
            category__kind=Category.Kind.EXPENSE,
        )
        .order_by('date', 'id')
    )
    transactions = list(qs)
    total = qs.aggregate(s=Sum('amount'))['s'] or 0
    return {
        'total': total,
        'count': len(transactions),
        'transactions': transactions,
    }


def build_tax_report_v2(
    year: int,
    exclude_year_end_adjusted: bool = True,
) -> TaxReportV2Summary:
    """確定申告レポート v2 の統合集計を返す。

    Args:
        year: 対象年
        exclude_year_end_adjusted: 生保・地震で年調済を除外するか。デフォルト True
                                   （= 確定申告で実際に書く額）。

    Returns:
        TaxReportV2Summary
    """
    medical = calculate_medical_deduction(year)
    insurance = calculate_insurance_deduction(
        year, exclude_year_end_adjusted=exclude_year_end_adjusted,
    )
    donation = _aggregate_donation(year)
    grand_deduction_total = medical.deduction + insurance.grand_total
    return TaxReportV2Summary(
        year=year,
        exclude_year_end_adjusted=exclude_year_end_adjusted,
        medical=medical,
        insurance=insurance,
        donation=donation,
        grand_deduction_total=grand_deduction_total,
    )