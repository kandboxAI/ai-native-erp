"""新建货品图纸绑定：真实文件绑定校验、模拟会话；不连接数据库或存储。"""
import asyncio
from contextlib import asynccontextmanager
from datetime import timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.core.exceptions import AppException
from app.framework.datetime_local import local_now
from app.modules.mes import service as module
from app.modules.mes.drawing_files import DRAWING_SCENE, DRAWING_TYPE
from app.modules.mes.repository import repository
from app.modules.mes.schemas import ProductionOrderCreate, WorkOrderCreate
from app.modules.mes.service import service
from test_web_production import actor


def body(**values):
    return dict(work_order_no="DRAWING-1", product_item_id=uuid4(), planned_quantity=1,
                publish=False, **values)


def fixture(monkeypatch, names):
    user = actor()
    rows = [SimpleNamespace(id=uuid4(), original_file_name=name, content_type=mime,
        scene_code=DRAWING_SCENE, status_code="pending", uploader_user_id=user.user_id,
        expires_at=local_now() + timedelta(hours=1)) for name, mime in names]
    added, commits, rollbacks = [], [], []
    class Session:
        async def exec(self, statement): return SimpleNamespace(all=lambda: rows)
        async def flush(self): pass
        async def commit(self): commits.append(True)
        def add(self, row): added.append(row)
    @asynccontextmanager
    async def sessions():
        try: yield Session()
        except Exception:
            rollbacks.append(True)
            raise
    async def item(*args): return SimpleNamespace(id=uuid4(), item_no="P1", item_name="支架", unit_code="pcs")
    async def exists(*args): return False
    monkeypatch.setattr(module, "get_session_context", sessions)
    monkeypatch.setattr(module, "get_active_item", item)
    monkeypatch.setattr(repository, "work_order_no_exists", exists)
    monkeypatch.setattr(repository, "add", lambda session, row: session.add(row))
    return user, rows, added, commits, rollbacks


@pytest.mark.parametrize("names", [
    [("支架.PDF", "application/pdf"), ("支架.stp", "application/step")],
    [("支架.step", "application/octet-stream")],
])
def test_create_binds_drawings_to_new_order_in_same_transaction(monkeypatch, names):
    user, rows, added, commits, _ = fixture(monkeypatch, names)
    result = asyncio.run(service.create_work_order(WorkOrderCreate(**body(
        drawing_attachment_ids=[row.id for row in rows], drawing_revision_label=" A ")), user))
    order = added[0]
    assert order.drawing_revision_label == "A"
    assert all(row.business_type_code == DRAWING_TYPE and str(row.business_id) == result["id"]
               and row.org_id == user.org_id and row.status_code == "bound" for row in rows)
    assert commits == [True]


@pytest.mark.parametrize("change", [
    {"uploader_user_id": uuid4()}, {"scene_code": "other_scene"},
    {"status_code": "bound"}, {"expires_at": local_now() - timedelta(seconds=1)},
    {"original_file_name": "payload.exe"}, {"content_type": "text/plain"},
])
def test_invalid_files_abort_creation_without_commit(monkeypatch, change):
    user, rows, _, commits, rollbacks = fixture(monkeypatch, [("支架.pdf", "application/pdf")])
    for key, value in change.items(): setattr(rows[0], key, value)
    with pytest.raises(AppException):
        asyncio.run(service.create_work_order(WorkOrderCreate(**body(
            drawing_attachment_ids=[rows[0].id], drawing_revision_label="A")), user))
    assert not commits and rollbacks == [True]


def test_second_product_file_failure_aborts_entire_project(monkeypatch):
    user, rows, _, commits, rollbacks = fixture(monkeypatch, [("支架.pdf", "application/pdf")])
    # The same pending file cannot be bound to two products; first binding is in the uncommitted transaction.
    products = [body(drawing_attachment_ids=[rows[0].id], drawing_revision_label="A") for _ in range(2)]
    products[1]["work_order_no"] = "DRAWING-2"
    with pytest.raises(AppException):
        asyncio.run(service.create_production_order(ProductionOrderCreate(
            production_order_no="PROJECT", project_name="图纸", products=products), user))
    assert not commits and rollbacks == [True]


@pytest.mark.parametrize("values", [
    {"drawing_attachment_ids": [uuid4() for _ in range(21)], "drawing_revision_label": "A"},
    {"drawing_attachment_ids": [uuid4()] * 2, "drawing_revision_label": "A"},
])
def test_drawing_payload_rejects_duplicate_and_excess_files(values):
    with pytest.raises(ValidationError): WorkOrderCreate(**body(**values))


def test_same_kind_files_cannot_be_created_and_label_is_optional(monkeypatch):
    user, rows, _, commits, _ = fixture(monkeypatch, [("a.pdf", "application/pdf"), ("b.pdf", "application/pdf")])
    with pytest.raises(AppException, match="最多一份"):
        asyncio.run(service.create_work_order(WorkOrderCreate(**body(drawing_attachment_ids=[r.id for r in rows])), user))
    assert not commits
