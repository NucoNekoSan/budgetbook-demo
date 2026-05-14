"""CSV インポート: パース・検証・確定。

入力フォーマットは `transaction_export` と対称（日付,種別,口座,カテゴリ,金額,摘要,メモ）。
v1.8.0 仕様: docs/specs/v1.8.0_csv_import.md
"""
from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Iterable

from django.db.models import Q

from ..models import Account, Category, MonthlyClosing, Transaction
from .csv_safe import CSV_FORMULA_PREFIXES
from .dates import clamp_future_month, shift_month

MAX_ROWS = 1000
MAX_BYTES = 1 * 1024 * 1024  # 1 MiB
EXPECTED_HEADER = ['日付', '種別', '口座', 'カテゴリ', '金額', '摘要', 'メモ']

# 種別の表記揺れを許容
KIND_INCOME_LABELS = {'収入', 'income'}
KIND_EXPENSE_LABELS = {'支出', 'expense'}
KIND_TRANSFER_LABELS = {'振替', 'transfer'}


@dataclass
class PreviewRow:
    line_no: int  # 1-origin（ヘッダを 1 とすると 2 始まり）
    raw: list[str] = field(default_factory=list)
    status: str = 'ok'  # ok | warning_duplicate | skip_transfer | error_*
    errors: list[str] = field(default_factory=list)
    csv_unsafe: bool = False

    # 検証済みの確定用フィールド（status が ok / warning_duplicate のときのみ有効）
    date: date | None = None
    account_id: int | None = None
    category_id: int | None = None
    amount: int | None = None
    description: str = ''
    memo: str = ''

    @property
    def is_importable(self) -> bool:
        return self.status in ('ok', 'warning_duplicate')


class CsvImportError(Exception):
    """ファイルレベルの拒否（行内エラーではなく全体エラー）。"""


def decode_csv_bytes(raw: bytes) -> str:
    """UTF-8 → Shift_JIS の順でデコード試行。両方失敗で例外。"""
    if len(raw) > MAX_BYTES:
        raise CsvImportError(f'ファイルサイズが上限 ({MAX_BYTES} bytes) を超えています。')
    # UTF-8 BOM を剥がす
    if raw.startswith(b'\xef\xbb\xbf'):
        raw = raw[3:]
    for enc in ('utf-8', 'cp932'):  # cp932 は Shift_JIS の Windows 拡張上位互換
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    raise CsvImportError('文字コードを判定できませんでした（UTF-8 / Shift_JIS のみ対応）。')


def parse_csv(text: str) -> list[list[str]]:
    """ヘッダを除いた行のリストを返す。ヘッダ不一致は例外。"""
    reader = csv.reader(io.StringIO(text))
    try:
        header = next(reader)
    except StopIteration:
        raise CsvImportError('空のファイルです。')
    header = [c.strip().lstrip('﻿') for c in header]
    if header[:len(EXPECTED_HEADER)] != EXPECTED_HEADER:
        raise CsvImportError(
            f'ヘッダ行が期待と異なります。期待: {",".join(EXPECTED_HEADER)} / 実際: {",".join(header)}'
        )
    rows = []
    for row in reader:
        rows.append(row)
        if len(rows) > MAX_ROWS:
            raise CsvImportError(f'行数が上限 ({MAX_ROWS}) を超えています。')
    return rows


def _normalize(s: str) -> str:
    return (s or '').strip()


def _check_csv_unsafe(value: str) -> bool:
    if not value:
        return False
    return value[0] in CSV_FORMULA_PREFIXES


def build_preview_rows(rows: list[list[str]]) -> list[PreviewRow]:
    """各行を validate し PreviewRow を返す。DB アクセスはここで完結。"""
    # 口座・カテゴリ・締め済み月を先読み
    accounts = {a.name: a for a in Account.objects.filter(is_active=True)}
    categories = {c.name: c for c in Category.objects.filter(is_active=True)}
    closed_months = set(MonthlyClosing.objects.values_list('month', flat=True))
    future_cutoff = clamp_future_month(date.today())
    future_limit = shift_month(future_cutoff, 1)  # 翌月以降を未来扱い

    results: list[PreviewRow] = []
    for idx, row in enumerate(rows, start=2):  # ヘッダ=1
        pr = PreviewRow(line_no=idx, raw=list(row))
        # カラム数不足はパディング、超過は無視
        cells = (row + [''] * len(EXPECTED_HEADER))[:len(EXPECTED_HEADER)]
        date_s, kind_s, account_s, category_s, amount_s, description_s, memo_s = [
            _normalize(c) for c in cells
        ]
        pr.description = description_s
        pr.memo = memo_s

        if _check_csv_unsafe(description_s) or _check_csv_unsafe(memo_s):
            pr.csv_unsafe = True

        # 振替はスキップ扱い（エラーではない）
        if kind_s in KIND_TRANSFER_LABELS:
            pr.status = 'skip_transfer'
            results.append(pr)
            continue

        # 日付
        parsed_date = None
        for fmt in ('%Y-%m-%d', '%Y/%m/%d'):
            try:
                parsed_date = datetime.strptime(date_s, fmt).date()
                break
            except ValueError:
                continue
        if parsed_date is None:
            pr.status = 'error_date'
            pr.errors.append(f'日付を解釈できません: {date_s!r}')
            results.append(pr)
            continue
        if parsed_date >= future_limit:
            pr.status = 'error_date'
            pr.errors.append(f'未来日付は取込できません: {parsed_date}')
            results.append(pr)
            continue
        pr.date = parsed_date

        # 金額
        try:
            amount = int(amount_s.replace(',', ''))
        except (ValueError, AttributeError):
            pr.status = 'error_amount'
            pr.errors.append(f'金額が整数ではありません: {amount_s!r}')
            results.append(pr)
            continue
        if amount < 1:
            pr.status = 'error_amount'
            pr.errors.append(f'金額は 1 以上で入力してください: {amount}')
            results.append(pr)
            continue
        pr.amount = amount

        # 口座
        account = accounts.get(account_s)
        if not account:
            pr.status = 'error_account'
            pr.errors.append(f'口座が見つかりません: {account_s!r}')
            results.append(pr)
            continue
        pr.account_id = account.pk

        # カテゴリ
        category = categories.get(category_s)
        if not category:
            pr.status = 'error_category'
            pr.errors.append(f'カテゴリが見つかりません: {category_s!r}')
            results.append(pr)
            continue
        # 種別とカテゴリ.kind の整合
        if kind_s in KIND_INCOME_LABELS:
            expected_kind = Category.Kind.INCOME
        elif kind_s in KIND_EXPENSE_LABELS:
            expected_kind = Category.Kind.EXPENSE
        else:
            pr.status = 'error_category'
            pr.errors.append(f'種別は 収入/支出 を指定してください: {kind_s!r}')
            results.append(pr)
            continue
        if category.kind != expected_kind:
            pr.status = 'error_category'
            pr.errors.append(
                f'種別「{kind_s}」とカテゴリ「{category.name}」({category.get_kind_display()}) が一致しません'
            )
            results.append(pr)
            continue
        pr.category_id = category.pk

        # 月次締め
        month_start = parsed_date.replace(day=1)
        if month_start in closed_months:
            pr.status = 'error_closed_month'
            pr.errors.append(f'{month_start:%Y-%m} は締め済みのため取込できません')
            results.append(pr)
            continue

        # 重複検出
        if Transaction.objects.filter(
            date=parsed_date,
            account_id=pr.account_id,
            category_id=pr.category_id,
            amount=amount,
        ).exists():
            pr.status = 'warning_duplicate'

        results.append(pr)
    return results


def commit_rows(preview_rows: Iterable[PreviewRow], selected_indices: set[int]) -> list[int]:
    """確定処理。atomic 内で bulk_create。作成 ID リストを返す。

    selected_indices: line_no の集合。プレビュー側で取込対象として選択されたもの。
    """
    to_create: list[Transaction] = []
    for pr in preview_rows:
        if not pr.is_importable:
            continue
        if pr.line_no not in selected_indices:
            continue
        # CSV インジェクション保護: 表示時には Django autoescape が効くが、
        # ストレージにも先頭プレフィクスは付けない（既存運用と整合）。
        to_create.append(Transaction(
            date=pr.date,
            account_id=pr.account_id,
            category_id=pr.category_id,
            amount=pr.amount,
            description=pr.description[:120],
            memo=pr.memo,
        ))
    if not to_create:
        return []
    created = Transaction.objects.bulk_create(to_create)
    return [t.pk for t in created]