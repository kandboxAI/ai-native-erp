"""自定义字段只校验登记值，不连接数据库。"""
from types import SimpleNamespace

import pytest
from app.core.exceptions import AppException
from app.modules.sample_app.flex_values import normalize_flex_form


def field(key, value_type, *, required=False, active=True):
    return SimpleNamespace(field_key=key, field_name=key, value_type_code=value_type, is_required=required, is_active=active)


def test_number_date_and_boolean_are_stored_without_business_rules():
    definitions = [field("monthly_wage", "number"), field("joined_on", "date"), field("onsite", "boolean", required=True)]
    result = normalize_flex_form(definitions, {"monthly_wage": "1351.1900", "joined_on": "2026-10-01", "onsite": True}, {})
    assert result == {"monthly_wage": "1351.19", "joined_on": "2026-10-01", "onsite": True}


def test_optional_blank_is_removed_and_inactive_value_is_kept():
    definitions = [field("note", "string"), field("old_note", "string", active=False)]
    result = normalize_flex_form(definitions, {"note": "  "}, {"old_note": "保留", "note": "旧值"})
    assert result == {"old_note": "保留"}


def test_missing_required_and_unknown_key_are_rejected():
    definitions = [field("note", "string", required=True)]
    with pytest.raises(AppException, match="请填写note"):
        normalize_flex_form(definitions, {}, {})
    with pytest.raises(AppException, match="未定义"):
        normalize_flex_form(definitions, {"note": "有", "extra": "不行"}, {})


def test_omitted_payload_keeps_previous_values():
    definitions = [field("note", "string", required=True)]
    assert normalize_flex_form(definitions, None, {"note": "已登记"}) == {"note": "已登记"}
