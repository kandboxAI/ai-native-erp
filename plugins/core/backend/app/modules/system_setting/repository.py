from __future__ import annotations

import json
from typing import Any

from fastapi import status
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.auth.schemas import AuthenticatedUser
from app.core.exceptions import AppException
from app.framework.crud.repository import ORGANIZATION_SCOPE_NONE, SqlModelCrudRepository

from .models import SysSetting
from .schemas import SystemSettingItem

# 代码定义的系统参数（setting_key 不可修改）；开通租户时补齐（tenant_setup），已存在的不覆盖。
DEFAULT_SETTINGS: list[dict[str, Any]] = [
    {
        "setting_key": "password_min_length",
        "setting_name": "密码最小长度",
        "setting_value": "8",
        "value_type_code": "number",
        "setting_group_code": "security",
        "description": "用户设置或重置密码时的最小长度。",
    },
    {
        "setting_key": "password_history_count",
        "setting_name": "不得与最近几次密码相同",
        "setting_value": "3",
        "value_type_code": "number",
        "setting_group_code": "security",
        "description": "改密时与最近 N 次历史密码比较；填 0 表示不限制。",
    },
    {
        "setting_key": "login_lock_threshold",
        "setting_name": "登录失败锁定次数",
        "setting_value": "10",
        "value_type_code": "number",
        "setting_group_code": "security",
        "description": "连续登录失败达到该次数后临时锁定账号。",
    },
    {
        "setting_key": "notify_wechat_enabled",
        "setting_name": "启用微信通知",
        "setting_value": "false",
        "value_type_code": "boolean",
        "setting_group_code": "notify",
        "description": "开启后，通知中心按场景配置向微信推送消息。",
    },
    {
        "setting_key": "hr_disable_account_on_leave",
        "setting_name": "员工离职时自动停用账号",
        "setting_value": "false",
        "value_type_code": "boolean",
        "setting_group_code": "hr",
        "description": "开启后，员工离职生效时自动停用其登录账号；关闭时由管理员处理。",
    },
]


def validate_setting_value(value_type_code: str, value: str | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if value_type_code == "number":
        try:
            float(text)
        except ValueError as exc:
            raise AppException("参数值必须是数字", status_code=status.HTTP_400_BAD_REQUEST) from exc
    elif value_type_code == "boolean":
        if text.lower() not in {"true", "false"}:
            raise AppException("参数值必须是 true 或 false", status_code=status.HTTP_400_BAD_REQUEST)
        text = text.lower()
    elif value_type_code == "json":
        try:
            json.loads(text)
        except ValueError as exc:
            raise AppException("参数值必须是合法的 JSON", status_code=status.HTTP_400_BAD_REQUEST) from exc
    return text


async def normalize_system_setting_payload(
    _session: AsyncSession,
    payload: dict[str, Any],
    _current_user: AuthenticatedUser,
    entity: SysSetting | None,
) -> dict[str, Any]:
    if entity is None:
        raise AppException("系统参数由系统定义，不能新增", status_code=status.HTTP_403_FORBIDDEN)
    data = dict(payload)
    data.pop("setting_key", None)
    if "setting_value" in data:
        data["setting_value"] = validate_setting_value(entity.value_type_code, data["setting_value"])
    return data


class SystemSettingRepository(SqlModelCrudRepository):
    async def get_by_key(self, session: AsyncSession, setting_key: str) -> SysSetting | None:
        statement = select(SysSetting).where(SysSetting.setting_key == setting_key, SysSetting.deleted_at.is_(None))
        return (await session.exec(statement)).first()

    async def ensure_defaults(self, session: AsyncSession, created_by=None) -> int:
        existing = set((await session.exec(select(SysSetting.setting_key).where(SysSetting.deleted_at.is_(None)))).all())
        created = 0
        for item in DEFAULT_SETTINGS:
            if item["setting_key"] not in existing:
                session.add(SysSetting(**item, created_by=created_by, updated_by=created_by))
                created += 1
        await session.flush()
        return created


repository = SystemSettingRepository(
    table_model=SysSetting,
    item_model=SystemSettingItem,
    writable_columns=["setting_key", "setting_name", "setting_value", "description", "is_active"],
    searchable_columns=["setting_key", "setting_name", "description"],
    filterable_columns=["setting_group_code", "is_active"],
    update_payload_normalizer=normalize_system_setting_payload,
    create_payload_normalizer=normalize_system_setting_payload,
    organization_scope=ORGANIZATION_SCOPE_NONE,
    scope_resource="system_setting",
)
