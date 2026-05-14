from __future__ import annotations

# CSV インジェクション + Excel が解釈する制御文字を無害化する
CSV_FORMULA_PREFIXES = ('=', '+', '-', '@', '\t', '\r')


def csv_safe_cell(value):
    if not isinstance(value, str):
        return value
    if value and value.lstrip().startswith(CSV_FORMULA_PREFIXES):
        return "'" + value
    return value


def csv_safe_row(row: list):
    return [csv_safe_cell(value) for value in row]