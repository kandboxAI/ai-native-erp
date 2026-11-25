"""开工事务的真实 ORM 写入顺序回归；仅使用 SQLite 内存库。"""
import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest
from sqlalchemy import Column, JSON, MetaData, Table, Uuid, create_engine, event, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session

from app.modules.mes import service as service_module
from app.modules.mes.models import MesExecutionEvent, MesOperationExecution
from app.modules.mes.repository import repository
from app.modules.mes.schemas import ProductionActionBody
from app.modules.mes.service import service
from test_reporting import fixture


@pytest.mark.parametrize("fail_event", [False, True])
def test_track_in_persists_execution_before_event_in_one_transaction(monkeypatch, fail_event):
    actor, order, task, _, _, _, _, _, _ = fixture(monkeypatch)
    order.status_code, task.status_code = "released", "dispatched"
    task.good_quantity = 0
    engine = create_engine("sqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")

    metadata = MetaData()
    # 外部拥有者仅保留主键桩；执行/事件保留真实列与即时外键约束。
    for name in ("sys_org", "sys_user", "mes_work_order_operation"):
        Table(name, metadata, Column("id", Uuid, primary_key=True))
    for model in (MesOperationExecution, MesExecutionEvent):
        table = model.__table__.to_metadata(metadata)
        for column in table.columns:
            column.server_default = None
            if isinstance(column.type, JSONB):
                column.type = JSON()
    metadata.create_all(engine)
    with engine.begin() as connection:
        for name, value in (("sys_org", actor.org_id), ("sys_user", actor.user_id), ("mes_work_order_operation", task.id)):
            connection.execute(metadata.tables[name].insert().values(id=value))

    async def pair(*args, **kwargs): return task, order
    async def detail(*args): return task
    async def no_execution(*args, **kwargs): return None
    monkeypatch.setattr(repository, "get_task", pair)
    monkeypatch.setattr(repository, "current_execution", no_execution)
    monkeypatch.setattr(service, "_detail", detail)

    if fail_event:
        original_event = service._event
        def rejected_event(*args, **kwargs):
            original_event(*args, **kwargs)
            raise RuntimeError("event failed")
        monkeypatch.setattr(service, "_event", rejected_event)

    @asynccontextmanager
    async def sessions():
        with Session(engine) as session:
            async def flush(): session.flush()
            async def commit(): session.commit()
            yield SimpleNamespace(add=session.add, flush=flush, commit=commit)
    monkeypatch.setattr(service_module, "get_session_context", sessions)
    try:
        if fail_event:
            with pytest.raises(RuntimeError, match="event failed"):
                asyncio.run(service.track_in(task.id, ProductionActionBody(version_no=1), actor))
        else:
            asyncio.run(service.track_in(task.id, ProductionActionBody(version_no=1), actor))
        with engine.connect() as connection:
            executions = connection.execute(select(metadata.tables["mes_operation_execution"])).mappings().all()
            events = connection.execute(select(metadata.tables["mes_execution_event"])).mappings().all()
        assert len(executions) == len(events) == (0 if fail_event else 1)
        if not fail_event:
            assert events[0]["execution_id"] == executions[0]["id"]
            assert task.status_code == order.status_code == "in_progress"
    finally:
        engine.dispose()
