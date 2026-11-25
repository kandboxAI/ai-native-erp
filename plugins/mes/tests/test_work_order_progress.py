"""列表工序投影：只使用已授权分页结果，复用一次批量查询，无数据库连接。"""
import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.modules.mes import service as service_module
from app.modules.mes.models import MesWorkOrder, MesWorkOrderOperation
from app.modules.mes.repository import repository
from app.modules.mes.schemas import MesWorkOrderListQuery
from app.modules.mes.service import service
from test_web_production import actor


@pytest.mark.parametrize("project_view", [False, True])
def test_list_returns_ordered_minimal_progress_without_per_row_requests(monkeypatch, project_view):
    user = actor("mes:work_order:list")
    project = SimpleNamespace(id=uuid4(), org_id=user.org_id, version_no=1, note=None,
        production_order_no="PO-1", project_name="项目", customer_id=None,
        customer_no_snapshot="C1", customer_name_snapshot="客户", created_at=service_module.utc_now())
    orders = [MesWorkOrder(org_id=user.org_id, work_order_no=f"MO-{i}", product_item_id=uuid4(),
        product_item_no_snapshot="P1", product_item_name_snapshot="产品", unit_code="pcs",
        planned_quantity=10, production_order_id=project.id, status_code="released", priority_code="normal") for i in range(2)]
    operations = [MesWorkOrderOperation(org_id=user.org_id, work_order_id=orders[0].id,
        sequence_no=seq, operation_no=str(seq*10), operation_name_snapshot=name,
        planned_quantity=planned, good_quantity=good, scrap_quantity=scrap, rework_quantity=rework,
        status_code=status, operation_description="不应发布的现场说明", assigned_user_id=uuid4())
        for seq, name, planned, good, scrap, rework, status in [
            (2, "QA", 12, 5, 0, 1, "waiting_quality"), (1, "下料", 10, 9, 1, 0, "completed")]]
    queries = []
    @asynccontextmanager
    async def sessions(): yield object()
    async def list_orders(session, query, current_user):
        assert current_user is user
        return orders, 27
    async def list_projects(session, query, current_user): return [project], orders, 27
    async def batch(session, ids):
        queries.append(ids)
        assert ids == [row.id for row in orders]
        return operations
    async def projects(*args): return {project.id: project}
    async def names(*args): return {}
    async def summaries(session, ids):
        assert set(ids) == {op.id for op in operations}
        return {op.id: SimpleNamespace(started_at=project.created_at, finished_at=project.created_at) for op in operations}
    async def forbidden(*args, **kwargs): pytest.fail("列表不能逐工单读取详情或人员工时")
    monkeypatch.setattr(service_module, "get_session_context", sessions)
    monkeypatch.setattr(service_module, "user_display_names", names)
    monkeypatch.setattr(repository, "list_work_orders", list_orders)
    monkeypatch.setattr(repository, "list_projects", list_projects)
    monkeypatch.setattr(repository, "projects", projects)
    monkeypatch.setattr(repository, "operations_for_orders", batch)
    monkeypatch.setattr(repository, "work_order_operations", forbidden)
    monkeypatch.setattr(repository, "execution_summaries", summaries)
    method = service.list_production_orders if project_view else service.list_work_orders
    result = asyncio.run(method(MesWorkOrderListQuery(), user))
    children = result["items"][0]["orders"] if project_view else result["items"]
    progress = children[0]["operation_progress"]
    assert result["total"] == 27 and len(queries) == 1
    assert [row["operation_name"] for row in progress] == ["下料", "QA"]
    assert progress[1]["planned_quantity"] == 12 and progress[1]["rework_quantity"] == 1
    assert progress[1]["status_label"] == "待检验"
    assert progress[0]["actual_finished_at"] is not None
    assert progress[1]["actual_started_at"] is not None and progress[1]["actual_finished_at"] is None
    assert children[0]["completed_operation_count"] == 1
    assert children[1]["operation_progress"] == []
    assert all(not {"assigned_user_id", "operation_description", "events", "executions"} & set(row) for row in progress)


def test_progress_projection_does_not_publish_another_parent_or_org():
    user = actor("mes:work_order:list")
    order = MesWorkOrder(org_id=user.org_id, work_order_no="MO1", product_item_id=uuid4(),
        product_item_no_snapshot="P1", product_item_name_snapshot="产品", unit_code="pcs", planned_quantity=10,
        status_code="released", priority_code="normal")
    operations = [MesWorkOrderOperation(org_id=org, work_order_id=parent, sequence_no=1,
        operation_no="10", operation_name_snapshot="不可见", planned_quantity=10)
        for org, parent in [(uuid4(), order.id), (user.org_id, uuid4())]]
    assert service._work_order_item(order, 0, 0, operations=operations).operation_progress == []
