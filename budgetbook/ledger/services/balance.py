from __future__ import annotations

from datetime import date

from django.db.models import IntegerField, Sum, Value
from django.db.models.functions import Coalesce

from ..models import Account, Category, LoanProfile, MonthlyClosing, Transaction, Transfer


def _sum_by_account(qs, group_field: str) -> dict[int, int]:
    rows = qs.values(group_field).annotate(total=Sum('amount'))
    return {row[group_field]: int(row['total'] or 0) for row in rows}


def all_account_balances(until_date: date) -> dict[int, int]:
    """口座 pk -> 残高 を 4 クエリで返す（振替は from/to の差し引きで合計に影響しない）。"""
    income = _sum_by_account(
        Transaction.objects.filter(category__kind=Category.Kind.INCOME, date__lte=until_date),
        'account_id',
    )
    expense = _sum_by_account(
        Transaction.objects.filter(category__kind=Category.Kind.EXPENSE, date__lte=until_date),
        'account_id',
    )
    transfer_out = _sum_by_account(
        Transfer.objects.filter(date__lte=until_date),
        'from_account_id',
    )
    transfer_in = _sum_by_account(
        Transfer.objects.filter(date__lte=until_date),
        'to_account_id',
    )
    result: dict[int, int] = {}
    for acct in Account.objects.all().only('pk', 'opening_balance'):
        result[acct.pk] = (
            acct.opening_balance
            + income.get(acct.pk, 0)
            - expense.get(acct.pk, 0)
            - transfer_out.get(acct.pk, 0)
            + transfer_in.get(acct.pk, 0)
        )
    return result


def calculate_account_balance(account: Account, until_date: date) -> int:
    """単口座残高。互換のため残す。複数口座を扱う場面では all_account_balances を使うこと。"""
    return all_account_balances(until_date).get(account.pk, account.opening_balance)


def calculate_total_balance(until_date: date) -> int:
    """全口座合計残高(振替は from/to で打ち消されるため 0 影響)。

    純資産的な意味合い: 資産口座 + 負債口座（負債は通常マイナス値で保持）。
    """
    return sum(all_account_balances(until_date).values())


def balance_sheet(until_date: date) -> dict:
    """個人 B/S スナップショット。

    返り値:
      {
        'assets': [{'account': Account, 'balance': int}, ...],
        'liabilities': [
          {'account': Account, 'balance': int, 'owed': int,
           'profile': LoanProfile|None,
           'annual_interest_est': int, 'monthly_interest_est': int},
          ...
        ],
        'asset_total': int,
        'liability_total': int,             # 借入総額（正値）
        'monthly_interest_total': int,      # 月間想定利息合計
        'annual_interest_total': int,
        'net_worth': int,
      }
    """
    balances = all_account_balances(until_date)
    # LoanProfile を一括 prefetch
    profile_map = {p.account_id: p for p in LoanProfile.objects.all()}
    assets = []
    liabilities = []
    asset_total = 0
    liability_total = 0
    monthly_interest_total = 0
    annual_interest_total = 0
    for account in Account.objects.all().order_by('kind', 'name'):
        b = balances.get(account.pk, account.opening_balance)
        if account.kind == Account.Kind.LIABILITY:
            owed = -b  # 借入額（正値）
            liability_total += owed
            profile = profile_map.get(account.pk)
            annual_int = 0
            monthly_int = 0
            if profile and profile.annual_rate_bp > 0 and owed > 0:
                annual_int = int(owed * profile.annual_rate_bp / 10000)
                monthly_int = int(annual_int / 12)
            monthly_interest_total += monthly_int
            annual_interest_total += annual_int
            # v1.15.0: 単一口座の完済予測を付与（read-only）
            from .loan_projection import project_fixed_principal_payoff
            projection = project_fixed_principal_payoff(
                account, as_of=until_date, owed=owed, profile=profile,
            )
            liabilities.append({
                'account': account,
                'balance': b,
                'owed': owed,
                'profile': profile,
                'annual_interest_est': annual_int,
                'monthly_interest_est': monthly_int,
                'projection': projection,
            })
        else:
            assets.append({'account': account, 'balance': b})
            asset_total += b
    # 高金利順にソート（リボ識別用）
    liabilities.sort(
        key=lambda x: (x['profile'].annual_rate_bp if x['profile'] else 0),
        reverse=True,
    )
    return {
        'assets': assets,
        'liabilities': liabilities,
        'asset_total': asset_total,
        'liability_total': liability_total,
        'monthly_interest_total': monthly_interest_total,
        'annual_interest_total': annual_interest_total,
        'net_worth': asset_total - liability_total,
    }


def compute_month_totals(target_month: date) -> dict:
    """月次の純粋集計（dashboard より軽量、drift / closing 用）。"""
    from .dates import shift_month
    start = target_month
    end = shift_month(target_month, 1)
    monthly_qs = Transaction.objects.filter(date__gte=start, date__lt=end)
    income = monthly_qs.filter(category__kind=Category.Kind.INCOME).aggregate(
        total=Coalesce(Sum('amount'), Value(0, output_field=IntegerField()))
    )['total']
    expense = monthly_qs.filter(category__kind=Category.Kind.EXPENSE).aggregate(
        total=Coalesce(Sum('amount'), Value(0, output_field=IntegerField()))
    )['total']
    return {
        'income': int(income),
        'expense': int(expense),
        'net': int(income) - int(expense),
    }


def is_month_closed(entry_date: date) -> bool:
    return MonthlyClosing.objects.filter(month=date(entry_date.year, entry_date.month, 1)).exists()