"""产品执行工单的自制/委外类型；离线模拟会话，不连接数据库。"""
import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy.dialects import postgresql

from app.core.exceptions import AppException
from app.modules.mes import service as module
from app.modules.mes.models import MesWorkOrder
from app.modules.mes.order_service import order_service
from app.modules.mes.repository import repository
from app.modules.mes.schemas import WorkOrderCreate, WorkOrderUpdate, MesWorkOrderListQuery, ProductionOrderCreate
from app.modules.mes.service import service
from test_web_production import actor, payload
from test_order_lifecycle import lifecycle_fixture, no_pending_report_changes


@pytest.mark.parametrize("kind", ["in_house", "outsourced"])
def test_create_persists_type_and_publishes_it_in_list_projection(monkeypatch, kind):
    user, added = actor(), []
    @asynccontextmanager
    async def sessions():
        async def flush(): pass
        async def commit(): pass
        yield SimpleNamespace(flush=flush,commit=commit)
    async def item(*args): return SimpleNamespace(id=uuid4(),item_no="P1",item_name="产品",unit_code="pcs")
    async def exists(*args): return False
    async def detail(*args): return None
    monkeypatch.setattr(module, "get_session_context", sessions)
    monkeypatch.setattr(module, "get_active_item", item)
    monkeypatch.setattr(repository, "work_order_no_exists", exists)
    monkeypatch.setattr(repository, "add", lambda session,row: added.append(row))
    monkeypatch.setattr(service, "_detail", detail)
    asyncio.run(service.create_work_order(WorkOrderCreate(**payload(processing_type_code=kind)), user))
    order = next(row for row in added if isinstance(row, MesWorkOrder))
    assert order.processing_type_code == kind
    projection = service._work_order_item(order,2,0)
    assert projection.processing_type_code == kind
    assert projection.processing_type_label == ("委外" if kind == "outsourced" else "自制")


def test_type_defaults_to_in_house_and_nested_products_keep_individual_choices():
    first = WorkOrderCreate(**payload())
    assert first.processing_type_code == "in_house"
    second = first.model_copy(update={"work_order_no":"MO-2","processing_type_code":"outsourced"})
    project = ProductionOrderCreate(production_order_no="PO",project_name="项目",products=[first,second])
    assert [row.processing_type_code for row in project.products] == ["in_house","outsourced"]
    for invalid in ["purchase", "委外", "", None]:
        with pytest.raises(ValidationError): WorkOrderCreate(**payload(processing_type_code=invalid))


def test_running_order_cannot_change_processing_type(monkeypatch):
    user, order, task, commits, records = lifecycle_fixture(monkeypatch,"in_progress")
    body = WorkOrderUpdate(org_id=order.org_id,work_order_no=order.work_order_no,product_item_id=order.product_item_id,
        planned_quantity=order.planned_quantity,version_no=1,processing_type_code="outsourced",
        operations=[dict(operation_no="10",operation_name="下料")])
    with pytest.raises(AppException,match="货品类型"):
        asyncio.run(order_service.update(order.id,body,user))
    assert order.processing_type_code == "in_house" and not commits and not records


def test_filter_has_processing_type_and_keeps_scope():
    user = actor("mes:work_order:list")
    statements=[]
    class Session:
        async def execute(self,stmt): return SimpleNamespace(scalar_one=lambda:0)
        async def exec(self,stmt):
            statements.append(str(stmt.compile(dialect=postgresql.dialect(),compile_kwargs={"literal_binds":True})))
            return SimpleNamespace(scalars=lambda:SimpleNamespace(all=lambda:[]))
    asyncio.run(repository.list_work_orders(Session(),MesWorkOrderListQuery(processing_type_code="outsourced"),user))
    assert "processing_type_code = 'outsourced'" in statements[0]
    assert str(user.org_id) in statements[0] and "deleted_at IS NULL" in statements[0]
