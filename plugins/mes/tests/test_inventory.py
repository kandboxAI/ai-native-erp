"""仓储编排离线回归：额度、来源保护、审批、调用方事务；不连接业务库。"""
import asyncio
from decimal import Decimal as D
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.core.exceptions import AppException
from app.modules.mes import inventory_service as module
from app.modules.mes.inventory_service import inventory_service as service, active
from app.modules.mes.inventory_schemas import InventoryPostingBody
from app.modules.mes.delivery_repository import delivery_repository
from app.modules.inventory import public as stock
from app.modules.inventory.stock_order import lifecycle


@pytest.fixture
def warehouse(monkeypatch):
    order = NS(id=uuid4(), org_id=uuid4(), product_item_id=uuid4(), unit_code="piece", status_code="in_progress")
    operation = NS(id=uuid4(), sequence_no=10, status_code="pending", good_quantity=D(10), is_quality_required=False)
    rows, states, movements = [], {}, []
    monkeypatch.setattr(module.repo, "postings", AsyncMock(side_effect=lambda *args: rows))
    monkeypatch.setattr(module.repo, "operations", AsyncMock(return_value=[operation]))
    monkeypatch.setattr(module.repo, "order", AsyncMock(return_value=order))
    monkeypatch.setattr(module.report_repository, "pending_for_order", AsyncMock(return_value=False))
    monkeypatch.setattr(delivery_repository, "direct_shipped_quantity", AsyncMock(return_value=D(0)))
    monkeypatch.setattr(stock, "get_stock_order_states", AsyncMock(side_effect=lambda *args: states))
    monkeypatch.setattr(stock, "get_stock_order_lots", AsyncMock(side_effect=lambda *args: movements))
    monkeypatch.setattr(stock, "get_stock_order_allocations", AsyncMock(return_value={}))
    monkeypatch.setattr(stock, "get_stock_warehouse", AsyncMock(return_value=dict(org_id=order.org_id, warehouse_no="HQ-01", warehouse_type_code="general")))
    def add(kind, quantity, status="confirmed", **values):
        row = NS(id=uuid4(), work_order_id=order.id, org_id=order.org_id, posting_type_code=kind,
            operation_id=None, item_id=order.product_item_id, unit_code=order.unit_code, quantity=D(quantity),
            warehouse_id=values.pop("warehouse_id", order.org_id), lot_id=None, source_posting_id=None,
            stock_order_id=uuid4(), shipment_line_id=None)
        for key, value in values.items(): setattr(row, key, value)
        rows.append(row)
        states[row.stock_order_id] = dict(status_code=status, is_reversed=False)
        return row
    return order, operation, rows, states, movements, add


def test_receipts_and_direct_shipments_cannot_claim_the_same_output(warehouse, monkeypatch):
    order, _, _, states, _, add = warehouse
    old = add("receipt", 4, "submitted")
    new = add("receipt", 4)
    monkeypatch.setattr(delivery_repository, "direct_shipped_quantity", AsyncMock(return_value=D(3)))
    async def run():
        with pytest.raises(AppException, match="可入库数量不足"):
            await service.validate(None, new, order, exclude=new.id)
        states[old.stock_order_id]["status_code"] = "voided"
        await service.validate(None, new, order, exclude=new.id)
    asyncio.run(run())


def test_stock_shipping_uses_only_confirmed_receipts_in_selected_warehouse(warehouse):
    order, _, _, states, _, add = warehouse
    add("receipt", 5)
    add("receipt", 30, "submitted")
    add("receipt", 40, warehouse_id=uuid4())
    pending = add("shipment", 3, "approved")
    current = add("shipment", 3)
    async def run():
        assert await service.warehouse_remaining(None, order.id, current.warehouse_id, exclude=current.id) == 2
        with pytest.raises(AppException, match="可出货入库数量不足"):
            await service.validate(None, current, order, exclude=current.id)
        states[pending.stock_order_id]["is_reversed"] = True
        await service.validate(None, current, order, exclude=current.id)
    asyncio.run(run())


@pytest.mark.parametrize("state,quality,expected", [("in_progress", False, 0), ("pending", True, 0), ("completed", True, 10), ("pending", False, 10)])
def test_output_requires_ended_execution_and_required_quality(warehouse, state, quality, expected):
    order, operation, *_ = warehouse
    operation.status_code, operation.is_quality_required = state, quality
    assert asyncio.run(service.produced(None, order)) == expected


def test_returns_reserve_original_actual_batch_and_cannot_overreturn(warehouse, monkeypatch):
    order, _, _, states, movements, add = warehouse
    lot = uuid4()
    original = add("issue", 8)
    monkeypatch.setattr(module.repo, "posting", AsyncMock(return_value=original))
    movements.extend([dict(lot_id=lot, item_id=original.item_id, warehouse_id=original.warehouse_id, quantity=D(5)),
        dict(lot_id=uuid4(), item_id=original.item_id, warehouse_id=original.warehouse_id, quantity=D(3))])
    old = add("return", 3, "submitted", source_posting_id=original.id, lot_id=lot)
    current = add("return", 3, source_posting_id=original.id, lot_id=lot)
    async def run():
        with pytest.raises(AppException, match="可退数量不足"):
            await service.validate(None, current, order, exclude=current.id)
        states[old.stock_order_id]["status_code"] = "voided"
        await service.validate(None, current, order, exclude=current.id)
        current.warehouse_id = uuid4()
        with pytest.raises(AppException, match="必须与原领料一致"):
            await service.validate(None, current, order, exclude=current.id)
    asyncio.run(run())


def test_receipt_reversal_cannot_remove_shipment_backing(warehouse):
    order, _, _, states, _, add = warehouse
    receipt = add("receipt", 5)
    shipment = add("shipment", 2, "submitted")
    async def run():
        with pytest.raises(AppException, match="已被出货占用"):
            await service.validate_reversal(None, receipt, order)
        states[shipment.stock_order_id]["status_code"] = "voided"
        await service.validate_reversal(None, receipt, order)
        issue = add("issue", 3)
        add("return", 1, source_posting_id=issue.id)
        with pytest.raises(AppException, match="先冲销退料"):
            await service.validate_reversal(None, issue, order)
    asyncio.run(run())


def test_missing_inventory_state_fails_closed(warehouse):
    order, _, _, states, _, add = warehouse
    add("receipt", 5)
    states.clear()
    with pytest.raises(AppException, match="来源记录不完整"):
        asyncio.run(service.receipt_reserved(None, order.id))


def test_generic_mutation_cannot_detach_manufacturing_source(warehouse, monkeypatch):
    _, _, _, _, _, add = warehouse
    row = add("issue", 3)
    monkeypatch.setattr(module.repo, "posting", AsyncMock(return_value=row))
    monkeypatch.setattr(service, "require_access", AsyncMock())
    inv = NS(id=row.stock_order_id)
    async def run():
        for action in ("update", "delete"):
            with pytest.raises(AppException, match="由 MES 业务维护"):
                await module.mutation_guard(None, inv, None, action)
        await module.mutation_guard(None, inv, None, "approve")
        row.posting_type_code = "shipment"
        with pytest.raises(AppException, match="由 MES 业务维护"):
            await module.mutation_guard(None, inv, None, "confirm")
        with module.inventory_request(row, "cancel"):
            await module.mutation_guard(None, inv, None, "update")
        assert module._context.get() is None
    asyncio.run(run())


def test_generic_create_cannot_spoof_mes_type_or_source():
    async def run():
        for source, number in ((module.SOURCE, "PURCHASE_IN"), (None, "MES_PRODUCTION_ISSUE")):
            with pytest.raises(AppException, match="必须从来源业务创建"):
                await module.validate_write(None, NS(source_doc_type_code=source), NS(type_no=number), [], None)
        await module.validate_write(None, NS(source_doc_type_code=None), NS(type_no="PURCHASE_IN"), [], None)
    asyncio.run(run())


@pytest.mark.parametrize("approval", [False, True])
def test_creation_respects_stock_approval_and_never_commits_caller_session(warehouse, monkeypatch, approval):
    _, _, _, _, _, add = warehouse
    row = add("receipt", 2)
    row.note, row.unit_price = "入库", None
    spec = dict(id=uuid4(), direction_code="in", is_negative_allowed=False, default_to_status_code="available", is_approval_required=approval)
    monkeypatch.setattr(stock, "get_stock_order_type", AsyncMock(return_value=spec))
    create = AsyncMock(return_value=dict(id=row.stock_order_id))
    confirm = AsyncMock()
    monkeypatch.setattr(stock, "create_stock_order", create)
    monkeypatch.setattr(stock, "confirm_stock_order", confirm)
    monkeypatch.setattr(module.repo, "add", lambda *args: None)
    session = NS(flush=AsyncMock(), commit=AsyncMock())
    asyncio.run(service.create_in_session(session, row, None))
    payload = create.await_args.args[1]
    assert payload.submit is True and "business_date" not in payload.model_fields_set
    assert payload.lines[0].lot_no.startswith("MES-") and payload.lines[0].lot_id is None
    assert confirm.await_count == (0 if approval else 1)
    session.commit.assert_not_called()


def test_stock_shipment_waits_for_all_approvals_before_confirming(warehouse, monkeypatch):
    order, _, _, states, _, add = warehouse
    one, two = add("shipment", 1), add("shipment", 2, "submitted")
    one.shipment_line_id, two.shipment_line_id = uuid4(), uuid4()
    monkeypatch.setattr(module.repo, "shipment_postings", AsyncMock(return_value=[one, two]))
    confirm = AsyncMock()
    monkeypatch.setattr(stock, "confirm_stock_order", confirm)
    lines = [NS(id=row.shipment_line_id) for row in (one, two)]
    async def run():
        assert await service.finish_shipment(None, NS(id=uuid4()), lines, {order.id: order}, None) is False
        confirm.assert_not_called()
        states[two.stock_order_id]["status_code"] = "approved"
        assert await service.finish_shipment(None, NS(id=uuid4()), lines, {order.id: order}, None) is True
        assert confirm.await_args.args[1] == two.stock_order_id
        states[two.stock_order_id]["is_reversed"] = True
        with pytest.raises(AppException, match="已作废或冲销"):
            await service.finish_shipment(None, NS(id=uuid4()), lines, {order.id: order}, None)
    asyncio.run(run())


def test_public_cancel_selects_reverse_or_void_without_internal_commit(monkeypatch):
    identifier = uuid4()
    state = dict(is_reversed=False, status_code="confirmed")
    monkeypatch.setattr(stock._integration, "order_briefs", AsyncMock(return_value={identifier: state}))
    row = NS(id=identifier, status_code="confirmed", order_no="TEST")
    reverse, void = AsyncMock(return_value=row), AsyncMock(return_value=row)
    monkeypatch.setattr(stock._orders, "reverse_in_session", reverse)
    monkeypatch.setattr(stock._orders, "void_in_session", void)
    session = NS(commit=AsyncMock())
    async def run():
        await stock.cancel_stock_order(session, identifier, "撤销", None)
        reverse.assert_awaited_once(); void.assert_not_called()
        state["status_code"] = "submitted"
        await stock.cancel_stock_order(session, identifier, "撤销", None)
        void.assert_awaited_once()
        state["status_code"] = "voided"
        await stock.cancel_stock_order(session, identifier, "撤销", None)
        assert void.await_count == 1
        session.commit.assert_not_called()
    asyncio.run(run())


def test_source_guard_is_opt_in_for_ordinary_inventory(monkeypatch):
    guard = AsyncMock()
    monkeypatch.setattr(lifecycle, "_mutation_guards", {})
    lifecycle.register_source_mutation_guard("manufacturing-test", guard)
    lifecycle.register_source_mutation_guard("manufacturing-test", guard)
    async def run():
        for source in (None, "canteen_plan", "inventory_requisition"):
            await lifecycle.run_source_mutation_guards(None, NS(source_doc_type_code=source), None, "update")
        guard.assert_not_called()
        await lifecycle.run_source_mutation_guards(None, NS(source_doc_type_code="manufacturing-test"), None, "update")
        guard.assert_awaited_once()
    asyncio.run(run())


def test_confirmation_rejects_changed_warehouse_or_stock_status(warehouse, monkeypatch):
    order, _, _, _, _, add = warehouse
    row = add("receipt", 3)
    row.lot_id = uuid4()
    monkeypatch.setattr(module.repo, "posting", AsyncMock(return_value=row))
    monkeypatch.setattr(service, "require_access", AsyncMock())
    inv = NS(id=row.stock_order_id, reversal_of_order_id=None, source_doc_type_code=module.SOURCE,
        source_doc_id=order.id, org_id=order.org_id, from_warehouse_id=None, to_warehouse_id=row.warehouse_id)
    kind = NS(type_no="MES_PRODUCTION_RECEIPT", direction_code="in", is_negative_allowed=False,
        default_from_status_code=None, default_to_status_code="available")
    line = NS(item_id=row.item_id, quantity=row.quantity, unit_code=row.unit_code, lot_id=row.lot_id,
        from_warehouse_id=None, to_warehouse_id=None, from_stock_status_code=None, to_stock_status_code="available")
    async def run():
        await module.validate_confirmation(None, inv, kind, [line], None)
        line.to_warehouse_id = uuid4()
        with pytest.raises(AppException, match="偏离来源"):
            await module.validate_confirmation(None, inv, kind, [line], None)
        line.to_warehouse_id, line.to_stock_status_code = None, "quarantine"
        with pytest.raises(AppException, match="偏离来源"):
            await module.validate_confirmation(None, inv, kind, [line], None)
    asyncio.run(run())


def test_source_actions_require_business_permission_and_scope(warehouse, monkeypatch):
    *_, add = warehouse
    row = add("issue", 1)
    monkeypatch.setattr(module.repo, "posting", AsyncMock(return_value=None))
    async def run():
        with pytest.raises(AppException, match="缺少来源"):
            await service.require_access(None, row, NS(permissions=[]))
        with pytest.raises(AppException, match="超出当前业务数据范围"):
            await service.require_access(None, row, NS(permissions=["mes:inventory:manage"]))
    asyncio.run(run())


def test_consumption_counts_confirmed_issues_less_returns_and_reversals(warehouse, monkeypatch):
    order, operation, _, states, _, add = warehouse
    add("issue", 8, operation_id=operation.id)
    add("return", 2, operation_id=operation.id)
    add("issue", 40, "submitted", operation_id=operation.id)
    reversed_row = add("issue", 30, operation_id=operation.id)
    states[reversed_row.stock_order_id]["is_reversed"] = True
    add("issue", 70, operation_id=uuid4())
    requirement = NS(operation_id=operation.id, item_id=order.product_item_id, consumed_quantity=D(0))
    monkeypatch.setattr(module.repo, "requirements", AsyncMock(return_value=[requirement]))
    asyncio.run(module.refresh_consumed(None, NS(source_doc_id=order.id), None, [], NS(user_id=uuid4())))
    assert requirement.consumed_quantity == 6


@pytest.mark.parametrize("changes", [dict(quantity="0"), dict(quantity="1.0001"), dict(note=" "), dict(posting_type_code="shipment"), dict(posting_type_code="return")])
def test_invalid_commands_rejected_without_inventory_access(changes):
    values = dict(work_order_id=uuid4(), item_id=uuid4(), warehouse_id=uuid4(), posting_type_code="issue", quantity="1", note="领料", idempotency_key="test-key")
    values.update(changes)
    with pytest.raises(ValidationError): InventoryPostingBody(**values)
