"""Ledger views package.

views.py から分割。urls.py / 既存テスト / management command の import 互換のため、
パブリックシンボルはここで re-export する。
"""
from __future__ import annotations

# --- services 再エクスポート（既存 import 互換） -------------------------------
from ..services.balance import (  # noqa: F401
    all_account_balances,
    calculate_account_balance,
    calculate_total_balance,
    compute_month_totals,
    is_month_closed,
)
from ..services.closing import (  # noqa: F401
    build_monthly_closing_preflight,
    build_monthly_closing_snapshot,
    enrich_monthly_closings_with_drift,
)
from ..services.csv_safe import (  # noqa: F401
    CSV_FORMULA_PREFIXES,
    csv_safe_cell,
    csv_safe_row,
)
from ..services.dashboard import (  # noqa: F401
    TRANSACTIONS_PER_PAGE,
    get_dashboard_context,
)
from ..services.dates import (  # noqa: F401
    clamp_future_month,
    clamp_future_year,
    default_transaction_date,
    month_end,
    month_from_entry_date,
    month_param,
    parse_month,
    parse_year,
    shift_month,
)
from ..services.filters import (  # noqa: F401
    build_filter_query_string,
    parse_filters,
    parse_preserved_filters,
)

# --- views helpers 再エクスポート -------------------------------------------
from .helpers import (  # noqa: F401
    build_form_context,
    build_transaction_form_context,
    build_transfer_form_context,
    closed_month_response,
    record_audit,
    render_dashboard_bundle,
    render_dashboard_oob,
    render_dashboard_section,
)

# --- 各ハンドラ ---------------------------------------------------------------
from .accounting import (  # noqa: F401
    accounting,
    monthly_closing_create,
    monthly_closing_delete,
    monthly_closing_resnapshot,
    reconciliation_create,
    reconciliation_delete,
)
from .dashboard import (  # noqa: F401
    category_options,
    dashboard,
    transaction_export,
)
from .balance_sheet import balance_sheet_view  # noqa: F401
from .csv_import import transaction_import  # noqa: F401
from .pwa import (  # noqa: F401
    manifest as pwa_manifest,
    offline as pwa_offline,
    service_worker as pwa_service_worker,
)
from .observability import login_history, metrics  # noqa: F401
from .budget import budget_edit  # noqa: F401
from .loan_strategy import loan_strategy_view  # noqa: F401
from .preview import transaction_preview  # noqa: F401
from .sections import sections_bulk_edit  # noqa: F401
from .health import healthz  # noqa: F401
from .reports import (  # noqa: F401
    annual,
    expense_breakdown,
    tax_deductions,
    tax_deductions_csv,
    tax_deductions_v2,
    tax_deductions_v2_csv,
)
from .medical import (  # noqa: F401
    income_snapshot_delete,
    income_snapshot_list,
    income_snapshot_save,
    medical_expense_create,
    medical_expense_csv,
    medical_expense_delete,
    medical_expense_list,
    medical_expense_update,
    transaction_medical_fields,
)
from .insurance import (  # noqa: F401
    insurance_premium_create,
    insurance_premium_csv,
    insurance_premium_delete,
    insurance_premium_list,
    insurance_premium_update,
)
from .settings_views import (  # noqa: F401
    account_create,
    account_delete,
    account_toggle,
    account_update,
    category_create,
    category_delete,
    category_toggle,
    category_update,
    settings_page,
)
from .transactions import (  # noqa: F401
    transaction_create,
    transaction_delete,
    transaction_inline_cancel,
    transaction_inline_update,
    transaction_update,
)
from .transfers import (  # noqa: F401
    transfer_create,
    transfer_delete,
    transfer_inline_cancel,
    transfer_inline_update,
    transfer_update,
)