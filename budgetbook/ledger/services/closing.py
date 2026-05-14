from __future__ import annotations

from datetime import date, timedelta

from ..models import Account, AccountReconciliation, MonthlyClosing, Transaction, Transfer
from .balance import all_account_balances, compute_month_totals
from .dates import month_end, shift_month


def build_monthly_closing_snapshot(target_month: date) -> dict:
    m_end = month_end(target_month)
    prev_day = target_month - timedelta(days=1)
    has_accounts = Account.objects.exists()
    opening_balances = all_account_balances(prev_day) if has_accounts else {}
    closing_balances = all_account_balances(m_end) if has_accounts else {}
    opening_carry = sum(opening_balances.values())
    closing_balance = sum(closing_balances.values())
    totals = compute_month_totals(target_month)

    account_balances = []
    for account in Account.objects.order_by('name').only('pk', 'name', 'opening_balance', 'is_active'):
        account_balances.append({
            'account_id': account.pk,
            'name': account.name,
            'opening_balance': account.opening_balance,
            'balance': closing_balances.get(account.pk, account.opening_balance),
            'is_active': account.is_active,
        })
    return {
        'month': target_month,
        'opening_carry': opening_carry,
        'income': totals['income'],
        'expense': totals['expense'],
        'net': totals['net'],
        'closing_balance': closing_balance,
        'account_balances': account_balances,
    }


def _account_balance_map(snapshot: list[dict]) -> dict[int, int]:
    result = {}
    for item in snapshot or []:
        account_id = item.get('account_id')
        if account_id is not None:
            result[int(account_id)] = int(item.get('balance', 0))
    return result


def enrich_monthly_closings_with_drift(closings) -> list[MonthlyClosing]:
    """締め時点のスナップショットと現在の帳簿再計算値を比較する。"""
    enriched = list(closings)
    for closing in enriched:
        current = build_monthly_closing_snapshot(closing.month)
        total_drift = {
            'opening_carry': current['opening_carry'] - closing.opening_carry,
            'income': current['income'] - closing.income,
            'expense': current['expense'] - closing.expense,
            'net': current['net'] - closing.net,
            'closing_balance': current['closing_balance'] - closing.closing_balance,
        }
        snapshot_accounts = _account_balance_map(closing.account_balances)
        current_accounts = _account_balance_map(current['account_balances'])
        account_drift = []
        account_names = {
            int(item['account_id']): item.get('name', '')
            for item in current['account_balances']
            if item.get('account_id') is not None
        }
        account_names.update({
            int(item['account_id']): item.get('name', '')
            for item in closing.account_balances or []
            if item.get('account_id') is not None
        })
        for account_id in sorted(set(snapshot_accounts) | set(current_accounts)):
            diff = current_accounts.get(account_id, 0) - snapshot_accounts.get(account_id, 0)
            if diff:
                account_drift.append({
                    'account_id': account_id,
                    'name': account_names.get(account_id, f'Account#{account_id}'),
                    'difference': diff,
                })

        closing.current_snapshot = current
        closing.total_drift = total_drift
        closing.account_drift = account_drift
        closing.has_drift = any(total_drift.values()) or bool(account_drift)
    return enriched


def build_monthly_closing_preflight(target_month: date) -> dict:
    snapshot = build_monthly_closing_snapshot(target_month)
    start = target_month
    end = shift_month(target_month, 1)
    closing_day = month_end(target_month)
    active_accounts = list(Account.objects.filter(is_active=True).order_by('name'))
    reconciliations = {
        item.account_id: item
        for item in AccountReconciliation.objects.filter(
            account__in=active_accounts,
            reconciled_on=closing_day,
        )
    }
    unreconciled_accounts = [
        account for account in active_accounts
        if account.pk not in reconciliations
    ]
    reconciliation_differences = [
        item for item in reconciliations.values()
        if item.difference != 0
    ]
    transaction_count = Transaction.objects.filter(date__gte=start, date__lt=end).count()
    transfer_count = Transfer.objects.filter(date__gte=start, date__lt=end).count()
    is_closed = MonthlyClosing.objects.filter(month=target_month).exists()
    has_warnings = is_closed or bool(unreconciled_accounts) or bool(reconciliation_differences)
    return {
        'target_month': target_month,
        'closing_day': closing_day,
        'snapshot': snapshot,
        'transaction_count': transaction_count,
        'transfer_count': transfer_count,
        'active_account_count': len(active_accounts),
        'unreconciled_accounts': unreconciled_accounts,
        'reconciliation_differences': reconciliation_differences,
        'is_closed': is_closed,
        'has_warnings': has_warnings,
    }