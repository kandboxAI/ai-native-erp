from __future__ import annotations

import io
from datetime import datetime
from decimal import Decimal
from typing import Any
from zipfile import ZipFile

from openpyxl import Workbook, load_workbook
from openpyxl.comments import Comment
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.workbook.defined_name import DefinedName
from pydantic import BaseModel, ValidationError

from app.core.exceptions import AppException
from app.framework.export.xlsx_builder import XLSX_MEDIA_TYPE

from .schemas import (
    InventoryImportIssue,
    ItemCategoryImportRow,
    ItemImportRow,
    ItemTemplateChoices,
    StockImportRow,
    StockTemplateChoices,
)

MAX_IMPORT_BYTES = 5 * 1024 * 1024
MAX_TEMPLATE_ROWS = 1000
MAX_ITEM_ROWS = 10000
SHEET_OPTIONS = "_下拉选项"
SHEET_CATEGORY = "物料分类"
SHEET_ITEM = "物料档案"
SHEET_STOCK = "库存盘点"

_HEADER_FILL = PatternFill("solid", fgColor="1F4E79")
_HEADER_FONT = Font(color="FFFFFF", bold=True, size=11)
_REQUIRED_FILL = PatternFill("solid", fgColor="FFF2CC")
_REQUIRED_FONT = Font(color="000000", bold=True, size=11)

CATEGORY_HEADERS = [
    ("category_name", "分类名称", True, "物料分类名称，同名分类不能重复"),
    ("description", "分类说明", False, "选填，用于说明该分类的适用范围"),
]

ITEM_HEADERS = [
    ("category_name", "物料分类", False, "选填；填写时从系统已有分类下拉中选择，留空表示无分类"),
    ("item_name", "物料名称", True, "物料名称"),
    ("specification", "规格型号", False, "例如 500ml、10片/盒；可留空"),
    ("unit_name", "单位", True, "从下拉选择（字典：计量单位）"),
    ("sub_unit_name", "辅助单位", False, "选填，从下拉选择"),
    ("unit_price", "参考单价", False, "元/基本单位，最多2位小数；留空清空，0保留为有效值"),
    ("supplier_name", "默认供应商", False, "选填；如填写，必须从系统启用供应商中选择"),
    ("is_active", "是否启用", True, "从下拉选择“是”或“否”"),
    ("remark", "备注", False, "选填"),
    ("item_no", "物料编号", False, "填写时按编号匹配；新物料可指定编号，留空自动生成"),
    ("is_lot_controlled", "批次管理", True, "从下拉选择“是”或“否”"),
    ("shelf_life_days", "保质期（天）", False, "非负整数；留空表示未设置"),
    ("is_asset_managed", "纳入资产管理", True, "是/否；只有选择是的物料才可新增资产登记，不代表财务固定资产认定"),
    ("default_asset_type_code", "默认资产类型", False, "选填，从资产类型下拉选择；留空清空原值"),
]

STOCK_HEADERS = [
    ("warehouse_label", "仓库", True, "必须从下拉选择：组织 / 仓库"),
    ("item_selection", "物料", True, "必须从系统启用物料中选择：物料编号｜物料名称｜规格"),
    ("counted_quantity", "实盘数量", True, "盘点后的实际库存，不是增加数量；最多 3 位小数"),
    ("lot_no", "批次号", False, "选填；不填表示无批次库存"),
    ("production_date", "生产日期", False, "格式 YYYY-MM-DD"),
    ("expiry_date", "有效期", False, "格式 YYYY-MM-DD，不能早于生产日期"),
    ("remark", "备注", False, "选填"),
]


def build_category_template() -> bytes:
    wb, ws = _base_workbook(
        SHEET_CATEGORY,
        [
            "物料分类导入说明",
            "1. 一行代表一个物料分类；黄色表头为必填，蓝色表头为选填。",
            "2. 默认不覆盖系统已有同名分类；确需更新说明时，请在导入窗口开启“允许更新已有数据”。",
            "3. 正式导入前必须先预校验，整批数据在同一事务内提交或回滚。",
        ],
    )
    _write_headers(ws, CATEGORY_HEADERS)
    return _save(wb)


def _item_workbook(choices: ItemTemplateChoices):
    wb, ws = _base_workbook(
        SHEET_ITEM,
        [
            "物料档案导入说明",
            "1. 请先维护或导入物料分类，再下载最新模板。",
            "2. 填写物料编号时按编号匹配；留空按名称+规格匹配，新增时自动生成编号。",
            "3. 默认不覆盖已有物料；确需更新时，请在导入窗口开启“允许更新已有数据”。",
            "4. 正式导入前必须先预校验，整批数据在同一事务内提交或回滚。",
            "5. 可选字段留空会清空原值，0保留；导出文件可直接修改后回导，更新须开启允许更新已有数据。",
            "6. 分类、规格可留空；是否启用、批次管理及纳入资产管理填写是/否，保质期填写非负整数。",
            "7. 单文件不超过5MB、最多10000条物料；不支持公式单元格。纳入资产管理的物料统一逐件编号，无需选择登记方式。",
        ],
    )
    ranges = _write_options(
        wb,
        {"categories": choices.categories, "suppliers": choices.suppliers, "units": choices.units, "yes_no": ["是", "否"], "asset_types": choices.asset_types},
        "item_import",
    )
    _write_headers(
        ws,
        ITEM_HEADERS,
        dropdowns={
            "category_name": ranges.get("categories"),
            "unit_name": ranges.get("units"),
            "sub_unit_name": ranges.get("units"),
            "supplier_name": ranges.get("suppliers"),
            "is_active": ranges.get("yes_no"),
            "is_lot_controlled": ranges.get("yes_no"),
            "is_asset_managed": ranges.get("yes_no"),
            "default_asset_type_code": ranges.get("asset_types"),
        },
    )
    return wb, ws


def build_item_template(choices: ItemTemplateChoices) -> bytes:
    wb, _ = _item_workbook(choices)
    return _save(wb)


def build_item_export(choices: ItemTemplateChoices, rows: list[dict[str, Any]]) -> bytes:
    wb, ws = _item_workbook(choices)
    for row in rows:
        values = []
        for field, _label, _required, _note in ITEM_HEADERS:
            value = row.get(field)
            if isinstance(value, bool):
                value = "是" if value else "否"
            elif isinstance(value, Decimal):
                value = str(value)
            values.append(value)
        ws.append(values)
        for cell in ws[ws.max_row]:
            if isinstance(cell.value, str):
                cell.data_type = "s"
                cell.number_format = "@"
    ws.auto_filter.ref = ws.dimensions
    return _save(wb)


def build_stock_template(choices: StockTemplateChoices) -> bytes:
    wb, ws = _base_workbook(
        SHEET_STOCK,
        [
            "库存盘点导入说明",
            "1. 实盘数量表示盘点后的实际库存，不是本次增加数量；重复导入相同数量不会重复入库。",
            "2. 默认只初始化空库存；已有非零库存需要调整时，请开启“允许更新已有数据”。",
            "3. 系统按每个仓库生成一张“盘点调整”库存单据并确认，按实盘数与账面数的差额记库存流水。",
            "4. 仓库和物料必须从系统下拉选择；正式导入前必须先预校验，整批事务提交或回滚。",
        ],
    )
    ranges = _write_options(wb, {"warehouses": choices.warehouses, "items": choices.items}, "stock_import")
    _write_headers(
        ws,
        STOCK_HEADERS,
        dropdowns={"warehouse_label": ranges.get("warehouses"), "item_selection": ranges.get("items")},
    )
    ws.cell(2, 3).number_format = "0.000"
    ws.cell(2, 5).number_format = "yyyy-mm-dd"
    ws.cell(2, 6).number_format = "yyyy-mm-dd"
    return _save(wb)


def parse_category_workbook(
    content: bytes, filename: str
) -> tuple[list[ItemCategoryImportRow], list[InventoryImportIssue]]:
    return _parse_workbook(content, filename, SHEET_CATEGORY, CATEGORY_HEADERS, ItemCategoryImportRow)


def parse_item_workbook(
    content: bytes, filename: str
) -> tuple[list[ItemImportRow], list[InventoryImportIssue]]:
    return _parse_workbook(content, filename, SHEET_ITEM, ITEM_HEADERS, ItemImportRow)


def parse_stock_workbook(
    content: bytes, filename: str
) -> tuple[list[StockImportRow], list[InventoryImportIssue]]:
    return _parse_workbook(content, filename, SHEET_STOCK, STOCK_HEADERS, StockImportRow)


def _base_workbook(sheet_name: str, instructions: list[str]):
    wb = Workbook()
    readme = wb.active
    assert readme is not None
    readme.title = "导入说明"
    for text in instructions:
        readme.append([text])
    readme.column_dimensions["A"].width = 110
    readme["A1"].fill = _HEADER_FILL
    readme["A1"].font = _HEADER_FONT
    readme.freeze_panes = "A2"
    ws = wb.create_sheet(sheet_name)
    return wb, ws


def _write_headers(
    ws,
    headers: list[tuple[str, str, bool, str]],
    dropdowns: dict[str, str | None] | None = None,
) -> None:
    dropdowns = dropdowns or {}
    ws.row_dimensions[1].height = 24
    for column, (field, label, required, note) in enumerate(headers, 1):
        cell = ws.cell(1, column, label)
        cell.fill = _REQUIRED_FILL if required else _HEADER_FILL
        cell.font = _REQUIRED_FONT if required else _HEADER_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.comment = Comment(note, "系统")
        ws.column_dimensions[get_column_letter(column)].width = max(14, min(len(label) + 8, 28))
        range_name = dropdowns.get(field)
        if not range_name:
            continue
        validation = DataValidation(
            type="list",
            formula1=f"={range_name}",
            allow_blank=not required,
        )
        validation.error = "请从系统下拉列表中选择"
        validation.errorTitle = "选项无效"
        validation.prompt = note
        validation.promptTitle = "填写说明"
        validation.showErrorMessage = True
        validation.showInputMessage = True
        ws.add_data_validation(validation)
        letter = get_column_letter(column)
        validation.add(f"{letter}2:{letter}{MAX_TEMPLATE_ROWS + 1}")
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:{get_column_letter(len(headers))}1"


def _write_options(
    wb: Workbook,
    options: dict[str, list[str]],
    prefix: str,
) -> dict[str, str]:
    ws = wb.create_sheet(SHEET_OPTIONS)
    ranges: dict[str, str] = {}
    for column, (key, values) in enumerate(options.items(), 1):
        ws.cell(1, column, key)
        clean_values = sorted({str(value).strip() for value in values if str(value).strip()})
        for row, value in enumerate(clean_values, 2):
            ws.cell(row, column, value)
        if clean_values:
            letter = get_column_letter(column)
            name = f"{prefix}_{key}"
            wb.defined_names.add(
                DefinedName(name, attr_text=f"'{SHEET_OPTIONS}'!${letter}$2:${letter}${len(clean_values) + 1}")
            )
            ranges[key] = name
        ws.column_dimensions[get_column_letter(column)].width = 48
    ws.sheet_state = "veryHidden"
    return ranges


def _parse_workbook(
    content: bytes,
    filename: str,
    sheet_name: str,
    headers: list[tuple[str, str, bool, str]],
    row_model: type[BaseModel],
):
    if len(content) > MAX_IMPORT_BYTES:
        raise AppException("Excel 文件过大（上限 5MB）", status_code=400)
    if not filename.lower().endswith(".xlsx"):
        raise AppException("仅支持系统下载的 .xlsx 导入模板", status_code=400)
    try:
        with ZipFile(io.BytesIO(content)) as archive:
            if sum(info.file_size for info in archive.infolist()) > 32 * 1024 * 1024:
                raise ValueError("解压内容过大")
        wb = load_workbook(io.BytesIO(content), data_only=sheet_name != SHEET_ITEM, read_only=True)
    except Exception as exc:
        raise AppException("Excel 文件损坏或格式不正确", status_code=400) from exc
    try:
        return _read_sheet(wb, sheet_name, headers, row_model)
    except AppException:
        raise
    except Exception as exc:
        raise AppException("Excel内容损坏或格式不正确，请重新下载模板填写") from exc
    finally:
        wb.close()


def _read_sheet(wb, sheet_name, headers, row_model):
    if sheet_name not in wb.sheetnames:
        return [], [InventoryImportIssue(sheet=sheet_name, row=1, message=f"缺少「{sheet_name}」工作表")]
    ws = wb[sheet_name]
    expected = [label for _field, label, _required, _note in headers]
    actual = [str(ws.cell(1, idx).value or "").strip() for idx in range(1, len(expected) + 1)]
    if sheet_name == SHEET_ITEM:
        if ws.max_column > len(expected):
            if ws.max_column == 15 and str(ws.cell(1, 15).value or "").strip() == "建议登记方式":
                headers = [*headers, ("default_asset_management_mode_code", "建议登记方式", False, "兼容旧模板；仅支持单件登记")]
                expected = [label for _, label, _, _ in headers]
                actual = [str(ws.cell(1, idx).value or "").strip() for idx in range(1, len(expected) + 1)]
            else:
                return [], [InventoryImportIssue(sheet=sheet_name, row=1, message="模板表头已被修改，请重新下载模板")]
        for width in (9, 12):
            if ws.max_column <= width and actual[:width] == expected[:width] and not any(actual[width:]):
                headers, expected, actual = headers[:width], expected[:width], actual[:width]
                break
    if actual != expected:
        return [], [
            InventoryImportIssue(
                sheet=sheet_name,
                row=1,
                message="模板表头已被修改，请重新下载模板",
            )
        ]

    fields = [field for field, _label, _required, _note in headers]
    labels = {field: label for field, label, _required, _note in headers}
    rows: list[BaseModel] = []
    errors: list[InventoryImportIssue] = []
    for row_no, cells in enumerate(ws.iter_rows(min_row=2, max_col=len(fields)), 2):
        if sheet_name == SHEET_ITEM and row_no > MAX_ITEM_ROWS + 1:
            errors.append(InventoryImportIssue(sheet=sheet_name, row=row_no, message="单次最多10000条物料，请拆分文件"))
            break
        values = [cell.value for cell in cells]
        if not any(value is not None and str(value).strip() for value in values):
            continue
        if sheet_name == SHEET_ITEM and any(cell.data_type in {"f", "e"} for cell in cells):
            errors.append(InventoryImportIssue(sheet=sheet_name, row=row_no, message="不支持公式或错误单元格，请填写实际值"))
            continue
        raw = {field: _clean_value(field, value) for field, value in zip(fields, values)}
        raw["row_no"] = row_no
        if sheet_name == SHEET_ITEM and len(headers) == 9 and raw.get("unit_price") is None:
            raw["unit_price"] = Decimal("0")
        if "is_active" in raw:
            raw["is_active"] = _yes_no(raw["is_active"])
        if "is_asset_managed" in raw:
            raw["is_asset_managed"] = _yes_no(raw["is_asset_managed"])
        if "is_lot_controlled" in raw:
            raw["is_lot_controlled"] = _yes_no(raw["is_lot_controlled"])
        if sheet_name == SHEET_ITEM:
            missing = [label for field, label, required, _ in headers if required and raw.get(field) is None]
            if missing:
                errors.extend(InventoryImportIssue(sheet=sheet_name, row=row_no, field=label, message="该字段必填") for label in missing)
                continue
        try:
            rows.append(row_model.model_validate(raw))
        except ValidationError as exc:
            for item in exc.errors():
                location = item.get("loc") or ()
                field = str(location[-1]) if location else ""
                errors.append(
                    InventoryImportIssue(
                        sheet=sheet_name,
                        row=row_no,
                        field=labels.get(field, field or None),
                        message=_validation_message(item),
                    )
                )
    if sheet_name == SHEET_ITEM and not rows and not errors:
        errors.append(InventoryImportIssue(sheet=sheet_name, row=2, message="没有可导入的物料数据"))
    return rows, errors


def _clean_value(field: str, value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, str):
        return value.strip() or None
    if isinstance(value, datetime) and field in {"production_date", "expiry_date"}:
        return value.date()
    if field in {
        "item_no",
        "category_name",
        "item_name",
        "specification",
        "unit_name",
        "sub_unit_name",
        "supplier_name",
        "warehouse_label",
        "item_selection",
        "lot_no",
    }:
        if isinstance(value, float) and value.is_integer():
            return str(int(value))
        return str(value).strip() or None
    return value


def _yes_no(value: Any) -> Any:
    if isinstance(value, bool):
        return value
    text = str(value or "").strip().lower()
    if text in {"是", "启用", "true", "1", "yes"}:
        return True
    if text in {"否", "停用", "false", "0", "no"}:
        return False
    return value


def _validation_message(error: dict[str, Any]) -> str:
    message = str(error.get("msg") or "")
    error_type = str(error.get("type") or "")
    if "库存下限必须小于库存上限" in message:
        return "库存下限必须小于库存上限"
    if "有效期不能早于生产日期" in message:
        return "有效期不能早于生产日期"
    if error_type == "missing":
        return "该字段必填"
    if "bool" in error_type:
        return "必须从下拉列表选择“是”或“否”"
    if "decimal" in error_type or error_type in {"greater_than", "greater_than_equal"}:
        return "必须填写符合范围要求的数字"
    if "date" in error_type:
        return "日期格式必须为 YYYY-MM-DD"
    if "string" in error_type:
        return "文本内容无效或超过长度限制"
    return "字段格式不正确"


def _save(wb: Workbook) -> bytes:
    output = io.BytesIO()
    wb.save(output)
    return output.getvalue()


__all__ = [
    "XLSX_MEDIA_TYPE",
    "build_category_template",
    "build_item_template",
    "build_stock_template",
    "parse_category_workbook",
    "parse_item_workbook",
    "parse_stock_workbook",
]
