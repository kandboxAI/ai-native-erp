"""制造仓库配置与工单成品隔离，全部离线。"""
import asyncio
from decimal import Decimal as D
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from app.auth.schemas import AuthenticatedUser
from app.core.exceptions import AppException
from app.modules.mes import inventory_service as module
from app.modules.mes.inventory_service import inventory_service as service
from app.modules.mes.warehouse_policy import allows, validate_warehouse
from app.modules.inventory import public as stock, integration_repository as integration
from app.modules.inventory.warehouse_scope import warehouse_condition
from app.modules.inventory.stock_order.service import service as stock_service
from app.modules.inventory.warehouse.repository import warehouse_repository


@pytest.fixture
def actor():
    return AuthenticatedUser(auth_user_id=uuid4(), tenant_id=uuid4(), tenant_no="test", tenant_schema="t_test",
        user_id=uuid4(), org_id=uuid4(), data_scope_code="all", enabled_plugin_keys=["inv", "mes"],
        permission_scopes={"mes:warehouse:list": "all", "mes:warehouse:manage": "all"},
        permissions=["mes:warehouse:list", "mes:warehouse:manage"])


def test_scope_opt_in_preserves_school_default_and_requires_enabled_plugin(actor):
    school = str(warehouse_condition().compile(compile_kwargs={"literal_binds": True}))
    manufacturing = str(warehouse_condition("mes", actor).compile(compile_kwargs={"literal_binds": True}))
    assert "NOT IN" in school and "mes_finished" in school and "CANTEEN" not in school and "HQ-01" not in school
    assert "mes_finished" in manufacturing and "HQ-01" in manufacturing and "CANTEEN" not in manufacturing
    actor.enabled_plugin_keys = ["inv"]
    with pytest.raises(AppException, match="未启用"): warehouse_condition("mes", actor)
    with pytest.raises(AppException, match="未登记"): warehouse_condition("arbitrary", actor)


def test_warehouse_purpose_dictionary_remains_an_inventory_owned_extension():
    from app.modules.inventory.dictionary_specs import DICTIONARIES
    from app.modules.mes.dictionary_specs import DICT_ITEMS
    definitions = [row for row in DICTIONARIES if row["dict_code"] == "inv_warehouse_type"]
    assert len(definitions) == 1
    assert "general" in dict(definitions[0]["items"])
    assert "mes_finished" in dict(DICT_ITEMS["inv_warehouse_type"])


def test_edu_and_manufacturing_coexist_without_hiding_the_general_warehouse(actor):
    from sqlalchemy import create_engine, MetaData, Table, Column, Uuid, String, select, insert
    from app.modules.inventory.models import InvWarehouse
    engine = create_engine("sqlite://")
    table = Table("inv_warehouse", MetaData(), Column("id", Uuid(), primary_key=True),
        Column("warehouse_no", String()), Column("warehouse_type_code", String()))
    table.metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(insert(table), [
            dict(id=uuid4(), warehouse_no="HQ-01", warehouse_type_code="general"),
            dict(id=uuid4(), warehouse_no="CANTEEN", warehouse_type_code="general"),
            dict(id=uuid4(), warehouse_no="CUSTOM", warehouse_type_code="general"),
            dict(id=uuid4(), warehouse_no="MES-FINISHED", warehouse_type_code="mes_finished"),
        ])
        ordinary = connection.execute(select(InvWarehouse.warehouse_no).where(warehouse_condition())).scalars().all()
        manufacturing = connection.execute(select(InvWarehouse.warehouse_no).where(warehouse_condition("mes", actor))).scalars().all()
    engine.dispose()
    assert set(ordinary) == {"HQ-01", "CANTEEN", "CUSTOM"}
    assert set(manufacturing) == {"HQ-01", "MES-FINISHED"}


@pytest.mark.parametrize("kind,purpose,expected", [("mes_raw", "issue", True), ("mes_wip", "return", True),
    ("mes_finished", "receipt", True), ("mes_finished", "shipment", True), ("mes_raw", "shipment", False),
    ("mes_finished", "issue", False), ("canteen", "receipt", False)])
def test_warehouse_use_rules(kind, purpose, expected):
    assert allows(dict(warehouse_no="CUSTOM", warehouse_type_code=kind), purpose) is expected


def test_warehouse_requires_matching_organization(monkeypatch, actor):
    monkeypatch.setattr(stock, "get_stock_warehouse", AsyncMock(return_value=dict(org_id=uuid4(), warehouse_no="RAW", warehouse_type_code="mes_raw")))
    with pytest.raises(AppException, match="组织不符"):
        asyncio.run(validate_warehouse(None, NS(warehouse_id=uuid4(), org_id=actor.org_id, posting_type_code="issue")))


def test_config_create_is_scoped_and_caller_owns_transaction(actor):
    added = []
    session = NS(add=added.append, flush=AsyncMock(), commit=AsyncMock())
    payload = dict(org_id=actor.org_id, warehouse_no="RAW-01", warehouse_name="制造原料", warehouse_type_code="mes_raw", is_active=True)
    row = asyncio.run(integration.configure_warehouse(session, "mes", payload, actor))
    assert row.org_id == actor.org_id and row.created_by == actor.user_id and row in added
    session.commit.assert_not_called()
    actor.permissions.remove("mes:warehouse:manage")
    with pytest.raises(AppException, match="缺少仓库配置权限"):
        asyncio.run(integration.configure_warehouse(session, "mes", payload, actor))


@pytest.mark.parametrize("change,history,stock,pending,message", [
    ({"warehouse_type_code": "mes_finished"}, True, False, False, "不能改变仓库用途"),
    ({"is_active": False}, False, True, False, "不能停用"),
    ({"is_active": False}, False, False, True, "不能停用"),
    ({"org_id": uuid4()}, False, False, False, "不能变更"),
])
def test_config_rejects_unsafe_changes(actor, change, history, stock, pending, message):
    row = NS(id=uuid4(), warehouse_type_code="mes_raw")
    answers = [NS(scalars=lambda: NS(first=lambda: row))]
    if "warehouse_type_code" in change: answers.append(NS(first=lambda: (1,) if history else None))
    if "is_active" in change:
        answers.extend([NS(first=lambda: (1,) if stock else None), NS(first=lambda: (1,) if pending else None)])
    session = NS(execute=AsyncMock(side_effect=answers), commit=AsyncMock())
    with pytest.raises(AppException, match=message):
        asyncio.run(integration.configure_warehouse(session, "mes", change, actor, row.id))
    session.commit.assert_not_called()


def test_config_cannot_edit_legacy_general_warehouse(actor):
    row = NS(id=uuid4(), warehouse_type_code="general")
    session = NS(execute=AsyncMock(return_value=NS(scalars=lambda: NS(first=lambda: row))))
    with pytest.raises(AppException, match="不属于可维护"):
        asyncio.run(integration.configure_warehouse(session, "mes", {"warehouse_name": "新名称"}, actor, row.id))


@pytest.fixture
def lots(monkeypatch):
    orders, item, warehouse = [uuid4(), uuid4()], uuid4(), uuid4()
    rows, movements, plans, states = [], {}, {}, {}
    def add(order, kind, quantity, lot=None, status="confirmed"):
        row = NS(id=uuid4(), stock_order_id=uuid4(), work_order_id=orders[order], warehouse_id=warehouse,
            item_id=item, quantity=D(quantity), posting_type_code=kind, lot_id=lot, unit_code="piece")
        rows.append(row)
        states[row.stock_order_id] = dict(status_code=status, is_reversed=False)
        entry = dict(lot_id=lot, quantity=D(quantity), item_id=item, warehouse_id=warehouse, unit_code="piece")
        if kind == "receipt" or status == "confirmed": movements[row.stock_order_id] = [entry]
        if kind != "receipt": plans[row.stock_order_id] = [dict(entry)]
        return row
    monkeypatch.setattr(module.repo, "postings", AsyncMock(side_effect=lambda session, order_id: [row for row in rows if row.work_order_id == order_id]))
    monkeypatch.setattr(module.repo, "receipts_for_items", AsyncMock(side_effect=lambda *args: [row for row in rows if row.posting_type_code == "receipt"]))
    monkeypatch.setattr(stock, "get_stock_order_states", AsyncMock(side_effect=lambda session, ids: {key: states[key] for key in ids}))
    monkeypatch.setattr(stock, "get_stock_order_lots", AsyncMock(side_effect=lambda session, key: movements.get(key, [])))
    monkeypatch.setattr(stock, "get_stock_order_allocations", AsyncMock(side_effect=lambda session, ids: {key: plans[key] for key in ids if key in plans}))
    return add, rows, movements, plans, states


def test_same_item_orders_never_substitute_and_pending_shipments_reserve(lots):
    add, _, _, _, states = lots
    lot_a, lot_b, lot_other = uuid4(), uuid4(), uuid4()
    first = add(0, "receipt", 3, lot_a)
    add(0, "receipt", 4, lot_b)
    add(1, "receipt", 100, lot_other)
    pending = add(0, "shipment", 2, lot_a, "submitted")
    current = add(0, "shipment", 4, lot_b, "approved")
    async def run():
        assert await service.finished_lots(None, current, exclude=current.id) == {lot_a: D(1), lot_b: D(4)}
        await service.validate_shipment_lots(None, current, [NS(lot_id=lot_a, quantity=D(1)), NS(lot_id=lot_b, quantity=D(3))])
        with pytest.raises(AppException, match="禁止混发"):
            await service.validate_shipment_lots(None, current, [NS(lot_id=lot_other, quantity=D(1))])
        with pytest.raises(AppException, match="数量不足"):
            await service.validate_shipment_lots(None, current, [NS(lot_id=lot_a, quantity=D(2))])
        states[pending.stock_order_id]["status_code"] = "voided"
        assert (await service.finished_lots(None, current, exclude=current.id))[lot_a] == 3
        states[first.stock_order_id]["is_reversed"] = True
        with pytest.raises(AppException, match="禁止混发"):
            await service.validate_shipment_lots(None, current, [NS(lot_id=lot_a, quantity=D(1))])
    asyncio.run(run())


def test_legacy_unbatched_receipt_or_shipment_fails_closed(lots):
    add, _, movements, plans, _ = lots
    receipt = add(0, "receipt", 2)
    current = add(0, "shipment", 1, uuid4())
    with pytest.raises(AppException, match="未绑定批次的历史成品"):
        asyncio.run(service.finished_lots(None, current, exclude=current.id))
    movements[receipt.stock_order_id][0]["lot_id"] = current.lot_id
    old = add(0, "shipment", 1, status="submitted")
    with pytest.raises(AppException, match="历史出货申请"):
        asyncio.run(service.finished_lots(None, current, exclude=current.id))
    plans[old.stock_order_id] = []
    with pytest.raises(AppException, match="历史出货申请"):
        asyncio.run(service.finished_lots(None, current, exclude=current.id))


def test_legacy_shared_lot_cannot_be_used_by_two_orders(lots):
    add, *_ = lots
    lot = uuid4()
    add(0, "receipt", 2, lot)
    add(1, "receipt", 3, lot)
    current = add(0, "shipment", 1, lot)
    with pytest.raises(AppException, match="多个工单共用"):
        asyncio.run(service.finished_lots(None, current, exclude=current.id))


def test_confirmed_legacy_fifo_shipment_uses_actual_lot_not_empty_plan(lots):
    add, _, _, plans, _ = lots
    lot = uuid4()
    receipt = add(0, "receipt", 5, lot)
    shipped = add(0, "shipment", 2, lot)
    plans[shipped.stock_order_id][0]["lot_id"] = None
    # 实际出库流水保留批次，旧单据计划行可能未指定。
    assert asyncio.run(service.finished_lots(None, receipt)) == {lot: D(3)}


def test_multi_lot_shipment_passes_explicit_allocations_to_inv(lots, monkeypatch):
    add, _, _, _, _ = lots
    lot_a, lot_b = uuid4(), uuid4()
    add(0, "receipt", 3, lot_a)
    add(0, "receipt", 4, lot_b)
    row = add(0, "shipment", 5, status="voided")  # 创建中的关联不计预留。
    row.org_id, row.unit_price, row.note = uuid4(), None, "出货"
    monkeypatch.setattr(module, "validate_warehouse", AsyncMock())
    monkeypatch.setattr(stock, "get_stock_order_type", AsyncMock(return_value=dict(id=uuid4(), direction_code="out", is_negative_allowed=False,
        default_from_status_code="available", is_approval_required=False)))
    create = AsyncMock(return_value=dict(id=row.stock_order_id))
    monkeypatch.setattr(stock, "create_stock_order", create)
    monkeypatch.setattr(module.repo, "add", lambda *args: None)
    session = NS(flush=AsyncMock(), commit=AsyncMock())
    asyncio.run(service.create_in_session(session, row, None, confirm=False))
    payload = create.await_args.args[1]
    assert [(line.lot_id, line.quantity) for line in payload.lines] == [(lot_a, D(3)), (lot_b, D(2))]
    session.commit.assert_not_called()


def test_ordinary_fifo_and_explicit_lot_cannot_consume_protected_finished_stock(lots, monkeypatch):
    add, _, _, _, _ = lots
    lot = uuid4()
    receipt = add(0, "receipt", 2, lot)
    monkeypatch.setattr(module.repo, "receipts_for_items", AsyncMock(return_value=[receipt]))
    monkeypatch.setattr(stock, "get_stock_warehouse", AsyncMock(return_value=dict(warehouse_type_code="general")))
    order = NS(source_doc_type_code=None, from_warehouse_id=receipt.warehouse_id, to_warehouse_id=None)
    line = NS(item_id=receipt.item_id, from_warehouse_id=None, to_warehouse_id=None, lot_id=None)
    async def run():
        for value in (None, lot):
            line.lot_id = value
            with pytest.raises(AppException, match="工单隔离成品"):
                await module.protect_finished_lots(None, order, NS(type_no="ORDINARY_OUT"), [line], None)
        line.lot_id = uuid4()
        await module.protect_finished_lots(None, order, NS(type_no="ORDINARY_OUT"), [line], None)
    asyncio.run(run())


def test_configured_warehouse_operations_require_plugin_and_same_org(actor, monkeypatch):
    identifier = uuid4()
    warehouse = NS(id=identifier, org_id=actor.org_id, warehouse_type_code="mes_raw")
    monkeypatch.setattr(warehouse_repository, "get_many", AsyncMock(return_value={identifier: warehouse}))
    order = NS(org_id=actor.org_id, from_warehouse_id=None, to_warehouse_id=identifier, source_doc_type_code=None)
    kind = NS(type_no="PURCHASE_IN")
    async def run():
        await stock_service._validate_line_warehouses(None, order, kind, [], actor, "mes:warehouse:manage")
        warehouse.org_id = uuid4()
        with pytest.raises(AppException, match="所属组织一致"):
            await stock_service._validate_line_warehouses(None, order, kind, [], actor, "mes:warehouse:manage")
        actor.enabled_plugin_keys = ["inv"]
        with pytest.raises(AppException, match="未启用"):
            await stock_service._validate_line_warehouses(None, order, kind, [], actor, "mes:warehouse:manage")
    asyncio.run(run())
