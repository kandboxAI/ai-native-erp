"""图纸上传更新：每类单份、另一类沿用、旧修订保留；模拟会话，不访问存储或业务库。"""
import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.core.exceptions import AppException
from app.modules.mes import drawing_service as module
from app.modules.mes.drawing_service import drawing_service
from app.modules.mes.schemas import WorkOrderDrawingUpdate
from test_web_production import actor


def fixture(monkeypatch, kind):
    user = actor("mes:work_order:manage")
    order = SimpleNamespace(id=uuid4(), org_id=user.org_id, version_no=2, status_code="draft", drawing_revision_label="A")
    def file(name, mime): return SimpleNamespace(id=uuid4(), original_file_name=name, content_type=mime)
    current = [file("old.pdf", "application/pdf"), file("old.stp", "application/step")]
    uploaded = file("new.pdf", "application/pdf") if kind == "pdf" else file("new.step", "application/step")
    commits, rollbacks, revisions = [], [], []
    @asynccontextmanager
    async def sessions():
        async def commit(): commits.append(True)
        try: yield SimpleNamespace(commit=commit, add=lambda row: None)
        except Exception:
            rollbacks.append(True)
            raise
    async def get(*args, **kwargs):
        assert kwargs["permission"] == "mes:work_order:manage" and kwargs["for_update"]
        return order
    async def history(*args): return False
    async def current_files(*args): return SimpleNamespace(revision_no=1), current
    async def bind(session, ids, **kwargs):
        assert ids == [uploaded.id]
        assert kwargs["business_id"] == order.id and kwargs["org_id"] == user.org_id
        return [uploaded]
    async def append(session, parent, ids, number, label, note, actor_):
        revisions.append(dict(ids=ids, number=number, note=note))
    async def no_delete(*args, **kwargs): pytest.fail("更新不得删除旧修订的文件")
    monkeypatch.setattr(module, "get_session_context", sessions)
    monkeypatch.setattr(module.repository, "get_work_order", get)
    monkeypatch.setattr(module.repository, "history_exists", history)
    monkeypatch.setattr(module, "current_files", current_files)
    monkeypatch.setattr(module.files, "bind", bind)
    monkeypatch.setattr(module.files, "replace", no_delete)
    monkeypatch.setattr(module.files, "delete_row", no_delete)
    monkeypatch.setattr(module, "append_revision", append)
    return user, order, current, uploaded, commits, rollbacks, revisions


@pytest.mark.parametrize("kind", ["pdf", "model"])
def test_upload_update_replaces_one_kind_and_preserves_the_other_and_history(monkeypatch, kind):
    user, order, current, uploaded, commits, _, revisions = fixture(monkeypatch, kind)
    other = current[1] if kind == "pdf" else current[0]
    body = WorkOrderDrawingUpdate(version_no=2, attachment_ids=[uploaded.id, other.id],
        revision_label="A", change_note="上传更新图纸")
    result = asyncio.run(drawing_service.save(order.id, body, user))
    assert revisions == [dict(ids=[uploaded.id, other.id], number=2, note="上传更新图纸")]
    assert [row.original_file_name for row in current] == ["old.pdf", "old.stp"]
    assert result["version_no"] == 3 and result["revision_no"] == 2 and commits == [True]


def test_update_rejects_two_current_pdf_files_without_committing(monkeypatch):
    user, order, current, uploaded, commits, rollbacks, revisions = fixture(monkeypatch, "pdf")
    body = WorkOrderDrawingUpdate(version_no=2, attachment_ids=[current[0].id, uploaded.id],
        change_note="上传更新图纸")
    with pytest.raises(AppException, match="最多一份"):
        asyncio.run(drawing_service.save(order.id, body, user))
    assert commits == [] and revisions == [] and rollbacks == [True] and order.version_no == 2


@pytest.mark.parametrize("revision,count,expected,is_legacy", [(None, 0, 0, False), (None, 2, 0, True), (4, 2, 4, False)])
def test_reading_legacy_attachments_does_not_invent_a_revision_or_write_data(monkeypatch, revision, count, expected, is_legacy):
    user = actor("mes:work_order:list")
    order = SimpleNamespace(id=uuid4(), version_no=2, drawing_revision_label=None, status_code="draft")
    rows = [SimpleNamespace(name=f"old-{index}.pdf") for index in range(count)]
    @asynccontextmanager
    async def sessions(): yield object()  # Deliberately no commit/add: viewing must remain read-only.
    async def get(*args): return order
    async def current(*args): return SimpleNamespace(revision_no=revision) if revision else None, rows
    async def history(*args): return False
    monkeypatch.setattr(module, "get_session_context", sessions)
    monkeypatch.setattr(module.repository, "get_work_order", get)
    monkeypatch.setattr(module.repository, "history_exists", history)
    monkeypatch.setattr(module, "current_files", current)
    monkeypatch.setattr(module, "file_item", lambda row: dict(file_name=row.name))
    result = asyncio.run(drawing_service.drawings(order.id, user))
    assert result["revision_no"] == expected and result["is_legacy"] is is_legacy
    assert len(result["items"]) == count
