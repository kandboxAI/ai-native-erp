"""制造档案与采购价的持久化/范围回归；只使用内存 SQLite，不连接业务库。"""
import asyncio
from contextlib import asynccontextmanager
from datetime import date
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine, MetaData, Table, Column, Uuid, JSON, event, select, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session
from app.auth.schemas import AuthenticatedUser
from app.core.exceptions import AppException
from app.modules.mes import archive_service as module, archive_binding as binding
from app.modules.mes.archive_models import MesCustomer, MesProjectStage, MesProcess, MesEquipment, MesProcessRequirement, MesProcessDependency, MesEquipmentProcess
from app.modules.mes.archive_service import archive_service as service, validate_graph, ARCHIVES
from app.modules.mes.archive_schemas import ArchiveQuery, ProcessBody
from app.modules.mes.schemas import WorkOrderOperationCreate
from app.modules.inventory_pricing import service as prices
from app.modules.inventory_pricing.models import InvSupplierPrice
from app.modules.inventory_pricing.schemas import PriceBody


@pytest.fixture
def store(monkeypatch):
    from app.framework.db.registry import import_all_models
    import_all_models()
    engine = create_engine("sqlite:///:memory:")
    @event.listens_for(engine, "connect")
    def foreign_keys(connection, _): connection.execute("PRAGMA foreign_keys=ON")
    metadata = MetaData()
    for name in ("sys_org", "sys_user", "md_item", "md_supplier"):
        Table(name, metadata, Column("id", Uuid, primary_key=True))
    models = (MesCustomer, MesProjectStage, MesProcessRequirement, MesProcess, MesEquipment, MesProcessDependency, MesEquipmentProcess, InvSupplierPrice)
    for model in models:
        table = model.__table__.to_metadata(metadata)
        for column in table.columns:
            column.server_default = None
            if isinstance(column.type, JSONB): column.type = JSON()
    metadata.create_all(engine)
    org, other_org, user_id, supplier_id, item_id = (uuid4() for _ in range(5))
    permissions = [f"mes:archive:{resource}:{action}" for resource in ("customer", "stage", "process", "equipment", "requirement") for action in ("list", "manage")]
    permissions += ["inventory_supplier_price:manage", "inventory_supplier_price:list", "mes:work_order:create"]
    actor = AuthenticatedUser(auth_user_id=uuid4(), tenant_id=uuid4(), tenant_no="test", tenant_schema="t_test", user_id=user_id,
        org_id=org, org_access_mode_code="all", permissions=permissions, permission_scopes={key: "all" for key in permissions})
    with engine.begin() as connection:
        for name, ids in (("sys_org", [org, other_org]), ("sys_user", [user_id]), ("md_item", [item_id]), ("md_supplier", [supplier_id])):
            for identifier in ids: connection.execute(metadata.tables[name].insert().values(id=identifier))
    class Adapter:
        def __init__(self, session): self.session = session
        async def execute(self, statement): return self.session.execute(statement)
        async def flush(self): self.session.flush()
        async def commit(self): self.session.commit()
        def add(self, row): self.session.add(row)
    @asynccontextmanager
    async def sessions():
        with Session(engine, expire_on_commit=False) as session:
            try: yield Adapter(session)
            except BaseException:
                session.rollback()
                raise
    monkeypatch.setattr(module, "get_session_context", sessions)
    monkeypatch.setattr(prices, "get_session_context", sessions)
    monkeypatch.setattr(module.repo, "lock_organization", AsyncMock())
    monkeypatch.setattr(prices.repo, "lock", AsyncMock())
    monkeypatch.setattr(prices.repo, "references", AsyncMock(return_value=(True, NS(unit_code="piece"), True)))
    return NS(actor=actor, org=org, other_org=other_org, engine=engine, sessions=sessions, supplier_id=supplier_id, item_id=item_id)


def body(store, **changes):
    return dict(org_id=store.org, record_no="A-01", record_name="档案一", **changes)


def test_equipment_multiple_processes_save_edit_and_selection(store):
    async def run():
        first = await service.save("processes", body(store), store.actor)
        second = await service.save("processes", {**body(store), "record_no": "P2"}, store.actor)
        machine = await service.save("equipment", {**body(store), "process_ids": [first["id"], second["id"]]}, store.actor)
        assert machine["process_id"] is None and set(machine["process_ids"]) == {first["id"], second["id"]}
        assert len(machine["process_labels"]) == 2
        options = await service.options("equipment", ArchiveQuery(org_id=store.org, applicable_process_id=second["id"]), store.actor)
        assert options["total"] == 1 and len(options["items"][0]["process_ids"]) == 2
        changed = await service.save("equipment", {**body(store), "version_no": machine["version_no"], "process_ids": [second["id"]]}, store.actor, machine["id"])
        assert changed["version_no"] == 2 and changed["process_id"] == second["id"]
        assert changed["process_ids"] == [second["id"]]
    asyncio.run(run())


def test_archive_save_version_organization_and_disabled_selection(store):
    async def run():
        created = await service.save("customers", body(store), store.actor)
        updated = await service.save("customers", {**body(store), "record_name": "新简称", "version_no": created["version_no"], "is_active": False}, store.actor, created["id"])
        assert updated["version_no"] == 2 and not updated["is_active"]
        with pytest.raises(AppException, match="已更新"):
            await service.save("customers", {**body(store), "version_no": 1}, store.actor, created["id"])
        with pytest.raises(AppException, match="不能变更"):
            await service.save("customers", {**body(store), "record_no": "CHANGED", "version_no": 2}, store.actor, created["id"])
        selected = await service.options("customers", ArchiveQuery(org_id=store.org), store.actor)
        assert selected["items"] == []
        async with store.sessions() as session:
            with pytest.raises(AppException, match="已停用"):
                await binding.customer_snapshot(session, NS(customer_id=created["id"]), store.org)
    asyncio.run(run())


def test_archive_cross_organization_links_and_cycles_rollback(store):
    async def run():
        foreign = await service.save("project-stages", {**body(store), "org_id": store.other_org}, store.actor)
        with pytest.raises(AppException, match="不属于当前组织"):
            await service.save("processes", {**body(store), "project_stage_id": foreign["id"]}, store.actor)
        first = await service.save("processes", body(store), store.actor)
        second = await service.save("processes", {**body(store), "record_no": "B-02", "previous_process_ids": [first["id"]]}, store.actor)
        with pytest.raises(AppException, match="形成循环"):
            await service.save("processes", {**body(store), "version_no": 1, "previous_process_ids": [second["id"]]}, store.actor, first["id"])
        with Session(store.engine) as session:
            assert session.scalar(select(func.count()).select_from(MesProcess)) == 2
            assert session.scalar(select(func.count()).select_from(MesProcessDependency)) == 1
    asyncio.run(run())


def test_archives_require_own_permission_and_options_do_not_publish_customer_notes(store):
    async def run():
        await service.save("customers", body(store, description="内部说明"), store.actor)
        store.actor.permissions = ["mes:work_order:create"]
        result = await service.options("customers", ArchiveQuery(org_id=store.org), store.actor)
        assert len(result["items"]) == 1 and "description" not in result["items"][0]
        assert not {"created_by", "updated_by", "pricing_description"} & result["items"][0].keys()
        with pytest.raises(AppException, match="缺少"):
            await service.page("customers", ArchiveQuery(), store.actor)
        with pytest.raises(AppException, match="缺少"):
            await service.save("customers", body(store), store.actor)
        store.actor.permissions = ["mes:archive:process:manage"]
        with pytest.raises(AppException, match="选用权限"):
            await service.options("customers", ArchiveQuery(org_id=store.org), store.actor)
    asyncio.run(run())


def test_operation_binding_snapshots_requirements_equipment_and_precedence(store):
    async def run():
        stage = await service.save("project-stages", body(store), store.actor)
        requirement = await service.save("requirements", body(store, description="边缘去毛刺"), store.actor)
        process = await service.save("processes", {**body(store), "record_name": "CNC", "project_stage_id": stage["id"], "requirement_id": requirement["id"], "is_quality_required": True}, store.actor)
        equipment = await service.save("equipment", {**body(store), "process_id": process["id"], "work_center_name": "车间一"}, store.actor)
        op = WorkOrderOperationCreate(operation_no="10", operation_name="客户端名称", process_id=process["id"], equipment_id=equipment["id"])
        async with store.sessions() as session:
            snapshot = (await binding.prepare_operations(session, [op], store.org))[0]
            assert op.operation_name == "CNC" and op.workstation_name == equipment["record_no"]
            assert op.is_quality_required and "边缘去毛刺" in op.operation_description
            assert snapshot["project_stage_id"] == stage["id"] and snapshot["requirement_id"] == requirement["id"]
        old = NS(operation_no="10", operation_name_snapshot=op.operation_name, operation_description=op.operation_description,
            work_center_name_snapshot=op.work_center_name, workstation_name_snapshot=op.workstation_name, is_quality_required=True, **snapshot)
        # 后续编辑使用服务端返回的工单定义，其中包含当时自动选用的默认要求 ID。
        op.requirement_id = snapshot["requirement_id"]
        await service.save("processes", {**body(store), "record_name": "修改后的工艺", "is_active": False, "version_no": 1}, store.actor, process["id"])
        async with store.sessions() as session:
            assert await binding.prepare_operations(session, [op], store.org, [old]) == [snapshot]
            assert op.operation_name == "CNC"
            with pytest.raises(AppException, match="已停用"):
                await binding.prepare_operations(session, [op], store.org)
        await service.save("processes", {**body(store), "version_no": 2}, store.actor, process["id"])
        second = await service.save("processes", {**body(store), "record_no": "B-02", "previous_process_ids": [process["id"]]}, store.actor)
        later = WorkOrderOperationCreate(operation_no="20", operation_name="后工艺", process_id=second["id"])
        async with store.sessions() as session:
            with pytest.raises(AppException, match="缺少前置工艺"):
                await binding.prepare_operations(session, [later], store.org)
    asyncio.run(run())


def test_equipment_cannot_be_bound_to_another_process(store):
    async def run():
        first = await service.save("processes", body(store), store.actor)
        second = await service.save("processes", {**body(store), "record_no": "B-02"}, store.actor)
        equipment = await service.save("equipment", {**body(store), "process_id": first["id"]}, store.actor)
        op = WorkOrderOperationCreate(operation_no="10", operation_name="工序", process_id=second["id"], equipment_id=equipment["id"])
        async with store.sessions() as session:
            with pytest.raises(AppException, match="所属工艺"):
                await binding.prepare_operations(session, [op], store.org)
    asyncio.run(run())


def test_process_prerequisites_explain_missing_and_wrong_order_and_allow_valid_route(store):
    async def run():
        cutting = await service.save("processes", {**body(store), "record_name": "下料"}, store.actor)
        milling = await service.save("processes", {**body(store), "record_no": "CNC-01", "record_name": "CNC 铣削",
            "previous_process_ids": [cutting["id"]]}, store.actor)
        def op(identifier, number):
            return WorkOrderOperationCreate(operation_no=number, operation_name="选用工艺", process_id=identifier)
        async with store.sessions() as session:
            with pytest.raises(AppException) as error:
                await binding.prepare_operations(session, [op(milling["id"], "20")], store.org)
            assert error.value.status_code == 409
            assert "工序 20（CNC 铣削）" in str(error.value) and "缺少前置工艺“A-01 · 下料”" in str(error.value)
            with pytest.raises(AppException, match="移到本工序之前"):
                await binding.prepare_operations(session, [op(milling["id"], "20"), op(cutting["id"], "10")], store.org)
            result = await binding.prepare_operations(session, [op(cutting["id"], "10"), op(milling["id"], "20")], store.org)
            assert [row["process_id"] for row in result] == [cutting["id"], milling["id"]]
        options = await service.options("processes", ArchiveQuery(org_id=store.org), store.actor)
        selected = next(row for row in options["items"] if row["id"] == milling["id"])
        assert selected["previous_process_ids"] == [cutting["id"]]
        assert selected["previous_process_names"] == "A-01 · 下料"
    asyncio.run(run())


def price(store, **changes):
    return PriceBody(**{**dict(org_id=store.org, supplier_id=store.supplier_id, item_id=store.item_id, unit_price="12.34",
        valid_from="2026-01-01", valid_to="2026-02-01"), **changes})


def test_price_period_overlap_adjacent_dates_and_reactivation(store):
    async def run():
        first = await prices.price_service.save(price(store), store.actor)
        await prices.price_service.save(price(store, valid_from="2026-02-01", valid_to=None), store.actor)
        with pytest.raises(AppException, match="重叠有效期"):
            await prices.price_service.save(price(store, valid_from="2026-01-15", valid_to="2026-03-01"), store.actor)
        inactive = await prices.price_service.save(price(store, is_active=False), store.actor)
        with pytest.raises(AppException, match="重叠有效期"):
            await prices.price_service.save(price(store, version_no=1), store.actor, inactive["id"])
        assert first["unit_code"] == "piece" and first["unit_price"] == "12.34"
        with Session(store.engine) as session:
            assert session.scalar(select(func.count()).select_from(InvSupplierPrice)) == 3
    asyncio.run(run())


def test_price_stale_version_and_retired_source_can_be_deactivated(store, monkeypatch):
    async def run():
        first = await prices.price_service.save(price(store), store.actor)
        monkeypatch.setattr(prices.repo, "references", AsyncMock(return_value=(False, None, False)))
        inactive = await prices.price_service.save(price(store, is_active=False, version_no=1), store.actor, first["id"])
        assert not inactive["is_active"]
        prices.repo.references.assert_not_awaited()
        with pytest.raises(AppException, match="已更新"):
            await prices.price_service.save(price(store, version_no=1), store.actor, first["id"])
    asyncio.run(run())


@pytest.mark.parametrize("changes", [{"unit_price": "NaN"}, {"unit_price": "0.001"}, {"unit_price": "-1"}, {"valid_to": "2025-12-31"}])
def test_price_rejects_invalid_amount_and_period(store, changes):
    with pytest.raises(ValidationError): price(store, **changes)


def test_self_scope_filters_archive_rows(store):
    async def run():
        created = await service.save("customers", body(store), store.actor)
        store.actor.permission_scopes["mes:archive:customer:list"] = "self"
        store.actor.user_id = uuid4()
        page = await service.page("customers", ArchiveQuery(), store.actor)
        assert page["total"] == 0
        store.actor.permission_scopes["mes:archive:customer:list"] = "related"
        assert (await service.page("customers", ArchiveQuery(), store.actor))["total"] == 0
    asyncio.run(run())


def test_new_archives_and_prices_are_not_automatically_published_as_ai_tools():
    from app.integrations.harness_api_policy import http_registry
    registry = http_registry()
    assert registry.resolve("GET", "/api/inventory_supplier_price") is None
    assert registry.resolve("POST", "/api/inventory_supplier_price") is None
    assert registry.resolve("GET", "/api/mes/archives/customers") is None


def test_scheduling_equipment_options_filter_compatible_devices_before_pagination(store):
    async def run():
        first = await service.save("processes", body(store), store.actor)
        second = await service.save("processes", {**body(store), "record_no": "P2"}, store.actor)
        with Session(store.engine) as session:
            rows = [MesEquipment(org_id=store.org, equipment_no=f"A-{index:03}", equipment_name="其他工艺", process_id=second["id"]) for index in range(55)]
            rows += [MesEquipment(org_id=store.org, equipment_no="Y-GENERIC", equipment_name="通用设备"),
                MesEquipment(org_id=store.org, equipment_no="Z-MATCH", equipment_name="适用设备", process_id=first["id"]),
                MesEquipment(org_id=store.org, equipment_no="X-INACTIVE", equipment_name="停用设备", process_id=first["id"], is_active=False),
                MesEquipment(org_id=store.other_org, equipment_no="X-FOREIGN", equipment_name="其他组织", process_id=first["id"])]
            session.add_all(rows); session.commit()
        store.actor.permissions = ["mes:schedule:manage"]
        store.actor.permission_scopes = {"mes:schedule:manage": "all"}
        selected = await service.options("equipment", ArchiveQuery(org_id=store.org, applicable_process_id=first["id"], page_size=1, page=2), store.actor)
        assert selected["total"] == 2 and selected["items"][0]["record_no"] == "Z-MATCH"
        assert "description" not in selected["items"][0]
        generic = await service.options("equipment", ArchiveQuery(org_id=store.org, generic_equipment_only=True), store.actor)
        assert generic["total"] == 1 and generic["items"][0]["record_no"] == "Y-GENERIC"
    asyncio.run(run())
