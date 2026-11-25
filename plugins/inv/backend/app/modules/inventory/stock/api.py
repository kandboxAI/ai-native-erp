"""库存查询 /api/inventory_item（权限 inventory_item:list）与库存流水 /api/inventory_movement（权限 inventory_movement:list）。

沿用原有路由前缀与权限标识；数据来自 inv_stock_balance / inv_stock_transaction，只读。
"""

from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends
from fastapi.encoders import jsonable_encoder

from app.auth.dependencies import require_any_permissions, require_permissions
from app.auth.schemas import AuthenticatedUser
from app.core.response import paginated_response, success_response

from .schemas import LotOptionQuery, StockAlertQuery, StockBalanceQuery, StockSummaryQuery, TransactionQuery
from ..warning.schemas import StockSettingQuery, StockThresholdUpdate
from .service import service

stock_router = APIRouter(prefix="/api/inventory_item", tags=["inventory_item"])
movement_router = APIRouter(prefix="/api/inventory_movement", tags=["inventory_movement"])
alert_router = APIRouter(prefix="/api/inventory_stock_alert", tags=["inventory_stock_alert"])
setting_router = APIRouter(prefix="/api/inventory_item_warehouse_setting", tags=["inventory_item_warehouse_setting"])


def _encode(data: dict[str, Any]) -> dict[str, Any]:
    return jsonable_encoder(data, custom_encoder={Decimal: str})


@stock_router.get("/list")
async def stock_summary(
    query: StockSummaryQuery = Depends(),
    current_user: AuthenticatedUser = Depends(require_permissions(["inventory_item:list"])),
) -> dict[str, Any]:
    """库存查询：物料 × 组织汇总（账面、可用、借出数量，预警状态，库存价值）。"""
    return paginated_response(
        **_encode(await service.summary(query, current_user, warehouse_level=True))
    )


@alert_router.get("/list")
async def low_stock_alerts(
    query: StockAlertQuery = Depends(),
    current_user: AuthenticatedUser = Depends(require_permissions(["inventory_stock_alert:list"])),
) -> dict[str, Any]:
    """补货预警：按物料 × 仓库返回缺货或低于安全库存的实时汇总。"""
    summary_query = StockSummaryQuery(
        **query.model_dump(exclude={"status_code"}),
        alert_status=query.status_code,
        include_zero=True,
    )
    return paginated_response(
        **_encode(
            await service.low_stock_alerts(summary_query, current_user)
        )
    )


@alert_router.get("/{item_id}/{warehouse_id}")
async def stock_alert_detail(
    item_id: UUID,
    warehouse_id: UUID,
    current_user: AuthenticatedUser = Depends(
        require_any_permissions(["inventory_stock_alert:list", "inventory_item:list"])
    ),
) -> dict[str, Any]:
    """库存通知详情：按物料 × 仓库返回当前实时库存与预警状态。"""
    return success_response(
        _encode(await service.alert_detail(item_id, warehouse_id, current_user))
    )


@alert_router.put("/{item_id}/{warehouse_id}/threshold")
async def configure_stock_threshold(
    item_id: UUID,
    warehouse_id: UUID,
    payload: StockThresholdUpdate,
    current_user: AuthenticatedUser = Depends(require_permissions(["inventory_product:update"])),
) -> dict[str, Any]:
    """配置单个物料在指定仓库的安全库存下限和补货目标/库存上限。"""
    return success_response(
        _encode(await service.configure_threshold(item_id, warehouse_id, payload, current_user))
    )


@setting_router.get("/list")
async def stock_settings(
    query: StockSettingQuery = Depends(),
    current_user: AuthenticatedUser = Depends(require_permissions(["inventory_item:list"])),
) -> dict[str, Any]:
    """安全库存设置：已有余额或已有阈值的物料仓库组合。"""
    return paginated_response(**_encode(await service.stock_settings(query, current_user)))


@setting_router.put("/{item_id}/{warehouse_id}")
async def save_stock_setting(
    item_id: UUID,
    warehouse_id: UUID,
    payload: StockThresholdUpdate,
    current_user: AuthenticatedUser = Depends(require_permissions(["inventory_product:update"])),
) -> dict[str, Any]:
    """新增或调整指定物料在指定仓库的安全库存阈值。"""
    return success_response(
        _encode(await service.configure_threshold(item_id, warehouse_id, payload, current_user))
    )


@stock_router.get("/balance/list")
async def stock_balances(
    query: StockBalanceQuery = Depends(),
    current_user: AuthenticatedUser = Depends(require_permissions(["inventory_item:list"])),
) -> dict[str, Any]:
    """余额明细：物料 × 仓库 × 批次 × 库存状态。"""
    return paginated_response(**_encode(await service.balances(query, current_user)))


@stock_router.get("/lots")
async def lot_options(
    query: LotOptionQuery = Depends(),
    current_user: AuthenticatedUser = Depends(
        require_any_permissions(["inventory_item:list", "inventory_outbound:create", "inventory_transfer:create", "inventory_lend:create", "inventory_damage:create"])
    ),
) -> dict[str, Any]:
    return success_response(_encode({"items": await service.lot_options(query, current_user)}))


@movement_router.get("/list")
async def movement_list(
    query: TransactionQuery = Depends(),
    current_user: AuthenticatedUser = Depends(require_permissions(["inventory_movement:list"])),
) -> dict[str, Any]:
    """库存流水：每条可通过 stock_order_id / stock_order_line_id 追溯到单据与明细。"""
    return paginated_response(**_encode(await service.transactions(query, current_user)))
