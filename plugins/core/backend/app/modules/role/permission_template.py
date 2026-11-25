from __future__ import annotations

import io
import re
from dataclasses import dataclass, field
from typing import Any

from openpyxl import Workbook, load_workbook
from openpyxl.comments import Comment
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

from app.core.exceptions import AppException

ROLE_INFO_SHEET = "角色信息"
MENU_CONFIG_SHEET = "菜单权限配置"
PERMISSION_CONFIG_SHEET = "接口权限配置"
SCOPE_SHEET = "数据范围说明"

ROLE_INFO_HEADERS = ["角色编号", "角色名称", "说明", "默认数据范围"]
MENU_CONFIG_HEADERS = ["菜单分组", "菜单名称", "菜单标识"]
PERMISSION_CONFIG_HEADERS = ["接口权限名称", "权限标识"]

DATA_SCOPE_LABELS: dict[str, str] = {
    "all": "全部数据",
    "organization": "本组织",
    "department": "本部门",
    "self": "本人",
    "related": "关联关系",
}
DATA_SCOPE_BY_LABEL = {label: value for value, label in DATA_SCOPE_LABELS.items()}
YES_VALUES = {"是", "y", "yes", "true", "1", "√", "✓", "有"}
NO_VALUES = {"", "否", "n", "no", "false", "0", "无"}
ROLE_CODE_IN_HEADER_RE = re.compile(r"[（(]([a-z][a-z0-9_]*)[）)]\s*$")


@dataclass(frozen=True)
class RoleTemplateRow:
    row_number: int
    role_no: str
    role_name: str
    description: str | None
    data_scope_code: str
    menu_keys: list[str] = field(default_factory=list)
    permission_scopes: dict[str, str] = field(default_factory=dict)


def cell_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


def normalize_data_scope_text(value: Any) -> str:
    text = cell_text(value)
    if not text:
        return "organization"
    return DATA_SCOPE_BY_LABEL.get(text, text)


def _permission_selected(value: Any) -> bool:
    text = cell_text(value).lower()
    if text in YES_VALUES:
        return True
    if text in NO_VALUES:
        return False
    raise AppException(f"权限列只能选择“是”或“否”，当前值为：{cell_text(value)}")


def _validate_headers(ws, headers: list[str], sheet_name: str) -> None:
    actual = [cell_text(ws.cell(row=1, column=i).value) for i in range(1, len(headers) + 1)]
    if actual != headers:
        raise AppException(f"{sheet_name} 表头不匹配，请重新下载最新模板后填写")


def _role_code_from_header(header: str, roles_by_code: dict[str, RoleTemplateRow], roles_by_name: dict[str, list[str]]) -> str:
    text = header.strip()
    if text in roles_by_code:
        return text

    match = ROLE_CODE_IN_HEADER_RE.search(text)
    if match and match.group(1) in roles_by_code:
        return match.group(1)

    matched_codes = roles_by_name.get(text, [])
    if len(matched_codes) == 1:
        return matched_codes[0]
    if len(matched_codes) > 1:
        raise AppException(f"角色列「{text}」匹配到多个同名角色，请在列名中补充角色编号，例如：{text}（角色编号）")
    raise AppException(f"角色列「{text}」未在“角色信息”中配置")


def _parse_role_info(wb) -> tuple[dict[str, RoleTemplateRow], dict[str, list[str]]]:
    if ROLE_INFO_SHEET not in wb.sheetnames:
        raise AppException(f"Excel 缺少工作表：{ROLE_INFO_SHEET}")
    ws = wb[ROLE_INFO_SHEET]
    _validate_headers(ws, ROLE_INFO_HEADERS, ROLE_INFO_SHEET)

    roles_by_code: dict[str, RoleTemplateRow] = {}
    roles_by_name: dict[str, list[str]] = {}
    for row_number in range(2, ws.max_row + 1):
        values = [ws.cell(row=row_number, column=col).value for col in range(1, len(ROLE_INFO_HEADERS) + 1)]
        if not any(cell_text(value) for value in values):
            continue
        role = RoleTemplateRow(
            row_number=row_number,
            role_no=cell_text(values[0]),
            role_name=cell_text(values[1]),
            description=cell_text(values[2]) or None,
            data_scope_code=normalize_data_scope_text(values[3]),
        )
        if role.role_no in roles_by_code:
            raise AppException(f"角色信息第 {row_number} 行：角色编号 {role.role_no} 重复")
        roles_by_code[role.role_no] = role
        roles_by_name.setdefault(role.role_name, []).append(role.role_no)
    return roles_by_code, roles_by_name


def _parse_role_columns(
    ws,
    *,
    fixed_column_count: int,
    roles_by_code: dict[str, RoleTemplateRow],
    roles_by_name: dict[str, list[str]],
) -> dict[int, str]:
    role_columns: dict[int, str] = {}
    for col in range(fixed_column_count + 1, ws.max_column + 1):
        header = cell_text(ws.cell(row=1, column=col).value)
        if not header:
            continue
        role_columns[col] = _role_code_from_header(header, roles_by_code, roles_by_name)
    return role_columns


def _parse_menu_sheet(
    wb,
    roles_by_code: dict[str, RoleTemplateRow],
    roles_by_name: dict[str, list[str]],
) -> dict[str, list[str]]:
    if MENU_CONFIG_SHEET not in wb.sheetnames:
        raise AppException(f"Excel 缺少工作表：{MENU_CONFIG_SHEET}")
    ws = wb[MENU_CONFIG_SHEET]
    _validate_headers(ws, MENU_CONFIG_HEADERS, MENU_CONFIG_SHEET)
    role_columns = _parse_role_columns(
        ws,
        fixed_column_count=len(MENU_CONFIG_HEADERS),
        roles_by_code=roles_by_code,
        roles_by_name=roles_by_name,
    )
    menu_codes_by_role = {code: [] for code in roles_by_code}
    for row_number in range(2, ws.max_row + 1):
        menu_code = cell_text(ws.cell(row=row_number, column=3).value)
        if not menu_code:
            continue
        for col, role_code in role_columns.items():
            try:
                selected = _permission_selected(ws.cell(row=row_number, column=col).value)
            except AppException as exc:
                raise AppException(f"{MENU_CONFIG_SHEET} 第 {row_number} 行「{ws.cell(row=1, column=col).value}」：{exc.message}") from exc
            if selected:
                menu_codes_by_role.setdefault(role_code, []).append(menu_code)
    return menu_codes_by_role


def _parse_permission_sheet(
    wb,
    roles_by_code: dict[str, RoleTemplateRow],
    roles_by_name: dict[str, list[str]],
) -> dict[str, dict[str, str]]:
    if PERMISSION_CONFIG_SHEET not in wb.sheetnames:
        raise AppException(f"Excel 缺少工作表：{PERMISSION_CONFIG_SHEET}")
    ws = wb[PERMISSION_CONFIG_SHEET]
    _validate_headers(ws, PERMISSION_CONFIG_HEADERS, PERMISSION_CONFIG_SHEET)
    role_columns = _parse_role_columns(
        ws,
        fixed_column_count=len(PERMISSION_CONFIG_HEADERS),
        roles_by_code=roles_by_code,
        roles_by_name=roles_by_name,
    )
    permission_scopes_by_role = {code: {} for code in roles_by_code}
    for row_number in range(2, ws.max_row + 1):
        permission_code = cell_text(ws.cell(row=row_number, column=2).value)
        if not permission_code:
            continue
        for col, role_code in role_columns.items():
            try:
                selected = _permission_selected(ws.cell(row=row_number, column=col).value)
            except AppException as exc:
                raise AppException(f"{PERMISSION_CONFIG_SHEET} 第 {row_number} 行「{ws.cell(row=1, column=col).value}」：{exc.message}") from exc
            if selected:
                permission_scopes_by_role.setdefault(role_code, {})[permission_code] = roles_by_code[role_code].data_scope_code
    return permission_scopes_by_role


def parse_template_rows(content: bytes) -> list[RoleTemplateRow]:
    try:
        wb = load_workbook(io.BytesIO(content), data_only=True)
    except Exception as exc:  # openpyxl exposes multiple format exceptions.
        raise AppException("无法读取 Excel 模板，请上传系统下载的 .xlsx 模板") from exc

    roles_by_code, roles_by_name = _parse_role_info(wb)
    menu_codes_by_role = _parse_menu_sheet(wb, roles_by_code, roles_by_name)
    permission_scopes_by_role = _parse_permission_sheet(wb, roles_by_code, roles_by_name)
    rows: list[RoleTemplateRow] = []
    for code, role in roles_by_code.items():
        rows.append(
            RoleTemplateRow(
                row_number=role.row_number,
                role_no=role.role_no,
                role_name=role.role_name,
                description=role.description,
                data_scope_code=role.data_scope_code,
                menu_keys=list(dict.fromkeys(menu_codes_by_role.get(code, []))),
                permission_scopes=permission_scopes_by_role.get(code, {}),
            )
        )
    return rows


def _write_header(ws, headers: list[str]) -> None:
    fill = PatternFill("solid", fgColor="EAF2FF")
    for col, title in enumerate(headers, start=1):
        cell = ws.cell(row=1, column=col, value=title)
        cell.font = Font(bold=True)
        cell.fill = fill
        cell.alignment = Alignment(vertical="center", wrap_text=True)
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:{get_column_letter(len(headers))}1"


def _set_widths(ws, widths: list[int]) -> None:
    for index, width in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(index)].width = width


def _role_header(role: dict[str, Any]) -> str:
    name = str(role.get("role_name") or "").strip()
    code = str(role.get("role_no") or "").strip()
    return f"{name}（{code}）" if name else code


def _add_scope_validation(ws) -> None:
    scope_validation = DataValidation(
        type="list",
        formula1=f'"{",".join(DATA_SCOPE_LABELS.values())}"',
        allow_blank=False,
    )
    ws.add_data_validation(scope_validation)
    scope_validation.add("D2:D1048576")


def _add_yes_no_validation(ws, first_role_col: int, last_role_col: int) -> None:
    if last_role_col < first_role_col:
        return
    yes_no_validation = DataValidation(type="list", formula1='"是,否"', allow_blank=True)
    ws.add_data_validation(yes_no_validation)
    yes_no_validation.add(f"{get_column_letter(first_role_col)}2:{get_column_letter(last_role_col)}1048576")


def _write_role_info_sheet(wb: Workbook, roles: list[dict[str, Any]]) -> None:
    ws = wb.active
    assert ws is not None
    ws.title = ROLE_INFO_SHEET
    _write_header(ws, ROLE_INFO_HEADERS)
    _set_widths(ws, [22, 24, 32, 18])
    ws.cell(row=1, column=1).comment = Comment(
        "必填。存在则更新角色，不存在则创建角色。只能使用小写字母、数字、下划线，且小写字母开头。",
        "系统",
    )
    ws.cell(row=1, column=4).comment = Comment("中文下拉选择；接口权限的数据范围统一使用这里的值。", "系统")
    _add_scope_validation(ws)
    for row_idx, role in enumerate(roles, start=2):
        ws.cell(row=row_idx, column=1, value=role.get("role_no"))
        ws.cell(row=row_idx, column=2, value=role.get("role_name"))
        ws.cell(row=row_idx, column=3, value=role.get("description") or "")
        ws.cell(row=row_idx, column=4, value=DATA_SCOPE_LABELS.get(role.get("data_scope_code"), "本组织"))
    if not roles:
        ws.cell(row=2, column=4, value="本组织")


def _write_menu_config_sheet(wb: Workbook, roles: list[dict[str, Any]], menus: list[dict[str, Any]]) -> None:
    role_headers = [_role_header(role) for role in roles]
    ws = wb.create_sheet(MENU_CONFIG_SHEET)
    _write_header(ws, MENU_CONFIG_HEADERS + role_headers)
    _set_widths(ws, [24, 28, 18] + [16 for _ in roles])
    ws.column_dimensions["C"].hidden = True
    ws.freeze_panes = "D2"
    _add_yes_no_validation(ws, len(MENU_CONFIG_HEADERS) + 1, len(MENU_CONFIG_HEADERS) + len(roles))
    for idx, role in enumerate(roles, start=len(MENU_CONFIG_HEADERS) + 1):
        ws.cell(row=1, column=idx).comment = Comment(f"角色编号：{role.get('role_no')}", "系统")

    menu_codes_by_role = {role.get("role_no"): set(role.get("menu_keys") or []) for role in roles}
    for row_idx, menu in enumerate(menus, start=2):
        ws.cell(row=row_idx, column=1, value=menu.get("parent_name") or "独立菜单")
        ws.cell(row=row_idx, column=2, value=menu.get("menu_name"))
        ws.cell(row=row_idx, column=3, value=menu.get("menu_key"))
        for role_idx, role in enumerate(roles, start=len(MENU_CONFIG_HEADERS) + 1):
            selected = menu.get("menu_key") in menu_codes_by_role.get(role.get("role_no"), set())
            ws.cell(row=row_idx, column=role_idx, value="是" if selected else "否")


def _write_permission_config_sheet(wb: Workbook, roles: list[dict[str, Any]], permissions: list[dict[str, Any]]) -> None:
    role_headers = [_role_header(role) for role in roles]
    ws = wb.create_sheet(PERMISSION_CONFIG_SHEET)
    _write_header(ws, PERMISSION_CONFIG_HEADERS + role_headers)
    _set_widths(ws, [34, 24] + [16 for _ in roles])
    ws.column_dimensions["B"].hidden = True
    ws.freeze_panes = "C2"
    _add_yes_no_validation(ws, len(PERMISSION_CONFIG_HEADERS) + 1, len(PERMISSION_CONFIG_HEADERS) + len(roles))
    for idx, role in enumerate(roles, start=len(PERMISSION_CONFIG_HEADERS) + 1):
        ws.cell(row=1, column=idx).comment = Comment(f"角色编号：{role.get('role_no')}", "系统")

    permission_codes_by_role = {role.get("role_no"): set(role.get("permission_keys") or []) for role in roles}
    for row_idx, permission in enumerate(permissions, start=2):
        ws.cell(row=row_idx, column=1, value=permission.get("permission_name"))
        ws.cell(row=row_idx, column=2, value=permission.get("permission_key"))
        for role_idx, role in enumerate(roles, start=len(PERMISSION_CONFIG_HEADERS) + 1):
            selected = permission.get("permission_key") in permission_codes_by_role.get(role.get("role_no"), set())
            ws.cell(row=row_idx, column=role_idx, value="是" if selected else "否")


def _write_scope_sheet(wb: Workbook) -> None:
    scope_ws = wb.create_sheet(SCOPE_SHEET)
    _write_header(scope_ws, ["数据范围", "中文说明"])
    _set_widths(scope_ws, [24, 24])
    for row_idx, (code, label) in enumerate(DATA_SCOPE_LABELS.items(), start=2):
        scope_ws.cell(row=row_idx, column=1, value=code)
        scope_ws.cell(row=row_idx, column=2, value=label)


def build_role_permission_template(
    *,
    roles: list[dict[str, Any]],
    menus: list[dict[str, Any]],
    permissions: list[dict[str, Any]],
) -> bytes:
    wb = Workbook()
    _write_role_info_sheet(wb, roles)
    _write_menu_config_sheet(wb, roles, menus)
    _write_permission_config_sheet(wb, roles, permissions)
    _write_scope_sheet(wb)

    for sheet in wb.worksheets:
        for row in sheet.iter_rows():
            for cell in row:
                cell.alignment = Alignment(vertical="top", wrap_text=True)

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


__all__ = [
    "DATA_SCOPE_LABELS",
    "RoleTemplateRow",
    "build_role_permission_template",
    "parse_template_rows",
]
