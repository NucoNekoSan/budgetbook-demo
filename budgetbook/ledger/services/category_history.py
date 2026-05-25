from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import QuerySet

from ..models import AuditLog, Category, CategoryChangeLog, MonthlyClosing, Transaction


def category_snapshot(category: Category) -> dict:
    return {
        'id': category.pk,
        'name': category.name,
        'kind': category.kind,
        'section': category.section,
        'tax_tag': category.tax_tag,
        'is_active': category.is_active,
    }


def _category_transactions(category: Category) -> QuerySet:
    return Transaction.objects.filter(category=category)


def category_closed_months(category: Category) -> set[date]:
    closed_months = set(MonthlyClosing.objects.values_list('month', flat=True))
    transaction_months = {
        d.replace(day=1)
        for d in _category_transactions(category).values_list('date', flat=True)
    }
    return transaction_months & closed_months


def create_category_change_log(
    *,
    category: Category,
    action: str,
    before: dict,
    after: dict,
    reason: str = '',
    changed_by=None,
    affected_transaction_count: int | None = None,
    includes_closed_month: bool | None = None,
) -> CategoryChangeLog:
    if affected_transaction_count is None:
        affected_transaction_count = _category_transactions(category).count()
    if includes_closed_month is None:
        includes_closed_month = bool(category_closed_months(category))
    return CategoryChangeLog.objects.create(
        category=category,
        action=action,
        before=before,
        after=after,
        affected_transaction_count=affected_transaction_count,
        includes_closed_month=includes_closed_month,
        reason=reason.strip(),
        changed_by=changed_by if getattr(changed_by, 'is_authenticated', False) else None,
    )


@dataclass(frozen=True)
class ReclassificationPlan:
    from_category_id: int
    to_category_id: int
    affected_transaction_count: int
    includes_closed_month: bool
    closed_months: list[str] = field(default_factory=list)
    start_date: date | None = None
    end_date: date | None = None


def _reclassification_queryset(
    *,
    from_category: Category,
    start_date: date | None = None,
    end_date: date | None = None,
) -> QuerySet:
    qs = Transaction.objects.filter(category=from_category)
    if start_date is not None:
        qs = qs.filter(date__gte=start_date)
    if end_date is not None:
        qs = qs.filter(date__lte=end_date)
    return qs


def build_reclassification_plan(
    *,
    from_category: Category,
    to_category: Category,
    start_date: date | None = None,
    end_date: date | None = None,
) -> ReclassificationPlan:
    if from_category.pk == to_category.pk:
        raise ValidationError('変更前カテゴリと変更後カテゴリは別のカテゴリを指定してください。')
    if from_category.kind != to_category.kind:
        raise ValidationError('収入/支出の区分が異なるカテゴリへは再分類できません。')
    qs = _reclassification_queryset(
        from_category=from_category,
        start_date=start_date,
        end_date=end_date,
    )
    closed_months = set(MonthlyClosing.objects.values_list('month', flat=True))
    affected_months = {
        d.replace(day=1)
        for d in qs.values_list('date', flat=True)
    }
    included_closed_months = sorted(affected_months & closed_months)
    return ReclassificationPlan(
        from_category_id=from_category.pk,
        to_category_id=to_category.pk,
        affected_transaction_count=qs.count(),
        includes_closed_month=bool(included_closed_months),
        closed_months=[m.isoformat() for m in included_closed_months],
        start_date=start_date,
        end_date=end_date,
    )


def reclassify_transactions(
    *,
    from_category: Category,
    to_category: Category,
    reason: str,
    changed_by=None,
    start_date: date | None = None,
    end_date: date | None = None,
) -> ReclassificationPlan:
    if not reason.strip():
        raise ValidationError('再分類理由を入力してください。')
    with transaction.atomic():
        plan = build_reclassification_plan(
            from_category=from_category,
            to_category=to_category,
            start_date=start_date,
            end_date=end_date,
        )
        if plan.includes_closed_month:
            raise ValidationError('締め済み月を含むため再分類できません。締め取消後に再実行してください。')
        if plan.affected_transaction_count == 0:
            return plan
        qs = _reclassification_queryset(
            from_category=from_category,
            start_date=start_date,
            end_date=end_date,
        )
        qs.update(category=to_category)
        before = {
            'from_category': category_snapshot(from_category),
            'start_date': start_date.isoformat() if start_date else None,
            'end_date': end_date.isoformat() if end_date else None,
        }
        after = {
            'to_category': category_snapshot(to_category),
            'start_date': start_date.isoformat() if start_date else None,
            'end_date': end_date.isoformat() if end_date else None,
        }
        create_category_change_log(
            category=from_category,
            action=CategoryChangeLog.Action.RECLASSIFY,
            before=before,
            after=after,
            reason=reason,
            changed_by=changed_by,
            affected_transaction_count=plan.affected_transaction_count,
            includes_closed_month=False,
        )
        AuditLog.objects.create(
            user=changed_by if getattr(changed_by, 'is_authenticated', False) else None,
            action=AuditLog.Action.UPDATE,
            target_model='Category',
            target_id=str(from_category.pk),
            target_repr=str(from_category),
            summary='取引を再分類しました。',
            metadata={
                'from_category_id': from_category.pk,
                'to_category_id': to_category.pk,
                'count': plan.affected_transaction_count,
                'start_date': start_date.isoformat() if start_date else None,
                'end_date': end_date.isoformat() if end_date else None,
            },
        )
        return plan
