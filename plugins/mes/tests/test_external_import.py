"""外部四表解析及导入事务测试：内存 SQLite，inv/L1 公开能力用受控替身。"""
from datetime import date, datetime, timezone
from decimal import Decimal
from types import SimpleNamespace as NS
from uuid import uuid4

import pytest
from openpyxl import Workbook
from sqlalchemy import Column, MetaData, Table, Uuid, JSON, select, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session

from test_quotations import store, run
from app.core.exceptions import AppException
from app.modules.mes import external_import_service as module
from app.modules.mes.external_import_service import service, item_spec, REQUIRED_PERMISSIONS
from app.modules.mes.external_import_parser import (Dataset, SourceRow, FILES, read_dataset,
    standard_minutes, route_steps, number)
from app.modules.mes.external_import_models import MesExternalImportRow
from app.modules.mes.models import (MesProductionOrder, MesWorkOrder, MesWorkOrderOperation,
    MesWorkOrderEvent, MesProcessTemplate, MesProcessTemplateOperation)
from app.modules.mes.archive_models import MesProcess, MesProjectStage
from app.modules.mes.operation_planning import configuration_plan


def source(kind, key, values, line=2):
    return SourceRow(kind, key, f"{kind}.xlsx", "a" * 64, "Sheet1", line, values)


def dataset():
    return Dataset({
        "route_step": [source("route_step", "PART-1::1", {"工艺路线名称": "PART-1", "工艺": "CNC", "加工类型": "自制", "项目阶段": "加工", "标准工时": "0.5", "标准工时单位": "小时"}),
            source("route_step", "PART-1::2", {"工艺路线名称": "PART-1", "工艺": "QA", "加工类型": "品检", "项目阶段": "质检", "标准工时": "0", "标准工时单位": "分"}, 3)],
        "production_order": [source("production_order", "PO1", {"工单号": "PO1", "项目名称": "项目1", "货品款数": 2, "工单状态": "已下单"}),
            source("production_order", "PO2", {"工单号": "PO2", "项目名称": "项目2", "货品款数": 1, "工单状态": "已完工"}, 3)],
        "work_order": [source("work_order", "PO1-1", {"工单号": "PO1", "货品编码": "PO1-1", "货品名称": "PART-1", "货品类型": "采购", "货品材料": "AL6061", "热处理": "T6", "表面处理": "阳极氧化", "单位": "pcs", "数量": 5, "货品状态": "已下单", "工艺路线": "CNC【已完工】 >> QA【待生产】"})],
        "stock_balance": [source("stock_balance", "stock1", {"货品编码": "钢刀", "货品名称": "钢刀", "规格型号": "D10", "单位": "pcs", "实际库存": 3, "占用数": 0, "可用数": 3}),
            source("stock_balance", "stock2", {"货品编码": "钢刀", "货品名称": "钢刀", "规格型号": "D12", "单位": "支", "实际库存": 4, "占用数": 0, "可用数": 4}, 3)],
    })


@pytest.fixture
def imported(store, monkeypatch):
    models = (MesProductionOrder, MesWorkOrder, MesWorkOrderOperation, MesWorkOrderEvent,
        MesProcessTemplate, MesProcessTemplateOperation, MesProcess, MesProjectStage, MesExternalImportRow)
    metadata = MetaData()
    names = {model.__tablename__ for model in models}
    external = {fk.target_fullname.rsplit(".", 1)[0] for model in models for fk in model.__table__.foreign_keys} - names
    for name in external: Table(name, metadata, Column("id", Uuid, primary_key=True))
    for model in models:
        table = model.__table__.to_metadata(metadata)
        for column in table.columns:
            column.server_default = None
            if isinstance(column.type, JSONB): column.type = JSON()
        for index in table.indexes:
            where = index.dialect_options["postgresql"].get("where")
            if where is not None: index.dialect_options["sqlite"]["where"] = where
    metadata.create_all(store.engine)
    permissions = list({*store.user.permissions, *REQUIRED_PERMISSIONS})
    store.actor = NS(**{**vars(store.user), "permissions": permissions, "permission_scopes": {key: "organization" for key in permissions}})
    async def noop(*args, **kwargs): return None
    async def ready(*args): return []
    monkeypatch.setattr(module.repo, "lock", noop)
    monkeypatch.setattr(module.repo, "missing_columns", ready)
    monkeypatch.setattr(module, "ensure_builtin_definitions", noop)
    async def units(*args): return {"md_unit": [{"item_code": "piece"}, {"item_code": "branch"}]}
    monkeypatch.setattr(module.dictionaries, "options_in_session", units)
    store.catalogue, store.openings = {}, []
    async def ensure(session, **values):
        code = values["item_no"]
        if code not in store.catalogue:
            item = NS(id=uuid4(), item_no=code, item_name=values["item_name"], specification=values["specification"], unit_code=values["unit_code"])
            session.session.execute(metadata.tables["md_item"].insert().values(id=item.id))
            store.catalogue[code] = item
        return store.catalogue[code]
    monkeypatch.setattr(module.inventory, "ensure_active_item", ensure)
    store.warehouse = None
    async def warehouses(*args): return [store.warehouse] if store.warehouse else []
    monkeypatch.setattr(module.inventory, "list_configured_warehouses", warehouses)
    warehouse_id = uuid4()
    async def warehouse(*args, **kwargs):
        store.warehouse = {"id": warehouse_id, "org_id": store.actor.org_id, "warehouse_no": module.WAREHOUSE_NO, "is_active": True}
        return store.warehouse
    monkeypatch.setattr(module.inventory, "configure_warehouse", warehouse)
    store.zero_positions = []
    async def zero_positions(session, warehouse_id, item_ids, user, **kwargs):
        store.zero_positions.extend(item_ids)
        return len(item_ids)
    monkeypatch.setattr(module.inventory, "ensure_zero_stock_positions", zero_positions)
    monkeypatch.setattr(module.inventory, "ensure_stock_order_types", noop)
    async def order_type(*args): return {"id": uuid4(), "direction_code": "in", "is_approval_required": False, "is_negative_allowed": False}
    monkeypatch.setattr(module.inventory, "get_stock_order_type", order_type)
    async def opening(session, body, user):
        store.openings.append(body)
        identifier = uuid4()
        session.session.execute(metadata.tables["inv_stock_order"].insert().values(id=identifier))
        return {"id": identifier, "status_code": "confirmed"}
    monkeypatch.setattr(module.inventory, "create_stock_order", opening)
    return store


async def apply(store, data):
    async with store.sessions() as session:
        result = await service.apply(session, data, store.actor, store.actor.org_id, opening_date=date(2026, 10, 29))
        await session.commit()
        return result


def test_import_preserves_partial_projects_variants_purchase_type_and_real_opening_contract(imported):
    data = dataset()
    assert data.summary()["incomplete_projects"] == 2
    result = run(apply(imported, data))
    assert result["written"] == 7 and result["new_items"] == 3
    assert len(imported.openings) == 1
    opening = imported.openings[0]
    assert opening.confirm and opening.business_date == date(2026, 10, 29)
    assert {line.unit_code: line.quantity for line in opening.lines} == {"piece": 3, "branch": 4}
    with Session(imported.engine) as session:
        projects = session.scalars(select(MesProductionOrder)).all()
        assert len(projects) == 2 and all(row.is_import_incomplete for row in projects)
        work = session.scalar(select(MesWorkOrder))
        assert work.processing_type_code == "purchased" and work.material_name_snapshot == "AL6061"
        assert work.surface_treatment_snapshot == "阳极氧化"
        operations = session.scalars(select(MesWorkOrderOperation).order_by(MesWorkOrderOperation.sequence_no)).all()
        assert [row.status_code for row in operations] == ["completed", "pending"]
        assert operations[0].standard_minutes_per_unit == 30
        assert operations[0].good_quantity == 0  # 不根据状态伪造报工数量。
        assert all(row.is_imported_snapshot for row in operations)
        assert all(plan["planned_start_at"] is None for plan in configuration_plan(operations).values())
        assert session.scalar(select(func.count()).select_from(MesExternalImportRow)) == 7
    assert run(apply(imported, data))["written"] == 0
    assert len(imported.openings) == 1


def test_changed_source_does_not_overwrite_or_add_stock(imported):
    data = dataset()
    run(apply(imported, data))
    data.rows["stock_balance"][0].values["实际库存"] = 99
    with pytest.raises(AppException, match="发生变化"): run(apply(imported, data))
    assert len(imported.openings) == 1


def test_zero_inventory_is_visible_without_zero_quantity_transactions(imported):
    data = dataset()
    data.rows["stock_balance"][1].values.update({"实际库存": 0, "可用数": 0})
    run(apply(imported, data))
    assert len(imported.openings[0].lines) == 1
    assert len(set(imported.zero_positions)) == 1
    with Session(imported.engine) as session:
        zero = session.scalar(select(MesExternalImportRow).where(MesExternalImportRow.source_record_no == "stock2"))
        assert zero.item_id is not None and zero.stock_order_id is None
    assert run(apply(imported, data))["written"] == 0
    assert len(imported.openings) == 1


def test_stock_failure_rolls_back_mes_and_sources(imported, monkeypatch):
    async def fail(*args): raise RuntimeError("stock unavailable")
    monkeypatch.setattr(module.inventory, "create_stock_order", fail)
    with pytest.raises(RuntimeError): run(apply(imported, dataset()))
    with Session(imported.engine) as session:
        for model in (MesProductionOrder, MesWorkOrder, MesProcessTemplate, MesExternalImportRow):
            assert session.scalar(select(func.count()).select_from(model)) == 0


def test_import_respects_actual_permission_and_org_scope(imported):
    imported.actor.permissions.remove("inventory_inbound:list")
    with pytest.raises(AppException, match="导入需要权限"): run(apply(imported, dataset()))
    imported.actor.permissions.append("inventory_inbound:list")
    imported.actor.org_id = imported.foreign_org
    with pytest.raises(AppException):
        service.authorize(imported.actor, imported.user.org_id)


@pytest.mark.parametrize("value,unit,expected", [("90", "分", "90"), ("0.5", "小时", "30"), ("2", "天", "2880"), ("0", "分", None)])
def test_time_conversion(value, unit, expected):
    result = standard_minutes({"标准工时": value, "标准工时单位": unit})
    assert result == (Decimal(expected) if expected is not None else None)


def test_no_unknown_states_or_negative_values_are_invented():
    with pytest.raises(ValueError): route_steps("CNC【未知】")
    with pytest.raises(ValueError): number("NaN")
    with pytest.raises(ValueError): number("-1")
    first, second = dataset().rows["stock_balance"]
    assert item_spec(first, "stock_balance")[0] != item_spec(second, "stock_balance")[0]


def write_sources(directory, data):
    for kind, pattern in FILES.items():
        rows = data.rows[kind]
        headers = list(dict.fromkeys(["序号", *(key for row in rows for key in row.values)]))
        book = Workbook()
        sheet = book.active
        sheet.append(headers)
        for index, row in enumerate(rows, 1): sheet.append([index, *(row.values.get(key) for key in headers[1:])])
        book.save(directory / pattern.replace("*", "test"))


def test_workbook_parser_and_source_link_validation(tmp_path):
    data = dataset()
    write_sources(tmp_path, data)
    result = read_dataset(tmp_path)
    assert result.summary()["routes"] == 1
    assert len(result.rows["work_order"]) == 1
    assert result.rows["route_step"][1].line == 3
    data.rows["work_order"][0].values["工单号"] = "MISSING"
    write_sources(tmp_path, data)
    with pytest.raises(ValueError, match="未导出"): read_dataset(tmp_path)


def test_duplicate_source_item_spec_is_rejected_not_silently_combined(tmp_path):
    data = dataset()
    data.rows["stock_balance"][1].values.update({"规格型号": "D10", "单位": "pcs"})
    write_sources(tmp_path, data)
    with pytest.raises(ValueError, match="重复"): read_dataset(tmp_path)
