"""真实订单/生产事务的内存 SQLite 验证；文件与 inv 公共读取用替身，无外部调用。"""
from datetime import date
from decimal import Decimal
from io import BytesIO
from types import SimpleNamespace as NS
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Column, MetaData, Table, Uuid, JSON, select, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session
from openpyxl import load_workbook
from pydantic import ValidationError

from test_quotations import store, run, submit, price, approval, final_approval, service as quote_service
from app.core.exceptions import AppException
from app.modules.mes import sales_order_service as module, service as production_module
from app.modules.mes.sales_order_service import service
from app.modules.mes.sales_order_schemas import SalesOrderBody, SalesReleaseBody, SalesOrderQuery, SalesOrderApproval, SalesOrderCommand, SalesOrderEdit
from app.modules.mes.sales_order_models import MesSalesOrder, MesSalesOrderLine, MesSalesProduction, MesSalesAllocation, MesSalesOrderEvent
from app.modules.mes.quotation_models import MesQuotation, MesQuotationLine, MesQuotationPriceTier, MesQuotationCnc
from app.modules.mes.cnc.models import CncQuote
from app.modules.mes.quotation_production import production_operations
from app.modules.mes.operation_planning import configuration_plan
from app.modules.mes.sales_pricing import discounted_price
from app.modules.mes.quotation_schemas import QuotationCommand, EngineeringBody
from app.modules.mes.quotation_exports import workbook
from app.modules.mes.models import MesProductionOrder, MesWorkOrder, MesWorkOrderOperation, MesWorkOrderEvent, MesExecutionEvent
from app.modules.mes.archive_models import MesProcess, MesProcessDependency, MesProjectStage, MesEquipmentProcess
from app.modules.mes.archive_repository import archive_repository


@pytest.fixture
def sales(store, monkeypatch):
    models = (MesSalesOrder, MesSalesOrderLine, MesSalesProduction, MesSalesAllocation, MesSalesOrderEvent,
        MesProductionOrder, MesWorkOrder, MesWorkOrderOperation, MesWorkOrderEvent, MesExecutionEvent, CncQuote,
        MesProcess, MesProcessDependency, MesProjectStage, MesEquipmentProcess)
    metadata = MetaData()
    names = {m.__tablename__ for m in models}
    external = {fk.target_fullname.rsplit(".", 1)[0] for model in models for fk in model.__table__.foreign_keys} - names
    for name in external:
        Table(name, metadata, Column("id", Uuid, primary_key=True))
    for model in models:
        table = model.__table__.to_metadata(metadata)
        for column in table.columns:
            column.server_default = None
            if isinstance(column.type, JSONB): column.type = JSON()
        for index in table.indexes:
            where = index.dialect_options["postgresql"].get("where")
            if where is not None: index.dialect_options["sqlite"]["where"] = where
    # 报价 fixture 只建了外部核价快照的 id 占位；本组验证真实工艺快照读取。
    metadata.tables["mes_cnc_quote"].drop(store.engine)
    for name in ("mes_process", "mes_project_stage"):
        metadata.tables[name].drop(store.engine, checkfirst=True)
    metadata.create_all(store.engine)
    permissions = [*store.user.permissions, "mes:sales_order:list", "mes:sales_order:manage", "mes:sales_order:release", "mes:work_order:create", "mes:work_order:list"]
    store.actor = NS(**{**vars(store.user), "display_name": "生产安排人员", "permissions": permissions, "permission_scopes": {p: "organization" for p in permissions}})
    review_permissions = ["mes:sales_order:list", "mes:sales_order:approve"]
    store.order_reviewer = NS(**{**vars(store.actor), "user_id": store.reviewer.user_id,
        "permissions": review_permissions, "permission_scopes": {p: "organization" for p in review_permissions}})
    monkeypatch.setattr(module, "get_session_context", store.sessions)
    async def archive_lock(*args): pass
    monkeypatch.setattr(archive_repository, "lock_organization", archive_lock)
    # Adapter is the same transaction as quotation tests; core repositories use exec too.
    async def production_create(session, body, actor, **kwargs):
        async def execute(statement): return session.session.execute(statement)
        session.exec = execute
        return await real_create(session, body, actor, **kwargs)
    real_create = module.production.create_production_in_session
    monkeypatch.setattr(module.production, "create_production_in_session", production_create)
    item_id = uuid4()
    with store.engine.begin() as connection:
        connection.execute(metadata.tables["md_item"].insert().values(id=item_id))
    store.catalogue = {item_id: NS(id=item_id, item_no="CNC-001", item_name="连接板", unit_code="piece")}
    async def item(session, identifier):
        return store.catalogue.get(identifier)
    monkeypatch.setattr(module, "get_active_item", item)
    monkeypatch.setattr(production_module, "get_active_item", item)
    async def find(session, numbers):
        keys = {number.lower() for number in numbers}
        return [vars(value) for value in store.catalogue.values() if value.item_no.lower() in keys]
    monkeypatch.setattr(module, "find_active_items_by_numbers", find)
    async def units(codes):
        return {"md_unit": [{"item_code": "piece", "item_name": "件"}, {"item_code": "kg", "item_name": "千克"}]}
    monkeypatch.setattr(module.dictionary_service, "options", units)
    store.created_items = []
    async def ensure(session, *, item_no, item_name, unit_code, specification, user):
        previous = next((row for row in store.catalogue.values() if row.item_no == item_no), None)
        if previous:
            return previous
        if "inventory_product:create" not in user.permissions:
            raise AppException("需要新增物料权限", 403)
        row = NS(id=uuid4(), item_no=item_no, item_name=item_name, unit_code=unit_code)
        session.session.execute(metadata.tables["md_item"].insert().values(id=row.id))
        store.catalogue[row.id] = row
        store.created_items.append(row)
        return row
    monkeypatch.setattr(module, "ensure_active_item", ensure)
    async def customer(session, body, org_id): return "C01", "客户代号"
    monkeypatch.setattr(production_module, "customer_snapshot", customer)
    store.copied = []
    async def read(session, identifier, *, user): return NS(original_file_name="P1.pdf", content_type="application/pdf"), b"%PDF-test"
    async def upload(**kwargs):
        store.copied.append(kwargs)
        return {"id": str(uuid4())}
    async def bind(session, work, body, actor):
        assert body.drawing_attachment_ids and body.drawing_attachment_ids[0] != store.attachment_id
        work.drawing_revision_label = body.drawing_revision_label
    monkeypatch.setattr(module.files, "read_content", read)
    monkeypatch.setattr(module.files, "upload_bytes", upload)
    monkeypatch.setattr(production_module, "bind_product_drawings", bind)
    store.item_id = item_id
    return store


def approved(store):
    quote = price(store, submit(store))
    quote = run(quote_service.command(quote["id"], "finish", QuotationCommand(version_no=quote["version_no"]), store.user))
    first_review = run(quote_service.approve(quote["id"], approval(quote), store.reviewer))
    return final_approval(first_review, store.reviewer)


def body(quote, **changes):
    line = dict(quotation_line_id=quote["lines"][0]["id"], quotation_version_no=quote["version_no"],
        quantity="10", unit_price="12.80", due_date="2026-12-01", **changes)
    return SalesOrderBody(idempotency_key=str(uuid4()), lines=[line])


def release_body(order, sales, quantity="5", **changes):
    return SalesReleaseBody(version_no=order["version_no"], idempotency_key=str(uuid4()), is_unit_confirmed=True,
        lines=[dict(order_line_id=order["lines"][0]["id"], quantity=quantity, product_item_id=sales.item_id)], **changes)


def approve_order(order, sales):
    return run(service.approve(order["id"], SalesOrderApproval(version_no=order["version_no"]), sales.order_reviewer))


def test_customer_order_requires_scoped_review_before_any_production(sales):
    order = run(service.create(body(approved(sales)), sales.actor))
    assert order["status_code"] == "confirmed"
    with pytest.raises(AppException, match="先审核"):
        run(service.release(order["id"], release_body(order, sales), sales.actor))
    with pytest.raises(AppException, match="先审核"):
        run(service.production_defaults(order["id"], sales.actor))
    assert not sales.copied
    with Session(sales.engine) as session:
        assert session.scalar(select(func.count()).select_from(MesProductionOrder)) == 0

    command = SalesOrderApproval(version_no=order["version_no"])
    with pytest.raises(AppException, match="权限"):
        run(service.approve(order["id"], command, sales.actor))
    restricted = NS(**{**vars(sales.order_reviewer), "permission_scopes": {
        **sales.order_reviewer.permission_scopes, "mes:sales_order:approve": "self"}})
    with pytest.raises(AppException, match="无权"):
        run(service.approve(order["id"], command, restricted))
    with pytest.raises(AppException, match="版本"):
        run(service.approve(order["id"], SalesOrderApproval(version_no=command.version_no + 1), sales.order_reviewer))

    reviewed = approve_order(order, sales)
    assert reviewed["status_code"] == "approved"
    assert reviewed["version_no"] == order["version_no"] + 1
    assert reviewed["events"][0]["action_key"] == "approve"
    assert reviewed["events"][0]["created_by"] == str(sales.order_reviewer.user_id)
    assert run(service.page(sales.actor, SalesOrderQuery(status_code="approved")))["total"] == 1
    with pytest.raises(AppException, match="版本"):
        run(service.approve(order["id"], command, sales.order_reviewer))
    assert len(run(service.release(order["id"], release_body(reviewed, sales), sales.actor))["productions"]) == 1


def test_existing_batch_remains_readable_but_new_batch_requires_review(sales):
    order = approve_order(run(service.create(body(approved(sales)), sales.actor)), sales)
    command = release_body(order, sales)
    first = run(service.release(order["id"], command, sales.actor))
    with Session(sales.engine) as session:
        # Reproduce the status used by releases made before customer order review.
        session.get(MesSalesOrder, UUID(order["id"])).status_code = "confirmed"
        session.commit()
    with pytest.raises(AppException, match="先审核"):
        run(service.release(order["id"], release_body(first, sales), sales.actor))
    retried = run(service.release(order["id"], command, sales.actor))
    assert [batch["id"] for batch in retried["productions"]] == [batch["id"] for batch in first["productions"]]
    reviewed = approve_order(run(service.detail(order["id"], sales.actor)), sales)
    assert len(run(service.release(order["id"], release_body(reviewed, sales), sales.actor))["productions"]) == 2


def test_approved_quote_creates_durable_order_with_original_price_and_idempotency(sales):
    quote = approved(sales)
    command = body(quote)
    order = run(service.create(command, sales.actor))
    assert order["amount"] == "128.00" and order["line_count"] == 1
    assert order["lines"][0]["original_unit_price_snapshot"] == "12.80"
    assert run(service.create(command, sales.actor))["id"] == order["id"]
    assert run(service.detail(order["id"], sales.actor))["lines"][0]["quotation_line_id"] == quote["lines"][0]["id"]
    assert run(service.page(sales.actor, SalesOrderQuery()))["total"] == 1


def test_void_approved_quote_retains_audit_and_closes_order_source(sales):
    quote = approved(sales)
    quote_id = quote["id"]
    with pytest.raises(AppException, match="请填写作废原因"):
        run(quote_service.command(quote_id, "void", QuotationCommand(version_no=quote["version_no"]), sales.user))
    with pytest.raises(AppException, match="其他人员修改"):
        run(quote_service.command(quote_id, "void", QuotationCommand(version_no=quote["version_no"] - 1, note="询价取消"), sales.user))
    pending = run(quote_service.revise(quote_id, QuotationCommand(version_no=quote["version_no"]), sales.user))
    voided = run(quote_service.command(quote_id, "void", QuotationCommand(version_no=quote["version_no"], note="询价取消"), sales.user))
    assert voided["status_code"] == "voided"
    assert voided["version_no"] == quote["version_no"] + 1
    assert voided["lines"] == quote["lines"]
    assert (voided["events"][-1]["action_key"], voided["events"][-1]["note"]) == ("void", "询价取消")
    assert run(quote_service.detail(pending["id"], sales.user))["status_code"] == "draft"
    assert run(service.sources(sales.actor, quotation_id=UUID(quote_id)))["total"] == 0
    with pytest.raises(AppException, match="审核通过"):
        run(service.create(body(quote), sales.actor))
    sheet = load_workbook(BytesIO(workbook(voided))).active
    assert sheet["F1"].value == "已作废，仅供存档"


def test_void_checks_order_references_even_without_order_permissions(sales):
    quote = approved(sales)
    run(service.create(body(quote), sales.actor))
    limited = run(quote_service.detail(quote["id"], sales.user))
    assert "customer_order_count" not in limited
    command = QuotationCommand(version_no=quote["version_no"], note="询价取消")
    with pytest.raises(AppException, match="已关联客户订单"):
        run(quote_service.command(quote["id"], "void", command, sales.user))
    assert run(quote_service.detail(quote["id"], sales.user))["status_code"] == "quoted"


def test_unapproved_or_stale_quote_cannot_be_ordered(sales):
    quote = submit(sales)
    with pytest.raises(AppException, match="审核通过"):
        run(service.create(body(quote), sales.actor))
    quote = approved(sales)
    command = body(quote)
    command.lines[0].quotation_version_no -= 1
    with pytest.raises(AppException, match="审核通过"):
        run(service.create(command, sales.actor))
    assert run(service.page(sales.actor, SalesOrderQuery()))["total"] == 0


def test_customer_order_source_opens_only_after_final_review(sales):
    quote = price(sales, submit(sales))
    quote = run(quote_service.command(quote["id"], "finish", QuotationCommand(version_no=quote["version_no"]), sales.user))
    quote = run(quote_service.approve(quote["id"], approval(quote), sales.reviewer))
    quote_id = UUID(quote["id"])
    assert run(service.sources(sales.actor, quotation_id=quote_id))["total"] == 0
    with pytest.raises(AppException, match="审核通过"):
        run(service.create(body(quote), sales.actor))
    quote = final_approval(quote, sales.reviewer)
    assert run(service.sources(sales.actor, quotation_id=quote_id))["total"] == 1
    assert run(service.create(body(quote), sales.actor))["amount"] == "128.00"


def test_price_and_quantity_changes_require_reason_and_keep_source_snapshot(sales):
    quote = approved(sales)
    command = body(quote)
    command.lines[0].quantity, command.lines[0].unit_price = Decimal("5"), Decimal("11")
    with pytest.raises(AppException, match="调整"):
        run(service.create(command, sales.actor))
    command.lines[0].is_price_confirmed = True
    command.lines[0].adjustment_reason = "客户确认本次数量及成交折扣"
    order = run(service.create(command, sales.actor))
    assert order["lines"][0]["unit_price"] == "11.00"
    assert order["lines"][0]["original_unit_price_snapshot"] == "12.80"
    with Session(sales.engine) as session:
        assert "12.80" in session.scalar(select(MesSalesOrderEvent.note).where(MesSalesOrderEvent.order_id == UUID(order["id"])))


def test_partial_and_cross_quote_orders_and_separate_purchases(sales):
    a, b = approved(sales), approved(sales)
    command = body(a)
    command.lines.append(body(b).lines[0])
    combined = run(service.create(command, sales.actor))
    assert len(combined["lines"]) == 2
    assert run(service.create(body(a), sales.actor))["id"] != combined["id"]
    assert run(service.page(sales.actor, SalesOrderQuery(quotation_id=a["id"])))["total"] == 2


@pytest.mark.parametrize("field,value", [("currency", "USD"), ("customer_id", None), ("org_id", None)])
def test_mixed_context_is_rejected_without_partial_order(sales, field, value):
    a, b = approved(sales), approved(sales)
    with Session(sales.engine) as session:
        quote = session.get(MesQuotation, UUID(b["id"]))
        setattr(quote, field, value or (sales.outside_id if field == "customer_id" else sales.foreign_org))
        session.commit()
    command = body(a); command.lines.append(body(b).lines[0])
    with pytest.raises(AppException): run(service.create(command, sales.actor))
    assert run(service.page(sales.actor, SalesOrderQuery()))["total"] == 0


def test_order_access_action_scopes_and_read_only_sources(sales):
    quote = approved(sales)
    order = run(service.create(body(quote), sales.actor))
    order = approve_order(order, sales)
    other = NS(**{**vars(sales.actor), "org_id": sales.foreign_org})
    with pytest.raises(AppException): run(service.detail(order["id"], other))
    scoped = NS(**{**vars(sales.actor), "user_id": sales.reviewer.user_id,
        "permission_scopes": {**sales.actor.permission_scopes, "mes:sales_order:release": "self"}})
    with pytest.raises(AppException): run(service.release(order["id"], release_body(order, sales), scoped))
    assert run(service.sources(sales.actor))["total"] == 1
    reader = NS(**{**vars(sales.actor), "permissions": ["mes:sales_order:list"]})
    with pytest.raises(AppException): run(service.sources(reader))


def test_customer_picker_combines_visible_approved_quotes_and_filters_goods(sales):
    first, second, other = approved(sales), approved(sales), approved(sales)
    pending = submit(sales)
    with Session(sales.engine) as session:
        quote = session.get(MesQuotation, UUID(other["id"]))
        quote.customer_id = sales.outside_id
        quote.customer_name_snapshot = "客户B"
        session.commit()
        before = session.scalar(select(func.count()).select_from(MesQuotation))
    customers = run(service.source_customers(sales.actor))
    assert {row["id"] for row in customers} == {str(sales.customer_id), str(sales.outside_id)}
    assert len(customers) == 2  # 同一客户的多个报价只显示一个选项。
    assert run(service.source_customers(sales.actor, "客户B")) == [dict(id=str(sales.outside_id), name="客户B")]
    result = run(service.sources(sales.actor, customer_id=sales.customer_id))
    assert result["total"] == 2
    assert {row["quotation_id"] for row in result["items"]} == {first["id"], second["id"]}
    assert all(row["customer_id"] == str(sales.customer_id) for row in result["items"])
    assert pending["id"] not in {row["quotation_id"] for row in result["items"]}
    assert run(service.sources(sales.actor, customer_id=uuid4()))["total"] == 0
    assert run(service.sources(sales.actor, customer_id=sales.customer_id, keyword=first["quote_no"]))["total"] == 1
    with Session(sales.engine) as session:
        assert session.scalar(select(func.count()).select_from(MesQuotation)) == before


def test_customer_picker_hides_out_of_scope_deleted_and_unapproved_quotes(sales):
    own, deleted, other_org = approved(sales), approved(sales), approved(sales)
    with Session(sales.engine) as session:
        session.get(MesQuotationLine, UUID(own["lines"][0]["id"])).deleted_at = module.utc_now()
        session.get(MesQuotation, UUID(deleted["id"])).deleted_at = module.utc_now()
        foreign = session.get(MesQuotation, UUID(other_org["id"]))
        foreign.org_id = sales.foreign_org
        session.get(MesQuotationLine, UUID(other_org["lines"][0]["id"])).org_id = sales.foreign_org
        session.commit()
    assert run(service.source_customers(sales.actor)) == []
    assert run(service.sources(sales.actor, customer_id=sales.customer_id))["total"] == 0


@pytest.mark.parametrize("permission", ["mes:sales_order:list", "mes:sales_order:manage", "mes:quotation:list"])
def test_customer_picker_requires_existing_order_and_quotation_permissions(sales, permission):
    actor = NS(**{**vars(sales.actor), "permissions": [key for key in sales.actor.permissions if key != permission]})
    with pytest.raises(AppException) as error:
        run(service.source_customers(actor))
    assert error.value.status_code == 403


def test_customer_picker_scope_is_the_visible_quote_scope(sales):
    approved(sales)
    actor = NS(**{**vars(sales.actor), "user_id": sales.reviewer.user_id,
        "permission_scopes": {**sales.actor.permission_scopes, "mes:quotation:list": "self"}})
    assert run(service.source_customers(actor)) == []
    assert run(service.sources(actor, customer_id=sales.customer_id))["total"] == 0


def test_customer_picker_http_contract_validates_customer_and_retains_pagination(sales, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.modules.mes.sales_order_api import router
    calls = []
    async def customers(user, keyword):
        assert user == sales.actor
        return [dict(id=str(sales.customer_id), name="客户A")]
    async def sources(user, keyword, quotation_id, page, size, customer_id):
        calls.append((keyword, page, size, customer_id))
        return dict(items=[], total=0, page=page, page_size=size)
    monkeypatch.setattr(service, "source_customers", customers)
    monkeypatch.setattr(service, "sources", sources)
    app = FastAPI()
    app.include_router(router, prefix="/api/mes")
    for route in router.routes:
        for dependency in route.dependant.dependencies:
            app.dependency_overrides[dependency.call] = lambda: sales.actor
    with TestClient(app) as client:
        assert client.get("/api/mes/sales-orders/source-customers").json()["data"][0]["id"] == str(sales.customer_id)
        assert client.get("/api/mes/sales-orders/sources", params=dict(customer_id=str(sales.customer_id), page=2, page_size=20)).status_code == 200
        assert client.get("/api/mes/sales-orders/sources", params=dict(customer_id="invalid")).status_code == 422
    assert calls == [("", 2, 20, sales.customer_id)]


def test_two_releases_make_two_real_projects_and_never_overallocate(sales):
    order = run(service.create(body(approved(sales)), sales.actor))
    order = approve_order(order, sales)
    command = release_body(order, sales)
    first = run(service.release(order["id"], command, sales.actor))
    assert first["lines"][0]["remaining_quantity"] == "5.000"
    retried = run(service.release(order["id"], command, sales.actor))
    assert [p["id"] for p in retried["productions"]] == [p["id"] for p in first["productions"]]
    second = run(service.release(order["id"], release_body(first, sales), sales.actor))
    assert second["remaining_count"] == 0 and len(second["productions"]) == 2
    with pytest.raises(AppException, match="超过"):
        run(service.release(order["id"], release_body(second, sales, "1"), sales.actor))
    with Session(sales.engine) as session:
        assert session.scalar(select(func.count()).select_from(MesProductionOrder)) == 2
        works = session.scalars(select(MesWorkOrder)).all()
        assert all(w.status_code == "draft" and w.source_sales_order_line_id for w in works)
    assert len(sales.copied) == 2


def test_one_release_with_multiple_goods_is_one_project(sales):
    command = body(approved(sales)); command.lines.append(body(approved(sales)).lines[0])
    order = run(service.create(command, sales.actor))
    order = approve_order(order, sales)
    release = release_body(order, sales)
    release.lines.append(release.lines[0].model_copy(update={"order_line_id": UUID(order["lines"][1]["id"])}))
    result = run(service.release(order["id"], release, sales.actor))
    assert len(result["productions"]) == 1 and len(result["productions"][0]["lines"]) == 2
    with Session(sales.engine) as session:
        assert session.scalar(select(func.count()).select_from(MesProductionOrder)) == 1
        assert session.scalar(select(func.count()).select_from(MesWorkOrder)) == 2


def adopted_route(sales, quote, operations):
    part_id = uuid4()
    with sales.engine.begin() as connection:
        connection.exec_driver_sql("INSERT INTO mes_cnc_part (id) VALUES (?)", (part_id.hex,))
    with Session(sales.engine) as session:
        snapshot = CncQuote(org_id=sales.user.org_id, part_id=part_id, version_no=1,
            inputs_snapshot={"operations": operations}, created_by=sales.user.user_id)
        session.add(snapshot)
        session.flush()
        line = session.get(MesQuotationLine, UUID(quote["lines"][0]["id"]))
        line.adopted_cnc_quote_id = snapshot.id
        session.add(MesQuotationCnc(org_id=line.org_id, line_id=line.id, part_id=part_id,
            source_hash="test-snapshot", created_by=sales.user.user_id))
        session.commit()
        return snapshot.id, part_id


def test_adopted_process_seeds_editable_operations_and_partial_batch_time(sales):
    quote = approved(sales)
    snapshot_id, part_id = adopted_route(sales, quote, [
        dict(name="CNC 粗加工", unit_hours="0.125", machine="三轴加工中心", note="保留精加工余量"),
        dict(name="终检", unit_hours="0.05", process_type_code="inspection"),
        dict(name="委外氧化", pricing_mode_code="external"),
    ])
    # 后来的核算不应替换已经采用的来源；同零件的重复来源记录不产生重复工序。
    with Session(sales.engine) as session:
        session.add(CncQuote(org_id=sales.user.org_id, part_id=part_id, version_no=2,
            inputs_snapshot={"operations": [dict(name="不应带入的新核算")]}, created_by=sales.user.user_id))
        session.add(MesQuotationCnc(org_id=sales.user.org_id, line_id=UUID(quote["lines"][0]["id"]),
            part_id=part_id, source_hash="duplicate-link", created_by=sales.user.user_id))
        session.commit()
    order = run(service.create(body(quote), sales.actor))
    order = approve_order(order, sales)
    command = release_body(order, sales, quantity="3")
    # 生产安排只需自己的授权范围，不要求另外开放核价金额查询权限。
    actor = NS(**{**vars(sales.actor), "permissions": [p for p in sales.actor.permissions if not p.startswith("mes:quotation:")]})
    result = run(service.release(order["id"], command, actor))
    with Session(sales.engine) as session:
        work = session.scalar(select(MesWorkOrder))
        rows = session.scalars(select(MesWorkOrderOperation).order_by(MesWorkOrderOperation.sequence_no)).all()
        assert work.status_code == "draft"
        assert [r.operation_name_snapshot for r in rows] == ["CNC 粗加工", "终检", "委外氧化"]
        assert [r.operation_no for r in rows] == ["10", "20", "30"]
        assert all(r.planned_quantity == 3 and r.status_code == "draft" for r in rows)
        assert rows[0].standard_minutes_per_unit == Decimal("7.500")
        assert rows[1].is_quality_required and rows[2].standard_minutes_per_unit is None
        assert all(r.process_id is None and r.equipment_id is None and r.assigned_user_id is None for r in rows)
        assert "三轴加工中心" in rows[0].operation_description
        assert "请配置生产工时" in rows[2].operation_description
        assert configuration_plan(rows)[rows[0].id]["planned_duration_minutes"] == 22.5
        rows[0].operation_name_snapshot = "工程调整后的加工"
        session.commit()
    assert run(service.release(order["id"], command, actor))["id"] == result["id"]
    with Session(sales.engine) as session:
        assert session.scalar(select(func.count()).select_from(MesWorkOrderOperation)) == 3
        assert session.scalar(select(MesWorkOrderOperation.operation_name_snapshot)
            .where(MesWorkOrderOperation.sequence_no == 1)) == "工程调整后的加工"
        assert session.get(CncQuote, snapshot_id).inputs_snapshot["operations"][0]["name"] == "CNC 粗加工"


@pytest.mark.parametrize("invalid", ["wrong_org", "wrong_part", "missing_operations"])
def test_inaccessible_or_invalid_adopted_process_rolls_back_release(sales, invalid):
    quote = approved(sales)
    identifier, _ = adopted_route(sales, quote, [dict(name="CNC", unit_hours="0.1")])
    with Session(sales.engine) as session:
        row = session.get(CncQuote, identifier)
        if invalid == "wrong_org": row.org_id = sales.foreign_org
        elif invalid == "wrong_part":
            session.execute(MesQuotationCnc.__table__.update().values(deleted_at=module.utc_now()))
        else: row.inputs_snapshot = {}
        session.commit()
    order = run(service.create(body(quote), sales.actor))
    order = approve_order(order, sales)
    with pytest.raises(AppException, match="工艺快照"):
        run(service.release(order["id"], release_body(order, sales), sales.actor))
    assert not sales.copied
    with Session(sales.engine) as session:
        assert session.scalar(select(func.count()).select_from(MesProductionOrder)) == 0


@pytest.mark.parametrize("snapshot", [{}, [dict(name="", unit_hours="1")],
    [dict(name="CNC", unit_hours="NaN")], [dict(name="CNC", unit_hours="-1")]])
def test_invalid_process_template_is_not_silently_dropped(snapshot):
    with pytest.raises(AppException, match="工艺"):
        production_operations(snapshot, "DRAWING-1")


def test_no_adoption_remains_manual_and_zero_time_is_not_fabricated():
    assert production_operations(None, "P1") == []
    assert production_operations([], "P1") == []
    result = production_operations([dict(name="CNC", unit_hours=0)], "P1")
    assert result[0].standard_minutes_per_unit is None


@pytest.mark.parametrize("rate,expected", [("1", "12.80"), ("0.95", "12.16"), ("0.9", "11.52"),
    ("0.85", "10.88"), ("0.8", "10.24"), ("0.7", "8.96")])
def test_order_discount_is_persisted_without_changing_original_quote(sales, rate, expected):
    quote = approved(sales)
    command = body(quote)
    command.lines[0].discount_rate = Decimal(rate)
    command.lines[0].unit_price = Decimal(expected)
    command.lines[0].is_price_confirmed = True
    command.lines[0].adjustment_reason = "订单折扣"
    result = run(service.create(command, sales.actor))
    assert Decimal(result["lines"][0]["discount_rate"]) == Decimal(rate)
    assert result["lines"][0]["unit_price"] == expected
    assert result["lines"][0]["original_unit_price_snapshot"] == "12.80"
    assert run(quote_service.detail(quote["id"], sales.user))["lines"][0]["unit_price"] == "12.80"


@pytest.mark.parametrize("rate,price,message", [(None, "8.95", "七折"), (Decimal("0.9"), "10", "折扣不一致"),
    (Decimal("0.75"), "9.60", "有效的成交折扣")])
def test_manual_and_tampered_discount_cannot_bypass_floor(sales, rate, price, message):
    command = body(approved(sales))
    command.lines[0].discount_rate, command.lines[0].unit_price = rate, Decimal(price)
    command.lines[0].is_price_confirmed, command.lines[0].adjustment_reason = True, "尝试改价"
    with pytest.raises(AppException, match=message): run(service.create(command, sales.actor))
    assert run(service.page(sales.actor, SalesOrderQuery()))["total"] == 0


def test_discount_floor_applies_to_selected_quantity_tier_and_order_updates(sales):
    quote = tier_quote(sales)
    command = body(quote)
    command.lines[0].quotation_tier_id = UUID(quote["lines"][0]["quantity_tiers"][0]["id"])
    command.lines[0].quantity, command.lines[0].unit_price = Decimal(50), Decimal("5.60")
    command.lines[0].discount_rate = Decimal("0.7")
    command.lines[0].is_price_confirmed, command.lines[0].adjustment_reason = True, "七折成交"
    order = run(service.create(command, sales.actor))
    assert order["lines"][0]["original_unit_price_snapshot"] == "8.00"
    edit = SalesOrderEdit(version_no=order["version_no"], lines=[dict(id=order["lines"][0]["id"],
        quantity=50, unit_price="5.59", due_date="2026-12-01", is_price_confirmed=True, adjustment_reason="手动改价")])
    with pytest.raises(AppException, match="七折"): run(service.update(order["id"], edit, sales.actor))
    edit.lines[0].unit_price, edit.lines[0].discount_rate = Decimal("7.20"), Decimal("0.9")
    updated = run(service.update(order["id"], edit, sales.actor))
    assert Decimal(updated["lines"][0]["discount_rate"]) == Decimal("0.9")


def test_discount_cent_rounding_never_drops_below_floor():
    assert discounted_price(Decimal("0.03"), Decimal("0.7")) == Decimal("0.03")
    assert discounted_price(Decimal("1.01"), Decimal("0.95")) == Decimal("0.96")


def test_engineering_receives_matching_history_without_mutating_saved_quote(sales):
    previous = approved(sales)
    current = submit(sales)
    loaded = run(quote_service.detail(current["id"], sales.user))
    reference = loaded["lines"][0]["historical_reference"]
    assert reference["quote_no"] == previous["quote_no"] and reference["is_compatible"]
    assert reference["unit_price"] == "12.80"
    assert loaded["lines"][0]["unit_price"] is None
    # 不向无工程报价范围的业务人员泄露历史参考价格。
    actor = NS(**{**vars(sales.user), "permission_scopes": {**sales.user.permission_scopes, "mes:quotation:price": "self"}, "user_id": sales.reviewer.user_id})
    assert "historical_reference" not in run(quote_service.detail(current["id"], actor))["lines"][0]


def test_history_prefers_comparable_quote_and_matches_quantity_tier(sales):
    matched = tier_quote(sales)
    sales.body.lines[0].quantity_tiers = []
    other = approved(sales)
    with Session(sales.engine) as session:
        row = session.get(MesQuotationLine, UUID(other["lines"][0]["id"]))
        row.drawing_revision = "B"
        session.commit()
    sales.body.lines[0].quantity = Decimal(50)
    current = submit(sales)
    reference = run(quote_service.detail(current["id"], sales.user))["lines"][0]["historical_reference"]
    assert reference["quote_no"] == matched["quote_no"] and reference["is_compatible"]
    assert Decimal(reference["unit_price"]) == 8 and Decimal(reference["quantity"]) == 50


@pytest.mark.parametrize("field,value", [("drawing_revision", "B"), ("customer_material", "钢"),
    ("surface_treatment", "氧化"), ("quantity", Decimal(99)), ("unit_name", "kg")])
def test_history_differences_are_reference_only(sales, field, value):
    approved(sales)
    setattr(sales.body.lines[0], field, value)
    current = submit(sales)
    reference = run(quote_service.detail(current["id"], sales.user))["lines"][0]["historical_reference"]
    assert not reference["is_compatible"]


@pytest.mark.parametrize("field,value", [("currency", "USD"), ("customer_id", None), ("org_id", None)])
def test_history_isolates_customer_and_org_and_does_not_convert_currency(sales, field, value):
    previous = approved(sales)
    with Session(sales.engine) as session:
        row = session.get(MesQuotation, UUID(previous["id"]))
        setattr(row, field, value or (sales.outside_id if field == "customer_id" else sales.foreign_org))
        session.commit()
    current = submit(sales)
    reference = run(quote_service.detail(current["id"], sales.user))["lines"][0].get("historical_reference")
    if field == "currency": assert reference and not reference["is_compatible"]
    else: assert reference is None


def test_historical_price_checks_source_scope_independently_of_current_quote(sales):
    previous = approved(sales)
    with Session(sales.engine) as session:
        row = session.get(MesQuotation, UUID(previous["id"]))
        row.created_by = sales.reviewer.user_id
        session.commit()
    current = submit(sales)
    actor = NS(**{**vars(sales.user), "permission_scopes": {**sales.user.permission_scopes, "mes:quotation:price": "self"}})
    line = run(quote_service.detail(current["id"], actor))["lines"][0]
    assert "historical_reference" not in line


@pytest.mark.parametrize("model", [MesQuotation, MesQuotationLine])
def test_deleted_history_is_not_suggested(sales, model):
    previous = approved(sales)
    identifier = previous["id"] if model is MesQuotation else previous["lines"][0]["id"]
    with Session(sales.engine) as session:
        session.get(model, UUID(identifier)).deleted_at = module.utc_now()
        session.commit()
    current = submit(sales)
    assert "historical_reference" not in run(quote_service.detail(current["id"], sales.user))["lines"][0]


def test_quote_hours_times_batch_quantity_cannot_overflow_production_plan():
    with pytest.raises(AppException, match="超过10年"):
        production_operations([dict(name="CNC", unit_hours="1000")], "P1", Decimal(100))


def test_release_rolls_back_project_and_allocation_on_failure(sales, monkeypatch):
    order = run(service.create(body(approved(sales)), sales.actor))
    order = approve_order(order, sales)
    original = module.production.create_production_in_session
    async def fail(*args, **kwargs):
        await original(*args, **kwargs)
        raise RuntimeError("模拟工单创建中途失败")
    monkeypatch.setattr(module.production, "create_production_in_session", fail)
    with pytest.raises(RuntimeError): run(service.release(order["id"], release_body(order, sales), sales.actor))
    assert run(service.detail(order["id"], sales.actor))["lines"][0]["remaining_quantity"] == "10.000"
    with Session(sales.engine) as session:
        assert session.scalar(select(func.count()).select_from(MesProductionOrder)) == 0


def test_cancelled_work_restores_remaining_quantity_and_order_cancel_has_guard(sales):
    order = run(service.create(body(approved(sales)), sales.actor))
    order = approve_order(order, sales)
    order = run(service.release(order["id"], release_body(order, sales), sales.actor))
    cancel = SalesOrderCommand(version_no=order["version_no"], note="客户取消")
    with pytest.raises(AppException, match="生产安排"): run(service.cancel(order["id"], cancel, sales.actor))
    with Session(sales.engine) as session:
        work = session.scalar(select(MesWorkOrder)); work.status_code = "cancelled"; session.commit()
    assert run(service.detail(order["id"], sales.actor))["lines"][0]["remaining_quantity"] == "10.000"
    assert run(service.cancel(order["id"], cancel, sales.actor))["status_code"] == "cancelled"


def tier_quote(sales):
    sales.body.lines[0].quantity_tiers = [Decimal("50"), Decimal("100")]
    quote = submit(sales)
    line = quote["lines"][0]
    engineering = EngineeringBody(version_no=quote["version_no"], lines=[dict(id=line["id"],
        quoted_material="AL6082", weight_kg="0.5", unit_price="12.80", quantity_tiers=[
            dict(id=tier["id"], unit_price="8" if Decimal(tier["quantity"]) == 50 else "7", calculation_note="内部核算依据")
            for tier in line["quantity_tiers"]])])
    quote = run(quote_service.engineering(quote["id"], engineering, sales.user, submit=True))
    first_review = run(quote_service.approve(quote["id"], approval(quote), sales.reviewer))
    return final_approval(first_review, sales.reviewer)


def test_quantity_tiers_are_individually_priced_and_selected_for_customer_order(sales):
    quote = tier_quote(sales)
    tier = quote["lines"][0]["quantity_tiers"][0]
    command = body(quote)
    command.lines[0].quotation_tier_id = UUID(tier["id"])
    command.lines[0].quantity, command.lines[0].unit_price = Decimal("50"), Decimal("8")
    order = run(service.create(command, sales.actor))
    line = order["lines"][0]
    assert line["quantity"] == "50.000" and line["original_unit_price_snapshot"] == "8.00"
    assert line["quoted_quantity_snapshot"] == "50.000" and line["quotation_tier_id"] == tier["id"]
    assert quote["lines"][0]["unit_price"] == "12.80"
    book = load_workbook(BytesIO(workbook(quote)))
    assert book.active.max_row == 6
    assert [book.active.cell(row, 5).value for row in range(4, 7)] == [10, 50, 100]
    assert "内部核算依据" not in str(list(book.active.values))


def test_incomplete_or_forged_tiers_cannot_submit_and_nothing_is_saved(sales):
    sales.body.lines[0].quantity_tiers = [Decimal("50")]
    quote = submit(sales); line = quote["lines"][0]
    request = EngineeringBody(version_no=quote["version_no"], lines=[dict(id=line["id"], quoted_material="AL", unit_price="9",
        quantity_tiers=[dict(id=line["quantity_tiers"][0]["id"], unit_price=None)])])
    with pytest.raises(AppException, match="数量档"):
        run(quote_service.engineering(quote["id"], request, sales.user, submit=True))
    loaded = run(quote_service.detail(quote["id"], sales.user))
    assert loaded["status_code"] == "pending" and loaded["lines"][0]["unit_price"] is None
    request.lines[0].quantity_tiers[0].id = uuid4()
    with pytest.raises(AppException, match="数量档"):
        run(quote_service.engineering(quote["id"], request, sales.user))


def test_tier_validation_and_revision_preserve_separate_sources(sales):
    with pytest.raises(ValidationError):
        sales.body.model_validate({**sales.body.model_dump(), "lines": [{**sales.body.lines[0].model_dump(), "quantity_tiers": ["10"]}]})
    with pytest.raises(ValidationError):
        sales.body.model_validate({**sales.body.model_dump(), "lines": [{**sales.body.lines[0].model_dump(), "quantity_tiers": [1,2,3,4,5]}]})
    quote = tier_quote(sales)
    revision = run(quote_service.revise(quote["id"], QuotationCommand(version_no=quote["version_no"], note="客户改图"), sales.user))
    assert revision["revision"] == 2 and revision["status_code"] == "draft"
    assert revision["lines"][0]["lead_days"] is None
    assert revision["lines"][0]["quantity_tiers"][0]["id"] != quote["lines"][0]["quantity_tiers"][0]["id"]
    assert revision["lines"][0]["quantity_tiers"][0]["unit_price"] == "8.00"
    assert run(quote_service.detail(quote["id"], sales.user))["status_code"] == "quoted"


def test_history_only_returns_approved_authorized_matching_prices(sales):
    quote = tier_quote(sales)
    submit(sales)  # 未审批的同图号询价不出现在参考记录
    history = run(quote_service.historical_prices(sales.user, "p1", sales.customer_id))
    assert history["total"] == 1
    assert history["items"][0]["quote_no"] == quote["quote_no"]
    assert len(history["items"][0]["quantity_tiers"]) == 2
    scoped = NS(**{**vars(sales.reviewer), "permission_scopes": {**sales.reviewer.permission_scopes, "mes:quotation:price": "self"}})
    assert run(quote_service.historical_prices(scoped, "P1"))["total"] == 0
    assert run(quote_service.historical_prices(sales.user, "P1", sales.outside_id))["total"] == 0
    reader = NS(**{**vars(sales.user), "permissions": ["mes:quotation:list"]})
    with pytest.raises(AppException): run(quote_service.historical_prices(reader, "P1"))


def test_order_permissions_do_not_grant_engineering_notes_or_unrelated_files(sales):
    quote = approved(sales)
    order = run(service.create(body(quote), sales.actor))
    from app.modules.mes.quotation_service import file_access
    actor = NS(**{**vars(sales.actor), "permissions": ["mes:sales_order:list"]})
    async def allowed(identifier):
        async with sales.sessions() as session: return await file_access(session, actor, UUID(identifier))
    assert run(allowed(quote["lines"][0]["id"])) is True
    unrelated = approved(sales)
    assert run(allowed(unrelated["lines"][0]["id"])) is False
    assert "engineering_note" not in order["lines"][0]


def test_order_edits_keep_original_quote_price_and_audited_changes(sales):
    order = run(service.create(body(approved(sales)), sales.actor))
    order = approve_order(order, sales)
    edit = SalesOrderEdit(version_no=order["version_no"], customer_po_no="CUSTOMER-02", note="调整成交",
        lines=[dict(id=line["id"], quantity="6", unit_price="11", due_date="2026-12-03") for line in order["lines"]])
    with pytest.raises(AppException, match="调整原因"):
        run(service.update(order["id"], edit, sales.actor))
    edit.lines[0].is_price_confirmed, edit.lines[0].adjustment_reason = True, "客户确认新的成交价"
    updated = run(service.update(order["id"], edit, sales.actor))
    assert updated["status_code"] == "confirmed"
    assert updated["lines"][0]["quantity"] == "6.000"
    assert updated["lines"][0]["original_unit_price_snapshot"] == "12.80"
    assert updated["lines"][0]["unit_price"] == "11.00"
    assert any(event["action_key"] == "update" and "12.80" in event["note"] for event in updated["events"])
    with pytest.raises(AppException, match="版本"):
        run(service.update(order["id"], edit, sales.actor))
    with pytest.raises(AppException, match="先审核"):
        run(service.release(order["id"], release_body(updated, sales, "3"), sales.actor))
    reviewed = approve_order(updated, sales)
    released = run(service.release(order["id"], release_body(reviewed, sales, "3"), sales.actor))
    edit.version_no = released["version_no"]
    with pytest.raises(AppException, match="锁定"):
        run(service.update(order["id"], edit, sales.actor))


def test_order_source_product_and_quantity_cannot_be_replaced_in_work_order_editor(sales, monkeypatch):
    from contextlib import asynccontextmanager
    from app.modules.mes import order_service as order_module
    from app.modules.mes.schemas import WorkOrderUpdate
    order = run(service.create(body(approved(sales)), sales.actor))
    order = approve_order(order, sales)
    result = run(service.release(order["id"], release_body(order, sales), sales.actor))
    work_id = UUID(result["productions"][0]["lines"][0]["work_order_id"])
    @asynccontextmanager
    async def sessions():
        async with sales.sessions() as adapter:
            async def execute(statement): return adapter.session.execute(statement)
            adapter.exec = execute
            yield adapter
    monkeypatch.setattr(order_module, "get_session_context", sessions)
    actor = NS(**{**vars(sales.actor), "permissions": [*sales.actor.permissions, "mes:work_order:manage"],
        "permission_scopes": {**sales.actor.permission_scopes, "mes:work_order:manage": "organization"}})
    update = WorkOrderUpdate(org_id=actor.org_id, work_order_no="PO", product_item_id=sales.item_id,
        planned_quantity="9", version_no=1, publish=False, operations=[])
    with pytest.raises(AppException, match="不能直接更换"):
        run(order_module.order_service.update(work_id, update, actor))


def test_production_defaults_match_item_and_unit_without_creating_records(sales):
    order = run(service.create(body(approved(sales)), sales.actor))
    order = approve_order(order, sales)
    sales.catalogue[sales.item_id].item_no = "p1"
    defaults = run(service.production_defaults(order["id"], sales.actor))
    row = defaults["lines"][0]
    assert row["product_item_id"] == str(sales.item_id) and row["unit_name"] == "件"
    assert row["is_create_product"] is False and row["match_source"] == "drawing_no"
    assert sales.created_items == []
    with Session(sales.engine) as session:
        assert session.scalar(select(func.count()).select_from(MesProductionOrder)) == 0


def test_missing_product_is_created_only_on_release_and_reused_across_orders(sales):
    sales.actor.permissions.append("inventory_product:create")
    quote = approved(sales)
    first = run(service.create(body(quote), sales.actor))
    first = approve_order(first, sales)
    defaults = run(service.production_defaults(first["id"], sales.actor))["lines"][0]
    assert defaults["is_create_product"] is True and defaults["unit_code"] == "piece"
    assert defaults["item_no"] == "P1" and sales.created_items == []
    def auto(order):
        return SalesReleaseBody(version_no=order["version_no"], idempotency_key=str(uuid4()), is_unit_confirmed=True,
            lines=[dict(order_line_id=order["lines"][0]["id"], quantity="5", is_create_product=True, product_unit_code="piece")])
    result = run(service.release(first["id"], auto(first), sales.actor))
    assert len(sales.created_items) == 1
    second = run(service.create(body(quote), sales.actor))
    second = approve_order(second, sales)
    reused = run(service.production_defaults(second["id"], sales.actor))["lines"][0]
    assert reused["match_source"] == "catalog" and reused["product_item_id"] == str(sales.created_items[0].id)
    run(service.release(second["id"], auto(second), sales.actor))
    assert len(sales.created_items) == 1
    assert len(result["productions"]) == 1


def test_auto_product_cannot_change_known_unit_and_requires_creation_permission(sales):
    order = run(service.create(body(approved(sales)), sales.actor))
    order = approve_order(order, sales)
    command = SalesReleaseBody(version_no=order["version_no"], idempotency_key=str(uuid4()), is_unit_confirmed=True,
        lines=[dict(order_line_id=order["lines"][0]["id"], quantity="5", is_create_product=True, product_unit_code="kg")])
    with pytest.raises(AppException, match="单位"): run(service.release(order["id"], command, sales.actor))
    command.lines[0].product_unit_code = "piece"
    with pytest.raises(AppException, match="权限"): run(service.release(order["id"], command, sales.actor))
    assert sales.created_items == []
    defaults = run(service.production_defaults(order["id"], sales.actor))["lines"][0]
    assert defaults["can_create"] is False


def test_auto_product_rows_roll_back_when_production_creation_fails(sales, monkeypatch):
    sales.actor.permissions.append("inventory_product:create")
    order = run(service.create(body(approved(sales)), sales.actor))
    order = approve_order(order, sales)
    async def fail(*args, **kwargs): raise RuntimeError("生产创建失败")
    monkeypatch.setattr(module.production, "create_production_in_session", fail)
    command = SalesReleaseBody(version_no=order["version_no"], idempotency_key=str(uuid4()), is_unit_confirmed=True,
        lines=[dict(order_line_id=order["lines"][0]["id"], quantity="5", is_create_product=True, product_unit_code="piece")])
    with pytest.raises(RuntimeError): run(service.release(order["id"], command, sales.actor))
    assert len(sales.created_items) == 1
    with Session(sales.engine) as session:
        from sqlalchemy import text
        assert session.execute(text("select count(*) from md_item")).scalar_one() == 1  # only original fixture item
        assert session.scalar(select(func.count()).select_from(MesSalesProduction)) == 0


def test_defaults_keep_confirmed_previous_product_and_reject_ambiguous_item_numbers(sales):
    order = run(service.create(body(approved(sales)), sales.actor))
    order = approve_order(order, sales)
    released = run(service.release(order["id"], release_body(order, sales), sales.actor))
    previous = run(service.production_defaults(order["id"], sales.actor))["lines"][0]
    assert previous["match_source"] == "previous" and previous["product_item_id"] == str(sales.item_id)
    other = run(service.create(body(approved(sales)), sales.actor))
    other = approve_order(other, sales)
    for number in ("P1", "p1"):
        identifier = uuid4(); sales.catalogue[identifier] = NS(id=identifier, item_no=number, item_name="连接板", unit_code="piece")
    ambiguous = run(service.production_defaults(other["id"], sales.actor))["lines"][0]
    assert ambiguous["match_status"] == "ambiguous" and ambiguous["is_create_product"] is False


def test_matching_units_do_not_require_legacy_checkbox_and_material_reaches_production(sales):
    order = run(service.create(body(approved(sales)), sales.actor))
    order = approve_order(order, sales)
    command = release_body(order, sales)
    command.is_unit_confirmed = False
    defaults = run(service.production_defaults(order["id"], sales.actor))["lines"][0]
    assert defaults["material"] == "AL6082" and defaults["order_unit_code"] == "piece"
    result = run(service.release(order["id"], command, sales.actor))
    assert len(result["productions"]) == 1
    with Session(sales.engine) as session:
        work = session.scalar(select(MesWorkOrder))
        assert "加工材料 AL6082" in work.note


def test_genuinely_different_units_cannot_be_bypassed_by_legacy_confirmation(sales):
    order = run(service.create(body(approved(sales)), sales.actor))
    order = approve_order(order, sales)
    sales.catalogue[sales.item_id].item_no = "P1"
    sales.catalogue[sales.item_id].unit_code = "kg"
    defaults = run(service.production_defaults(order["id"], sales.actor))["lines"][0]
    assert defaults["match_status"] == "unit_mismatch"
    assert defaults["product_item_id"] == str(sales.item_id)
    assert defaults["unit_name"] == "千克" and defaults["order_unit_code"] == "piece"
    with pytest.raises(AppException, match="不一致"):
        run(service.release(order["id"], release_body(order, sales), sales.actor))
    with Session(sales.engine) as session:
        assert session.scalar(select(func.count()).select_from(MesProductionOrder)) == 0
