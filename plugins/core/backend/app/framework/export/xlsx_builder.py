"""将 JSON 友好的行序列化为 Excel 2007（.xlsx），使用 openpyxl。"""

import io
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from openpyxl import Workbook
from openpyxl.worksheet.worksheet import Worksheet
from openpyxl.utils import get_column_letter

from app.framework.export.column_comments import export_column_header
from app.framework.export.row_sanitize import sanitize_export_rows
from app.framework.export.value_format import export_cell_display

if TYPE_CHECKING:
    from app.framework.export.relation_paths import ExportRelationPath

_WORKBOOK_CELL_MAX_CHARS = 32_767

WORKBOOK_FILENAME_EXTENSION = ".xlsx"

XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _safe_sheet_title(title: str) -> str:
    t = (title or "export").strip() or "export"
    return t[:31]


def _populate_worksheet(
    ws: Worksheet,
    rows: list[dict[str, Any]],
    *,
    header_lookup: dict[str, str] | None = None,
    relation_paths: "tuple[ExportRelationPath, ...] | None" = None,
    column_order: "tuple[str, ...] | None" = None,
    numeric_keys: "frozenset[str] | set[str] | None" = None,
) -> None:
    clean_rows = sanitize_export_rows(rows, relation_paths)
    if not clean_rows:
        return

    present = {k for row in clean_rows for k in row.keys()}
    # 业务导出需要「按业务顺序」出列（如先班级后金额），默认仍沿用字典序；
    # column_order 里没出现过的列追加在后面，保证数据不丢列。
    if column_order:
        headers_keys = [k for k in column_order if k in present]
        headers_keys += sorted(present - set(headers_keys))
    else:
        headers_keys = sorted(present)
    header_labels = [export_column_header(key, header_lookup) for key in headers_keys]

    # 金额列写成真数字，财务在 Excel 里才能直接求和；其余列保持文本。
    numbers = numeric_keys or frozenset()
    for col_idx, header_text in enumerate(header_labels, start=1):
        ws.cell(row=1, column=col_idx, value=header_text)
        ws.column_dimensions[get_column_letter(col_idx)].width = min(len(str(header_text)) + 2, 40)

    for row_idx, row in enumerate(clean_rows, start=2):
        for col_idx, name in enumerate(headers_keys, start=1):
            value = row.get(name)
            if name in numbers:
                number = _numeric_cell(value)
                # 转不成数字（空、非数字文本）时回退成文本，绝不丢数据
                if number is None:
                    ws.cell(row=row_idx, column=col_idx, value=export_cell_display(value))
                    continue
                cell = ws.cell(row=row_idx, column=col_idx, value=number)
                cell.number_format = "#,##0.00"
                letter = get_column_letter(col_idx)
                cur = ws.column_dimensions[letter].width or 10
                if min(16, len(header_labels[col_idx - 1]) + 4) > cur:
                    ws.column_dimensions[letter].width = min(16, len(header_labels[col_idx - 1]) + 4)
                continue
            text = export_cell_display(value)
            if len(text) >= _WORKBOOK_CELL_MAX_CHARS:
                text = f"{text[: _WORKBOOK_CELL_MAX_CHARS - 1]}…"
            ws.cell(row=row_idx, column=col_idx, value=text)
            letter = get_column_letter(col_idx)
            cur = ws.column_dimensions[letter].width or 10
            want = min(len(text.replace("\n", " ")) + 2, 60)
            if want > cur:
                ws.column_dimensions[letter].width = want


def _numeric_cell(value: Any) -> float | int | None:
    """把金额 / 数量类值转成 Excel 数字；无法转换（如空、文本）返回 ``None``。"""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return value
    if isinstance(value, Decimal):
        return float(value)
    text = str(value).strip().replace(",", "")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def build_xlsx_bytes(
    rows: list[dict[str, Any]],
    *,
    sheet_title: str = "export",
    header_lookup: dict[str, str] | None = None,
    relation_paths: "tuple[ExportRelationPath, ...] | None" = None,
    column_order: "tuple[str, ...] | None" = None,
    numeric_keys: "frozenset[str] | set[str] | None" = None,
) -> bytes:
    wb = Workbook()
    ws = wb.active
    assert ws is not None
    ws.title = _safe_sheet_title(sheet_title)
    _populate_worksheet(
        ws, rows, header_lookup=header_lookup, relation_paths=relation_paths,
        column_order=column_order, numeric_keys=numeric_keys,
    )

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def build_multi_sheet_xlsx_bytes(
    sheets: "list[tuple[str, list[dict[str, Any]], dict[str, str] | None, Any]]",
    *,
    column_orders: "dict[str, tuple[str, ...]] | None" = None,
    numeric_keys: "frozenset[str] | set[str] | None" = None,
) -> bytes:
    """多工作表导出；每项为 (表标题, 行数据, 表头映射, relation_paths)。

    ``column_orders`` 按表标题给出列顺序（缺省按字典序）。
    """
    wb = Workbook()
    ws0 = wb.active
    assert ws0 is not None
    first = True
    for sheet_title, rows, header_lookup, relation_paths in sheets:
        if first:
            ws = ws0
            first = False
        else:
            ws = wb.create_sheet()
        ws.title = _safe_sheet_title(sheet_title)
        _populate_worksheet(
            ws, rows, header_lookup=header_lookup, relation_paths=relation_paths,
            column_order=(column_orders or {}).get(sheet_title), numeric_keys=numeric_keys,
        )

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
