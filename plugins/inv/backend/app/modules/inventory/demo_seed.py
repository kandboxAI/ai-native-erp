"""物资模块演示数据：供应商分类与供应商、物料分类与物料、两座预置仓库，以及几张已确认的库存单据。

库存余额与流水全部通过统一的“确认库存单据”服务生成（不直接写余额）。可重复执行：
主数据按编号 / 名称跳过已存在的；单据只在本租户还没有演示单据（备注以“演示：”开头）时生成。
演示数据预置总仓库（HQ-01）和食堂仓库（CANTEEN）；正常业务支持新增仓库，不创建库位。
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from uuid import UUID

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.auth.schemas import AuthenticatedUser
from app.framework.catalog import collect_catalog
from app.framework.datetime_local import local_now
from app.framework.db.models import utc_now
from app.modules.department.models import SysDepartment
from app.modules.location.models import MdLocation
from app.modules.supplier.models import MdSupplier
from app.modules.supplier.repository import ensure_supplier_party
from app.modules.supplier_category.models import MdSupplierCategory

from ..asset_management.stock_models import AssetStockBinding, AssetStockReceipt, AssetStockSelection
from .models import (
    InvItemWarehouse,
    InvItemWarehouseSetting,
    InvStockOrder,
    InvStockOrderLine,
    InvStockTransaction,
    InvWarehouse,
    MdItem,
    MdItemCategory,
)
from .stock_order.repository import type_repository
from .stock_order.schemas import OrderCreate, OrderLineWrite, ReturnCreate
from .stock_order.service import service as order_service

DEMO_ORDER = 50
DEMO_REMARK = "演示："

SUPPLIER_CATEGORIES = ["办公用品", "教学设备", "清洁卫生"]
SUPPLIERS = [
    ("GYS-DEMO-01", "演示办公用品供应商", "办公用品", "bank_transfer", "monthly"),
    ("GYS-DEMO-02", "演示设备供应商", "教学设备", "bank_transfer", "per_order"),
    ("GYS-DEMO-03", "演示清洁用品供应商", "清洁卫生", "cash", "per_order"),
]
ITEM_CATEGORIES = [
    ("办公耗材", "纸张、笔、文件夹等"),
    ("教学用品", "粉笔、教具、实验耗材"),
    ("设备器材", "可借用或独立编号管理的设备"),
    ("家具资产", "实训室、宿舍和办公场所家具"),
    ("清洁消毒", "清洁与消毒用品"),
    ("体育器材", ""),
]
# (item_no, name, category, spec, unit, price, supplier_no, lot_controlled, shelf_life_days, min, max)
ITEMS = [
    ("WL-DEMO-A4", "A4复印纸", "办公耗材", "70g 500张/包", "pack", "25.00", "GYS-DEMO-01", False, None, "20", "300"),
    ("WL-DEMO-PEN", "黑色签字笔", "办公耗材", "0.5mm 12支/盒", "box", "18.00", "GYS-DEMO-01", False, None, "10", "100"),
    ("WL-DEMO-CHALK", "无尘粉笔", "教学用品", "白色 50支/盒", "box", "6.50", "GYS-DEMO-01", False, None, "30", None),
    ("WL-DEMO-PROJ", "便携投影仪", "设备器材", "1080P", "set", "2600.00", "GYS-DEMO-02", False, None, None, None),
    ("WL-DEMO-DISINF", "84消毒液", "清洁消毒", "500ml/瓶", "bottle", "8.00", "GYS-DEMO-03", True, 730, "20", "200"),
    ("WL-DEMO-BALL", "7号篮球", "体育器材", "PU 标准7号", "piece", "120.00", None, False, None, "5", "40"),
    ("WL-DEMO-TRAIN-DESK", "实训桌", "家具资产", "双人位 1200×600mm", "piece", "680.00", "GYS-DEMO-02", False, None, None, None),
    ("WL-DEMO-TRAIN-CHAIR", "实训椅", "家具资产", "钢木结构", "piece", "160.00", "GYS-DEMO-02", False, None, None, None),
    ("WL-DEMO-DORM-BED", "宿舍床", "家具资产", "单人钢架床 2000×900mm", "piece", "950.00", "GYS-DEMO-02", False, None, None, None),
    ("WL-DEMO-DORM-DESK", "宿舍书桌", "家具资产", "双人组合书桌", "piece", "720.00", "GYS-DEMO-02", False, None, None, None),
    ("WL-DEMO-AIRCON", "壁挂式空调", "设备器材", "1.5匹 变频", "set", "3200.00", "GYS-DEMO-02", False, None, None, None),
    ("WL-DEMO-COMPUTER", "实训电脑", "设备器材", "教学台式机 i5/16GB/512GB", "set", "4600.00", "GYS-DEMO-02", False, None, None, None),
]


# 仅用于新建演示物料，明确列出资格；不覆盖已有物料的人工配置。
ASSET_ITEM_DEFAULTS = {
    "WL-DEMO-PROJ": ("equipment", "individual"),
    "WL-DEMO-TRAIN-DESK": ("furniture", "individual"),
    "WL-DEMO-TRAIN-CHAIR": ("furniture", "individual"),
    "WL-DEMO-DORM-BED": ("dormitory_facility", "individual"),
    "WL-DEMO-DORM-DESK": ("furniture", "individual"),
    "WL-DEMO-AIRCON": ("equipment", "individual"),
    "WL-DEMO-COMPUTER": ("it_equipment", "individual"),
}


def _demo_user(ctx, org_id: UUID) -> AuthenticatedUser:
    """以租户管理员身份调用业务服务（内置管理员被授予全部权限，数据范围为全部）。"""
    permissions = [item.key for item in collect_catalog().permissions]
    return AuthenticatedUser(
        auth_user_id=ctx.admin_user_id,
        tenant_id=ctx.tenant.id,
        tenant_no=ctx.tenant.tenant_no,
        tenant_schema=ctx.schema,
        user_id=ctx.admin_user_id,
        org_id=org_id,
        org_access_mode_code="all",
        data_scope_code="all",
        permissions=permissions,
        permission_scopes={key: "all" for key in permissions},
    )


async def _seed_suppliers(session: AsyncSession, user_id: UUID) -> dict[str, MdSupplier]:
    categories = {row.category_name: row for row in (await session.exec(select(MdSupplierCategory).where(MdSupplierCategory.deleted_at.is_(None)))).all()}
    for name in SUPPLIER_CATEGORIES:
        if name not in categories:
            categories[name] = MdSupplierCategory(category_name=name, created_by=user_id, updated_by=user_id)
            session.add(categories[name])
    await session.flush()
    suppliers = {row.supplier_no: row for row in (await session.exec(select(MdSupplier).where(MdSupplier.deleted_at.is_(None)))).all()}
    for supplier_no, name, category, method, cycle in SUPPLIERS:
        if supplier_no in suppliers:
            continue
        supplier = MdSupplier(
            supplier_no=supplier_no,
            party_id=await ensure_supplier_party(session, name, "organization", user_id),
            category_id=categories[category].id,
            settlement_method_code=method,
            settlement_cycle_code=cycle,
            created_by=user_id,
            updated_by=user_id,
        )
        session.add(supplier)
        suppliers[supplier_no] = supplier
    await session.flush()
    return suppliers


async def _seed_items(session: AsyncSession, suppliers: dict[str, MdSupplier], user_id: UUID) -> dict[str, MdItem]:
    categories = {row.category_name: row for row in (await session.exec(select(MdItemCategory).where(MdItemCategory.deleted_at.is_(None)))).all()}
    for name, description in ITEM_CATEGORIES:
        if name not in categories:
            categories[name] = MdItemCategory(category_name=name, description=description or None, created_by=user_id, updated_by=user_id)
            session.add(categories[name])
    await session.flush()
    items = {row.item_no: row for row in (await session.exec(select(MdItem).where(MdItem.deleted_at.is_(None)))).all()}
    for item_no, name, category, spec, unit, price, supplier_no, lot, shelf, _min_q, _max_q in ITEMS:
        if item_no in items:
            continue
        items[item_no] = MdItem(
            item_no=item_no,
            item_name=name,
            category_id=categories[category].id,
            specification=spec,
            unit_code=unit,
            unit_price=Decimal(price),
            default_supplier_id=suppliers[supplier_no].id if supplier_no else None,
            is_asset_managed=item_no in ASSET_ITEM_DEFAULTS,
            default_asset_type_code=ASSET_ITEM_DEFAULTS.get(item_no, (None, None))[0],
            default_asset_management_mode_code=ASSET_ITEM_DEFAULTS.get(item_no, (None, None))[1],
            is_lot_controlled=lot,
            shelf_life_days=shelf,
            created_by=user_id,
            updated_by=user_id,
        )
        session.add(items[item_no])
    await session.flush()
    return items


async def _ensure_warehouse(
    session: AsyncSession,
    org_id: UUID,
    warehouse_no: str,
    warehouse_name: str,
    user_id: UUID,
) -> InvWarehouse:
    warehouse = (
        await session.exec(
            select(InvWarehouse).where(InvWarehouse.org_id == org_id, InvWarehouse.warehouse_no == warehouse_no, InvWarehouse.deleted_at.is_(None))
        )
    ).first()
    if warehouse is None:
        warehouse = InvWarehouse(
            org_id=org_id,
            warehouse_no=warehouse_no,
            warehouse_name=warehouse_name,
            created_by=user_id,
            updated_by=user_id,
        )
        session.add(warehouse)
        await session.flush()
    elif warehouse.warehouse_name != warehouse_name:
        warehouse.warehouse_name = warehouse_name
        warehouse.updated_by = user_id
        session.add(warehouse)
    return warehouse


async def _ensure_warehouse_location(
    session: AsyncSession,
    warehouse: InvWarehouse,
    location_no: str,
    location_name: str,
    user_id: UUID,
) -> None:
    """为资产类演示物料补齐仓库的物理位置引用。"""
    if warehouse.location_id is not None:
        return
    location = (
        await session.exec(
            select(MdLocation).where(
                MdLocation.org_id == warehouse.org_id,
                MdLocation.location_no == location_no,
                MdLocation.deleted_at.is_(None),
            )
        )
    ).first()
    if location is None:
        location = MdLocation(
            org_id=warehouse.org_id,
            location_no=location_no,
            location_name=location_name,
            location_type_code="area",
            latitude=Decimal("0"),
            longitude=Decimal("0"),
            coordinate_system_code="gcj02",
            location_description="演示数据使用的仓库物理位置",
            created_by=user_id,
            updated_by=user_id,
        )
        session.add(location)
        await session.flush()
    warehouse.location_id = location.id
    warehouse.location = location_name
    warehouse.updated_by = user_id
    session.add(warehouse)
    await session.flush()


async def _ensure_demo_department(session: AsyncSession, org_id: UUID, user_id: UUID) -> SysDepartment:
    department = (
        await session.exec(
            select(SysDepartment).where(
                SysDepartment.org_id == org_id,
                SysDepartment.department_no == "DEMO-ASSET-MGMT",
                SysDepartment.deleted_at.is_(None),
            )
        )
    ).first()
    if department is None:
        department = SysDepartment(
            org_id=org_id,
            department_no="DEMO-ASSET-MGMT",
            department_name="演示资产管理组",
            manager_user_id=user_id,
            sort_no=0,
            created_by=user_id,
            updated_by=user_id,
            remark="演示数据使用的资产责任部门",
        )
        session.add(department)
        await session.flush()
    return department


async def _seed_thresholds(
    session: AsyncSession,
    items: dict[str, MdItem],
    warehouse: InvWarehouse,
    user_id: UUID,
) -> None:
    existing = set(
        (
            await session.exec(
                select(InvItemWarehouseSetting.item_id).where(
                    InvItemWarehouseSetting.warehouse_id == warehouse.id,
                    InvItemWarehouseSetting.deleted_at.is_(None),
                )
            )
        ).all()
    )
    for item_no, *_prefix, min_quantity, max_quantity in ITEMS:
        item = items[item_no]
        if item.id in existing or min_quantity is None or max_quantity is None:
            continue
        session.add(
            InvItemWarehouseSetting(
                org_id=warehouse.org_id,
                item_id=item.id,
                warehouse_id=warehouse.id,
                min_quantity=Decimal(min_quantity),
                max_quantity=Decimal(max_quantity),
                created_by=user_id,
                updated_by=user_id,
            )
        )
    await session.flush()


async def _seed_applicable_warehouses(
    session: AsyncSession,
    items: dict[str, MdItem],
    general_warehouse: InvWarehouse,
    canteen_warehouse: InvWarehouse,
    user_id: UUID,
) -> None:
    """为演示物料建立入库适用仓库关系；它与安全库存阈值是两套独立配置。"""
    pairs = [(item, general_warehouse) for item in items.values()]
    pairs.extend((items[item_no], canteen_warehouse) for item_no in ("WL-DEMO-A4", "WL-DEMO-CHALK"))
    existing = {
        (row.item_id, row.warehouse_id)
        for row in (
            await session.exec(
                select(InvItemWarehouse).where(
                    InvItemWarehouse.item_id.in_([item.id for item, _ in pairs]),
                    InvItemWarehouse.warehouse_id.in_([warehouse.id for _, warehouse in pairs]),
                    InvItemWarehouse.valid_to.is_(None),
                )
            )
        ).all()
    }
    now = utc_now()
    for item, warehouse in pairs:
        if (item.id, warehouse.id) in existing:
            continue
        session.add(
            InvItemWarehouse(
                org_id=warehouse.org_id,
                item_id=item.id,
                warehouse_id=warehouse.id,
                valid_from=now,
                created_by=user_id,
                updated_by=user_id,
            )
        )
    await session.flush()


async def _demo_order(session: AsyncSession, remark: str) -> InvStockOrder | None:
    return (
        await session.exec(
            select(InvStockOrder).where(InvStockOrder.remark == remark).order_by(InvStockOrder.created_at)
        )
    ).first()


async def _demo_return(session: AsyncSession, lend_order_id: UUID) -> InvStockOrder | None:
    return (
        await session.exec(
            select(InvStockOrder).where(InvStockOrder.remark == f"{DEMO_REMARK}归还一台").limit(1)
        )
    ).first()


async def seed_demo(session: AsyncSession, ctx) -> None:
    user_id = ctx.admin_user_id
    main_org = ctx.root_org_id

    suppliers = await _seed_suppliers(session, user_id)
    items = await _seed_items(session, suppliers, user_id)
    asset_department = await _ensure_demo_department(session, main_org, user_id)
    general_warehouse = await _ensure_warehouse(session, main_org, "HQ-01", "总仓库", user_id)
    canteen_warehouse = await _ensure_warehouse(session, main_org, "CANTEEN", "食堂仓库", user_id)
    for warehouse in (general_warehouse, canteen_warehouse):
        if warehouse.default_asset_department_id is None:
            warehouse.default_asset_department_id = asset_department.id
            warehouse.updated_by = user_id
            session.add(warehouse)
    await session.flush()
    await _ensure_warehouse_location(session, general_warehouse, "LOC-DEMO-HQ-01", "演示总仓库区域", user_id)
    await _ensure_warehouse_location(session, canteen_warehouse, "LOC-DEMO-CANTEEN", "演示食堂仓库区域", user_id)
    await _seed_thresholds(session, items, general_warehouse, user_id)
    await _seed_applicable_warehouses(session, items, general_warehouse, canteen_warehouse, user_id)
    department = (
        await session.exec(select(SysDepartment).where(SysDepartment.org_id == main_org, SysDepartment.deleted_at.is_(None)).order_by(SysDepartment.sort_no))
    ).first()
    await session.commit()

    types = {item.type_no: item for item in await type_repository.options(session, form=None, direction_code=None, include_inactive=False)}
    actor = _demo_user(ctx, main_org)
    today = local_now().date()

    def line(item_no: str, quantity: str, **extra) -> OrderLineWrite:
        return OrderLineWrite(item_id=items[item_no].id, quantity=Decimal(quantity), **extra)

    # 1. 采购入库（直接确认）
    if await _demo_order(session, f"{DEMO_REMARK}开学采购") is None:
        await order_service.create(
            OrderCreate(
                order_type_id=types["PURCHASE_IN"].id,
                business_date=today - timedelta(days=20),
                to_warehouse_id=general_warehouse.id,
                supplier_id=suppliers["GYS-DEMO-01"].id,
                remark=f"{DEMO_REMARK}开学采购",
                lines=[
                    line("WL-DEMO-A4", "200"),
                    line("WL-DEMO-PEN", "50"),
                    line("WL-DEMO-CHALK", "100"),
                    line("WL-DEMO-DISINF", "60", lot_no="XD20260901", production_date=today - timedelta(days=40), expiry_date=today + timedelta(days=690)),
                    line("WL-DEMO-BALL", "20"),
                ],
                confirm=True,
            ),
            actor,
        )
    if await _demo_order(session, f"{DEMO_REMARK}教学设备采购") is None:
        await order_service.create(
            OrderCreate(
                order_type_id=types["PURCHASE_IN"].id,
                business_date=today - timedelta(days=18),
                to_warehouse_id=general_warehouse.id,
                supplier_id=suppliers["GYS-DEMO-02"].id,
                remark=f"{DEMO_REMARK}教学设备采购",
                lines=[line("WL-DEMO-PROJ", "5")],
                confirm=True,
            ),
            actor,
        )
    # 2. 领用出库
    requisition_type = types["REQUISITION_OUT"] if department is not None else types["OTHER_OUT"]
    if await _demo_order(session, f"{DEMO_REMARK}教研组领用") is None:
        await order_service.create(
            OrderCreate(
                order_type_id=requisition_type.id,
                business_date=today - timedelta(days=10),
                from_warehouse_id=general_warehouse.id,
                department_id=department.id if department else None,
                counterparty_user_id=user_id,
                purpose="教研组日常办公",
                reason=None if department is not None else "演示领用",
                remark=f"{DEMO_REMARK}教研组领用",
                lines=[line("WL-DEMO-A4", "30"), line("WL-DEMO-PEN", "10")],
                confirm=True,
            ),
            actor,
        )
    # 3. 调拨（需要审批：提交 → 审批 → 确认）
    transfer = await _demo_order(session, f"{DEMO_REMARK}两仓调拨")
    if transfer is None:
        await order_service.create(
            OrderCreate(
                order_type_id=types["TRANSFER"].id,
                business_date=today - timedelta(days=8),
                from_warehouse_id=general_warehouse.id,
                to_warehouse_id=canteen_warehouse.id,
                remark=f"{DEMO_REMARK}两仓调拨",
                lines=[line("WL-DEMO-A4", "50"), line("WL-DEMO-CHALK", "40")],
                submit=True,
            ),
            actor,
        )
        transfer = await _demo_order(session, f"{DEMO_REMARK}两仓调拨")
    if transfer is not None:
        if transfer.status_code == "submitted":
            await order_service.approve(transfer.id, actor)
            transfer.status_code = "approved"
        if transfer.status_code == "approved":
            await order_service.confirm(transfer.id, actor)
            await session.refresh(transfer)
    # 4. 借出与部分归还
    lend = await _demo_order(session, f"{DEMO_REMARK}借用投影仪")
    if lend is None:
        projector_bindings = (
            await session.exec(
                select(AssetStockBinding)
                .join(AssetStockReceipt, AssetStockReceipt.id == AssetStockBinding.receipt_id)
                .where(
                    AssetStockReceipt.item_id == items["WL-DEMO-PROJ"].id,
                    AssetStockBinding.warehouse_id == general_warehouse.id,
                    AssetStockBinding.quantity > 0,
                )
                .order_by(AssetStockBinding.id)
            )
        ).all()
        tracking = {
            "asset": {
                "selections": [
                    {
                        "binding_id": binding.id,
                        "quantity": Decimal("1"),
                        "target_location_id": general_warehouse.location_id,
                        "department_id": asset_department.id,
                    }
                    for binding in projector_bindings[:2]
                ]
            }
        }
        await order_service.create(
            OrderCreate(
                order_type_id=types["LEND"].id,
                business_date=today - timedelta(days=5),
                from_warehouse_id=general_warehouse.id,
                counterparty_name_snapshot="张老师",
                expected_return_date=today + timedelta(days=10),
                purpose="公开课使用",
                remark=f"{DEMO_REMARK}借用投影仪",
                lines=[line("WL-DEMO-PROJ", "2", tracking=tracking)],
                confirm=True,
            ),
            actor,
        )
        lend = await _demo_order(session, f"{DEMO_REMARK}借用投影仪")
    if lend is not None and await _demo_return(session, lend.id) is None:
        lend_line = (
            await session.exec(
                select(InvStockOrderLine)
                .where(InvStockOrderLine.stock_order_id == lend.id)
                .order_by(InvStockOrderLine.line_no)
            )
        ).first()
        if lend_line is not None:
            lend_selections = (
                await session.exec(
                    select(AssetStockSelection)
                    .where(
                        AssetStockSelection.stock_order_line_id == lend_line.id,
                        AssetStockSelection.result_binding_id.is_not(None),
                    )
                    .order_by(AssetStockSelection.binding_id)
                )
            ).all()
            return_tracking = {
                "asset": {
                    "selections": [
                        {
                            "binding_id": selection.result_binding_id,
                            "quantity": Decimal("1"),
                            "target_location_id": general_warehouse.location_id,
                            "department_id": asset_department.id,
                        }
                        for selection in lend_selections[:1]
                    ]
                }
            }
            await order_service.create_return(
                lend.id,
                ReturnCreate(
                    lines=[{
                        "source_line_id": lend_line.id,
                        "quantity": Decimal("1"),
                        "tracking": return_tracking,
                    }],
                    remark=f"{DEMO_REMARK}归还一台",
                ),
                actor,
            )
    # 4. 报损（需要审批）
    damage = await _demo_order(session, f"{DEMO_REMARK}篮球报损")
    if damage is None:
        await order_service.create(
            OrderCreate(
                order_type_id=types["DAMAGE"].id,
                business_date=today - timedelta(days=2),
                from_warehouse_id=general_warehouse.id,
                reason="体育课使用中破损漏气",
                handling_method_code="scrap",
                remark=f"{DEMO_REMARK}篮球报损",
                lines=[line("WL-DEMO-BALL", "2")],
                submit=True,
            ),
            actor,
        )
        damage = await _demo_order(session, f"{DEMO_REMARK}篮球报损")
    if damage is not None:
        if damage.status_code == "submitted":
            await order_service.approve(damage.id, actor)
            damage.status_code = "approved"
        if damage.status_code == "approved":
            if damage.confirmed_at is not None:
                # bootstrap 外层会再次提交当前会话；修复早期演示数据在嵌套会话确认后留下的旧状态。
                damage.status_code = "confirmed"
                session.add(damage)
            elif (
                await session.exec(
                    select(InvStockTransaction.id)
                    .where(InvStockTransaction.stock_order_id == damage.id)
                    .limit(1)
                )
            ).first() is None:
                await order_service.confirm(damage.id, actor)
                await session.refresh(damage)
