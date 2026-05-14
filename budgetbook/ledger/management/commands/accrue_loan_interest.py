"""v1.11.0: LoanProfile 利息自動計上 management command。

仕様: docs/specs/v1.11.0_loan_auto_interest.md

annual_rate_bp > 0 の LoanProfile について、対象月の月末日付で
当月利息相当額を支出 Transaction として生成する。
"""
from __future__ import annotations

import calendar
from datetime import date
from typing import Iterable

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction as db_transaction
from django.utils import timezone

from ledger.models import (
    Account,
    AuditLog,
    Category,
    LoanProfile,
    MonthlyClosing,
    Transaction,
)
from ledger.services.balance import all_account_balances


def _month_end(year: int, month: int) -> date:
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, last_day)


def _month_start(year: int, month: int) -> date:
    return date(year, month, 1)


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


class Command(BaseCommand):
    help = (
        'LoanProfile (annual_rate_bp > 0) について、対象月の月末日付で当月利息相当額を '
        '支出 Transaction として生成する。デフォルトは dry-run。--apply で確定する。'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--month', type=str, default='',
            help='対象月 YYYY-MM。未指定なら現在月。',
        )
        parser.add_argument(
            '--apply', action='store_true',
            help='実際に Transaction を作成する。指定しなければ dry-run。',
        )
        parser.add_argument(
            '--account', type=str, default='',
            help='処理対象を口座名で絞り込み（完全一致）。',
        )

    def handle(self, *args, **options):
        # 対象月の決定
        if options['month']:
            year, month = _parse_month(options['month'])
        else:
            today = timezone.localdate()
            year, month = today.year, today.month

        month_start = _month_start(year, month)
        month_end = _month_end(year, month)

        # 月次締めチェック
        if MonthlyClosing.objects.filter(month=month_start).exists():
            raise CommandError(
                f'{year}-{month:02d} は月次締め済みのため、利息計上はできません。'
                ' 締めを取り消してから再実行してください。'
            )

        # カテゴリ検証
        category_name = settings.LOAN_INTEREST_CATEGORY_NAME
        try:
            interest_category = Category.objects.get(name=category_name)
        except Category.DoesNotExist:
            raise CommandError(
                f'利息計上カテゴリ「{category_name}」が見つかりません。'
                ' /settings/ で先に作成してください (kind=expense)。'
            )
        if interest_category.kind != Category.Kind.EXPENSE:
            raise CommandError(
                f'カテゴリ「{category_name}」は kind=expense である必要があります。'
                f' 現状: kind={interest_category.kind}'
            )

        # 対象 LoanProfile 抽出
        profiles = (
            LoanProfile.objects
            .select_related('account')
            .filter(annual_rate_bp__gt=0, account__is_active=True)
            .order_by('account__name')
        )
        if options['account']:
            profiles = profiles.filter(account__name=options['account'])

        profile_list = list(profiles)
        if not profile_list:
            self.stdout.write(self.style.WARNING(
                f'{year}-{month:02d}: 対象となる LoanProfile が見つかりませんでした。'
            ))
            return

        # 月初残高（残高=opening_balance + その時点までの取引）を取得
        # 月初日の前日 = 前月末まで反映された残高を「当月の元本」として扱う
        prev_day = date(year, month, 1)
        prev_day_minus1 = date.fromordinal(prev_day.toordinal() - 1)
        balances = all_account_balances(prev_day_minus1)

        # 既存利息 Transaction の重複検出
        existing_in_month = set(
            Transaction.objects
            .filter(
                date__gte=month_start, date__lte=month_end,
                category=interest_category,
                account__in=[p.account for p in profile_list],
            )
            .values_list('account_id', flat=True)
        )

        # 計算
        results = []
        for prof in profile_list:
            acct = prof.account
            if acct.id in existing_in_month:
                raise CommandError(
                    f'{acct.name}: {year}-{month:02d} に「{category_name}」の'
                    ' Transaction が既に存在します。二重計上を防ぐため処理を中止しました。'
                )
            principal = abs(balances.get(acct.id, acct.opening_balance))
            monthly_rate = (prof.annual_rate_bp / 10000) / 12
            interest = round(principal * monthly_rate)
            if interest <= 0:
                continue
            results.append({
                'profile': prof,
                'account': acct,
                'principal': principal,
                'monthly_rate_pct': monthly_rate * 100,
                'interest': interest,
            })

        if not results:
            self.stdout.write(self.style.WARNING(
                f'{year}-{month:02d}: 利息額 > 0 となる口座がありませんでした。'
            ))
            return

        # 出力
        mode = 'APPLY' if options['apply'] else 'DRY-RUN'
        self.stdout.write(
            f'[{mode}] {year}-{month:02d} 利息計上 ({len(results)} 件)'
        )
        total = 0
        for r in results:
            self.stdout.write(
                f'  {r["account"].name}  元本 ¥{r["principal"]:,}  '
                f'月利 {r["monthly_rate_pct"]:.4f}%  利息 ¥{r["interest"]:,}'
            )
            total += r['interest']
        self.stdout.write(f'合計利息: ¥{total:,}')

        if not options['apply']:
            self.stdout.write(self.style.WARNING(
                '※ --apply で確定します。今は何も書き込んでいません。'
            ))
            return

        # 適用 — atomic ブロック内で再チェックして同時実行レースを防ぐ
        with db_transaction.atomic():
            # SQLite では BEGIN 〜 COMMIT 間で書込ロックがかかるため、
            # ここで再度 existing チェックすれば直前に別プロセスが INSERT した行も検出できる
            existing_now = set(
                Transaction.objects
                .filter(
                    date__gte=month_start, date__lte=month_end,
                    category=interest_category,
                    account__in=[r['account'] for r in results],
                )
                .values_list('account_id', flat=True)
            )
            conflict = [r for r in results if r['account'].id in existing_now]
            if conflict:
                names = ', '.join(r['account'].name for r in conflict)
                raise CommandError(
                    f'競合検出: {names} に {year}-{month:02d} の利息 Transaction が'
                    ' 直前に作成されました（同時実行の可能性）。ロールバックします。'
                )
            created_ids = []
            for r in results:
                tx = Transaction.objects.create(
                    date=month_end,
                    account=r['account'],
                    category=interest_category,
                    amount=r['interest'],
                    description=f'{r["account"].name} {year}-{month:02d} 利息',
                )
                AuditLog.objects.create(
                    user=None,
                    action=AuditLog.Action.CREATE,
                    target_model=tx.__class__.__name__,
                    target_id=str(tx.pk),
                    target_repr=str(tx)[:200],
                    summary=f'accrue_loan_interest {year}-{month:02d}',
                    metadata={
                        'source': 'accrue_loan_interest',
                        'month': f'{year}-{month:02d}',
                        'account': r['account'].name,
                        'principal': r['principal'],
                        'annual_rate_bp': r['profile'].annual_rate_bp,
                        'interest': r['interest'],
                    },
                )
                created_ids.append(tx.pk)
            self.stdout.write(self.style.SUCCESS(
                f'Transaction {len(created_ids)} 件作成: {created_ids}'
            ))
            self.stdout.write(self.style.SUCCESS(
                f'AuditLog {len(created_ids)} 件記録。'
            ))