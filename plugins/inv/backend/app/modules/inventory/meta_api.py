"""库存页面用的字典选项：/api/inventory_meta/options（计量单位、库存状态、处理方式等）。"""

from typing import Any

from fastapi import APIRouter, Depends

from app.auth.dependencies import get_current_user
from app.auth.schemas import AuthenticatedUser
from app.core.response import success_response
from app.framework.db.session import get_session_context

from .imports.repository import repository

INVENTORY_DICTS = (
    "asset_type",
    "md_unit",
    "md_party_type",
    "md_settlement_method",
    "md_settlement_cycle",
    "md_currency",
    "inv_stock_status",
    "inv_stock_direction",
    "inv_stock_order_status",
    "inv_handling_method",
    "inv_transaction_type",
    "inv_requisition_status",
    "inv_requisition_event_type",
)

router = APIRouter(prefix="/api/inventory_meta", tags=["inventory_meta"])


@router.get("/options")
async def inventory_options(current_user: AuthenticatedUser = Depends(get_current_user)) -> dict[str, Any]:
    async with get_session_context() as session:
        data = {
            dict_code: [{"value": code, "label": name} for code, name in await repository.dict_items(session, dict_code)]
            for dict_code in INVENTORY_DICTS
        }
    return success_response(data)
