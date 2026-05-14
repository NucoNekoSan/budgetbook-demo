"""医療費控除（v1.16.0）の集計・計算ロジック。

国税庁「医療費控除の明細書」様式に準拠した集計を行う。
- 控除額 = max(0, 差引合計 − min(100,000, 総所得 × 5%))
- 総所得未登録時は 100,000 円ラインで暫定計算（200 万円超ライン相当）
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from django.db.models import Sum

from ..models import AnnualIncomeSnapshot, Category, MedicalExpense, Transaction


MEDICAL_DEDUCTION_FLAT_THRESHOLD = 100_000


@dataclass
class MedicalDeductionSummary:
    year: int
    total_paid: int
    total_reimbursement: int
    net_paid: int
    threshold: int
    deduction: int
    gross_income_known: bool
    gross_income: int | None


def calculate_medical_deduction(year: int) -> MedicalDeductionSummary:
    """指定年の医療費控除額を計算する。

    Returns:
        MedicalDeductionSummary
    """
    aggregates = MedicalExpense.objects.filter(paid_date__year=year).aggregate(
        paid=Sum('amount'),
        reimb=Sum('reimbursement'),
    )
    total_paid = aggregates['paid'] or 0
    total_reimbursement = aggregates['reimb'] or 0
    net_paid = total_paid - total_reimbursement

    snapshot = AnnualIncomeSnapshot.objects.filter(year=year).first()
    if snapshot:
        threshold = min(MEDICAL_DEDUCTION_FLAT_THRESHOLD, snapshot.gross_income * 5 // 100)
        gross_income_known = True
        gross_income = snapshot.gross_income
    else:
        threshold = MEDICAL_DEDUCTION_FLAT_THRESHOLD
        gross_income_known = False
        gross_income = None

    deduction = max(0, net_paid - threshold)

    return MedicalDeductionSummary(
        year=year,
        total_paid=total_paid,
        total_reimbursement=total_reimbursement,
        net_paid=net_paid,
        threshold=threshold,
        deduction=deduction,
        gross_income_known=gross_income_known,
        gross_income=gross_income,
    )


def group_by_patient(expenses: Iterable[MedicalExpense]) -> list[dict]:
    """受診者別小計（templateで使う降順リスト）。"""
    buckets: dict[str, dict] = {}
    for e in expenses:
        bucket = buckets.setdefault(e.patient, {
            'patient': e.patient,
            'count': 0,
            'paid': 0,
            'reimbursement': 0,
        })
        bucket['count'] += 1
        bucket['paid'] += e.amount
        bucket['reimbursement'] += e.reimbursement
    rows = list(buckets.values())
    for r in rows:
        r['net'] = r['paid'] - r['reimbursement']
    rows.sort(key=lambda r: r['paid'], reverse=True)
    return rows


_VALID_MEDICAL_CATEGORIES = {value for value, _ in MedicalExpense.MedicalCategory.choices}


def sync_medical_expense_from_post(transaction: Transaction, post_data) -> MedicalExpense | None:
    """取引フォーム POST から MedicalExpense を作成/更新する。

    - 取引のカテゴリ tax_tag が MEDICAL でなければ何もしない（None を返す）
    - medical_patient / medical_provider のいずれかが空なら何もしない
    - 既存の MedicalExpense があれば更新、なければ作成
    """
    if transaction.category.tax_tag != Category.TaxTag.MEDICAL:
        return None

    patient = (post_data.get('medical_patient') or '').strip()
    provider = (post_data.get('medical_provider') or '').strip()
    if not patient or not provider:
        return None

    category = post_data.get('medical_category') or MedicalExpense.MedicalCategory.TREATMENT
    if category not in _VALID_MEDICAL_CATEGORIES:
        category = MedicalExpense.MedicalCategory.TREATMENT

    try:
        reimbursement = int(post_data.get('medical_reimbursement') or 0)
    except (TypeError, ValueError):
        reimbursement = 0
    reimbursement = max(0, min(reimbursement, transaction.amount))

    existing = MedicalExpense.objects.filter(transaction=transaction).first()
    if existing:
        existing.paid_date = transaction.date
        existing.patient = patient[:50]
        existing.provider = provider[:120]
        existing.category = category
        existing.amount = transaction.amount
        existing.reimbursement = reimbursement
        existing.save()
        return existing

    return MedicalExpense.objects.create(
        transaction=transaction,
        paid_date=transaction.date,
        patient=patient[:50],
        provider=provider[:120],
        category=category,
        amount=transaction.amount,
        reimbursement=reimbursement,
    )


def group_by_provider(expenses: Iterable[MedicalExpense]) -> list[dict]:
    """医療機関別小計。"""
    buckets: dict[str, dict] = {}
    for e in expenses:
        bucket = buckets.setdefault(e.provider, {
            'provider': e.provider,
            'count': 0,
            'paid': 0,
            'reimbursement': 0,
        })
        bucket['count'] += 1
        bucket['paid'] += e.amount
        bucket['reimbursement'] += e.reimbursement
    rows = list(buckets.values())
    for r in rows:
        r['net'] = r['paid'] - r['reimbursement']
    rows.sort(key=lambda r: r['paid'], reverse=True)
    return rows