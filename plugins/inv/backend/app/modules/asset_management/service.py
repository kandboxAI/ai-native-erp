"""资产管理业务规则、事务编排及跨模块公开能力。"""

from __future__ import annotations

from contextlib import asynccontextmanager
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from fastapi import status
from sqlmodel.ext.asyncio.session import AsyncSession

from app.auth.schemas import AuthenticatedUser
from app.auth.scope_filters import ensure_org_access, resolve_write_org_id
from app.core.exceptions import AppException
from app.framework.db.models import utc_now
from app.framework.db.session import get_session_context

from app.modules.location.public import require_location

from .models import AssetChangeEvent, AssetLocation, AssetLocationItem, AssetRegister
from .repository import repository
from .schemas import (
    AssetItemOptionQuery,
    AssetEventItem,
    AssetEventQuery,
    AssetLedgerQuery,
    AssetLocationCreate,
    AssetLocationUpdate,
    AssetRegistrationConfirm,
    AssetRegistrationVoid,
    AssetRegisterCreate,
    AssetRegisterQuery,
    AssetRegisterTransfer,
    AssetRegisterUpdate,
    LocationAssetAdjust,
    LocationAssetCreate,
    LocationAssetQuery,
    LocationAssetTransfer,
    LocationAssetUpdate,
)


def _clean(value: Any) -> Any:
    if isinstance(value, str):
        return value.strip() or None
    return value


MANUAL_ASSET_STATUS_CODES = frozenset({"in_use", "idle"})


@asynccontextmanager
async def asset_transaction(session=None):
    """公开组合能力复用调用方事务，不提前提交。"""
    if session is not None:
        yield session
    else:
        async with get_session_context() as owned, owned.begin():
            yield owned


class AssetManagementService:
    async def _protect_stock_asset(self, session, asset, *, quantity_change=False):
        from .stock_service import stock_service
        await stock_service.protect_manual_change(session, asset, quantity_change=quantity_change)

    async def has_custody_for_user(self, session, *, org_id, user_id):
        """供已校验业务范围的调用方使用；只查本组织该用户的有效保管责任。"""
        if user_id is None:
            return False
        return await repository.has_custody_for_user(session, org_id=org_id, user_id=user_id)

    @staticmethod
    def _name(user: AuthenticatedUser) -> str:
        return (user.display_name or user.email or str(user.user_id)).strip()

    @staticmethod
    def _conflict(message: str) -> AppException:
        return AppException(message, status_code=status.HTTP_409_CONFLICT)

    @staticmethod
    def _not_found(message: str) -> AppException:
        return AppException(message, status_code=status.HTTP_404_NOT_FOUND)

    @staticmethod
    def _check_version(row: Any, expected_version: int) -> None:
        if row.version_no != expected_version:
            raise AssetManagementService._conflict("记录已被其他人员修改，请刷新后重试")

    @staticmethod
    def _validate_manual_status(status_code: str, current_status_code: str | None = None) -> None:
        """人工登记和编辑只维护常规状态，流程状态由所属业务模块维护。"""
        if status_code == current_status_code:
            return
        if status_code not in MANUAL_ASSET_STATUS_CODES or (
            current_status_code is not None
            and current_status_code not in MANUAL_ASSET_STATUS_CODES
        ):
            raise AppException(
                "维修中、待报废和已报废状态只能由维修或报废流程变更",
                status_code=status.HTTP_400_BAD_REQUEST,
            )

    async def _valid_code(self, session: AsyncSession, dict_code: str, value: str, label: str) -> None:
        if not await repository.valid_dict_item(session, dict_code, value):
            raise AppException(f"{label}不存在或已停用", status_code=status.HTTP_400_BAD_REQUEST)

    async def _validate_responsibility(
        self,
        session: AsyncSession,
        department_id: UUID | None,
        custodian_user_id: UUID | None,
        user: AuthenticatedUser,
        permission: str,
        *, reference_org_id: UUID | None = None,
    ) -> None:
        department = None
        if department_id is not None:
            if reference_org_id is not None:
                ensure_org_access(user, reference_org_id, permission)
                from app.modules.inventory.public import warehouse_department_reference
                department = await warehouse_department_reference(session, owner_org_id=reference_org_id, department_id=department_id)
            else:
                department = await repository.department_in_scope(session, department_id, user, permission)
        if department_id is not None and department is None:
            raise AppException(
                "责任部门不存在、已停用或不在当前数据范围内",
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        if custodian_user_id is not None:
            if reference_org_id is not None:
                ensure_org_access(user, reference_org_id, permission)
                from app.modules.inventory.public import warehouse_custodian_reference
                custodian = await warehouse_custodian_reference(session, owner_org_id=reference_org_id, user_id=custodian_user_id)
            else:
                custodian = await repository.user_in_scope(session, custodian_user_id, user, permission)
            if custodian is None:
                raise AppException("保管人不存在、已停用或不在当前数据范围内", status_code=400)


    @staticmethod
    def _registration_responsibility(
        body: LocationAssetCreate | AssetRegisterCreate,
    ) -> tuple[UUID | None, UUID | None]:
        """责任信息属于资产，仅采信本次登记，不从位置推导。"""
        return body.department_id, body.custodian_user_id

    def event(
        self,
        row: AssetLocationItem | AssetRegister,
        user: AuthenticatedUser,
        event_type_code: str,
        note: str,
        **values: Any,
    ) -> AssetChangeEvent:
        return AssetChangeEvent(
            org_id=row.org_id,
            asset_register_id=row.id if isinstance(row, AssetRegister) else None,
            location_item_id=row.id if isinstance(row, AssetLocationItem) else None,
            event_type_code=event_type_code,
            note=note.strip(),
            operator_user_id=user.user_id,
            operator_name_snapshot=self._name(user),
            created_by=user.user_id,
            **values,
        )

    @staticmethod
    def _location_item(row: Any) -> dict[str, Any]:
        asset, item, location, department_name, custodian_name = row
        return {
            "id": str(asset.id),
            "org_id": str(asset.org_id),
            "location_id": str(asset.location_id) if asset.location_id else None,
            "is_personal_custody": asset.location_id is None,
            "custody_location_note": asset.custody_location_note,
            "location_no": location.location_no if location else None,
            "location_name": location.location_name if location else f"个人保管 · {custodian_name or '未命名账号'}",
            "item_id": str(asset.item_id),
            "item_no": item.item_no,
            "item_name": item.item_name,
            "specification": item.specification,
            "asset_type_code": asset.asset_type_code,
            "quantity": str(asset.quantity),
            "unit_code": asset.unit_code_snapshot,
            "department_id": str(asset.department_id) if asset.department_id else None,
            "department_name": department_name,
            "custodian_user_id": str(asset.custodian_user_id) if asset.custodian_user_id else None,
            "custodian_name": custodian_name,
            "status_code": asset.status_code,
            "registration_status_code": asset.registration_status_code,
            "registered_at": asset.registered_at.isoformat() if asset.registered_at else None,
            "voided_at": asset.voided_at.isoformat() if asset.voided_at else None,
            "void_reason": asset.void_reason,
            "version_no": asset.version_no,
            "remark": asset.remark,
            "created_at": asset.created_at.isoformat(),
            "updated_at": asset.updated_at.isoformat(),
        }

    @staticmethod
    def _register(row: Any) -> dict[str, Any]:
        asset, item, location, department_name, custodian_name = row
        return {
            "id": str(asset.id),
            "org_id": str(asset.org_id),
            "asset_no": asset.asset_no,
            "item_id": str(asset.item_id),
            "item_no": item.item_no,
            "item_name": item.item_name,
            "specification": item.specification,
            "asset_type_code": asset.asset_type_code,
            "serial_no": asset.serial_no,
            "location_id": str(asset.location_id) if asset.location_id else None,
            "is_personal_custody": asset.location_id is None,
            "custody_location_note": asset.custody_location_note,
            "location_no": location.location_no if location else None,
            "location_name": location.location_name if location else f"个人保管 · {custodian_name or '未命名账号'}",
            "department_id": str(asset.department_id) if asset.department_id else None,
            "department_name": department_name,
            "custodian_user_id": str(asset.custodian_user_id) if asset.custodian_user_id else None,
            "custodian_name": custodian_name,
            "status_code": asset.status_code,
            "registration_status_code": asset.registration_status_code,
            "registered_at": asset.registered_at.isoformat() if asset.registered_at else None,
            "voided_at": asset.voided_at.isoformat() if asset.voided_at else None,
            "void_reason": asset.void_reason,
            "acquired_date": asset.acquired_date.isoformat() if asset.acquired_date else None,
            "original_amount": str(asset.original_amount) if asset.original_amount is not None else None,
            "version_no": asset.version_no,
            "remark": asset.remark,
            "created_at": asset.created_at.isoformat(),
            "updated_at": asset.updated_at.isoformat(),
        }

    async def item_options(self, query: AssetItemOptionQuery, user: AuthenticatedUser) -> dict[str, Any]:
        if query.permission_key not in user.permissions:
            raise AppException("无权查询资产物料", status_code=403)
        resolve_write_org_id(user, query.org_id, query.permission_key)
        async with get_session_context() as session:
            return await repository.asset_item_options(session, query)

    async def _registration_item(self, session, item_id):
        item = await repository.item(session, item_id)
        if item is None:
            raise AppException("物品不存在或已停用")
        if not item.is_asset_managed:
            raise AppException("该物料未允许登记为资产，请先在物资档案中开启“允许登记为资产”")
        return item

    async def options(
        self,
        org_id: UUID | None,
        scope: Literal["ledger"],
        user: AuthenticatedUser,
        *, permission_override: str | None = None,
    ) -> dict[str, Any]:
        permission = "asset_register:list"
        if permission_override in {"asset_register:transfer", "asset_register:create"}:
            permission = permission_override
        if permission not in user.permissions:
            raise AppException("无权加载资产选项", status_code=status.HTTP_403_FORBIDDEN)
        resolved_org_id = resolve_write_org_id(user, org_id, permission)
        async with get_session_context() as session:
            choices = await repository.option_rows(
                session,
                resolved_org_id,
                user,
                permission,
            )
            dictionaries = await repository.dictionary_options(
                session,
                {
                    "asset_type",
                    "asset_status",
                    "asset_location_type",
                    "md_location_type",
                    "asset_change_event_type",
                    "md_unit",
                },
            )
        legacy_types = {item["value"]: item for item in dictionaries.get("asset_location_type", [])}
        legacy_types.update({item["value"]: item for item in dictionaries.pop("md_location_type", [])})
        dictionaries["asset_location_type"] = list(legacy_types.values())
        return {"org_id": str(resolved_org_id), **choices, **dictionaries}

    async def summary(self, user: AuthenticatedUser) -> dict[str, Any]:
        async with get_session_context() as session:
            return await repository.summary(session, user)

    async def list_ledger(self, query: AssetLedgerQuery, user: AuthenticatedUser) -> dict[str, Any]:
        async with get_session_context() as session:
            total, rows = await repository.list_ledger(session, query, user)
        uuid_fields = (
            "id",
            "org_id",
            "item_id",
            "location_id",
            "department_id",
            "custodian_user_id",
        )
        items = []
        for source in rows:
            row = dict(source)
            for field in uuid_fields:
                row[field] = str(row[field]) if row.get(field) is not None else None
            row["is_personal_custody"] = row["location_id"] is None
            if row["is_personal_custody"]:
                row["location_name"] = f"个人保管 · {row.get('custodian_name') or '未命名账号'}"
            row["quantity"] = str(row["quantity"])
            row["original_amount"] = (
                str(row["original_amount"]) if row.get("original_amount") is not None else None
            )
            row["acquired_date"] = (
                row["acquired_date"].isoformat() if row.get("acquired_date") is not None else None
            )
            row["registered_at"] = (
                row["registered_at"].isoformat() if row.get("registered_at") is not None else None
            )
            row["voided_at"] = row["voided_at"].isoformat() if row.get("voided_at") is not None else None
            row["created_at"] = row["created_at"].isoformat()
            row["updated_at"] = row["updated_at"].isoformat()
            items.append(row)
        return {"items": items, "total": total, "page": query.page, "page_size": query.page_size}


    async def create_location(self, body: AssetLocationCreate, user: AuthenticatedUser) -> dict[str, Any]:
        async with get_session_context() as session, session.begin():
            org_id = resolve_write_org_id(user, body.org_id, "asset_location:manage")
            master = await require_location(session, body.physical_location_id, org_id, for_update=True)
            existing = await repository.asset_location_for_physical(session, master.id)
            if existing is not None:
                raise self._conflict("该位置已有资产配置，请编辑已有配置")
            row = AssetLocation(
                id=master.id, org_id=org_id, physical_location_id=master.id,
                location_no=repository.adapter_number(master.id), location_name=master.location_name,
                location_type_code=master.location_type_code,
                is_active=body.is_active, remark=_clean(body.remark),
                created_by=user.user_id, updated_by=user.user_id,
            )
            repository.add(session, row)
            await session.flush()
        return {"id": str(row.id)}


    async def update_location(self, location_id: UUID, body: AssetLocationUpdate, user: AuthenticatedUser) -> dict[str, Any]:
        """已关联的内部位置配置仅维护启停和备注，不再接受旧地点补关联。"""
        async with get_session_context() as session, session.begin():
            row = await repository.get_location(session, location_id, user, "asset_location:manage", for_update=True)
            if row is None:
                raise self._not_found("资产位置配置不存在或无权修改")
            self._check_version(row, body.expected_version)
            if row.physical_location_id is None or row.physical_location_id != body.physical_location_id:
                raise self._conflict("资产位置不支持补关联或改绑，请直接选择统一位置办理资产登记或调拨")
            await require_location(session, row.physical_location_id, row.org_id, for_update=True)
            for key, value in body.model_dump(exclude={"expected_version", "physical_location_id"}, exclude_unset=True).items():
                setattr(row, key, _clean(value) if key == "remark" else value)
            row.version_no += 1
            row.updated_at, row.updated_by = utc_now(), user.user_id
            repository.add(session, row)
        return {"id": str(row.id), "version_no": row.version_no}

    async def delete_location(
        self, location_id: UUID, expected_version: int, user: AuthenticatedUser
    ) -> None:
        async with get_session_context() as session, session.begin():
            row = await repository.get_location(
                session, location_id, user, "asset_location:manage", for_update=True
            )
            if row is None:
                raise self._not_found("资产位置不存在或无权删除")
            self._check_version(row, expected_version)
            if await repository.location_has_children_or_assets(session, row.id):
                raise self._conflict("资产位置仍有下级位置或资产，不能删除")
            row.deleted_at = utc_now()
            row.deleted_by = user.user_id
            row.updated_at = row.deleted_at
            row.updated_by = user.user_id
            row.version_no += 1
            repository.add(session, row)

    async def list_location_items(self, query: LocationAssetQuery, user: AuthenticatedUser) -> dict[str, Any]:
        async with get_session_context() as session:
            total, rows = await repository.list_location_items(session, query, user)
        return {
            "items": [self._location_item(row) for row in rows],
            "total": total,
            "page": query.page,
            "page_size": query.page_size,
        }

    async def location_item_detail(self, row_id: UUID, user: AuthenticatedUser) -> dict[str, Any]:
        async with get_session_context() as session:
            row = await repository.get_location_item(session, row_id, user, "asset_register:detail")
            if row is None:
                raise self._not_found("场所资产不存在或无权查看")
            view = await repository.location_item_view(session, row.id)
            return self._location_item(view)

    async def create_location_item(self, body: LocationAssetCreate, user: AuthenticatedUser, *, session=None) -> dict[str, Any]:
        raise AppException("新资产统一逐件编号，请通过新增资产或入库管理办理", status_code=400)

    async def update_location_item(
        self, row_id: UUID, body: LocationAssetUpdate, user: AuthenticatedUser
    ) -> dict[str, Any]:
        async with get_session_context() as session, session.begin():
            row = await repository.get_location_item(
                session, row_id, user, "asset_register:update", for_update=True
            )
            if row is None:
                raise self._not_found("场所资产不存在或无权修改")
            self._check_version(row, body.expected_version)
            if row.registration_status_code != "pending_confirmation":
                raise self._conflict("资产已完成登记确认，原始信息不可修改；请通过交接、调拨或作废重建处理")
            data = body.model_dump(exclude={"expected_version"}, exclude_unset=True)
            if "asset_type_code" in data:
                await self._valid_code(session, "asset_type", data["asset_type_code"], "资产类型")
            if "status_code" in data:
                await self._valid_code(session, "asset_status", data["status_code"], "资产状态")
                self._validate_manual_status(data["status_code"], row.status_code)
            department_id = data.get("department_id", row.department_id)
            custodian_user_id = data.get("custodian_user_id", row.custodian_user_id)
            await self._validate_responsibility(
                session,
                department_id,
                custodian_user_id,
                user,
                "asset_register:update",
            )
            before_department = row.department_id
            before_custodian = row.custodian_user_id
            before_status = row.status_code
            for key, value in data.items():
                setattr(row, key, _clean(value))
            row.version_no += 1
            row.updated_at = utc_now()
            row.updated_by = user.user_id
            repository.add(session, row)
            responsibility_changed = (
                before_department != row.department_id or before_custodian != row.custodian_user_id
            )
            repository.add(
                session,
                self.event(
                    row,
                    user,
                    "handover" if responsibility_changed else "updated",
                    "变更场所资产责任信息" if responsibility_changed else "修改场所资产信息",
                    from_department_id=before_department,
                    to_department_id=row.department_id,
                    from_custodian_user_id=before_custodian,
                    to_custodian_user_id=row.custodian_user_id,
                    from_status_code=before_status,
                    to_status_code=row.status_code,
                ),
            )
            view = await repository.location_item_view(session, row.id)
        return self._location_item(view)

    async def adjust_location_item(
        self, row_id: UUID, body: LocationAssetAdjust, user: AuthenticatedUser
    ) -> dict[str, Any]:
        async with get_session_context() as session, session.begin():
            row = await repository.get_location_item(
                session, row_id, user, "asset_register:adjust", for_update=True
            )
            if row is None:
                raise self._not_found("场所资产不存在或无权调整")
            self._check_version(row, body.expected_version)
            if row.registration_status_code != "confirmed":
                raise self._conflict("只有已确认登记的资产才能调整数量")
            before = Decimal(row.quantity)
            if body.quantity > before:
                raise self._conflict("新资产统一逐件编号，不能通过历史数量资产增量登记，请办理入库")
            await self._protect_stock_asset(session, row, quantity_change=True)
            if body.quantity == before:
                raise AppException("调整后数量与当前数量相同", status_code=status.HTTP_400_BAD_REQUEST)
            row.quantity = body.quantity
            row.version_no += 1
            row.updated_at = utc_now()
            row.updated_by = user.user_id
            if body.quantity == 0:
                row.deleted_at = row.updated_at
                row.deleted_by = user.user_id
            repository.add(
                session,
                row,
                self.event(
                    row,
                    user,
                    "quantity_adjusted",
                    body.reason,
                    quantity_before=before,
                    quantity_after=body.quantity,
                    from_location_id=row.location_id,
                    to_location_id=row.location_id,
                ),
            )
            await session.flush()
            view = None if body.quantity == 0 else await repository.location_item_view(session, row.id)
        return {"removed": body.quantity == 0, "item": self._location_item(view) if view else None}

    async def transfer_location_item(
        self, row_id: UUID, body: LocationAssetTransfer, user: AuthenticatedUser
    ) -> dict[str, Any]:
        async with get_session_context() as session, session.begin():
            source = await repository.get_location_item(
                session, row_id, user, "asset_register:transfer", for_update=True
            )
            if source is None:
                raise self._not_found("场所资产不存在或无权调拨")
            self._check_version(source, body.expected_version)
            if source.registration_status_code != "confirmed":
                raise self._conflict("只有已确认登记的资产才能办理调拨或交接")
            if source.location_id == body.target_location_id:
                raise AppException("目标地点不能与当前地点相同", status_code=status.HTTP_400_BAD_REQUEST)
            if body.quantity > source.quantity:
                raise self._conflict("调拨数量不能超过当前数量")
            await self._protect_stock_asset(session, source)
            target_location = await repository.location_for_org(
                session, body.target_location_id, source.org_id, for_update=True, user=user
            )
            if target_location is None or not target_location.is_active:
                raise AppException("目标资产位置不存在、已停用或不属于当前组织", status_code=status.HTTP_400_BAD_REQUEST)
            body = body.model_copy(update={"target_location_id": target_location.id})
            if source.location_id == target_location.id:
                raise AppException("目标地点不能与当前地点相同", status_code=status.HTTP_400_BAD_REQUEST)
            await self._validate_responsibility(
                session,
                body.target_department_id,
                body.target_custodian_user_id,
                user,
                "asset_register:transfer",
            )
            target = await repository.location_item_by_key(
                session, body.target_location_id, source.item_id, for_update=True
            )
            if target is not None and target.registration_status_code != "confirmed":
                raise self._conflict("目标地点的同类资产尚未完成登记确认，不能合并调拨")
            if target is not None and target.acquisition_source_code != source.acquisition_source_code:
                raise self._conflict("不同登记来源的数量资产不能直接合并，请先核对来源")
            if target is not None:
                await self._protect_stock_asset(session, target)
            source_before = Decimal(source.quantity)
            source.quantity -= body.quantity
            source.version_no += 1
            source.updated_at = utc_now()
            source.updated_by = user.user_id
            if source.quantity == 0:
                source.deleted_at = source.updated_at
                source.deleted_by = user.user_id
            if target is None:
                target = AssetLocationItem(
                    acquisition_source_code=source.acquisition_source_code,
                    org_id=source.org_id,
                    location_id=body.target_location_id,
                    item_id=source.item_id,
                    asset_type_code=source.asset_type_code,
                    quantity=body.quantity,
                    unit_code_snapshot=source.unit_code_snapshot,
                    department_id=body.target_department_id or source.department_id,
                    custodian_user_id=body.target_custodian_user_id or source.custodian_user_id,
                    status_code=source.status_code,
                    registration_status_code="confirmed",
                    registered_at=source.registered_at,
                    registered_by=source.registered_by,
                    remark=source.remark,
                    created_by=user.user_id,
                    updated_by=user.user_id,
                )
                target_before = Decimal("0")
            else:
                target_before = Decimal(target.quantity)
                target.quantity += body.quantity
                target.version_no += 1
                target.updated_at = utc_now()
                target.updated_by = user.user_id
                if body.target_department_id is not None:
                    target.department_id = body.target_department_id
                if body.target_custodian_user_id is not None:
                    target.custodian_user_id = body.target_custodian_user_id
            repository.add(session, source, target)
            await session.flush()
            repository.add(
                session,
                self.event(
                    source,
                    user,
                    "transfer_out",
                    body.reason,
                    quantity_before=source_before,
                    quantity_after=source.quantity,
                    from_location_id=source.location_id,
                    to_location_id=target.location_id,
                ),
                self.event(
                    target,
                    user,
                    "transfer_in",
                    body.reason,
                    quantity_before=target_before,
                    quantity_after=target.quantity,
                    from_location_id=source.location_id,
                    to_location_id=target.location_id,
                ),
            )
            view = await repository.location_item_view(session, target.id)
            from .stock_service import stock_service
            await stock_service.move_batch_bindings(session, source, target, body.quantity)
        return {"source_removed": source.quantity == 0, "target": self._location_item(view)}

    async def list_registers(self, query: AssetRegisterQuery, user: AuthenticatedUser) -> dict[str, Any]:
        async with get_session_context() as session:
            total, rows = await repository.list_registers(session, query, user)
        return {
            "items": [self._register(row) for row in rows],
            "total": total,
            "page": query.page,
            "page_size": query.page_size,
        }

    async def register_detail(self, register_id: UUID, user: AuthenticatedUser) -> dict[str, Any]:
        async with get_session_context() as session:
            row = await repository.get_register(session, register_id, user, "asset_register:detail")
            if row is None:
                raise self._not_found("单件设备不存在或无权查看")
            view = await repository.register_view(session, row.id)
            return self._register(view)

    async def create_register(self, body: AssetRegisterCreate, user: AuthenticatedUser, *, session=None, responsibility_org_id=None) -> dict[str, Any]:
        if body.acquisition_source_code == "stock_receipt" and session is None:
            raise AppException("仓库收货资产由确认入库自动登记", status_code=400)
        async with asset_transaction(session) as session:
            org_id = resolve_write_org_id(user, body.org_id, "asset_register:create")
            if responsibility_org_id is not None and responsibility_org_id != org_id:
                raise AppException("资产责任目录所属组织不一致", status_code=400)
            asset_no = body.asset_no.strip()
            if await repository.register_no_exists(session, org_id, asset_no):
                raise self._conflict("资产编号已存在")
            await self._registration_item(session, body.item_id)
            location = await repository.location_for_org(session, body.location_id, org_id, user=user)
            if location is None or not location.is_active:
                raise AppException("资产位置不存在、已停用或不属于当前组织", status_code=status.HTTP_400_BAD_REQUEST)
            body = body.model_copy(update={"location_id": location.id})
            await self._valid_code(session, "asset_type", body.asset_type_code, "资产类型")
            await self._valid_code(session, "asset_status", body.status_code, "资产状态")
            self._validate_manual_status(body.status_code)
            department_id, custodian_user_id = self._registration_responsibility(body)
            if department_id is None:
                raise AppException("责任部门不能为空", status_code=status.HTTP_400_BAD_REQUEST)
            await self._validate_responsibility(
                session,
                department_id,
                custodian_user_id,
                user,
                "asset_register:create",
                reference_org_id=org_id if body.acquisition_source_code == "stock_receipt" or responsibility_org_id is not None else None,
            )
            row = AssetRegister(
                **body.model_dump(
                    exclude={
                        "org_id",
                        "asset_no",
                        "serial_no",
                        "department_id",
                        "custodian_user_id",
                        "remark",
                    }
                ),
                org_id=org_id,
                asset_no=asset_no,
                serial_no=_clean(body.serial_no),
                department_id=department_id,
                custodian_user_id=custodian_user_id,
                remark=_clean(body.remark),
                created_by=user.user_id,
                updated_by=user.user_id,
            )
            repository.add(session, row)
            await session.flush()
            repository.add(
                session,
                self.event(
                    row,
                    user,
                    "created",
                    "登记单件设备",
                    to_location_id=row.location_id,
                    to_department_id=row.department_id,
                    to_custodian_user_id=row.custodian_user_id,
                    to_status_code=row.status_code,
                ),
            )
            view = await repository.register_view(session, row.id)
        return self._register(view)

    async def update_register(
        self, register_id: UUID, body: AssetRegisterUpdate, user: AuthenticatedUser
    ) -> dict[str, Any]:
        async with get_session_context() as session, session.begin():
            row = await repository.get_register(
                session, register_id, user, "asset_register:update", for_update=True
            )
            if row is None:
                raise self._not_found("单件设备不存在或无权修改")
            self._check_version(row, body.expected_version)
            if row.registration_status_code != "pending_confirmation":
                raise self._conflict("资产已完成登记确认，原始信息不可修改；请通过交接、调拨或作废重建处理")
            data = body.model_dump(exclude={"expected_version"}, exclude_unset=True)
            if "asset_no" in data:
                asset_no = data["asset_no"].strip()
                if await repository.register_no_exists(session, row.org_id, asset_no, exclude_id=row.id):
                    raise self._conflict("资产编号已存在")
                data["asset_no"] = asset_no
            if "asset_type_code" in data:
                await self._valid_code(session, "asset_type", data["asset_type_code"], "资产类型")
            if "status_code" in data:
                await self._valid_code(session, "asset_status", data["status_code"], "资产状态")
                self._validate_manual_status(data["status_code"], row.status_code)
            before_status = row.status_code
            for key, value in data.items():
                setattr(row, key, _clean(value))
            row.version_no += 1
            row.updated_at = utc_now()
            row.updated_by = user.user_id
            repository.add(
                session,
                row,
                self.event(
                    row,
                    user,
                    "status_changed" if before_status != row.status_code else "updated",
                    "变更设备状态" if before_status != row.status_code else "修改设备基础信息",
                    from_status_code=before_status,
                    to_status_code=row.status_code,
                ),
            )
            view = await repository.register_view(session, row.id)
        return self._register(view)

    async def transfer_register(
        self, register_id: UUID, body: AssetRegisterTransfer, user: AuthenticatedUser
    ) -> dict[str, Any]:
        async with get_session_context() as session, session.begin():
            row = await repository.get_register(
                session, register_id, user, "asset_register:transfer", for_update=True
            )
            if row is None:
                raise self._not_found("单件设备不存在或无权移交")
            if row.status_code in {"pending_disposal", "disposed"}:
                raise self._conflict("待报废或已报废资产不能办理普通移交或调拨")
            await self._protect_stock_asset(session, row)
            self._check_version(row, body.expected_version)
            if row.registration_status_code != "confirmed":
                raise self._conflict("只有已确认登记的资产才能办理调拨或交接")
            data = body.model_dump(exclude={"expected_version", "reason"}, exclude_unset=True)
            location_id = data.get("location_id", row.location_id)
            department_id = data.get("department_id", row.department_id)
            custodian_user_id = data.get("custodian_user_id", row.custodian_user_id)
            location = await repository.location_for_org(session, location_id, row.org_id, user=user) if location_id else None
            if location_id and (location is None or not location.is_active):
                raise AppException(
                    "目标资产位置不存在、已停用或不属于当前组织",
                    status_code=status.HTTP_400_BAD_REQUEST,
                )
            if location_id is None and custodian_user_id is None:
                raise AppException("个人保管必须指定保管人", status_code=400)
            await self._validate_responsibility(
                session,
                department_id,
                custodian_user_id,
                user,
                "asset_register:transfer",
            )
            before_location = row.location_id
            data["location_id"] = location.id if location else None
            if location is not None:
                row.custody_location_note = None
            before_department = row.department_id
            before_custodian = row.custodian_user_id
            for key, value in data.items():
                setattr(row, key, value)
            if (
                before_location == row.location_id
                and before_department == row.department_id
                and before_custodian == row.custodian_user_id
            ):
                raise AppException("移交后的地点和责任信息没有变化", status_code=status.HTTP_400_BAD_REQUEST)
            row.version_no += 1
            row.updated_at = utc_now()
            row.updated_by = user.user_id
            event_type = "transfer" if before_location != row.location_id else "handover"
            repository.add(
                session,
                row,
                self.event(
                    row,
                    user,
                    event_type,
                    body.reason,
                    from_location_id=before_location,
                    to_location_id=row.location_id,
                    from_department_id=before_department,
                    to_department_id=row.department_id,
                    from_custodian_user_id=before_custodian,
                    to_custodian_user_id=row.custodian_user_id,
                ),
            )
            view = await repository.register_view(session, row.id)
        return self._register(view)

    async def confirm_registration(
        self,
        management_mode: str,
        asset_id: UUID,
        body: AssetRegistrationConfirm,
        user: AuthenticatedUser,
        *, session=None,
    ) -> dict[str, Any]:
        async with asset_transaction(session) as session:
            if management_mode == "batch":
                row = await repository.get_location_item(
                    session, asset_id, user, "asset_register:confirm", for_update=True
                )
            elif management_mode == "individual":
                row = await repository.get_register(
                    session, asset_id, user, "asset_register:confirm", for_update=True
                )
            else:
                raise AppException("无效的资产管理模式", status_code=status.HTTP_400_BAD_REQUEST)
            if row is None:
                raise self._not_found("资产不存在或无权确认")
            self._check_version(row, body.expected_version)
            if row.registration_status_code != "pending_confirmation":
                raise self._conflict("资产登记状态已变化，请刷新后重试")
            await self._registration_item(session, row.item_id)
            if row.department_id is None:
                raise AppException("确认登记前必须指定责任部门", status_code=status.HTTP_400_BAD_REQUEST)
            row.registration_status_code = "confirmed"
            row.registered_at = utc_now()
            row.registered_by = user.user_id
            row.version_no += 1
            row.updated_at = utc_now()
            row.updated_by = user.user_id
            repository.add(
                session,
                row,
                self.event(row, user, "registration_confirmed", "确认资产登记信息并锁定原始字段"),
            )
            view = (
                await repository.location_item_view(session, row.id)
                if isinstance(row, AssetLocationItem)
                else await repository.register_view(session, row.id)
            )
        return self._location_item(view) if isinstance(row, AssetLocationItem) else self._register(view)

    async def void_registration(
        self,
        management_mode: str,
        asset_id: UUID,
        body: AssetRegistrationVoid,
        user: AuthenticatedUser,
    ) -> dict[str, Any]:
        async with get_session_context() as session, session.begin():
            if management_mode == "batch":
                row = await repository.get_location_item(
                    session, asset_id, user, "asset_register:void", for_update=True
                )
            elif management_mode == "individual":
                row = await repository.get_register(
                    session, asset_id, user, "asset_register:void", for_update=True
                )
            else:
                raise AppException("无效的资产管理模式", status_code=status.HTTP_400_BAD_REQUEST)
            if row is None:
                raise self._not_found("资产不存在或无权作废")
            self._check_version(row, body.expected_version)
            if row.registration_status_code == "voided":
                raise self._conflict("资产登记已经作废")
            if row.status_code in {"pending_disposal", "disposed"}:
                raise self._conflict("待报废或已报废资产不能作废登记，请从对应报废流程办理")
            from .stock_service import stock_service
            await stock_service.ensure_registration_can_be_voided(session, row)
            row.registration_status_code = "voided"
            row.voided_at = utc_now()
            row.voided_by = user.user_id
            row.void_reason = body.reason.strip()
            row.version_no += 1
            row.updated_at = utc_now()
            row.updated_by = user.user_id
            repository.add(
                session,
                row,
                self.event(row, user, "registration_voided", body.reason),
            )
            view = (
                await repository.location_item_view(session, row.id)
                if isinstance(row, AssetLocationItem)
                else await repository.register_view(session, row.id)
            )
        return self._location_item(view) if isinstance(row, AssetLocationItem) else self._register(view)

    async def events(self, query: AssetEventQuery, user: AuthenticatedUser) -> dict[str, Any]:
        async with get_session_context() as session:
            if query.asset_register_id is not None:
                if await repository.get_register(
                    session, query.asset_register_id, user, "asset_register:detail"
                ) is None:
                    raise self._not_found("单件设备不存在或无权查看")
            elif await repository.get_location_item(
                session, query.location_item_id, user, "asset_register:detail"
            ) is None:
                raise self._not_found("场所资产不存在或无权查看")
            total, rows = await repository.events(
                session,
                asset_register_id=query.asset_register_id,
                location_item_id=query.location_item_id,
                page=query.page,
                page_size=query.page_size,
            )
        return {
            "items": [AssetEventItem.model_validate(row).model_dump(mode="json") for row in rows],
            "total": total,
            "page": query.page,
            "page_size": query.page_size,
        }

    async def reference_options(self, session, *, org_id, user, permission, keyword="", page=1, page_size=20):
        """公开只读契约：按调用方已授权业务范围提供可关联设备，不返回责任人、电话或金额。"""
        if permission not in user.permissions:
            raise AppException("无权选择资产设备", status_code=403)
        ensure_org_access(user, org_id, permission)
        page, page_size = max(1, page), min(max(1, page_size), 50)
        total, rows = await repository.reference_options(
            session, org_id=org_id, user=user, permission=permission,
            keyword=keyword, page=page, page_size=page_size,
        )
        return {"items": [dict(row, id=str(row["id"])) for row in rows],
                "total": total, "page": page, "page_size": page_size}

    async def reference(
        self,
        session: AsyncSession,
        asset_id: UUID,
        org_id: UUID | None,
        *,
        user: AuthenticatedUser,
        permission: str,
        for_update: bool = False,
    ) -> dict[str, Any] | None:
        """跨模块只读契约：按调用权限范围读取；未指定组织时按资产实际权属返回。"""
        if permission not in user.permissions:
            raise AppException("无权引用资产设备", status_code=403)
        row = await repository.register_for_reference(
            session,
            asset_id,
            org_id,
            user=user,
            permission=permission,
            for_update=for_update,
        )
        if row is None:
            return None
        view = await repository.register_view(session, row.id)
        return self._register(view)

    async def receive_for_disposal(self, session, *, asset_id, org_id, receiver, source_id, source_no, user, permission):
        """调用方已验证报废单和接收账号；资产模块在同一事务移交责任并冻结正常流转。"""
        if permission not in user.permissions:
            raise AppException("无权办理报废接收", 403)
        ensure_org_access(user, org_id, permission)
        row = await repository.register_for_reference(session, asset_id, org_id, for_update=True)
        if row is None or row.registration_status_code != "confirmed":
            raise AppException("资产不存在或尚未确认登记", 409)
        if row.status_code not in {"in_use", "idle", "maintenance"}:
            raise AppException("资产已进入报废流程或不可接收，请刷新后核对", 409)
        await self._protect_stock_asset(session, row)
        await self._valid_code(session, "asset_status", "pending_disposal", "资产状态")
        event = self.event(row, user, "transfer", f"报废单 {source_no} 后勤接收，转为个人保管",
            from_location_id=row.location_id, to_location_id=None,
            from_department_id=row.department_id, to_department_id=receiver["department_id"],
            from_custodian_user_id=row.custodian_user_id, to_custodian_user_id=receiver["id"],
            from_status_code=row.status_code, to_status_code="pending_disposal",
            from_custody_location_note_snapshot=row.custody_location_note,
            source_type_code="asset_disposal", source_id=source_id)
        row.location_id = None
        row.custody_location_note = None
        row.custodian_user_id = receiver["id"]
        row.department_id = receiver["department_id"]
        row.status_code = "pending_disposal"
        row.version_no += 1
        row.updated_at, row.updated_by = utc_now(), user.user_id
        repository.add(session, row, event)
        await session.flush()
        return event.id, row.version_no

    async def finish_disposal_custody(self, session, *, asset_id, org_id, event_id, asset_version_no,
                                     source_id, source_no, user, permission, restore=False):
        """只结束/回退本单接收的当前责任；版本或责任变动时拒绝覆盖。"""
        if permission not in user.permissions:
            raise AppException("无权完成或作废报废接收", 403)
        ensure_org_access(user, org_id, permission)
        row = await repository.register_for_reference(session, asset_id, org_id, for_update=True)
        event = await repository.disposal_custody_event(session, event_id, asset_id, org_id, source_id)
        if (row is None or event is None or row.version_no != asset_version_no
            or row.status_code != "pending_disposal" or row.location_id is not None
            or row.custodian_user_id != event.to_custodian_user_id or row.department_id != event.to_department_id):
            raise self._conflict("资产责任或状态已变化，不能覆盖后续处理，请核对资产后重试")
        if restore:
            if not await repository.custody_restore_available(session, event):
                raise self._conflict("原保管人、责任部门或位置已失效，不能自动回退，请先核实责任关系")
            target = event.from_status_code
            if target not in {"in_use", "idle", "maintenance"}:
                raise self._conflict("原资产状态不支持自动恢复")
        else:
            target = "disposed"
            await self._protect_stock_asset(session, row)
        await self._valid_code(session, "asset_status", target, "资产状态")
        change = self.event(row, user, "transfer" if restore else "status_changed",
            f"报废单 {source_no} {'作废，恢复原保管责任' if restore else '完成处置，结束有效保管责任'}",
            from_location_id=row.location_id, to_location_id=event.from_location_id if restore else row.location_id,
            from_department_id=row.department_id, to_department_id=event.from_department_id if restore else row.department_id,
            from_custodian_user_id=row.custodian_user_id,
            to_custodian_user_id=event.from_custodian_user_id if restore else row.custodian_user_id,
            from_status_code=row.status_code, to_status_code=target,
            from_custody_location_note_snapshot=row.custody_location_note,
            source_type_code="asset_disposal", source_id=source_id)
        if restore:
            row.location_id, row.department_id = event.from_location_id, event.from_department_id
            row.custodian_user_id = event.from_custodian_user_id
            row.custody_location_note = event.from_custody_location_note_snapshot
        row.status_code = target
        row.version_no += 1
        row.updated_at, row.updated_by = utc_now(), user.user_id
        repository.add(session, row, change)
        await session.flush()

    async def change_status_from_business(
        self,
        session: AsyncSession,
        *,
        asset_id: UUID,
        org_id: UUID,
        status_code: str,
        source_type_code: str,
        source_id: UUID,
        note: str,
        user: AuthenticatedUser,
        from_statuses: set[str] | None = None,
    ) -> None:
        """跨模块写契约：维修或报废在同一事务内变更设备状态并追加事件。"""
        row = await repository.register_for_reference(session, asset_id, org_id, for_update=True)
        if row is None:
            raise AppException("关联资产不存在或不属于当前组织", status_code=status.HTTP_400_BAD_REQUEST)
        if row.status_code == "pending_disposal":
            raise self._conflict("资产正在报废处置中，只能从对应报废单完成或作废")
        if from_statuses is not None and row.status_code not in from_statuses:
            return
        await self._valid_code(session, "asset_status", status_code, "资产状态")
        if row.status_code == status_code:
            return
        if status_code == "disposed":
            await self._protect_stock_asset(session, row)
        before = row.status_code
        row.status_code = status_code
        row.version_no += 1
        row.updated_at = utc_now()
        row.updated_by = user.user_id
        repository.add(
            session,
            row,
            self.event(
                row,
                user,
                "status_changed",
                note,
                from_status_code=before,
                to_status_code=status_code,
                source_type_code=source_type_code,
                source_id=source_id,
            ),
        )

    async def reference_by_no(
        self,
        session: AsyncSession,
        asset_no: str,
        org_id: UUID,
        *,
        user: AuthenticatedUser,
        permission: str,
    ) -> dict[str, Any] | None:
        """跨模块只读契约：按组织内资产编号匹配可见的单件设备。"""
        row = await repository.register_by_no_for_reference(
            session,
            asset_no.strip(),
            org_id,
            user=user,
            permission=permission,
        )
        if row is None:
            return None
        view = await repository.register_view(session, row.id)
        return self._register(view)


service = AssetManagementService()
