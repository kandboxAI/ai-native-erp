from typing import Any

from fastapi import Depends

from app.auth.dependencies import require_permissions
from app.auth.schemas import AuthenticatedUser
from app.core.response import paginated_response, success_response
from app.framework.crud.router import build_crud_router

from .import_api import router as import_router
from .schemas import OrganizationCreate, OrganizationListQuery, OrganizationListWithDepartmentsQuery, OrganizationUpdate
from .service import service

_STRUCTURE_HEADERS: dict[str, str] = {
    "structure_node_type": "类型",
    "org_no": "组织编号",
    "org_name": "组织名称",
    "department_no": "部门编号",
    "department_name": "部门名称",
    "contact_name": "联系人",
    "contact_phone": "联系电话",
    "province": "省",
    "city": "市",
    "district": "区县",
    "address": "详细地址",
    "remark": "备注",
    "created_at": "创建时间",
}

router = build_crud_router(
    module_name="organization",
    service=service,
    create_model=OrganizationCreate,
    update_model=OrganizationUpdate,
    tags=["organization"],
    list_model=OrganizationListQuery,
    export_list_model=OrganizationListWithDepartmentsQuery,
    export_header_zh=_STRUCTURE_HEADERS,
)

router.include_router(import_router)


@router.get("/list_with_departments")
async def list_with_departments(
    params: OrganizationListWithDepartmentsQuery = Depends(),
    current_user: AuthenticatedUser = Depends(require_permissions(["organization:list"])),
) -> dict[str, Any]:
    result = await service.list_with_departments(params, current_user)
    return paginated_response(**result)


@router.get("/tree")
async def organization_tree(
    current_user: AuthenticatedUser = Depends(require_permissions(["organization:list"])),
) -> dict[str, Any]:
    """组织树（集团 / 租户 / 校区），供用户、部门等页面选择组织。"""
    return success_response(await service.tree(current_user))
