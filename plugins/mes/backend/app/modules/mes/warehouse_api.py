"""制造仓库配置；仓库生命周期调用 inv 公开服务，不建立第二套仓库模型。"""
from typing import Literal
from uuid import UUID
from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.exc import IntegrityError
from app.auth.dependencies import require_permissions
from app.core.exceptions import AppException
from app.core.response import success_response
from app.framework.db.session import get_session_context
from app.modules.inventory import public as stock
from .warehouse_policy import WAREHOUSE_TYPES
from app.modules.organization.public import list_writable_org_options


class WarehouseCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    org_id: UUID
    warehouse_no: str = Field(min_length=1, max_length=64)
    warehouse_name: str = Field(min_length=1, max_length=128)
    warehouse_type_code: Literal["mes_raw", "mes_wip", "mes_finished", "mes_tool"]
    is_active: bool = True


class WarehouseUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    warehouse_name: str = Field(min_length=1, max_length=128)
    warehouse_type_code: Literal["mes_raw", "mes_wip", "mes_finished", "mes_tool"]
    is_active: bool


router = APIRouter(tags=["mes-warehouses"])


@router.get("/warehouses")
async def warehouses(user=Depends(require_permissions(["mes:warehouse:list"]))):
    async with get_session_context() as session:
        permission = "mes:warehouse:manage" if "mes:warehouse:manage" in user.permissions else "mes:warehouse:list"
        organizations = await list_writable_org_options(session, user, permission)
        return success_response(dict(items=await stock.list_configured_warehouses(session, "mes", user), types=WAREHOUSE_TYPES, organizations=organizations))


async def save(payload, user, warehouse_id=None):
    async with get_session_context() as session:
        try:
            row = await stock.configure_warehouse(session, "mes", payload.model_dump(), user, warehouse_id=warehouse_id)
            await session.commit()
        except IntegrityError as error:
            raise AppException("同一组织内仓库编号已存在，或仓库引用已变化", 409) from error
        return success_response(row)


@router.post("/warehouses")
async def create(body: WarehouseCreate, user=Depends(require_permissions(["mes:warehouse:manage"]))):
    return await save(body, user)


@router.patch("/warehouses/{warehouse_id}")
async def update(warehouse_id: UUID, body: WarehouseUpdate, user=Depends(require_permissions(["mes:warehouse:manage"]))):
    return await save(body, user, warehouse_id)
