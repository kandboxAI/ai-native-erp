"""自定义字段只做登记：按页面定义校验后写入记录的 flex_form，不参与核算。"""
import re
from datetime import date
from decimal import Decimal, InvalidOperation

from app.core.exceptions import AppException

FORM_KEYS = {"employee_internal": "内部员工", "employee_outsourced": "外包项目人员", "project": "项目"}
VALUE_TYPES = {"string", "number", "date", "boolean"}
FIELD_KEY = re.compile(r"^[a-z][a-z0-9_]{0,62}$")


def require_form_key(form_key: str) -> str:
    if form_key not in FORM_KEYS:
        raise AppException(message="请选择内部员工、外包项目人员或项目", status_code=422)
    return form_key


def normalize_flex_form(definitions, incoming, previous) -> dict:
    """incoming 为空表示本次未提交扩展值，保留原值并仍检查必填项。"""
    stored = dict(previous or {})
    if incoming is None:
        _require(definitions, stored)
        return stored
    if not isinstance(incoming, dict):
        raise AppException(message="自定义字段格式不正确", status_code=422)
    defined = {row.field_key: row for row in definitions}
    unknown = sorted(set(incoming) - set(defined))
    if unknown:
        raise AppException(message=f"不能提交未定义的自定义字段：{'、'.join(unknown)}", status_code=422)
    result = {}
    for key, row in defined.items():
        if not row.is_active:
            if stored.get(key) not in (None, ""):
                result[key] = stored[key]
            continue
        present = key in incoming and incoming[key] not in (None, "")
        if present and row.value_type_code == "string" and not str(incoming[key]).strip():
            present = False
        if not present:
            if row.is_required:
                raise AppException(message=f"请填写{row.field_name}", status_code=422)
            continue
        result[key] = _coerce(row, incoming[key])
    return result


def _require(definitions, values: dict) -> None:
    for row in definitions:
        if row.is_active and row.is_required and values.get(row.field_key) in (None, ""):
            raise AppException(message=f"请填写{row.field_name}", status_code=422)


def _coerce(row, value):
    if row.value_type_code == "string":
        text = str(value).strip()
        if len(text) > 500:
            raise AppException(message=f"{row.field_name}不能超过 500 字", status_code=422)
        return text
    if row.value_type_code == "number":
        try:
            number = Decimal(str(value))
        except (InvalidOperation, ValueError):
            number = None
        if number is None or not number.is_finite() or number != number.quantize(Decimal("0.0001")) or abs(number) >= Decimal("100000000000000"):
            raise AppException(message=f"{row.field_name}须为数字，最多四位小数", status_code=422)
        return format(number.normalize(), "f")
    if row.value_type_code == "date":
        text = str(value)
        try:
            parsed = date.fromisoformat(text)
        except ValueError:
            parsed = None
        if parsed is None or parsed.isoformat() != text:
            raise AppException(message=f"{row.field_name}须为日期", status_code=422)
        return text
    if row.value_type_code == "boolean":
        if not isinstance(value, bool):
            raise AppException(message=f"{row.field_name}须为是或否", status_code=422)
        return value
    raise AppException(message=f"{row.field_name}的类型不正确", status_code=422)
