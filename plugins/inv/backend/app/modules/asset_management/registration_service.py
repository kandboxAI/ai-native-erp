"""简洁资产登记：有仓库走库存公开能力，无仓库仅创建逐件资产，共用原子事务。"""
from uuid import UUID

from sqlalchemy.exc import IntegrityError

from app.auth.scope_filters import ensure_org_access, resolve_write_org_id
from app.core.exceptions import AppException
from app.framework.db.ids import uuid7
from app.framework.db.models import utc_now
from app.framework.db.session import get_session_context
from app.modules.inventory.public import (
    asset_registration_directory, asset_registration_warehouses, asset_registration_warehouse,
    receive_registered_assets,
)
from .schemas import AssetRegistrationCreate, AssetRegisterCreate, AssetRegistrationConfirm
from .service import service as assets


def require_registration(user, org_id):
    for permission in ("asset_register:create", "asset_register:confirm"):
        if permission not in user.permissions:
            raise AppException("新增资产需要资产新增及确认权限", status_code=403)
        ensure_org_access(user, org_id, permission)


class AssetRegistrationService:
    async def options(self, user, org_id=None):
        org_id = resolve_write_org_id(user, org_id, "asset_register:create")
        require_registration(user, org_id)
        base = await assets.options(org_id, "ledger", user, permission_override="asset_register:create")
        async with get_session_context() as session:
            directory = await asset_registration_directory(session, user, org_id)
            warehouses = await asset_registration_warehouses(session, user, org_id)
        return {**base, **directory, "warehouses": [row.model_dump(mode="json") for row in warehouses]}

    async def create(self, body: AssetRegistrationCreate, user):
        org_id = resolve_write_org_id(user, body.org_id, "asset_register:create")
        require_registration(user, org_id)
        try:
            async with get_session_context() as session, session.begin():
                item = await assets._registration_item(session, body.item_id)
                if not item.default_asset_type_code:
                    raise AppException("请先在物料档案配置资产类型", status_code=400)
                await assets._valid_code(session, "asset_type", item.default_asset_type_code, "资产类型")
                department_id, custodian_user_id, location_id = body.department_id, body.custodian_user_id, body.location_id
                if body.warehouse_id:
                    warehouse = await asset_registration_warehouse(session, user, body.warehouse_id, org_id)
                    if location_id is not None and location_id != warehouse["location_id"]:
                        raise AppException("资产位置必须与目标仓库的统一位置一致", status_code=400)
                    location_id = warehouse["location_id"]
                    department_id = department_id or warehouse["default_asset_department_id"]
                    custodian_user_id = custodian_user_id or warehouse["default_asset_custodian_user_id"]
                if not department_id or not custodian_user_id or not location_id:
                    raise AppException("请填写责任部门、资产保管人和资产位置，或补齐仓库默认设置", status_code=400)
                await assets._validate_responsibility(session, department_id, custodian_user_id,
                    user, "asset_register:create", reference_org_id=org_id)
                if body.warehouse_id:
                    registration = dict(department_id=str(department_id), custodian_user_id=str(custodian_user_id),
                        asset_no=body.asset_no, acquired_date=body.acquired_date, original_amount=body.original_amount)
                    order_id = await receive_registered_assets(session, user, org_id=org_id, warehouse_id=body.warehouse_id,
                        item_id=body.item_id, quantity=body.quantity, registration=registration, remark=body.remark)
                    return {"registered_quantity": body.quantity, "stock_order_id": str(order_id)}
                for _ in range(body.quantity):
                    created = await assets.create_register(AssetRegisterCreate(
                        org_id=org_id, acquisition_source_code="direct_delivery",
                        asset_no=body.asset_no or f"ZC-{utc_now():%Y%m%d}-{uuid7().hex}",
                        item_id=body.item_id, asset_type_code=item.default_asset_type_code,
                        location_id=location_id, department_id=department_id, custodian_user_id=custodian_user_id,
                        status_code=body.status_code, acquired_date=body.acquired_date,
                        original_amount=body.original_amount, remark=body.remark), user,
                        session=session, responsibility_org_id=org_id)
                    await assets.confirm_registration("individual", UUID(created["id"]),
                        AssetRegistrationConfirm(expected_version=created["version_no"]), user, session=session)
                return {"registered_quantity": body.quantity, "stock_order_id": None}
        except IntegrityError as error:
            raise AppException("资产编号已存在或登记数据冲突，请核对后重试", status_code=409) from error


registration_service = AssetRegistrationService()
