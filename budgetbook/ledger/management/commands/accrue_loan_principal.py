"""v1.12.0: LoanProfile 元金返済 Transfer 自動化 management command。

仕様: docs/specs/v1.12.0_loan_auto_principal.md

monthly_payment > 0 かつ source_account が設定された LoanProfile について、
対象月の payment_day に銀行(資産)→負債口座への Transfer を自動生成する。
"""
from __future__ import annotations

import calendar
from datetime import date

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction as db_transaction
from django.utils import timezone

from ledger.models import (
    Account,
    AuditLog,
    LoanProfile,
    MonthlyClosing,
    Transfer,
)


def _last_day(year: int, month: int) -> int:
    return calendar.monthrange(year, month)[1]


def _parse_month(s: str) -> tuple[int, int]:
    try:
        y, m = s.split('-')
        year = int(y)
        month = int(m)
        if month < 1 or month > 12:
            raise ValueError
        return year, month
    except (ValueError, AttributeError):
        raise CommandError(f'--month は YYYY-MM 形式で指定してください: 受け取った値={s!r}')


def _payment_date(year: int, month: int, payment_day: int) -> date:
    last = _last_day(year, month)
    if payment_day < 1 or payment_day > 31:
        return date(year, month, last)
    return date(year, month, min(payment_day, last))


class Command(BaseCommand):
    help = (
        'LoanProfile (monthly_payment > 0 かつ source_account 設定済) について、'
        'payment_day に銀行→負債口座の Transfer を自動生成する。デフォルトは dry-run。'
    )

    def add_arguments(self, parser):
        parser.add_argument('--month', type=str, default='',
                            help='対象月 YYYY-MM。未指定なら現在月。')
        parser.add_argument('--apply', action='store_true',
                            help='実際に Transfer を作成する。指定しなければ dry-run。')
        parser.add_argument('--account', type=str, default='',
                            help='処理対象を負債口座名で絞り込み（完全一致）。')

    def handle(self, *args, **options):
        if options['month']:
            year, month = _parse_month(options['month'])
        else:
            today = timezone.localdate()
            year, month = today.year, today.month

        month_start = date(year, month, 1)

        if MonthlyClosing.objects.filter(month=month_start).exists():
            raise CommandError(
                f'{year}-{month:02d} は月次締め済みのため、元金返済 Transfer は作成できません。'
            )

        profiles = (
            LoanProfile.objects
            .select_related('account', 'source_account')
            .filter(
                monthly_payment__gt=0,
                source_account__isnull=False,
                account__is_active=True,
                source_account__is_active=True,
            )
            .order_by('account__name')
        )
        if options['account']:
            profiles = profiles.filter(account__name=options['account'])

        profile_list = list(profiles)
        if not profile_list:
            self.stdout.write(self.style.WARNING(
                f'{year}-{month:02d}: 対象となる LoanProfile が見つかりませんでした。'
                ' (monthly_payment と source_account の両方を設定してください)'
            ))
            return

        # 既存自動生成 Transfer の重複検出
        # 一意性: (from_account, to_account, month) + AuditLog metadata source
        existing_auto = set(
            AuditLog.objects
            .filter(
                target_model='Transfer',
                metadata__source='accrue_loan_principal',
                metadata__month=f'{year}-{month:02d}',
            )
            .values_list('metadata__account', flat=True)
        )

        results = []
        for prof in profile_list:
            if prof.account.name in existing_auto:
                raise CommandError(
                    f'{prof.account.name}: {year}-{month:02d} に accrue_loan_principal による'
                    ' Transfer が既に存在します。二重計上を防ぐため処理を中止しました。'
                )
            results.append({
                'profile': prof,
                'from': prof.source_account,
                'to': prof.account,
                'date': _payment_date(year, month, prof.payment_day),
                'amount': prof.monthly_payment,
            })

        mode = 'APPLY' if options['apply'] else 'DRY-RUN'
        self.stdout.write(
            f'[{mode}] {year}-{month:02d} 元金返済 ({len(results)} 件)'
        )
        total = 0
        for r in results:
            self.stdout.write(
                f'  {r["to"].name}  {r["from"].name} → {r["to"].name}  '
                f'{r["date"].isoformat()}  ¥{r["amount"]:,}'
            )
            total += r['amount']
        self.stdout.write(f'合計返済: ¥{total:,}')

        if not options['apply']:
            self.stdout.write(self.style.WARNING(
                '※ --apply で確定します。今は何も書き込んでいません。'
            ))
            return

        with db_transaction.atomic():
            # 同時実行レース対策: atomic ブロック内で再チェック
            existing_now = set(
                AuditLog.objects
                .filter(
                    target_model='Transfer',
                    metadata__source='accrue_loan_principal',
                    metadata__month=f'{year}-{month:02d}',
                )
                .values_list('metadata__account', flat=True)
            )
            conflict = [r for r in results if r['to'].name in existing_now]
            if conflict:
                names = ', '.join(r['to'].name for r in conflict)
                raise CommandError(
                    f'競合検出: {names} に {year}-{month:02d} の元金返済 Transfer が'
                    ' 直前に作成されました（同時実行の可能性）。ロールバックします。'
                )
            created_ids = []
            for r in results:
                tr = Transfer.objects.create(
                    date=r['date'],
                    from_account=r['from'],
                    to_account=r['to'],
                    amount=r['amount'],
                    description=f'{r["to"].name} {year}-{month:02d} 返済',
                )
                AuditLog.objects.create(
                    user=None,
                    action=AuditLog.Action.CREATE,
                    target_model=tr.__class__.__name__,
                    target_id=str(tr.pk),
                    target_repr=str(tr)[:200],
                    summary=f'accrue_loan_principal {year}-{month:02d}',
                    metadata={
                        'source': 'accrue_loan_principal',
                        'month': f'{year}-{month:02d}',
                        'account': r['to'].name,
                        'source_account': r['from'].name,
                        'amount': r['amount'],
                    },
                )
                created_ids.append(tr.pk)
            self.stdout.write(self.style.SUCCESS(
                f'Transfer {len(created_ids)} 件作成: {created_ids}'
            ))
            self.stdout.write(self.style.SUCCESS(
                f'AuditLog {len(created_ids)} 件記録。'
            ))