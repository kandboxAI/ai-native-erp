"""工艺分页完整性、正式档案关联及事务验证；只使用内存 SQLite。"""
import json
from decimal import Decimal
from types import SimpleNamespace as NS
from uuid import uuid4

import pytest
from sqlalchemy import Column, JSON, MetaData, Table, Uuid, create_engine, select, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session

from app.core.exceptions import AppException
from app.modules.mes.process_archive_import import read_pages, archive_values, service, stable_number
from app.modules.mes.process_archive_import import archive_repository, repository
from app.modules.mes.archive_models import MesProcess, MesEquipment, MesProcessDependency, MesEquipmentProcess
from app.modules.mes.external_import_models import MesExternalImportRow
from app.modules.mes.models import MesProcessTemplate, MesProcessTemplateOperation, MesWorkOrderOperation
from test_quotations import run


def raw(code="GY001", name="CNC", **extra):
    return dict(recordId=str(uuid4()), code=code, name=name, processingType="SELF_MADE", piecework=True,
        enableStatus="ENABLE", disabled=False, previousCraftList=[], nextCraftList=[]) | extra


def pages(tmp_path, rows, size=2):
    count = (len(rows) + size - 1) // size
    paths = []
    for page in range(count):
        path = tmp_path / f"{page}.json"
        path.write_text(json.dumps(dict(success=True, data=dict(totalPages=count, totalElements=len(rows),
            number=page, size=size, content=rows[page * size:(page + 1) * size], hasNext=page < count - 1))), encoding="utf-8")
        paths.append(path)
    return paths


def test_complete_pages_and_projection(tmp_path):
    rows = [raw(), raw("GY002", "QC", processingType="QC")]
    paths = pages(tmp_path, rows, size=1)
    parsed, files = read_pages(paths[::-1])
    assert parsed == rows and len(files) == 2
    values = archive_values(parsed[1])
    assert values["is_quality_required"] is True and values["processing_type_code"] == "in_house"
    assert "recordId" not in values and "jobPermissionsList" not in values


@pytest.mark.parametrize("failure", ["missing", "duplicate_page", "duplicate_code", "unknown_type", "dependency", "count", "status"])
def test_reject_invalid_source(tmp_path, failure):
    rows = [raw(), raw("GY002", "QA")]
    if failure == "duplicate_code": rows[1]["code"] = rows[0]["code"]
    if failure == "unknown_type": rows[1]["processingType"] = "UNKNOWN"
    if failure == "dependency": rows[1]["previousCraftList"] = [rows[0]["recordId"]]
    if failure == "status": rows[1]["disabled"] = True
    paths = pages(tmp_path, rows, size=1)
    if failure == "missing": paths.pop()
    if failure == "duplicate_page": paths.append(paths[0])
    if failure == "count":
        content = json.loads(paths[1].read_text())
        content["data"]["content"] = []
        paths[1].write_text(json.dumps(content))
    with pytest.raises(ValueError): read_pages(paths)


class Adapter:
    def __init__(self, session): self.session = session
    async def execute(self, statement): return self.session.execute(statement)
    async def flush(self): self.session.flush()
    def add(self, row): self.session.add(row)


@pytest.fixture
def state(monkeypatch):
    models = (MesProcess, MesEquipment, MesProcessDependency, MesEquipmentProcess, MesExternalImportRow,
        MesProcessTemplate, MesProcessTemplateOperation, MesWorkOrderOperation)
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
    engine = create_engine("sqlite:///:memory:")
    metadata.create_all(engine)
    org_id, user_id = uuid4(), uuid4()
    keys = ["mes:archive:process:manage", "mes:process_template:manage", "mes:work_order:manage"]
    actor = NS(org_id=org_id, user_id=user_id, permissions=keys, enabled_plugin_keys=["mes"],
        org_access_mode_code="selected", org_ids=[], department_id=None,
        permission_scopes={key: "all" for key in keys})
    async def noop(*args): pass
    monkeypatch.setattr(archive_repository, "lock_organization", noop)
    monkeypatch.setattr(repository, "lock_import", noop)
    yield NS(engine=engine, actor=actor, org_id=org_id)
    engine.dispose()


def setup_route(state):
    with Session(state.engine) as session:
        old = MesProcess(org_id=state.org_id, process_no=stable_number("GDB-PR-", ["CNC", "加工", "自制", ""]), process_name="CNC")
        template = MesProcessTemplate(org_id=state.org_id, template_no="SOURCE", template_name="路线")
        session.add_all([old, template]); session.flush()
        operation = MesProcessTemplateOperation(org_id=state.org_id, template_id=template.id, process_id=old.id,
            sequence_no=1, operation_no="10", operation_name="CNC", standard_minutes_per_unit=Decimal("3.5"), stage_name_snapshot="加工")
        session.add(operation); session.flush()
        session.add(MesExternalImportRow(org_id=state.org_id, source_system_key="gendanbao", record_type_key="route_step",
            source_record_no="SOURCE::1", source_file_name="routes.xlsx", source_file_sha256="a" * 64, source_sheet_name="路线",
            source_row_no=2, source_row_sha256="b" * 64,
            source_values_snapshot={"工艺": "CNC", "项目阶段": "加工", "加工类型": "自制"}, template_operation_id=operation.id))
        session.commit()
        return old.id, template.id, operation.id


def test_atomic_import_rebind_and_idempotency(state):
    legacy, template, operation = setup_route(state)
    rows = [raw()]
    with Session(state.engine) as session:
        result = run(service.apply(Adapter(session), rows, state.actor, state.org_id)); session.commit()
        assert result == dict(source_processes=1, new_processes=1, route_operations_linked=1, legacy_processes_deactivated=1)
        old = session.get(MesProcess, legacy)
        op = session.get(MesProcessTemplateOperation, operation)
        canonical = session.scalar(select(MesProcess).where(MesProcess.process_no == "GY001"))
        assert not old.is_active and op.process_id == canonical.id
        assert op.standard_minutes_per_unit == Decimal("3.5") and op.stage_name_snapshot == "加工" and op.sequence_no == 1
        assert session.get(MesProcessTemplate, template).version_no == 2
        again = run(service.apply(Adapter(session), rows, state.actor, state.org_id)); session.commit()
        assert again["new_processes"] == again["route_operations_linked"] == again["legacy_processes_deactivated"] == 0
        assert session.get(MesProcessTemplate, template).version_no == 2


def test_foreign_references_block_import_and_rollback(state):
    legacy, *_ = setup_route(state)
    with Session(state.engine) as session:
        session.add(MesEquipment(org_id=state.org_id, equipment_no="EQ1", equipment_name="设备", process_id=legacy)); session.commit()
        with pytest.raises(AppException): run(service.apply(Adapter(session), [raw()], state.actor, state.org_id))
        session.rollback()
        assert session.scalar(select(func.count()).select_from(MesProcess)) == 1
        assert session.get(MesProcess, legacy).is_active


def test_manual_collision_and_permission_scope(state):
    rows = [raw()]
    with Session(state.engine) as session:
        session.add(MesProcess(org_id=state.org_id, process_no="GY001", process_name="人工档案")); session.commit()
        with pytest.raises(AppException): run(service.apply(Adapter(session), rows, state.actor, state.org_id))
        state.actor.permission_scopes = {key: "organization" for key in state.actor.permissions}
        with pytest.raises(AppException): run(service.apply(Adapter(session), rows, state.actor, uuid4()))


def test_caller_transaction_can_rollback(state):
    legacy, _, operation = setup_route(state)
    with Session(state.engine) as session:
        run(service.apply(Adapter(session), [raw()], state.actor, state.org_id))
        session.rollback()
    with Session(state.engine) as session:
        assert session.scalar(select(func.count()).select_from(MesProcess)) == 1
        assert session.get(MesProcess, legacy).is_active
        assert session.get(MesProcessTemplateOperation, operation).process_id == legacy
