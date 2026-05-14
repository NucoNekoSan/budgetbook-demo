"""CSV インポートのビュー。

GET: アップロードフォーム
POST (csv_file あり, confirm なし): プレビュー
POST (confirm=1, csv_text + selected_lines): 確定 → ダッシュボードへリダイレクト

仕様: docs/specs/v1.8.0_csv_import.md
"""
from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from ..forms import CsvImportForm
from ..models import AuditLog, Transaction
from ..services.csv_import import (
    CsvImportError,
    build_preview_rows,
    commit_rows,
    decode_csv_bytes,
    parse_csv,
)
from .helpers import record_audit


@login_required
@require_http_methods(['GET', 'POST'])
def transaction_import(request: HttpRequest) -> HttpResponse:
    if request.method == 'GET':
        return render(request, 'ledger/csv_import.html', {
            'form': CsvImportForm(),
        })

    # 確定 POST
    if request.POST.get('confirm') == '1':
        return _handle_confirm(request)

    # アップロード（プレビュー）
    form = CsvImportForm(request.POST, request.FILES)
    if not form.is_valid():
        return render(request, 'ledger/csv_import.html', {'form': form})

    f = form.cleaned_data['csv_file']
    try:
        text = decode_csv_bytes(f.read())
        rows = parse_csv(text)
    except CsvImportError as e:
        form.add_error('csv_file', str(e))
        return render(request, 'ledger/csv_import.html', {'form': form})

    preview = build_preview_rows(rows)
    importable = [pr for pr in preview if pr.is_importable]
    return render(request, 'ledger/csv_import_preview.html', {
        'preview': preview,
        'importable_count': len(importable),
        'error_count': sum(1 for pr in preview if pr.status.startswith('error_')),
        'duplicate_count': sum(1 for pr in preview if pr.status == 'warning_duplicate'),
        'skip_count': sum(1 for pr in preview if pr.status == 'skip_transfer'),
        'csv_text': text,
        'filename': f.name,
    })


def _handle_confirm(request: HttpRequest) -> HttpResponse:
    text = request.POST.get('csv_text', '')
    filename = request.POST.get('filename', '')
    selected_raw = request.POST.getlist('selected_lines')
    try:
        selected_indices = {int(s) for s in selected_raw}
    except ValueError:
        messages.error(request, '不正な選択値が含まれています。')
        return redirect('ledger:transaction_import')

    # サーバ側で再パース・再検証（クライアントの hidden を信用しない）
    try:
        rows = parse_csv(text)
    except CsvImportError as e:
        messages.error(request, f'CSV の再検証に失敗しました: {e}')
        return redirect('ledger:transaction_import')
    preview = build_preview_rows(rows)

    with transaction.atomic():
        created_ids = commit_rows(preview, selected_indices)

    if created_ids:
        record_audit(
            request, AuditLog.Action.CREATE,
            Transaction(),
            f'CSV インポートで {len(created_ids)} 件の取引を作成しました。',
            {
                'count': len(created_ids),
                'created_ids': created_ids,
                'filename': filename[:120],
            },
            target_id='bulk', target_repr='CSV インポート (一括)',
        )
        messages.success(request, f'{len(created_ids)} 件の取引を取り込みました。')
    else:
        messages.warning(request, '取込対象がありませんでした。')
    return redirect(reverse('ledger:dashboard'))