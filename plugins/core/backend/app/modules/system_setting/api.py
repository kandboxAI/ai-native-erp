from __future__ import annotations

from typing import Any

from fastapi import Depends

from app.auth.dependencies import require_permissions
from app.auth.schemas import AuthenticatedUser
from app.core.response import success_response
from app.framework.crud.router import build_crud_router

from .schemas import SystemSettingCreate, SystemSettingListQuery, SystemSettingUpdate
from .service import service

# 系统参数由代码定义：只开放查询与修改（不新增、不删除）
router = build_crud_router(
    module_name="system_setting",
    service=service,
    create_model=SystemSettingCreate,
    update_model=SystemSettingUpdate,
    tags=["system_setting"],
    list_model=SystemSettingListQuery,
    enable_create=False,
    enable_delete=False,
)


@router.post("/seed-defaults")
async def seed_system_setting_defaults(
    current_user: AuthenticatedUser = Depends(require_permissions(["system_setting:update"])),
) -> dict[str, Any]:
    """补齐代码定义的系统参数（已存在的不覆盖）。"""
    return success_response(await service.seed_defaults(current_user))
