from __future__ import annotations

import io
from typing import Any

from openpyxl import Workbook, load_workbook
from openpyxl.comments import Comment
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation
from pydantic import ValidationError

from app.core.exceptions import AppException
from app.framework.export.xlsx_builder import XLSX_MEDIA_TYPE

from .import_models import OrganizationImportError, OrganizationImportRow

MAX_IMPORT_BYTES = 5 * 1024 * 1024
MAX_TEMPLATE_ROWS = 1000
SHEET_DATA = "组织架构"

HEADERS = [
    ("node_type", "类型", True, "集团/组织/部门"),
    ("org_name", "组织名称", True, "集团/组织名称；部门行填写所属组织名称"),
    ("parent_org_name", "上级组织名称", False, "仅集团/组织行需要；不填表示挂在根组织下"),
    ("leader_name", "联系人", False, ""),
    ("contact_phone", "联系电话", False, ""),
    ("province", "省", False, ""),
    ("city", "市", False, ""),
    ("district", "区/县", False, ""),
    ("address", "详细地址", False, ""),
    ("department_name", "部门名称", False, "类型为部门时必填；组织行填写时作为该组织直属部门"),
    ("parent_department_name", "上级部门名称", False, "仅支持同一组织内的上级部门"),
    ("sort_no", "排序号", False, "不填默认为 0"),
    ("is_active", "是否启用", False, "是/否，不填默认为是"),
    ("remark", "备注", False, ""),
]

_HEADER_FILL = PatternFill("solid", fgColor="1F4E79")
_REQUIRED_FILL = PatternFill("solid", fgColor="FFF2CC")
_HEADER_FONT = Font(color="FFFFFF", bold=True)


def build_organization_import_template() -> bytes:
    wb = Workbook()
    readme = wb.active
    readme.title = "导入说明"
    for text in [
        "组织架构导入说明",
        "1. 类型填写“集团”“组织”或“部门”；不需要填写 ID 或编号，系统会自动生成编号。",
        "2. 部门行必须填写所属组织名称和部门名称；可引用同一模板前面创建的组织。组织行同时填写部门名称时，会创建该组织直属部门。",
        "3. 默认不覆盖已有组织与部门；如确需更新，请在页面勾选允许更新已有数据。",
    ]:
        readme.append([text])
    readme.column_dimensions["A"].width = 110

    ws = wb.create_sheet(SHEET_DATA)
    for col_idx, (field, label, required, comment) in enumerate(HEADERS, 1):
        cell = ws.cell(1, col_idx, label)
        cell.fill = _REQUIRED_FILL if required else _HEADER_FILL
        cell.font = Font(bold=True) if required else _HEADER_FONT
        cell.alignment = Alignment(horizontal="center")
        if comment:
            cell.comment = Comment(comment, "系统")
        ws.column_dimensions[get_column_letter(col_idx)].width = max(14, min(len(label) + 8, 26))
        if field == "node_type":
            _add_list_validation(ws, col_idx, ["集团", "组织", "部门"], required)
        elif field == "is_active":
            _add_list_validation(ws, col_idx, ["是", "否"], required)
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:{get_column_letter(len(HEADERS))}1"

    output = io.BytesIO()
    wb.save(output)
    return output.getvalue()


def _add_list_validation(ws, col_idx: int, values: list[str], required: bool) -> None:
    validation = DataValidation(type="list", formula1=f'"{",".join(values)}"', allow_blank=not required)
    validation.error = "请从下拉列表中选择"
    validation.errorTitle = "选项无效"
    validation.showErrorMessage = True
    ws.add_data_validation(validation)
    letter = get_column_letter(col_idx)
    validation.add(f"{letter}2:{letter}{MAX_TEMPLATE_ROWS + 1}")


def parse_organization_import_workbook(
    content: bytes, filename: str
) -> tuple[list[OrganizationImportRow], list[OrganizationImportError]]:
    if len(content) > MAX_IMPORT_BYTES:
        raise AppException("Excel 文件过大（上限 5MB）", status_code=400)
    if not filename.lower().endswith(".xlsx"):
        raise AppException("仅支持系统下载的 .xlsx 导入模板", status_code=400)
    try:
        wb = load_workbook(io.BytesIO(content), data_only=True, read_only=True)
    except Exception as exc:
        raise AppException("Excel 文件损坏或格式不正确", status_code=400) from exc
    if SHEET_DATA not in wb.sheetnames:
        return [], [OrganizationImportError(sheet=SHEET_DATA, row=1, message=f"缺少「{SHEET_DATA}」Sheet")]

    ws = wb[SHEET_DATA]
    expected = [label for _field, label, _required, _comment in HEADERS]
    actual = [str(ws.cell(1, idx).value or "").strip() for idx in range(1, len(expected) + 1)]
    if actual != expected:
        return [], [OrganizationImportError(sheet=SHEET_DATA, row=1, message="模板表头已被修改，请重新下载模板")]
    fields = [field for field, _label, _required, _comment in HEADERS]
    labels = {field: label for field, label, _required, _comment in HEADERS}
    result: list[OrganizationImportRow] = []
    errors: list[OrganizationImportError] = []
    for row_no, values in enumerate(ws.iter_rows(min_row=2, max_col=len(fields), values_only=True), 2):
        if not any(value is not None and str(value).strip() for value in values):
            continue
        raw = {field: _clean(value, field) for field, value in zip(fields, values)}
        raw["row_no"] = row_no
        raw["is_active"] = _yes_no(raw.get("is_active"))
        try:
            result.append(OrganizationImportRow.model_validate(raw))
        except ValidationError as exc:
            for item in exc.errors():
                field = str(item.get("loc", [""])[-1])
                errors.append(OrganizationImportError(
                    sheet=SHEET_DATA,
                    row=row_no,
                    field=labels.get(field, field),
                    message=_validation_message(item),
                ))
    return result, errors


def _clean(value: Any, field: str) -> Any:
    if value is None:
        if field == "sort_no":
            return 0
        return None
    if isinstance(value, str):
        if field == "sort_no" and not value.strip():
            return 0
        return value.strip() or None
    if field == "sort_no":
        return value
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip() or None


def _yes_no(value: Any) -> Any:
    if value is None or value == "":
        return True
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"是", "true", "1", "yes"}:
        return True
    if text in {"否", "false", "0", "no"}:
        return False
    return value


def _validation_message(error: dict[str, Any]) -> str:
    error_type = str(error.get("type") or "")
    if error_type == "missing":
        return "该字段必填"
    if "int" in error_type:
        return "必须填写整数"
    if "bool" in error_type:
        return "必须从下拉列表选择“是”或“否”"
    return str(error.get("msg") or "字段格式不正确")


__all__ = ["XLSX_MEDIA_TYPE", "build_organization_import_template", "parse_organization_import_workbook"]
