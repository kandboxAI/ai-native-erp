from typing import Any

from fastapi import Depends, Query

from app.auth.dependencies import get_current_user, require_permissions
from app.auth.schemas import AuthenticatedUser
from app.core.exceptions import AppException
from app.core.response import paginated_response, success_response
from app.framework.crud.router import build_crud_router

from .schemas import DictionaryCreate, DictionaryEntryListQuery, DictionaryListQuery, DictionaryUpdate
from .service import service

router = build_crud_router(
    module_name="dictionary",
    service=service,
    create_model=DictionaryCreate,
    update_model=DictionaryUpdate,
    tags=["dictionary"],
    list_model=DictionaryListQuery,
)


@router.get("/entry/list")
async def list_dictionary_entries(
    params: DictionaryEntryListQuery = Depends(),
    current_user: AuthenticatedUser = Depends(require_permissions(["dictionary:list"])),
) -> dict[str, Any]:
    return paginated_response(**await service.list_entries(params, current_user))


@router.get("/options")
async def dictionary_options(
    dict_codes: str = Query(..., description="字典编码，逗号分隔，如 sys_org_type,sys_data_scope"),
    include_inactive: bool = False,
    _: AuthenticatedUser = Depends(get_current_user),
) -> dict[str, Any]:
    """下拉选项：登录用户均可读取（字典是界面显示用的取值表）。返回 {dict_code: [{item_code, item_name, ...}]}。"""
    codes = [code.strip() for code in dict_codes.split(",") if code.strip()]
    if not codes or len(codes) > 50:
        raise AppException("请提供 1 到 50 个字典编码")
    return success_response(await service.options(codes, include_inactive=include_inactive))
