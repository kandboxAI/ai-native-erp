"""询价真实事务回归；只用临时 SQLite，不连接业务库或调用模型。"""
import asyncio
from decimal import Decimal
from contextlib import asynccontextmanager
from io import BytesIO
from types import SimpleNamespace as NS
from uuid import UUID, uuid4

import pytest
from openpyxl import load_workbook
from pydantic import ValidationError
from sqlalchemy import Column, JSON, MetaData, Table, Uuid, create_engine, event, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session

from app.core.exceptions import AppException
from app.modules.mes import quotation_service as module
from app.modules.mes.quotation_service import service
from app.modules.mes.quotation_models import MesQuotation, MesQuotationLine, MesQuotationFile, MesQuotationCnc, MesQuotationEvent, MesQuotationPriceTier
from app.modules.mes.quotation_schemas import QuotationBody, EngineeringBody, QuotationCommand, QuotationAdoptBody, QuotationCncBody, QuotationApprovalBody, QuotationAdoptionPreview, QuotationBatchAdopt
from app.modules.mes.quotation_exports import workbook
from app.modules.mes.archive_models import MesCustomer
from app.framework.db.registry import import_all_models

import_all_models()


def run(value):
    return asyncio.run(value)


@pytest.fixture
def store(monkeypatch):
    perms = [f"mes:quotation:{key}" for key in ("list", "manage", "price", "approve", "export")]
    user = NS(user_id=uuid4(), auth_user_id=uuid4(), org_id=uuid4(), org_ids=[], department_id=None, enabled_plugin_keys=["mes"],
        org_access_mode_code="selected", permissions=perms, permission_scopes={key: "organization" for key in perms})
    reviewer = NS(**{**vars(user), "user_id": uuid4()})
    engine = create_engine("sqlite:///:memory:")
    @event.listens_for(engine, "connect")
    def foreign_keys(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")
    metadata = MetaData()
    models = (MesCustomer, MesQuotation, MesQuotationLine, MesQuotationFile, MesQuotationCnc, MesQuotationEvent, MesQuotationPriceTier)
    names = {model.__tablename__ for model in models}
    external = {fk.target_fullname.rsplit(".", 1)[0] for model in models for fk in model.__table__.foreign_keys} - names
    for name in external:
        Table(name, metadata, Column("id", Uuid, primary_key=True))
    for model in models:
        table = model.__table__.to_metadata(metadata)
        for column in table.columns:
            column.server_default = None
            if isinstance(column.type, JSONB):
                column.type = JSON()
        for index in table.indexes:
            where = index.dialect_options["postgresql"].get("where")
            if where is not None:
                index.dialect_options["sqlite"]["where"] = where
    metadata.create_all(engine)
    foreign_org, foreign_user, attachment_id = uuid4(), uuid4(), uuid4()
    with engine.begin() as connection:
        for identifier in (user.org_id, foreign_org):
            connection.execute(metadata.tables["sys_org"].insert().values(id=identifier))
        for identifier in (user.user_id, reviewer.user_id, foreign_user):
            connection.execute(metadata.tables["sys_user"].insert().values(id=identifier))
        connection.execute(metadata.tables["file_attachment"].insert().values(id=attachment_id))
    customer = MesCustomer(org_id=user.org_id, customer_no="C01", customer_name="客户代号", created_by=user.user_id)
    outside = MesCustomer(org_id=foreign_org, customer_no="C02", customer_name="其他组织", created_by=foreign_user)
    with Session(engine) as session:
        session.add_all([customer, outside]); session.commit()
        customer_id, outside_id = customer.id, outside.id
    class Adapter:
        def __init__(self, session): self.session = session
        async def execute(self, statement): return self.session.execute(statement)
        async def flush(self): self.session.flush()
        async def commit(self): self.session.commit()
        def add(self, row): self.session.add(row)
    @asynccontextmanager
    async def sessions():
        with Session(engine, expire_on_commit=False) as session:
            try:
                yield Adapter(session)
            except BaseException:
                session.rollback()
                raise
    monkeypatch.setattr(module, "get_session_context", sessions)
    async def download(identifier, actor):
        return {"name": "P1.pdf", "file_size": 20}
    monkeypatch.setattr(module.files, "download_url", download)
    body = QuotationBody(title="真实询价", customer_id=customer_id, currency="EUR", lines=[dict(
        drawing_no="P1", description="零件", quantity=10, customer_material="6082", unit_name="件")])
    return NS(user=user, reviewer=reviewer, engine=engine, body=body, customer_id=customer_id,
        outside_id=outside_id, attachment_id=attachment_id, foreign_org=foreign_org, sessions=sessions)


def create(store):
    return run(service.save(None, store.body, store.user))


def attach(store, quote):
    with Session(store.engine) as session:
        session.add(MesQuotationFile(org_id=store.user.org_id, line_id=UUID(quote["lines"][0]["id"]),
            attachment_id=store.attachment_id, kind="pdf", created_by=store.user.user_id))
        session.commit()


def submit(store):
    quote = create(store)
    attach(store, quote)
    return run(service.command(quote["id"], "submit", QuotationCommand(version_no=quote["version_no"]), store.user))


def price(store, quote):
    return run(service.engineering(quote["id"], EngineeringBody(version_no=quote["version_no"], lines=[dict(
        id=quote["lines"][0]["id"], quoted_material="AL6082", weight_kg="0.5", unit_price="12.80")]), store.user))


def approval(quote, days=14):
    return QuotationApprovalBody(version_no=quote["version_no"], lines=[
        dict(id=row["id"], lead_days=days) for row in quote["lines"]])


def final_approval(quote, user):
    return run(service.command(quote["id"], "final_approve", QuotationCommand(version_no=quote["version_no"]), user))


def test_quotation_todos_follow_handoffs_without_notifications_or_workflow(store, monkeypatch):
    from app.modules.mes import todos
    monkeypatch.setattr(todos, "get_session_context", store.sessions)
    def actor(base, *actions):
        return NS(**{**vars(base), "permissions": ["mes:quotation:list", *[f"mes:quotation:{a}" for a in actions]]})
    sales = actor(store.user, "manage")
    engineer = actor(store.reviewer, "price")
    boss = actor(store.user, "approve")
    tasks = lambda person: run(todos.load(person, 100))
    quote = create(store)
    assert tasks(sales).total == tasks(engineer).total == tasks(boss).total == 0
    attach(store, quote)
    quote = run(service.command(quote["id"], "submit", QuotationCommand(version_no=quote["version_no"]), sales))
    task = tasks(engineer)
    assert task.total == 1 and task.items[0].description == "待工程报价"
    assert f"quote_id={quote['id']}&mode=engineering" in task.items[0].path
    assert tasks(sales).total == tasks(boss).total == 0
    quote = price(NS(**{**vars(store), "user": engineer}), quote)
    assert tasks(engineer).total == 1  # 保存不完成待办
    assert run(todos.search(engineer, quote["quote_no"], 10)).total == 1
    assert run(todos.search(engineer, "__not_an_existing_quote__", 10)).total == 0
    quote = run(service.command(quote["id"], "finish", QuotationCommand(version_no=quote["version_no"]), engineer))
    assert tasks(engineer).total == 0 and tasks(boss).total == 1
    assert "mode=review" in tasks(boss).items[0].path
    assert tasks(actor(store.reviewer, "price", "approve")).total == 0  # 不能自审
    admin = actor(store.reviewer, "price", "approve", "approve_self")
    admin.permission_scopes = {**admin.permission_scopes, "mes:quotation:approve_self": "organization"}
    assert tasks(admin).total == 1  # 管理员获自审授权后也能收到自己的待审核报价。
    admin.permission_scopes["mes:quotation:approve_self"] = "self"
    assert tasks(admin).total == 0  # 此单由业务人员创建，自审授权的数据范围仍须满足。
    quote = run(service.command(quote["id"], "reject", QuotationCommand(version_no=quote["version_no"], note="补核材料"), boss))
    assert tasks(boss).total == 0 and tasks(engineer).items[0].description == "报价退回修改"
    quote = run(service.command(quote["id"], "return", QuotationCommand(version_no=quote["version_no"], note="补图纸"), engineer))
    assert tasks(engineer).total == 0 and tasks(sales).total == 1
    assert "mode=sales" in tasks(sales).items[0].path
    assert tasks(actor(store.reviewer, "manage")).total == 0
    quote = run(service.command(quote["id"], "submit", QuotationCommand(version_no=quote["version_no"]), sales))
    quote = price(NS(**{**vars(store), "user": engineer}), quote)
    quote = run(service.command(quote["id"], "finish", QuotationCommand(version_no=quote["version_no"]), engineer))
    quote = run(service.approve(quote["id"], approval(quote), boss))
    assert tasks(boss).items[0].description == "待报价复审"
    assert "mode=final_review" in tasks(boss).items[0].path
    assert tasks(engineer).total == tasks(admin).total == 0
    final_approval(quote, boss)
    assert tasks(sales).total == tasks(engineer).total == tasks(boss).total == 0


def test_quotation_todos_intersect_list_and_action_scopes_and_hide_deleted(store, monkeypatch):
    from app.modules.mes import todos
    monkeypatch.setattr(todos, "get_session_context", store.sessions)
    quote = submit(store)
    with Session(store.engine) as session:
        session.add(MesQuotation(org_id=store.foreign_org, quote_no="OTHER", title="其他组织",
            customer_id=store.outside_id, customer_name_snapshot="外部客户", currency="EUR",
            status_code="pending", created_by=store.user.user_id))
        session.commit()
    assert run(todos.load(store.user, 100)).total == 1
    scoped = NS(**{**vars(store.reviewer), "permission_scopes": {**store.user.permission_scopes, "mes:quotation:list": "self"}})
    assert run(todos.load(scoped, 100)).total == 0
    scoped = NS(**{**vars(store.reviewer), "permission_scopes": {**store.user.permission_scopes, "mes:quotation:price": "self"}})
    assert run(todos.load(scoped, 100)).total == 0
    reader = NS(**{**vars(store.user), "permissions": ["mes:quotation:list"]})
    assert run(todos.load(reader, 100)).total == 0
    with Session(store.engine) as session:
        row = session.get(MesQuotation, UUID(quote["id"]))
        row.deleted_at = module.utc_now()
        session.commit()
    assert run(todos.load(store.user, 100)).total == 0


def test_persistence_and_engineer_receives_customer_requirements(store):
    quote = submit(store)
    loaded = run(service.detail(quote["id"], store.reviewer))
    assert loaded["lines"][0]["customer_material"] == "6082"
    assert loaded["lines"][0]["files"][0]["name"] == "P1.pdf"
    assert loaded["status_code"] == "pending"
    assert run(service.page(store.reviewer))["total"] == 1


def cnc_reader(store):
    return NS(**{**vars(store.user), "permissions": [*store.user.permissions, "mes:quote:list"],
        "permission_scopes": {**store.user.permission_scopes, "mes:quote:list": "organization"}})


def test_cnc_progress_reads_live_status_only_without_files_history_or_mutations(store, monkeypatch):
    quote = submit(store)
    user = cnc_reader(store)
    part_id = uuid4()
    async def links(session, line_id):
        line = session.session.get(MesQuotationLine, line_id)
        bindings = await module.repo.files(session, line_id)
        return [NS(id=uuid4(), part_id=part_id, source_hash=module.source_hash(line, bindings), created_at=line.created_at)]
    async def part(session, identifier, actor, permission):
        assert identifier == part_id and actor is user and permission == "mes:quote:list"
    state = NS(status_code="queued", stage="等待解析")
    async def jobs(session, identifier):
        return state
    async def forbidden(*args):
        raise AssertionError("进度查询不读取文件内容/下载地址或操作历史")
    monkeypatch.setattr(module.repo, "cnc_links", links)
    monkeypatch.setattr(module.cnc_repo, "part", part)
    monkeypatch.setattr(module.cnc_repo, "jobs", jobs)
    monkeypatch.setattr(module.files, "download_url", forbidden)
    monkeypatch.setattr(module.repo, "history", forbidden)
    for status in ("queued", "running", "completed", "failed"):
        state.status_code, state.stage = status, f"任务 {status}"
        result = run(service.cnc_progress(quote["id"], user))
        assert set(result) == {"lines"}
        line = result["lines"][0]
        assert set(line) == {"id", "cnc_records"} and line["id"] == quote["lines"][0]["id"]
        assert line["cnc_records"][0]["status_code"] == status
        assert line["cnc_records"][0]["stage"] == f"任务 {status}"
        assert line["cnc_records"][0]["is_stale"] is False
    with Session(store.engine) as session:
        assert session.get(MesQuotation, UUID(quote["id"])).version_no == quote["version_no"]
        assert len(session.execute(select(MesQuotationEvent)).scalars().all()) == len(quote["events"])


@pytest.mark.parametrize("missing", ["mes:quotation:list", "mes:quotation:price", "mes:quote:list"])
def test_cnc_progress_requires_all_permissions(store, missing):
    quote = create(store)
    user = cnc_reader(store)
    user.permissions = [key for key in user.permissions if key != missing]
    with pytest.raises(AppException) as error:
        run(service.cnc_progress(quote["id"], user))
    assert error.value.status_code == 403


@pytest.mark.parametrize("permission", ["mes:quotation:list", "mes:quotation:price"])
def test_cnc_progress_intersects_quotation_read_and_engineering_scopes(store, permission):
    quote = create(store)
    user = cnc_reader(store)
    user.user_id = store.reviewer.user_id
    user.permission_scopes[permission] = "self"
    with pytest.raises(AppException) as error:
        run(service.cnc_progress(quote["id"], user))
    assert error.value.status_code == 404


def test_cnc_progress_hides_inaccessible_cnc_parts_and_deleted_quotation_lines(store, monkeypatch):
    quote = create(store)
    async def links(*args):
        return [NS(part_id=uuid4())]
    async def forbidden_part(*args):
        raise AppException("无权查看", 404)
    monkeypatch.setattr(module.repo, "cnc_links", links)
    monkeypatch.setattr(module.cnc_repo, "part", forbidden_part)
    assert run(service.cnc_progress(quote["id"], cnc_reader(store)))["lines"][0]["cnc_records"] == []
    with Session(store.engine) as session:
        line = session.get(MesQuotationLine, UUID(quote["lines"][0]["id"]))
        line.deleted_at = module.utc_now()
        session.commit()
    assert run(service.cnc_progress(quote["id"], cnc_reader(store))) == {"lines": []}


def test_cnc_progress_http_contract(store, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.modules.mes.quotation_api import router
    calls = []
    async def progress(identifier, user):
        calls.append((identifier, user))
        return {"lines": []}
    monkeypatch.setattr(service, "cnc_progress", progress)
    app = FastAPI()
    app.include_router(router, prefix="/api/mes")
    for route in router.routes:
        for dependency in route.dependant.dependencies:
            app.dependency_overrides[dependency.call] = lambda: store.user
    identifier = uuid4()
    with TestClient(app) as client:
        response = client.get(f"/api/mes/quotations/{identifier}/cnc-records")
    assert response.status_code == 200
    assert response.json() == {"code": 0, "message": "success", "data": {"lines": []}}
    assert calls == [(identifier, store.user)]


def test_engineering_and_independent_approval(store):
    quote = price(store, submit(store))
    quote = run(service.command(quote["id"], "finish", QuotationCommand(version_no=quote["version_no"]), store.user))
    assert quote["status_code"] == "review"
    assert quote["lines"][0]["lead_days"] is None
    with pytest.raises(AppException, match="本人审核"):
        run(service.approve(quote["id"], approval(quote), store.user))
    with pytest.raises(AppException, match="当前询价状态"):
        final_approval(quote, store.reviewer)
    approved = run(service.approve(quote["id"], approval(quote), store.reviewer))
    assert approved["status_code"] == "final_review"
    assert approved["lines"][0]["unit_price"] == "12.80"
    assert approved["lines"][0]["lead_days"] == 14
    assert [row["action_key"] for row in approved["events"]][-1] == "approve"
    with pytest.raises(AppException, match="其他人员修改"):
        final_approval(quote, store.reviewer)
    with pytest.raises(AppException, match="本人审核"):
        final_approval(approved, store.user)
    persisted = run(service.detail(quote["id"], store.reviewer))
    completed = final_approval(approved, store.reviewer)
    assert completed["status_code"] == "quoted" and completed["lines"] == persisted["lines"]
    assert completed["events"][-1]["action_key"] == "final_approve"
    assert completed["events"][-1]["created_by"] == str(store.reviewer.user_id)
    with pytest.raises(AppException, match="当前询价状态"):
        final_approval(completed, store.reviewer)


def test_final_review_can_return_to_first_review_and_requires_new_approval(store):
    quote = price(store, submit(store))
    quote = run(service.command(quote["id"], "finish", QuotationCommand(version_no=quote["version_no"]), store.user))
    quote = run(service.approve(quote["id"], approval(quote), store.reviewer))
    with pytest.raises(AppException, match="退回初审的原因"):
        run(service.command(quote["id"], "final_reject", QuotationCommand(version_no=quote["version_no"]), store.reviewer))
    body = QuotationCommand(version_no=quote["version_no"], note="请重新核对交期")
    returned = run(service.command(quote["id"], "final_reject", body, store.reviewer))
    assert returned["status_code"] == "review" and returned["return_reason"] == body.note
    assert returned["events"][-1]["action_key"] == "final_reject"
    with pytest.raises(AppException, match="当前询价状态"):
        final_approval(returned, store.reviewer)
    resubmitted = run(service.approve(quote["id"], approval(returned, days=20), store.reviewer))
    assert resubmitted["status_code"] == "final_review" and resubmitted["return_reason"] == ""
    completed = final_approval(resubmitted, store.reviewer)
    assert completed["lines"][0]["lead_days"] == 20


def test_explicit_self_review_permission_allows_own_quotation_and_records_actor(store):
    quote = price(store, submit(store))
    quote = run(service.command(quote["id"], "finish", QuotationCommand(version_no=quote["version_no"]), store.user))
    actor = NS(**{**vars(store.user), "permissions": [*store.user.permissions, "mes:quotation:approve_self"],
        "permission_scopes": {**store.user.permission_scopes, "mes:quotation:approve_self": "organization"}})
    approved = run(service.approve(quote["id"], approval(quote), actor))
    assert approved["status_code"] == "final_review" and approved["lines"][0]["lead_days"] == 14
    assert approved["events"][-1]["note"] == "经授权审核本人提交的报价"
    completed = final_approval(approved, actor)
    assert completed["events"][-1]["note"] == "经授权复审本人提交的报价"
    with Session(store.engine) as session:
        event = session.execute(select(MesQuotationEvent).where(
            MesQuotationEvent.quotation_id == UUID(quote["id"]), MesQuotationEvent.action_key == "approve")).scalar_one()
        assert event.created_by == actor.user_id


def test_admin_role_name_without_self_review_permission_does_not_bypass_restriction(store):
    quote = price(store, submit(store))
    quote = run(service.command(quote["id"], "finish", QuotationCommand(version_no=quote["version_no"]), store.user))
    actor = NS(**{**vars(store.user), "role_nos": ["admin"], "is_admin": True})
    with pytest.raises(AppException, match="本人审核"):
        run(service.approve(quote["id"], approval(quote), actor))
    assert run(service.detail(quote["id"], store.user))["status_code"] == "review"


@pytest.mark.parametrize("limited", ["approve", "approve_self", "list"])
def test_self_review_respects_all_three_permission_scopes(store, limited):
    quote = submit(store)
    quote = price(NS(**{**vars(store), "user": store.reviewer}), quote)
    quote = run(service.command(quote["id"], "finish", QuotationCommand(version_no=quote["version_no"]), store.reviewer))
    actor = NS(**{**vars(store.reviewer), "permissions": [*store.reviewer.permissions, "mes:quotation:approve_self"],
        "permission_scopes": {**store.reviewer.permission_scopes, "mes:quotation:approve_self": "organization",
            f"mes:quotation:{limited}": "self"}})
    with pytest.raises(AppException) as error:
        run(service.approve(quote["id"], approval(quote), actor))
    assert error.value.status_code == 404
    loaded = run(service.detail(quote["id"], store.user))
    assert loaded["version_no"] == quote["version_no"] and loaded["status_code"] == "review"
    assert loaded["lines"][0]["lead_days"] is None


def test_self_review_permission_still_requires_ordinary_approval_and_final_delivery(store):
    quote = price(store, submit(store))
    quote = run(service.command(quote["id"], "finish", QuotationCommand(version_no=quote["version_no"]), store.user))
    actor = NS(**{**vars(store.user), "permissions": ["mes:quotation:list", "mes:quotation:approve_self"],
        "permission_scopes": {**store.user.permission_scopes, "mes:quotation:approve_self": "organization"}})
    with pytest.raises(AppException) as error:
        run(service.approve(quote["id"], approval(quote), actor))
    assert error.value.status_code == 403
    actor.permissions.append("mes:quotation:approve")
    with pytest.raises(AppException, match="最终交期"):
        run(service.command(quote["id"], "approve", QuotationCommand(version_no=quote["version_no"]), actor))
    assert run(service.detail(quote["id"], store.user))["status_code"] == "review"


def test_self_review_permission_is_declared_once_in_mes_catalog():
    from app.modules.mes.catalog import PERMISSIONS
    definitions = [item for item in PERMISSIONS if item.key == "mes:quotation:approve_self"]
    assert len(definitions) == 1 and definitions[0].module_code == "mes"


def test_engineering_and_adoption_payloads_cannot_assign_final_delivery():
    with pytest.raises(ValidationError):
        EngineeringBody(version_no=1, lines=[dict(id=uuid4(), lead_days=5)])
    with pytest.raises(ValidationError):
        QuotationAdoptBody(version_no=1, cnc_quote_id=uuid4(), final_unit_price=10, lead_days=5)
    for days in (None, 0, -1, 3651):
        with pytest.raises(ValidationError):
            QuotationApprovalBody(version_no=1, lines=[dict(id=uuid4(), lead_days=days)])


def test_final_delivery_requires_approval_permission_and_cannot_bypass_review(store):
    quote = price(store, submit(store))
    quote = run(service.command(quote["id"], "finish", QuotationCommand(version_no=quote["version_no"]), store.user))
    limited = NS(**{**vars(store.reviewer), "permissions": ["mes:quotation:list", "mes:quotation:price"]})
    with pytest.raises(AppException, match="权限"):
        run(service.approve(quote["id"], approval(quote), limited))
    with pytest.raises(AppException, match="最终交期"):
        run(service.command(quote["id"], "approve", QuotationCommand(version_no=quote["version_no"]), store.reviewer))
    loaded = run(service.detail(quote["id"], store.reviewer))
    assert loaded["status_code"] == "review" and loaded["lines"][0]["lead_days"] is None


@pytest.mark.parametrize("invalid", ["foreign", "duplicate", "stale"])
def test_invalid_delivery_approval_does_not_update_quote(store, invalid):
    quote = price(store, submit(store))
    quote = run(service.command(quote["id"], "finish", QuotationCommand(version_no=quote["version_no"]), store.user))
    body = approval(quote)
    if invalid == "foreign":
        body.lines[0].id = uuid4()
    elif invalid == "duplicate":
        body.lines.append(body.lines[0])
    else:
        body.version_no -= 1
    with pytest.raises(AppException):
        run(service.approve(quote["id"], body, store.reviewer))
    loaded = run(service.detail(quote["id"], store.reviewer))
    assert loaded["status_code"] == "review" and loaded["version_no"] == quote["version_no"]
    assert loaded["lines"][0]["lead_days"] is None


def test_business_cannot_mutate_engineering_fields(store):
    with pytest.raises(ValidationError):
        QuotationBody(**{**store.body.model_dump(), "lines": [{**store.body.lines[0].model_dump(), "unit_price": 1}]})
    user = NS(**{**vars(store.user), "permissions": ["mes:quotation:list", "mes:quotation:manage"]})
    quote = submit(store)
    with pytest.raises(AppException, match="权限"):
        run(service.engineering(quote["id"], EngineeringBody(version_no=quote["version_no"], lines=[dict(id=quote["lines"][0]["id"])]), user))


def test_engineering_owns_net_weight_and_business_save_preserves_existing_weight(store):
    from decimal import Decimal
    with pytest.raises(ValidationError, match="weight_kg"):
        QuotationBody(**{**store.body.model_dump(), "lines": [{**store.body.lines[0].model_dump(), "weight_kg": "0.125"}]})
    quote = create(store)
    assert quote["lines"][0]["weight_kg"] is None
    line_id = UUID(quote["lines"][0]["id"])
    with Session(store.engine) as session:
        session.get(MesQuotationLine, line_id).weight_kg = Decimal("0.125")
        session.commit()
    body = store.body.model_copy(update={"version_no": quote["version_no"], "lines": [store.body.lines[0].model_copy(update={"id": line_id})]})
    quote = run(service.save(quote["id"], body, store.user))
    assert Decimal(quote["lines"][0]["weight_kg"]) == Decimal("0.125")
    attach(store, quote)
    quote = run(service.command(quote["id"], "submit", QuotationCommand(version_no=quote["version_no"]), store.user))
    quote = price(store, quote)
    assert Decimal(quote["lines"][0]["weight_kg"]) == Decimal("0.5")


def test_stale_version_does_not_overwrite(store):
    quote = create(store)
    body = store.body.model_copy(update={"version_no": quote["version_no"]})
    run(service.save(quote["id"], body, store.user))
    with pytest.raises(AppException, match="其他人员修改"):
        run(service.save(quote["id"], body.model_copy(update={"title": "不应覆盖"}), store.user))
    assert run(service.detail(quote["id"], store.user))["title"] == store.body.title


def test_cross_organization_and_unknown_line_rejected(store):
    with pytest.raises(AppException, match="客户"):
        run(service.save(None, store.body.model_copy(update={"customer_id": store.outside_id}), store.user))
    quote = create(store)
    stranger = NS(**{**vars(store.user), "org_id": store.foreign_org})
    with pytest.raises(AppException, match="无权"):
        run(service.detail(quote["id"], stranger))
    body = store.body.model_copy(update={"version_no": quote["version_no"], "lines": [store.body.lines[0].model_copy(update={"id": uuid4()})]})
    with pytest.raises(AppException, match="不属于"):
        run(service.save(quote["id"], body, store.user))
    assert len(run(service.detail(quote["id"], store.user))["lines"]) == 1


def test_return_requires_reason_and_blocks_business_edit_until_return(store):
    quote = submit(store)
    with pytest.raises(AppException, match="状态"):
        run(service.save(quote["id"], store.body.model_copy(update={"version_no": quote["version_no"]}), store.user))
    with pytest.raises(AppException, match="原因"):
        run(service.command(quote["id"], "return", QuotationCommand(version_no=quote["version_no"]), store.user))
    quote = run(service.command(quote["id"], "return", QuotationCommand(version_no=quote["version_no"], note="补充图纸"), store.user))
    assert quote["status_code"] == "draft" and quote["return_reason"] == "补充图纸"


def test_business_does_not_receive_internal_engineering_note(store):
    quote = submit(store)
    with Session(store.engine) as session:
        line = session.get(MesQuotationLine, UUID(quote["lines"][0]["id"]))
        line.engineering_note = "内部成本依据"
        session.commit()
    user = NS(**{**vars(store.user), "permissions": ["mes:quotation:list"]})
    assert "engineering_note" not in run(service.detail(quote["id"], user))["lines"][0]


def test_self_scope_cannot_use_global_list_to_gain_action_access(store):
    quote = create(store)
    user = NS(**{**vars(store.reviewer), "permission_scopes": {**store.reviewer.permission_scopes, "mes:quotation:manage": "self"}})
    with pytest.raises(AppException, match="无权"):
        run(service.save(quote["id"], store.body.model_copy(update={"version_no": quote["version_no"]}), user))


def test_missing_files_and_incomplete_prices_cannot_advance(store):
    quote = create(store)
    with pytest.raises(AppException, match="图纸"):
        run(service.command(quote["id"], "submit", QuotationCommand(version_no=quote["version_no"]), store.user))
    attach(store, quote)
    quote = run(service.command(quote["id"], "submit", QuotationCommand(version_no=quote["version_no"]), store.user))
    with pytest.raises(AppException, match="材料"):
        run(service.command(quote["id"], "finish", QuotationCommand(version_no=quote["version_no"]), store.user))


@pytest.mark.parametrize("field,label", [("description", "描述"), ("customer_material", "客户材料")])
def test_missing_basic_requirement_cannot_be_saved_or_submitted(store, field, label):
    line = store.body.lines[0].model_copy(update={field: ""})
    body = store.body.model_copy(update={"lines": [line]})
    for submitting in (False, True):
        with pytest.raises(AppException, match=label):
            run(service.save(None, body, store.user, submit=submitting))
    assert run(service.page(store.user))["total"] == 0


def test_submit_missing_file_does_not_create_saved_quote(store):
    with pytest.raises(AppException, match="P1.*图纸"):
        run(service.save(None, store.body, store.user, submit=True))
    assert run(service.page(store.user))["total"] == 0


def pending_uploads(store, monkeypatch, invalid=None):
    async def pending(session, identifier, **kwargs):
        if identifier == invalid:
            raise AppException("附件已失效，请重新上传", 422)
        return NS(content_type="application/pdf"), b"%PDF-"
    async def bind(*args, **kwargs):
        return None
    monkeypatch.setattr(module.files, "read_pending_for_ingest", pending)
    monkeypatch.setattr(module.files, "bind", bind)


def test_new_quote_is_saved_and_submitted_as_one_action(store, monkeypatch):
    pending_uploads(store, monkeypatch)
    line = store.body.lines[0].model_copy(update={"files": [module_file(store.attachment_id)]})
    result = run(service.save(None, store.body.model_copy(update={"lines": [line]}), store.user, submit=True))
    assert result["status_code"] == "pending"
    assert result["lines"][0]["files"][0]["attachment_id"] == str(store.attachment_id)
    assert [row["action_key"] for row in result["events"]] == ["submit"]


def module_file(identifier):
    from app.modules.mes.quotation_schemas import QuotationFileBody
    return QuotationFileBody(attachment_id=identifier, kind="pdf")


@pytest.mark.parametrize("existing", [False, True])
def test_attachment_failure_rolls_back_entire_submission(store, monkeypatch, existing):
    original = create(store) if existing else None
    bad_id = uuid4()
    pending_uploads(store, monkeypatch, invalid=bad_id)
    first = store.body.lines[0].model_copy(update={"files": [module_file(store.attachment_id)],
        **({"id": UUID(original["lines"][0]["id"])} if original else {})})
    second = first.model_copy(update={"id": None, "drawing_no": "P2", "files": [module_file(bad_id)]})
    body = store.body.model_copy(update={"title": "不应保存的改动", "version_no": original["version_no"] if original else 1,
        "lines": [first, second]})
    with pytest.raises(AppException, match="附件已失效"):
        run(service.save(original["id"] if original else None, body, store.user, submit=True))
    assert run(service.page(store.user))["total"] == (1 if existing else 0)
    if original:
        loaded = run(service.detail(original["id"], store.user))
        assert loaded["title"] == original["title"]
        assert loaded["status_code"] == "draft" and loaded["version_no"] == original["version_no"]
        assert len(loaded["lines"]) == 1 and not loaded["lines"][0]["files"]
        assert [row["action_key"] for row in loaded["events"]] == ["save"]
    else:
        with Session(store.engine) as session:
            assert session.execute(select(MesQuotationLine)).scalars().all() == []
            assert session.execute(select(MesQuotationFile)).scalars().all() == []
            assert session.execute(select(MesQuotationEvent)).scalars().all() == []


def test_engineering_submission_validates_before_commit(store):
    original = submit(store)
    body = EngineeringBody(version_no=original["version_no"], lines=[dict(
        id=original["lines"][0]["id"], unit_price=99)])
    with pytest.raises(AppException, match="P1.*采用材料"):
        run(service.engineering(original["id"], body, store.user, submit=True))
    loaded = run(service.detail(original["id"], store.user))
    assert loaded["status_code"] == "pending" and loaded["version_no"] == original["version_no"]
    assert loaded["lines"][0]["unit_price"] is None
    body.lines[0].quoted_material = "AL6082"
    submitted = run(service.engineering(original["id"], body, store.user, submit=True))
    assert submitted["status_code"] == "review"
    from decimal import Decimal
    assert Decimal(submitted["lines"][0]["unit_price"]) == Decimal("99")
    assert submitted["events"][-1]["action_key"] == "finish"
    assert not any(row["action_key"] == "engineering" for row in submitted["events"])


@pytest.mark.parametrize("scope", ["new", "existing", "engineering", "approval"])
def test_atomic_submit_routes_accept_current_form_body(store, monkeypatch, scope):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.modules.mes.quotation_api import router
    calls = []
    async def save(identifier, body, user, **options):
        calls.append((identifier, body, user, options))
        return {"status_code": "review" if scope == "engineering" else "pending"}
    monkeypatch.setattr(service, "save", save)
    monkeypatch.setattr(service, "engineering", save)
    monkeypatch.setattr(service, "approve", save)
    app = FastAPI()
    app.include_router(router, prefix="/api/mes")
    for route in router.routes:
        for dependency in route.dependant.dependencies:
            app.dependency_overrides[dependency.call] = lambda: store.user
    identifier = uuid4()
    path = "/api/mes/quotations/submit" if scope == "new" else f"/api/mes/quotations/{identifier}/submit"
    body = store.body.model_dump(mode="json")
    if scope == "engineering":
        path = f"/api/mes/quotations/{identifier}/engineering/submit"
        body = EngineeringBody(version_no=3, lines=[dict(id=uuid4(), quoted_material="6082", unit_price=12)]).model_dump(mode="json")
    if scope == "approval":
        path = f"/api/mes/quotations/{identifier}/approve"
        body = QuotationApprovalBody(version_no=3, lines=[dict(id=uuid4(), lead_days=14)]).model_dump(mode="json")
    with TestClient(app) as client:
        result = client.post(path, json=body)
    assert result.status_code == 200 and result.json()["code"] == 0
    assert len(calls) == 1 and calls[0][3] == ({} if scope == "approval" else {"submit": True})
    assert calls[0][0] == (None if scope == "new" else identifier)
    assert calls[0][1].version_no == body["version_no"]


def test_export_client_text_cannot_become_formula(store):
    quote = create(store)
    quote["lines"][0]["description"] = '=HYPERLINK("https://example.invalid")'
    quote["lines"][0]["engineering_note"] = "不能导出"
    book = load_workbook(BytesIO(workbook(quote)))
    assert book.active["D4"].data_type == "s"
    assert "不能导出" not in str(list(book.active.values))


def test_negative_nonfinite_and_excess_precision_rejected(store):
    with pytest.raises(ValidationError):
        EngineeringBody(version_no=1, lines=[dict(id=uuid4(), unit_price="NaN")])
    with pytest.raises(ValidationError):
        EngineeringBody(version_no=1, lines=[dict(id=uuid4(), unit_price="1.001")])
    with pytest.raises(ValidationError):
        QuotationBody(**{**store.body.model_dump(), "lines": [{**store.body.lines[0].model_dump(), "quantity": -1}]})


def test_adopt_requires_explicit_human_confirmation(store):
    quote = price(store, submit(store))
    user = NS(**{**vars(store.user), "permissions": [*store.user.permissions, "mes:quote:list"]})
    with pytest.raises(AppException, match="复核"):
        run(service.adopt(quote["id"], quote["lines"][0]["id"], QuotationAdoptBody(
            version_no=quote["version_no"], cnc_quote_id=uuid4()), user))


def test_revision_preserves_approved_source_and_prevents_two_open_revisions(store):
    quote = price(store, submit(store))
    quote = run(service.command(quote["id"], "finish", QuotationCommand(version_no=quote["version_no"]), store.user))
    quote = run(service.approve(quote["id"], approval(quote), store.reviewer))
    quote = final_approval(quote, store.reviewer)
    revised = run(service.revise(quote["id"], QuotationCommand(version_no=quote["version_no"]), store.user))
    assert revised["revision"] == 2 and revised["status_code"] == "draft"
    assert revised["lines"][0]["files"][0]["attachment_id"] == str(store.attachment_id)
    assert revised["lines"][0]["adopted_cnc_quote_id"] is None
    assert revised["lines"][0]["lead_days"] is None
    assert run(service.detail(quote["id"], store.user))["status_code"] == "quoted"
    with pytest.raises(AppException, match="未完成修订"):
        run(service.revise(quote["id"], QuotationCommand(version_no=quote["version_no"]), store.user))
    run(service.delete_draft(revised["id"], revised["version_no"], store.user))
    following = run(service.revise(quote["id"], QuotationCommand(version_no=quote["version_no"]), store.user))
    assert following["revision"] == 3


def test_delete_draft_checks_version_and_scope_and_preserves_audit(store):
    quote = create(store)
    identifier = UUID(quote["id"])
    outside = NS(**{**vars(store.user), "org_id": store.foreign_org})
    with pytest.raises(AppException) as error:
        run(service.delete_draft(identifier, quote["version_no"], outside))
    assert error.value.status_code == 404
    with pytest.raises(AppException, match="其他人员修改"):
        run(service.delete_draft(identifier, quote["version_no"] + 1, store.user))
    assert run(service.delete_draft(identifier, quote["version_no"], store.user)) == {"id": str(identifier)}
    assert run(service.page(store.user))["total"] == 0
    with pytest.raises(AppException) as error:
        run(service.detail(identifier, store.user))
    assert error.value.status_code == 404
    with Session(store.engine) as session:
        stored = session.get(module.MesQuotation, identifier)
        assert stored.deleted_at and stored.deleted_by == store.user.user_id
        assert stored.version_no == quote["version_no"] + 1
        assert session.get(MesQuotationLine, UUID(quote["lines"][0]["id"])) is not None
        event = session.execute(select(MesQuotationEvent).where(
            MesQuotationEvent.quotation_id == identifier, MesQuotationEvent.action_key == "delete")).scalar_one()
        assert event.created_by == store.user.user_id and event.version_no_snapshot == stored.version_no


def test_cannot_delete_a_submitted_quotation(store):
    quote = submit(store)
    with pytest.raises(AppException, match="仅业务录入"):
        run(service.delete_draft(quote["id"], quote["version_no"], store.user))
    assert run(service.detail(quote["id"], store.user))["status_code"] == "pending"


def test_removed_line_and_reordered_lines_can_be_saved_repeatedly(store):
    quote = create(store)
    second = store.body.lines[0].model_copy(update={"drawing_no": "P2"})
    body = store.body.model_copy(update={"version_no": quote["version_no"], "lines": [second]})
    quote = run(service.save(quote["id"], body, store.user))
    body = store.body.model_copy(update={"version_no": quote["version_no"], "lines": [store.body.lines[0]]})
    quote = run(service.save(quote["id"], body, store.user))
    assert quote["lines"][0]["drawing_no"] == "P1"


def test_adopt_binds_real_snapshot_and_uses_confirmed_currency_conversion(store, monkeypatch):
    quote = price(store, submit(store))
    part_id, cnc_quote_id = uuid4(), uuid4()
    with store.engine.begin() as connection:
        connection.exec_driver_sql("INSERT INTO mes_cnc_part (id) VALUES (?)", (part_id.hex,))
        connection.exec_driver_sql("INSERT INTO mes_cnc_quote (id) VALUES (?)", (cnc_quote_id.hex,))
    with Session(store.engine) as session:
        line = session.get(MesQuotationLine, UUID(quote["lines"][0]["id"]))
        bindings = session.execute(select(MesQuotationFile).where(MesQuotationFile.line_id == line.id)).scalars().all()
        session.add(MesQuotationCnc(org_id=store.user.org_id, line_id=line.id, part_id=part_id,
            source_hash=module.source_hash(line, bindings), created_by=store.user.user_id))
        session.commit()
    async def part(*args, **kwargs):
        return NS(id=part_id, org_id=store.user.org_id, version_no=1, material="核价采用材料", quantity=10, treatment="")
    async def snapshots(*args, **kwargs):
        return [NS(id=cnc_quote_id, approved_by=None, version_no=1, unit_price="80.00", result_snapshot={"currency": "CNY"}, inputs_snapshot={})]
    async def active(*args, **kwargs): return None
    async def no_jobs(*args, **kwargs): return None
    monkeypatch.setattr(module.cnc_repo, "part", part)
    monkeypatch.setattr(module.cnc_repo, "quotes", snapshots)
    monkeypatch.setattr(module.cnc_repo, "active", active)
    monkeypatch.setattr(module.cnc_repo, "jobs", no_jobs)
    user = NS(**{**vars(store.user), "permissions": [*store.user.permissions, "mes:quote:list"]})
    body = QuotationAdoptBody(version_no=quote["version_no"], cnc_quote_id=cnc_quote_id,
        exchange_rate="8", is_confirmed=True)
    adopted = run(service.adopt(quote["id"], UUID(quote["lines"][0]["id"]), body, user))
    assert adopted["currency"] == "EUR"
    assert adopted["lines"][0]["unit_price"] == "10.00"
    assert adopted["lines"][0]["adopted_cnc_quote_id"] == str(cnc_quote_id)
    assert adopted["lines"][0]["lead_days"] is None
    assert adopted["status_code"] == "pricing"
    assert run(module.cnc_repo.quotes(None, part_id))[0].approved_by is None
    with Session(store.engine) as session:
        line = session.get(MesQuotationLine, UUID(quote["lines"][0]["id"]))
        line.quantity = 11
        session.commit()
    with pytest.raises(AppException, match="来源已变化"):
        run(service.adopt(quote["id"], UUID(quote["lines"][0]["id"]), body.model_copy(update={"version_no": adopted["version_no"]}), user))


def test_cnc_configuration_failure_is_actionable_without_uploading_or_calling_model(store, monkeypatch):
    quote = submit(store)
    keys = ("mes:quote:list", "mes:quote:manage", "mes:quote:analyze")
    user = NS(**{**vars(store.user), "permissions": [*store.user.permissions, *keys],
        "permission_scopes": {**store.user.permission_scopes, **{key: "organization" for key in keys}}})
    def invalid(*args, **kwargs): raise ValueError("请先配置模型服务")
    monkeypatch.setattr(module, "analysis_plan", invalid)
    monkeypatch.setattr(module, "cnc_settings", lambda: None)
    with pytest.raises(AppException, match="配置模型") as error:
        run(service.prepare_cnc(quote["id"], UUID(quote["lines"][0]["id"]), QuotationCncBody(
            version_no=quote["version_no"], cloud_allowed=True), user))
    assert error.value.status_code == 422
    with Session(store.engine) as session:
        assert session.execute(select(MesQuotationCnc)).scalars().all() == []


def test_upload_rejects_mismatched_file_content_before_file_service(store):
    class Upload:
        filename = "不是PDF.pdf"
        async def read(self, size): return b"not a PDF"
    with pytest.raises(AppException, match="内容与扩展名"):
        run(service.upload(Upload(), store.user))


def test_file_content_reader_denies_before_storage_access(monkeypatch):
    from app.modules.file import service as file_module
    async def missing(*args, **kwargs): return None
    monkeypatch.setattr(file_module.repository, "file_for_read", missing)
    with pytest.raises(AppException, match="无权访问"):
        run(file_module.service.read_content(None, uuid4(), user=NS(user_id=uuid4())))


def test_customer_or_currency_change_requires_price_reconfirmation(store):
    quote = price(store, submit(store))
    quote = run(service.command(quote["id"], "return", QuotationCommand(version_no=quote["version_no"], note="调整币种"), store.user))
    line = store.body.lines[0].model_copy(update={"id": UUID(quote["lines"][0]["id"]),
        "files": []})
    body = store.body.model_copy(update={"version_no": quote["version_no"], "currency": "USD", "lines": [line]})
    saved = run(service.save(quote["id"], body, store.user))
    assert saved["currency"] == "USD" and saved["lines"][0]["unit_price"] is None


# 批量采用使用实际询价持久化和权限范围，仅替换外部 CNC 核价读取。
def batch_case(store, monkeypatch):
    store.body = store.body.model_copy(update={"lines": [store.body.lines[0].model_copy(
        update={"drawing_no": f"P{index + 1}"}) for index in range(3)]})
    quote = create(store)
    parts, snapshots, lines_by_part = {}, {}, {}
    with store.engine.begin() as connection:
        identifiers = [(uuid4(), uuid4()) for _ in quote["lines"]]
        for part_id, snapshot_id in identifiers:
            connection.exec_driver_sql("INSERT INTO mes_cnc_part (id) VALUES (?)", (part_id.hex,))
            connection.exec_driver_sql("INSERT INTO mes_cnc_quote (id) VALUES (?)", (snapshot_id.hex,))
    with Session(store.engine) as session:
        for value, (part_id, snapshot_id) in zip(quote["lines"], identifiers):
            line = session.get(MesQuotationLine, UUID(value["id"]))
            session.add(MesQuotationFile(org_id=store.user.org_id, line_id=line.id,
                attachment_id=store.attachment_id, kind="pdf", created_by=store.user.user_id))
            session.flush()
            bindings = session.execute(select(MesQuotationFile).where(MesQuotationFile.line_id == line.id)).scalars().all()
            session.add(MesQuotationCnc(org_id=store.user.org_id, line_id=line.id, part_id=part_id,
                source_hash=module.source_hash(line, bindings), created_by=store.user.user_id))
            parts[part_id] = NS(id=part_id, org_id=store.user.org_id, quantity=10,
                treatment="", material="核价材料", version_no=1)
            snapshots[part_id] = NS(id=snapshot_id, approved_by=None, version_no=1,
                unit_price="80.00", result_snapshot={"currency": "CNY"}, inputs_snapshot={})
            lines_by_part[part_id] = line.id
        session.commit()
    async def part(session, identifier, user, permission, **kwargs):
        assert permission == "mes:quote:list"
        return parts[identifier]
    async def history(session, identifier): return [snapshots[identifier]]
    async def empty(*args): return None
    async def finished(*args): return NS(status_code="completed", stage="解析完成")
    monkeypatch.setattr(module.cnc_repo, "part", part)
    monkeypatch.setattr(module.cnc_repo, "quotes", history)
    monkeypatch.setattr(module.cnc_repo, "jobs", finished)
    monkeypatch.setattr(module.cnc_repo, "active", empty)
    user = cnc_reader(store)
    quote = run(service.command(quote["id"], "submit", QuotationCommand(version_no=quote["version_no"]), user))
    return NS(quote=quote, user=user, parts=parts, snapshots=snapshots, line_ids=lines_by_part)


def batch_body(case):
    return QuotationBatchAdopt(version_no=case.quote["version_no"], is_confirmed=True, exchange_rate="8", lines=[
        dict(line_id=line_id, cnc_quote_id=case.snapshots[part_id].id)
        for part_id, line_id in case.line_ids.items()])


def test_batch_preview_reports_blocked_rows_and_does_not_write(store, monkeypatch):
    case = batch_case(store, monkeypatch)
    list(case.parts.values())[1].version_no = 2
    result = run(service.adoption_preview(case.quote["id"], QuotationAdoptionPreview(
        version_no=case.quote["version_no"], line_ids=list(case.line_ids.values())), case.user))
    assert [row["can_adopt"] for row in result["items"]] == [True, False, True]
    assert "依据已更新" in result["items"][1]["message"]
    assert "cnc_quote_id" not in result["items"][1]
    loaded = run(service.detail(case.quote["id"], case.user))
    assert loaded["version_no"] == case.quote["version_no"]
    assert all(row["unit_price"] is None and row["adopted_cnc_quote_id"] is None for row in loaded["lines"])
    assert loaded["events"] == case.quote["events"]


def test_batch_adoption_commits_valid_rows_once_and_reports_individual_failures(store, monkeypatch):
    case = batch_case(store, monkeypatch)
    list(case.parts.values())[1].version_no = 2
    list(case.snapshots.values())[2].result_snapshot["weight_estimate"] = {
        "method_key": "cad_volume", "net_weight_kg": "0.162000"
    }
    result = run(service.adopt_batch(case.quote["id"], batch_body(case), case.user))
    assert [row["is_success"] for row in result["items"]] == [True, False, True]
    assert result["items"][1]["code"] == 409
    quote = result["quotation"]
    assert quote["version_no"] == case.quote["version_no"] + 1
    assert quote["currency"] == "EUR" and quote["status_code"] == "pricing"
    assert [row["unit_price"] for row in quote["lines"]] == ["10.00", None, "10.00"]
    assert [row["weight_kg"] for row in quote["lines"]] == [None, None, "0.162000"]
    assert all(row["lead_days"] is None for row in quote["lines"])
    assert quote["events"][-1]["note"].startswith("批量采用 2 项核价")
    assert len(quote["events"]) == len(case.quote["events"]) + 1
    loaded = run(service.detail(case.quote["id"], case.user))
    fields = ("id", "unit_price", "quoted_material", "adopted_cnc_quote_id", "lead_days", "updated_by")
    assert [{key: row[key] for key in fields} for row in loaded["lines"]] == [
        {key: row[key] for key in fields} for row in quote["lines"]]


def test_batch_rechecks_snapshot_after_preview_and_does_not_increment_version_if_all_fail(store, monkeypatch):
    case = batch_case(store, monkeypatch)
    body = batch_body(case)
    for snapshot in case.snapshots.values():
        snapshot.id = uuid4()
    result = run(service.adopt_batch(case.quote["id"], body, case.user))
    assert all(not item["is_success"] and "快照已变化" in item["message"] for item in result["items"])
    assert result["quotation"]["version_no"] == case.quote["version_no"]
    assert result["quotation"]["events"] == case.quote["events"]


def test_batch_unexpected_failure_rolls_back_all_writes(store, monkeypatch):
    case = batch_case(store, monkeypatch)
    async def unavailable(*args): raise RuntimeError("文件服务不可用")
    with monkeypatch.context() as temporary:
        temporary.setattr(module.files, "download_url", unavailable)
        with pytest.raises(RuntimeError, match="文件服务不可用"):
            run(service.adopt_batch(case.quote["id"], batch_body(case), case.user))
    loaded = run(service.detail(case.quote["id"], case.user))
    assert loaded["version_no"] == case.quote["version_no"]
    assert loaded["events"] == case.quote["events"]
    assert all(row["adopted_cnc_quote_id"] is None for row in loaded["lines"])


@pytest.mark.parametrize("permission", ["mes:quotation:list", "mes:quotation:price", "mes:quote:list"])
def test_batch_permissions_and_read_preview_require_same_authorization(store, monkeypatch, permission):
    case = batch_case(store, monkeypatch)
    case.user.permissions.remove(permission)
    for operation, body in ((service.adopt_batch, batch_body(case)), (service.adoption_preview,
            QuotationAdoptionPreview(version_no=case.quote["version_no"], line_ids=list(case.line_ids.values())))):
        with pytest.raises(AppException) as error:
            run(operation(case.quote["id"], body, case.user))
        assert error.value.status_code == 403


@pytest.mark.parametrize("action", ["preview", "adopt"])
def test_batch_respects_quotation_scope_and_stale_versions(store, monkeypatch, action):
    case = batch_case(store, monkeypatch)
    body = batch_body(case) if action == "adopt" else QuotationAdoptionPreview(
        version_no=case.quote["version_no"], line_ids=list(case.line_ids.values()))
    operation = service.adopt_batch if action == "adopt" else service.adoption_preview
    with pytest.raises(AppException) as error:
        run(operation(case.quote["id"], body.model_copy(update={"version_no": 999}), case.user))
    assert error.value.status_code == 409
    case.user.user_id = store.reviewer.user_id
    case.user.permission_scopes["mes:quotation:price"] = "self"
    with pytest.raises(AppException) as error:
        run(operation(case.quote["id"], body, case.user))
    assert error.value.status_code == 404


def test_batch_confirmation_and_duplicate_or_invalid_items_are_rejected(store, monkeypatch):
    case = batch_case(store, monkeypatch)
    body = batch_body(case)
    with pytest.raises(AppException, match="确认"):
        run(service.adopt_batch(case.quote["id"], body.model_copy(update={"is_confirmed": False}), case.user))
    with pytest.raises(ValidationError, match="不重复"):
        QuotationBatchAdopt(version_no=1, lines=[body.lines[0], body.lines[0]])
    with pytest.raises(ValidationError):
        QuotationBatchAdopt(version_no=1, lines=[dict(line_id=uuid4(), cnc_quote_id=uuid4(), final_unit_price="NaN")])
    with pytest.raises(ValidationError):
        QuotationAdoptionPreview(version_no=1, line_ids=[uuid4()] * 501)


@pytest.mark.parametrize("action", ["adoption-preview", "adopt-batch"])
def test_batch_http_routes(store, monkeypatch, action):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.modules.mes.quotation_api import router
    calls = []
    async def execute(identifier, body, user):
        calls.append((identifier, body, user))
        return {"items": []}
    monkeypatch.setattr(service, "adoption_preview", execute)
    monkeypatch.setattr(service, "adopt_batch", execute)
    app = FastAPI()
    app.include_router(router, prefix="/api/mes")
    for route in router.routes:
        for dependency in route.dependant.dependencies:
            app.dependency_overrides[dependency.call] = lambda: store.user
    identifier = uuid4()
    body = dict(version_no=2, line_ids=[str(uuid4())]) if action == "adoption-preview" else dict(
        version_no=2, is_confirmed=True, lines=[dict(line_id=str(uuid4()), cnc_quote_id=str(uuid4()))])
    with TestClient(app) as client:
        response = client.post(f"/api/mes/quotations/{identifier}/{action}", json=body)
    assert response.status_code == 200 and response.json()["data"] == {"items": []}
    assert len(calls) == 1 and calls[0][0] == identifier


def test_engineer_adopts_unreviewed_ai_results_then_boss_approves_final_quotation(store, monkeypatch):
    case = batch_case(store, monkeypatch)
    assert "mes:quote:approve" not in case.user.permissions
    assert all(snapshot.approved_by is None for snapshot in case.snapshots.values())
    preview = run(service.adoption_preview(case.quote["id"], QuotationAdoptionPreview(
        version_no=case.quote["version_no"], line_ids=list(case.line_ids.values())), case.user))
    assert all(row["can_adopt"] for row in preview["items"])
    adopted = run(service.adopt_batch(case.quote["id"], batch_body(case), case.user))["quotation"]
    assert adopted["status_code"] == "pricing"
    assert all(snapshot.approved_by is None for snapshot in case.snapshots.values())
    submitted = run(service.command(adopted["id"], "finish", QuotationCommand(
        version_no=adopted["version_no"]), case.user))
    assert submitted["status_code"] == "review"
    with pytest.raises(AppException) as error:
        run(service.approve(submitted["id"], approval(submitted), case.user))
    assert error.value.status_code == 403
    approved = run(service.approve(submitted["id"], approval(submitted), store.reviewer))
    assert approved["status_code"] == "final_review"
    assert all(row["lead_days"] == 14 for row in approved["lines"])
    assert all(snapshot.approved_by is None for snapshot in case.snapshots.values())
    assert [row["action_key"] for row in approved["events"]][-3:] == ["adopt", "finish", "approve"]
    assert final_approval(approved, store.reviewer)["status_code"] == "quoted"


@pytest.mark.parametrize("status", ["queued", "running", "failed"])
def test_adoption_still_rejects_unfinished_or_failed_analysis(store, monkeypatch, status):
    case = batch_case(store, monkeypatch)
    blocked_part = list(case.parts)[1]
    async def latest_job(session, identifier):
        return NS(status_code=status, stage=f"任务 {status}") if identifier == blocked_part else None
    monkeypatch.setattr(module.cnc_repo, "jobs", latest_job)
    preview = run(service.adoption_preview(case.quote["id"], QuotationAdoptionPreview(
        version_no=case.quote["version_no"], line_ids=list(case.line_ids.values())), case.user))
    assert [row["can_adopt"] for row in preview["items"]] == [True, False, True]
    assert "尚未成功完成" in preview["items"][1]["message"]
    result = run(service.adopt_batch(case.quote["id"], batch_body(case), case.user))
    assert [row["is_success"] for row in result["items"]] == [True, False, True]


@pytest.mark.parametrize("currency,rate,expected", [("CNY", None, "80.00"), ("EUR", "8", "10.00"), ("USD", "7", "11.43")])
def test_blank_prices_are_filled_from_ai_snapshot_in_quotation_currency(store, monkeypatch, currency, rate, expected):
    case = batch_case(store, monkeypatch)
    with Session(store.engine) as session:
        quote = session.get(MesQuotation, UUID(case.quote["id"]))
        quote.currency = currency
        session.commit()
    body = QuotationBatchAdopt(version_no=case.quote["version_no"], is_confirmed=True,
        exchange_rate=rate, lines=[dict(line_id=line_id, cnc_quote_id=case.snapshots[part_id].id)
            for part_id, line_id in case.line_ids.items()])
    preview = run(service.adoption_preview(case.quote["id"], QuotationAdoptionPreview(
        version_no=case.quote["version_no"], line_ids=list(case.line_ids.values()), exchange_rate=rate), case.user))
    assert all(item["suggested_unit_price"] == expected and item["cnc_currency"] == "CNY" for item in preview["items"])
    result = run(service.adopt_batch(case.quote["id"], body, case.user))
    assert all(item["is_success"] for item in result["items"])
    assert all(item["unit_price"] == expected for item in result["quotation"]["lines"])
    assert result["quotation"]["status_code"] == "pricing"
    assert all(item["lead_days"] is None for item in result["quotation"]["lines"])
    assert "AI 核价自动回填 3 项" in result["quotation"]["events"][-1]["note"]
    if rate:
        assert f"1 {currency} = {rate} CNY" in result["quotation"]["events"][-1]["note"]


def test_single_adoption_can_omit_price_and_rounds_half_up(store, monkeypatch):
    case = batch_case(store, monkeypatch)
    part_id, line_id = next(iter(case.line_ids.items()))
    case.snapshots[part_id].unit_price = "1.00"
    result = run(service.adopt(case.quote["id"], line_id, QuotationAdoptBody(
        version_no=case.quote["version_no"], cnc_quote_id=case.snapshots[part_id].id,
        exchange_rate="8", is_confirmed=True), case.user))
    assert result["lines"][0]["unit_price"] == "0.13"
    assert result["lines"][0]["adopted_cnc_quote_id"] == str(case.snapshots[part_id].id)


def test_missing_exchange_rate_does_not_copy_cny_cost_into_eur_price(store, monkeypatch):
    case = batch_case(store, monkeypatch)
    preview = run(service.adoption_preview(case.quote["id"], QuotationAdoptionPreview(
        version_no=case.quote["version_no"], line_ids=list(case.line_ids.values())), case.user))
    assert all(item["can_adopt"] and item["suggested_unit_price"] is None for item in preview["items"])
    assert all("汇率" in item["price_message"] for item in preview["items"])
    body = QuotationBatchAdopt(version_no=case.quote["version_no"], is_confirmed=True,
        lines=[dict(line_id=line_id, cnc_quote_id=case.snapshots[part_id].id)
            for part_id, line_id in case.line_ids.items()])
    result = run(service.adopt_batch(case.quote["id"], body, case.user))
    assert all(not item["is_success"] and "汇率" in item["message"] for item in result["items"])
    assert result["quotation"]["version_no"] == case.quote["version_no"]
    assert all(line["unit_price"] is None for line in result["quotation"]["lines"])


@pytest.mark.parametrize("value", ["0.00", "19.99"])
def test_engineer_can_manually_adjust_price_after_adopting_ai_quote(store, monkeypatch, value):
    case = batch_case(store, monkeypatch)
    adopted = run(service.adopt_batch(case.quote["id"], batch_body(case), case.user))["quotation"]
    body = EngineeringBody(version_no=adopted["version_no"], lines=[dict(id=line["id"],
        quoted_material=line["quoted_material"], unit_price=value if index == 0 else line["unit_price"])
        for index, line in enumerate(adopted["lines"])])
    result = run(service.engineering(case.quote["id"], body, case.user))
    assert result["lines"][0]["unit_price"] == value
    assert result["lines"][1]["unit_price"] == "10.00"
    assert result["status_code"] == "pricing"


def test_adoption_without_rate_does_not_claim_success_by_retaining_old_price(store, monkeypatch):
    case = batch_case(store, monkeypatch)
    with Session(store.engine) as session:
        session.get(MesQuotationLine, next(iter(case.line_ids.values()))).unit_price = 0
        session.commit()
    body = QuotationBatchAdopt(version_no=case.quote["version_no"], is_confirmed=True,
        lines=[dict(line_id=line_id, cnc_quote_id=case.snapshots[part_id].id)
            for part_id, line_id in case.line_ids.items()])
    result = run(service.adopt_batch(case.quote["id"], body, case.user))
    assert [item["is_success"] for item in result["items"]] == [False, False, False]
    assert result["quotation"]["lines"][0]["unit_price"] == "0.00"


@pytest.mark.parametrize("rate", [0, -1, "NaN", "Infinity", "1000001"])
def test_invalid_exchange_rates_rejected(rate):
    with pytest.raises(ValidationError):
        QuotationAdoptBody(version_no=1, cnc_quote_id=uuid4(), exchange_rate=rate, is_confirmed=True)


@pytest.mark.parametrize("single", [False, True])
def test_explicit_ai_price_replaces_existing_price_even_after_engineering_save(store, monkeypatch, single):
    case = batch_case(store, monkeypatch)
    with Session(store.engine) as session:
        for identifier in case.line_ids.values():
            line = session.get(MesQuotationLine, identifier)
            line.unit_price = 12
            line.weight_kg = Decimal("0.5")
            link = session.execute(select(MesQuotationCnc).where(MesQuotationCnc.line_id == identifier)).scalar_one()
            bindings = session.execute(select(MesQuotationFile).where(MesQuotationFile.line_id == identifier)).scalars().all()
            link.source_hash = module.source_hash(line, bindings, legacy=True)
        session.commit()
    snapshots = list(case.snapshots.values())
    snapshots[0].result_snapshot["weight_estimate"] = {"method_key": "cad_volume", "net_weight_kg": "0.162000", "stock_weight_kg": "0.534600"}
    snapshots[1].result_snapshot["weight_estimate"] = {"method_key": "model_bounds", "net_weight_kg": None, "estimated_weight_kg": "0.27"}
    preview = run(service.adoption_preview(case.quote["id"], QuotationAdoptionPreview(
        version_no=case.quote["version_no"], line_ids=list(case.line_ids.values())), case.user))
    assert [item["net_weight_kg"] for item in preview["items"]] == ["0.162000", None, None]
    if single:
        part_id, line_id = next(iter(case.line_ids.items()))
        quote = run(service.adopt(case.quote["id"], line_id, QuotationAdoptBody(
            version_no=case.quote["version_no"], cnc_quote_id=case.snapshots[part_id].id,
            is_confirmed=True, exchange_rate="8"), case.user))
        assert quote["lines"][0]["unit_price"] == "10.00"
        assert quote["lines"][1]["unit_price"] == "12.00"
    else:
        body = QuotationBatchAdopt(version_no=case.quote["version_no"], is_confirmed=True, exchange_rate="8",
            lines=[dict(line_id=line_id, cnc_quote_id=case.snapshots[part_id].id)
                for part_id, line_id in case.line_ids.items()])
        result = run(service.adopt_batch(case.quote["id"], body, case.user))
        assert all(item["is_success"] for item in result["items"])
        quote = result["quotation"]
        assert [item["unit_price"] for item in quote["lines"]] == ["10.00"] * 3
    assert quote["status_code"] == "pricing"
    assert [Decimal(row["weight_kg"]) for row in quote["lines"]] == [Decimal("0.162"), Decimal("0.5"), Decimal("0.5")]
    assert all(not row["cnc_records"][0]["is_stale"] for row in quote["lines"])
    assert all(snapshot.approved_by is None for snapshot in case.snapshots.values())
    assert "1 EUR = 8 CNY" in quote["events"][-1]["note"]


def test_explicit_ai_price_without_rate_does_not_silently_keep_existing_price(store, monkeypatch):
    case = batch_case(store, monkeypatch)
    with Session(store.engine) as session:
        for identifier in case.line_ids.values(): session.get(MesQuotationLine, identifier).unit_price = 12
        session.commit()
    body = QuotationBatchAdopt(version_no=case.quote["version_no"], is_confirmed=True,
        lines=[dict(line_id=line_id, cnc_quote_id=case.snapshots[part_id].id)
            for part_id, line_id in case.line_ids.items()])
    result = run(service.adopt_batch(case.quote["id"], body, case.user))
    assert all(not item["is_success"] and "汇率" in item["message"] for item in result["items"])
    assert [item["unit_price"] for item in result["quotation"]["lines"]] == ["12.00"] * 3
    assert result["quotation"]["version_no"] == case.quote["version_no"]
    assert all(line["adopted_cnc_quote_id"] is None for line in result["quotation"]["lines"])


def test_adoption_cannot_accept_manual_price_override_or_a_preserve_flag():
    with pytest.raises(ValidationError):
        QuotationAdoptBody(version_no=1, cnc_quote_id=uuid4(), final_unit_price=12)
    with pytest.raises(ValidationError):
        QuotationBatchAdopt(version_no=1, lines=[dict(line_id=uuid4(), cnc_quote_id=uuid4(),
            is_use_ai_price=True, final_unit_price=12)])


def test_exchange_rate_scopes_quotation_before_requesting_public_data(store, monkeypatch):
    quote = create(store)
    user = cnc_reader(store)
    calls = []
    async def fetch(base, target):
        calls.append((base, target))
        return dict(base=base, quote=target, rate="8")
    monkeypatch.setattr(module.exchange_rates, "get", fetch)
    assert run(service.exchange_rate(quote["id"], "CNY", user))["rate"] == "8"
    assert calls == [(quote["currency"], "CNY")]
    for permission in ("mes:quotation:list", "mes:quotation:price"):
        restricted = NS(**{**vars(user), "user_id": store.reviewer.user_id,
            "permission_scopes": {**user.permission_scopes, permission: "self"}})
        with pytest.raises(AppException) as error:
            run(service.exchange_rate(quote["id"], "CNY", restricted))
        assert error.value.status_code == 404
    user.permissions = [key for key in user.permissions if key != "mes:quote:list"]
    with pytest.raises(AppException) as error:
        run(service.exchange_rate(quote["id"], "CNY", user))
    assert error.value.status_code == 403 and len(calls) == 1


def test_exchange_rate_route_has_typed_currency_and_actual_permission_dependency(store, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.modules.mes.quotation_api import router
    calls = []
    async def fetch(identifier, quote_currency, user):
        calls.append((identifier, quote_currency, user))
        return dict(rate="8.00000000")
    monkeypatch.setattr(service, "exchange_rate", fetch)
    app = FastAPI()
    app.include_router(router, prefix="/api/mes")
    for route in router.routes:
        for dependency in route.dependant.dependencies:
            app.dependency_overrides[dependency.call] = lambda: store.user
    identifier = uuid4()
    with TestClient(app) as client:
        path = f"/api/mes/quotations/{identifier}/exchange-rate"
        assert client.get(path, params={"quote_currency": "CNY"}).json()["data"]["rate"] == "8.00000000"
        assert client.get(path, params={"quote_currency": "BTC"}).status_code == 422
    assert calls == [(identifier, "CNY", store.user)]


@pytest.mark.parametrize("used_rate,expected,adjusted", [("8", "10.00", False), ("10", "8.00", True)])
def test_adoption_freezes_confirmed_fx_rate_source_and_date(store, monkeypatch, used_rate, expected, adjusted):
    from app.modules.mes import quotation_exchange_rates as fx
    monkeypatch.setattr(fx, "signing_key", lambda: b"test-only-key")
    reference = fx.seal_reference(dict(base="EUR", quote="CNY", rate="8.00000000",
        provider=fx.PROVIDER, rate_date="2026-11-05", fetched_at="2026-11-06T01:00:00+00:00"))
    case = batch_case(store, monkeypatch)
    body = batch_body(case).model_copy(update={"exchange_rate": Decimal(used_rate), "exchange_rate_reference": reference})
    adopted = run(service.adopt_batch(case.quote["id"], body, case.user))["quotation"]
    assert all(line["unit_price"] == expected for line in adopted["lines"])
    note = adopted["events"][-1]["note"]
    assert fx.PROVIDER in note and "参考日期 2026-11-05" in note
    assert f"1 EUR = {used_rate} CNY" in note
    assert ("已人工调整" in note) == adjusted
    # 后续读取不查询公开来源、不重算原单价，也不重写采用记录。
    async def forbidden(*args): raise AssertionError("不应重新获取已采用的汇率")
    monkeypatch.setattr(module.exchange_rates, "get", forbidden)
    reloaded = run(service.detail(adopted["id"], case.user))
    assert reloaded["events"][-1]["note"] == note
    assert all(line["unit_price"] == expected for line in reloaded["lines"])


def test_invalid_fx_reference_rolls_back_batch_prices_and_version(store, monkeypatch):
    case = batch_case(store, monkeypatch)
    body = batch_body(case).model_copy(update={"exchange_rate_reference": "tampered"})
    with pytest.raises(AppException, match="汇率参考信息无效"):
        run(service.adopt_batch(case.quote["id"], body, case.user))
    current = run(service.detail(case.quote["id"], case.user))
    assert current["version_no"] == case.quote["version_no"]
    assert all(line["adopted_cnc_quote_id"] is None for line in current["lines"])
