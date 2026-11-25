"""面向用户的字段校验消息，供请求校验和业务模型校验共同使用。"""
from typing import Any

FIELD_LABELS = {'org_id': '组织', 'title': '名称', 'status_code': '状态', 'remark': '备注', 'user_id': '用户', 'email': '邮箱'}



def format_validation_errors(errors: list[dict[str, Any]], labels: dict[str, str] | None = None) -> str:
    from app.framework.catalog import iter_module_attr
    names = dict(FIELD_LABELS)
    for module in iter_module_attr("validation_labels"):
        names.update(module.FIELD_LABELS)
    names.update(labels or {})
    missing, invalid = [], []
    for error in errors:
        location = [str(part) for part in error.get('loc', ()) if part not in ('body', 'query', 'path')]
        field = names.get(location[-1], location[-1]) if location else '提交内容'
        kind = error.get('type', '')
        value = error.get('input')
        empty = value is None or (isinstance(value, str) and not value.strip())
        if kind == 'missing' or (empty and kind != 'json_invalid'):
            if field not in missing:
                missing.append(field)
            continue
        raw = str(error.get('msg', '')).removeprefix('Value error, ')
        if kind == 'literal_error' or kind == 'enum':
            reason = '请选择有效选项'
        elif kind.startswith(('date_', 'datetime_')):
            reason = '日期格式不正确'
        elif kind == 'uuid_parsing':
            reason = '记录编号格式不正确'
        elif kind == 'string_too_long':
            reason = f"不能超过 {error.get('ctx', {}).get('max_length', '')} 个字符"
        elif kind == 'value_error' and raw:
            reason = raw
        else:
            reason = '格式或取值不正确'
        detail = f'{field}：{reason}'
        if detail not in invalid:
            invalid.append(detail)
    parts = ([f"请填写必填字段：{'、'.join(missing)}"] if missing else []) + invalid
    return '；'.join(parts) or '提交内容校验失败'
