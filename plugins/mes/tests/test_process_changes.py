"""工艺切换、审批冻结和已加工件处置的离线回归。"""
import asyncio
from contextlib import asynccontextmanager
from decimal import Decimal
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.core.exceptions import AppException
from app.modules.mes import process_change_service as module
from app.modules.mes.process_change_api import DispositionBody, ProcessChangeBody
from app.modules.mes.process_change_models import MesWorkOrderProcessChange as Change
from app.modules.mes.process_change_service import process_change_service as service


@pytest.fixture
def state(monkeypatch):
    user = NS(user_id=uuid4(), permissions=[module.MANAGE, module.APPROVE, "mes:quality:inspect"])
    order = NS(id=uuid4(), org_id=uuid4(), status_code="paused", version_no=7,
               is_process_change_pending=True)
    task = NS(id=uuid4(), org_id=order.org_id, work_order_id=order.id,
              operation_no="20", sequence_no=2, status_code="pending", process_id=uuid4(),
              operation_name_snapshot="旧工艺", planned_quantity=Decimal(100),
              good_quantity=Decimal(25), scrap_quantity=Decimal(3), rework_quantity=Decimal(2),
              version_no=3, planned_start_at=None, equipment_id=None, requirement_id=None,
              operation_description=None, work_center_name_snapshot=None, workstation_name_snapshot=None,
              is_quality_required=False, standard_minutes_per_unit=Decimal(2), assigned_user_id=uuid4())
    row = Change(org_id=order.org_id, work_order_id=order.id, operation_id=task.id,
        previous_process_id=task.process_id, new_process_id=uuid4(),
        previous_name_snapshot=task.operation_name_snapshot, new_name_snapshot="新工艺",
        new_process_version_snapshot=1, previous_configuration_snapshot={},
        remaining_quantity_snapshot=Decimal(70), disposition_quantity_snapshot=Decimal(25),
        disposition_code="keep", reason="客户改工艺", previous_order_status_code="in_progress",
        created_by=user.user_id, wf_instance_id=uuid4(), status_code="approved")
    session = NS(add=lambda row: None, commit=AsyncMock())
    @asynccontextmanager
    async def sessions():
        yield session
    monkeypatch.setattr(module, "get_session_context", sessions)
    monkeypatch.setattr(service, "order", AsyncMock(return_value=order))
    monkeypatch.setattr(module.changes, "get", AsyncMock(return_value=row))
    monkeypatch.setattr(module.repository, "work_order_operations", AsyncMock(return_value=[task]))
    monkeypatch.setattr(module.repository, "open_executions_exist", AsyncMock(return_value=False))
    monkeypatch.setattr(module.service, "_ensure_no_pending_change", AsyncMock())
    monkeypatch.setattr(module.report_repository, "downstream_history", AsyncMock(return_value=False))
    monkeypatch.setattr(module.phases, "order_phases", AsyncMock(return_value=[]))
    monkeypatch.setattr(module.inventory_service, "has_active", AsyncMock(return_value=False))
    monkeypatch.setattr(module.delivery_repository, "has_shipments", AsyncMock(return_value=False))
    monkeypatch.setattr(service, "target", AsyncMock(return_value=NS(id=row.new_process_id, process_name="新工艺", version_no=1)))
    monkeypatch.setattr(module.changes, "preserve_report_names", AsyncMock())
    monkeypatch.setattr(module.changes, "previous_standard_minutes", AsyncMock(return_value=None))
    monkeypatch.setattr(module, "prepare_operations", AsyncMock(return_value=[{"process_id": row.new_process_id, "equipment_id": None}]))
    return NS(user=user, order=order, task=task, row=row, session=session)


def test_switch_preserves_actual_and_uses_remaining_count(state):
    result = asyncio.run(service.dispose(state.order.id, state.row.id, "apply", DispositionBody(), state.user))
    assert result["status_code"] == "applied"
    assert Decimal(result["remaining_quantity_snapshot"]) == 70
    assert state.task.process_id == state.row.new_process_id
    assert state.task.operation_name_snapshot == "新工艺"
    assert (state.task.good_quantity, state.task.scrap_quantity, state.task.rework_quantity) == (25, 3, 2)
    assert state.task.planned_quantity == 100 and state.task.version_no == 4
    assert state.task.standard_minutes_per_unit is None
    assert state.order.status_code == "in_progress" and not state.order.is_process_change_pending
    module.changes.preserve_report_names.assert_awaited_once_with(state.session, state.task)


def test_switch_back_reuses_previously_configured_standard_minutes(state):
    module.changes.previous_standard_minutes.return_value = "21.000"
    result = asyncio.run(service.dispose(state.order.id, state.row.id, "apply", DispositionBody(), state.user))
    assert result["status_code"] == "applied"
    assert state.task.standard_minutes_per_unit == Decimal("21.000")
    module.changes.previous_standard_minutes.assert_awaited_once_with(state.session, state.row)


def test_reinspection_requires_authorized_confirmation_and_can_go_to_rework(state, monkeypatch):
    state.row.disposition_code = "reinspect"
    with pytest.raises(AppException, match="由质检人员"):
        asyncio.run(service.dispose(state.order.id, state.row.id, "apply", DispositionBody(), state.user))
    monkeypatch.setattr(module.repository, "get_task", AsyncMock(return_value=(state.task, state.order)))
    result = asyncio.run(service.dispose(state.order.id, state.row.id, "rework", DispositionBody(note="复检不合格"), state.user))
    assert result["disposition_code"] == "rework"
    assert result["disposition_note"] == "复检不合格"
    assert state.order.status_code == "paused"


def test_rework_must_return_same_quantity_before_switching(state, monkeypatch):
    state.row.disposition_code = "rework"
    state.row.repair_order_id = uuid4()
    repair = NS(id=state.row.repair_order_id, status_code="completed", good_quantity=Decimal(24))
    monkeypatch.setattr(module.changes, "repair", AsyncMock(return_value=repair))
    with pytest.raises(AppException, match="返工合格数量"):
        asyncio.run(service.dispose(state.order.id, state.row.id, "apply", DispositionBody(), state.user))
    assert state.order.is_process_change_pending
    repair.good_quantity = Decimal(25)
    module.repository.work_order_operations.side_effect = [
        [state.task], [NS(status_code="completed", good_quantity=Decimal(25), process_id=state.row.new_process_id)],
    ]
    result = asyncio.run(service.dispose(state.order.id, state.row.id, "apply", DispositionBody(), state.user))
    assert result["status_code"] == "applied"
    assert state.task.good_quantity == 25


@pytest.mark.parametrize("dependency,message", [
    ("open", "结束当前执行"), ("formal", "已有正式排程"), ("downstream", "后续工序已有生产记录"),
])
def test_live_or_formal_execution_blocks_switch(state, dependency, message):
    if dependency == "open":
        module.repository.open_executions_exist.return_value = True
    elif dependency == "formal":
        module.phases.order_phases.return_value = [NS()]
    else:
        module.report_repository.downstream_history.return_value = True
    with pytest.raises(AppException, match=message):
        asyncio.run(service.dispose(state.order.id, state.row.id, "apply", DispositionBody(), state.user))
    assert state.task.operation_name_snapshot == "旧工艺"
    assert state.row.applied_at is None


def test_repair_does_not_generate_independent_stock(state):
    repair = NS(is_process_change_repair=True)
    assert asyncio.run(module.inventory_service.produced(state.session, repair)) == 0


def test_approval_rejection_restores_previous_order_state(state):
    state.row.status_code = "submitted"
    ctx = NS(session=state.session, business_id=state.row.id, instance_id=state.row.wf_instance_id,
             current_user=state.user, org_id=state.order.org_id)
    asyncio.run(service.hook("rejected", ctx))
    assert state.row.status_code == "rejected"
    assert state.order.status_code == "in_progress" and not state.order.is_process_change_pending


def test_submission_records_quantities_before_workflow_freezes_order(state, monkeypatch):
    state.order.status_code, state.order.is_process_change_pending = "in_progress", False
    state.task.model_dump = lambda **kwargs: {"operation_description": "旧工艺说明"}
    state.session.flush = AsyncMock()
    saved = []
    state.session.add = saved.append

    async def start(**kwargs):
        row = saved[0]
        assert kwargs["business_id"] == row.id
        assert row.status_code == "draft"
        module.changes.get.return_value = row
        await service.hook("started", NS(session=state.session, business_id=row.id, instance_id=uuid4(),
                                       current_user=state.user, org_id=state.order.org_id))

    monkeypatch.setattr(module.workflow_runtime_service, "start", start)
    body = ProcessChangeBody(version_no=state.order.version_no, operation_id=state.task.id,
                             new_process_id=state.row.new_process_id, disposition_code="reinspect", reason="客户变更")
    result = asyncio.run(service.submit(state.order.id, body, state.user))
    assert result["status_code"] == "submitted"
    assert result["disposition_code"] == "reinspect"
    assert result["previous_configuration_snapshot"]["operation_description"] == "旧工艺说明"
    assert Decimal(result["remaining_quantity_snapshot"]) == 70
    assert Decimal(result["disposition_quantity_snapshot"]) == 25
    assert state.order.status_code == "paused" and state.order.is_process_change_pending


@pytest.mark.parametrize("has_custom_default", [False, True])
def test_mes_only_setup_installs_missing_process_approval(monkeypatch, has_custom_default):
    from app.modules.notification_center import tenant_setup as notifications
    from app.modules.navigation import tenant_setup as navigation
    from app.modules.system import tenant_template
    from app.modules.workflow import tenant_setup as workflow

    session = NS(commit=AsyncMock())
    ctx = NS(root_org_id=uuid4(), admin_user_id=uuid4())
    monkeypatch.setattr(tenant_template, "iter_module_attr", lambda *args: ())
    monkeypatch.setattr(navigation, "setup_tenant", AsyncMock())
    monkeypatch.setattr(notifications, "setup_tenant", AsyncMock())
    definition_repo = workflow.repository
    monkeypatch.setattr(definition_repo, "get_by_definition_no", AsyncMock(side_effect=[NS(), None]))
    monkeypatch.setattr(definition_repo, "has_default_for_org", AsyncMock(return_value=has_custom_default))
    monkeypatch.setattr(definition_repo, "add", AsyncMock())
    monkeypatch.setattr(definition_repo, "create_version", AsyncMock(return_value=NS(id=uuid4())))
    monkeypatch.setattr(definition_repo, "publish_version", AsyncMock())

    asyncio.run(tenant_template._run_module_setups(session, ctx, {"mes"}))

    definition_repo.has_default_for_org.assert_awaited_once_with(
        session, org_id=ctx.root_org_id, business_type_code="mes_process_change",
    )
    if has_custom_default:
        definition_repo.publish_version.assert_not_awaited()
    else:
        definition = definition_repo.publish_version.await_args.kwargs["definition"]
        assert definition.definition_no == "mes_process_change"
        assert definition.org_id == ctx.root_org_id and definition.is_default
        design = definition_repo.create_version.await_args.kwargs["spiff_spec_snapshot"]["design"]
        assert design["nodes"][0]["assignee"]["value"] == "mes:process_change:approve"
