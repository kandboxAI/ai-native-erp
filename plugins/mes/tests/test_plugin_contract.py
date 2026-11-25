"""MES onboarding regressions: compiled SQL and mocked sessions only."""
import asyncio
from contextlib import asynccontextmanager
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

from app.auth.schemas import AuthenticatedUser
from app.core.exceptions import AppException
from app.framework.db.registry import import_all_models
from app.modules.dictionary.builtin_dicts import builtin_dict_specs
from app.modules.mes import catalog, models
from app.modules.mes.repository import _org_conditions, repository
from app.modules.mes.schemas import ProductionActionBody, ProductionDispatchBody, ProductionReportBody, ProductionTaskListQuery
from app.modules.mes.service import service


@pytest.fixture(autouse=True)
def no_pending_report_changes(monkeypatch):
    from app.modules.mes.report_repository import report_repository
    async def empty(*args): return False
    monkeypatch.setattr(report_repository, "pending_for_order", empty)


def user(scope="all", permission="mes:production_report:create"):
    return AuthenticatedUser(auth_user_id=uuid4(), tenant_id=uuid4(), tenant_no="test",
        tenant_schema="t_test", user_id=uuid4(), org_id=uuid4(),
        org_access_mode_code="all", permissions=[permission], permission_scopes={permission: scope})


def test_catalog_dictionary_and_model_contracts():
    import_all_models()
    definitions = {item["dict_code"]: item for item in builtin_dict_specs()}
    assert sum(code.startswith("mes_") and not code.startswith("mes_cnc_") for code in definitions) == 21
    assert sum(code.startswith("mes_cnc_") for code in definitions) == 10
    assert ("mes", "制造执行") in definitions["sys_module"]["items"]
    assert not any(menu.key == "Mes" for menu in catalog.MENUS)
    assert {menu.key for menu in catalog.MENUS if menu.parent_key is None} == {"MesDashboard", "MesSales", "MesProduction", "MesReporting", "MesDelivery", "MesWarehouse", "MesExtensions", "MesArchives"}
    assert not next(menu for menu in catalog.MENUS if menu.key == "MesInventory").is_visible
    assert sum(menu.parent_key == "MesWarehouse" and menu.is_visible for menu in catalog.MENUS) == 6
    assert {menu.portal_code for menu in catalog.MINIAPP_MENUS} == {"standard"}
    tables = [table for table in models.SQLModel.metadata.tables.values() if table.name.startswith("mes_")]
    assert sum(not table.name.startswith("mes_cnc_") for table in tables) == 28
    assert sum(table.name.startswith("mes_cnc_") for table in tables) == 8
    for table in tables:
        str(CreateTable(table).compile(dialect=postgresql.dialect()))
        assert table.schema is None
        assert table.comment and all(column.comment for column in table.columns)
        for column in table.columns:
            if column.type.__class__.__name__ == "Boolean":
                assert column.name.startswith(("is_", "has_", "can_"))


def test_sales_pages_use_catalog_permissions_and_contained_views():
    from pathlib import Path
    import tomllib
    root = Path(__file__).resolve().parents[1]
    manifest = tomllib.loads((root / "plugin.toml").read_text(encoding="utf-8"))
    definitions = {row.key: row for row in catalog.MENUS}
    permissions = {row.key for row in catalog.PERMISSIONS}
    assert {"MesSales", "MesQuotations", "MesSalesOrders"} <= set(manifest["menu_keys"])
    for key, path, permission in (("MesQuotations", "/mes/quotations", "mes:quotation:list"),
                                  ("MesSalesOrders", "/mes/sales-orders", "mes:sales_order:list")):
        row = definitions[key]
        assert row.parent_key == "MesSales" and row.path == path
        assert row.permission_key == permission and permission in permissions
        assert (root / "web/src/views" / f"{row.component}.vue").is_file()
    assert len(definitions) == len(catalog.MENUS)
    assert len(permissions) == len(catalog.PERMISSIONS)


def test_quotation_catalog_projects_single_tag_to_existing_tenant_menu():
    from app.framework.catalog import single_tag_menu_paths
    from app.modules.menu.models import SysMenu
    from app.modules.menu.repository import build_tree

    menu = SysMenu(menu_key="MesQuotations", menu_name="询价报价", menu_type_code="menu",
        path="/mes/quotations", component="mes/quotations/index",
        flex_form={"route": {"meta": {"keepAlive": True}}})
    projected, = build_tree([menu], {}, single_tag_paths=single_tag_menu_paths())
    assert projected["flex_form"]["route"]["meta"] == {"keepAlive": True, "dynamicLevel": 1}
    assert menu.flex_form["route"]["meta"] == {"keepAlive": True}


def test_cnc_and_sales_catalog_entries_survive_merge_with_distinct_permissions():
    from pathlib import Path
    import tomllib
    root = Path(__file__).resolve().parents[1]
    manifest = tomllib.loads((root / "plugin.toml").read_text(encoding="utf-8"))
    definitions = {row.key: row for row in catalog.MENUS}
    assert {"MesQuoting", "MesQuotations", "MesSalesOrders"} <= set(manifest["menu_keys"])
    row = definitions["MesQuoting"]
    assert row.parent_key == "MesProduction" and row.path == "/mes/quoting"
    assert row.permission_key == "mes:quote:list"
    assert row.permission_key != definitions["MesQuotations"].permission_key
    assert (root / "web/src/views" / f"{row.component}.vue").is_file()
    assert "MesQuoting" in catalog.MENU_GROUPS["MesProduction"]
    assert set(definitions) <= set(manifest["menu_keys"])
    assert len(manifest["menu_keys"]) == len(set(manifest["menu_keys"]))


@pytest.mark.parametrize("scope,needle", [("self", "created_by"), ("related", "false"), ("all", None)])
def test_permission_scope_is_not_bypassed_by_all_org_access(scope, needle):
    sql = " AND ".join(str(condition.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))
                       for condition in _org_conditions(models.MesWorkOrderOperation, user(scope)))
    if needle:
        assert needle in sql
    else:
        assert "created_by =" not in sql


def test_list_only_permission_does_not_require_manage_scope():
    class Session:
        async def execute(self, statement):
            return SimpleNamespace(scalar_one=lambda: 0)
        async def exec(self, statement):
            assert "created_by" in str(statement)
            return SimpleNamespace(all=lambda: [])
    result = asyncio.run(repository.list_tasks(Session(), ProductionTaskListQuery(),
                         user("self", "mes:operation_task:list"), manager=True))
    assert result == ([], 0)


@pytest.mark.parametrize("old_parent", [None, "Mes"])
def test_existing_mes_menu_ids_move_to_groups_and_keep_warehouse_children(old_parent):
    from app.modules.menu.models import SysMenu
    from app.modules.system.tenant_template import relocate_catalog_menu
    root = SysMenu(menu_key="Mes", menu_name="MES 制造执行", menu_type_code="directory", path="/mes")
    rows = {item.key: SysMenu(menu_key=item.key, menu_name=item.name, menu_type_code=item.menu_type_code) for item in catalog.MENUS}
    for item in catalog.MENUS:
        if item.key.startswith("MesWarehouse") and item.key != "MesWarehouse":
            rows[item.key].parent_id = rows["MesWarehouse"].id
        elif item.menu_type_code != "directory" or item.key == "MesWarehouse":
            rows[item.key].parent_id = root.id if old_parent else None
    before = {key: row.id for key, row in rows.items()}
    all_rows = {root.id: root, **{row.id: row for row in rows.values()}}
    for item in catalog.MENUS:
        relocate_catalog_menu(rows[item.key], item, {"Mes": root, **rows}, all_rows)
    assert not any(row.parent_id == root.id for row in rows.values())
    assert {key: row.id for key, row in rows.items()} == before
    for item in catalog.MENUS:
        assert rows[item.key].parent_id == (rows[item.parent_key].id if item.parent_key else None)
    assert rows["MesWarehouseInbound"].parent_id == rows["MesWarehouse"].id
    custom = SysMenu(menu_key="Custom", menu_name="自定义", menu_type_code="directory")
    rows["MesWorkOrders"].parent_id = custom.id
    all_rows[custom.id] = custom
    assert not relocate_catalog_menu(rows["MesWorkOrders"], next(item for item in catalog.MENUS if item.key == "MesWorkOrders"), rows, all_rows)
    assert rows["MesWorkOrders"].parent_id == custom.id


@pytest.mark.parametrize("children,path,changed", [(0, "/mes", True), (1, "/mes", False), (0, "/custom", False)])
def test_retiring_old_directory_preserves_custom_children(children, path, changed):
    from unittest.mock import AsyncMock
    from app.modules.menu.models import SysMenu
    from app.modules.menu.repository import repository as menus
    row = SysMenu(menu_key="Mes", menu_name="MES 制造执行", menu_type_code="directory", path=path)
    result = SimpleNamespace(scalars=lambda: SimpleNamespace(first=lambda: row))
    session = SimpleNamespace(execute=AsyncMock(return_value=result), scalar=AsyncMock(return_value=children), flush=AsyncMock())
    assert asyncio.run(menus.retire_empty_directory(session, "Mes", "/mes", uuid4())) is changed
    assert row.is_active is (not changed) and row.is_visible is (not changed)


def test_inventory_alias_is_hidden_without_disabling_old_route():
    from unittest.mock import AsyncMock
    from app.modules.menu.models import SysMenu
    from app.modules.menu.repository import repository as menus
    row = SysMenu(menu_key="MesInventory", menu_name="MES 库存协同", menu_type_code="menu", path="/mes/inventory")
    old_id = row.id
    result = SimpleNamespace(scalars=lambda: SimpleNamespace(first=lambda: row))
    session = SimpleNamespace(execute=AsyncMock(return_value=result), flush=AsyncMock())
    assert asyncio.run(menus.hide_legacy_entry(session, row.menu_key, row.path, uuid4()))
    assert not row.is_visible and row.is_active and row.id == old_id
    assert not asyncio.run(menus.hide_legacy_entry(session, row.menu_key, row.path, uuid4()))


def workflow(monkeypatch):
    from app.modules.mes import service as service_module
    actor = user()
    task = SimpleNamespace(id=uuid4(), org_id=actor.org_id, version_no=1, assigned_user_id=actor.user_id,
        status_code="in_progress", sequence_no=1, is_predecessor_ready=True, is_quality_required=False,
        planned_quantity=Decimal("10"), good_quantity=Decimal("10"), scrap_quantity=Decimal("0"), rework_quantity=Decimal("0"))
    order = SimpleNamespace(id=uuid4(), version_no=1, status_code="in_progress",
        good_quantity=Decimal("0"), scrap_quantity=Decimal("0"), rework_quantity=Decimal("0"))
    execution = SimpleNamespace(id=uuid4())
    commits = []
    @asynccontextmanager
    async def sessions():
        async def commit():
            commits.append(True)
        yield SimpleNamespace(commit=commit, add=lambda row: None)
    async def pair(*args, **kwargs):
        return task, order
    async def current(*args, **kwargs):
        return execution
    async def detail(*args):
        return task
    monkeypatch.setattr(service_module, "get_session_context", sessions)
    monkeypatch.setattr(repository, "get_task", pair)
    monkeypatch.setattr(repository, "current_execution", current)
    monkeypatch.setattr(service, "_detail", detail)
    monkeypatch.setattr(service, "_event", lambda *args, **kwargs: None)
    return actor, task, order, commits


@pytest.mark.parametrize("other_status,expected", [("pending", "in_progress"), ("completed", "completed")])
def test_order_completes_only_when_all_operations_complete(monkeypatch, other_status, expected):
    actor, task, order, commits = workflow(monkeypatch)
    other = SimpleNamespace(status_code=other_status, sequence_no=2, good_quantity=Decimal("8"),
                            scrap_quantity=Decimal("2"), rework_quantity=Decimal("0"))
    async def operations(*args):
        return [task, other]
    monkeypatch.setattr(repository, "work_order_operations", operations)
    asyncio.run(service.track_out(task.id, ProductionActionBody(version_no=1), actor))
    assert task.status_code == "completed" and order.status_code == expected
    assert order.good_quantity == (Decimal("8") if expected == "completed" else Decimal("0"))
    assert commits == [True]


def test_predecessors_are_checked_beyond_cached_flag(monkeypatch):
    actor, task, order, commits = workflow(monkeypatch)
    task.status_code, task.sequence_no = "pending", 2
    async def operations(*args):
        return [SimpleNamespace(sequence_no=1, status_code="pending"), task]
    monkeypatch.setattr(repository, "work_order_operations", operations)
    with pytest.raises(AppException, match="前置工序"):
        asyncio.run(service.track_in(task.id, ProductionActionBody(version_no=1), actor))
    assert not commits


def test_report_idempotency_cannot_reuse_another_operation(monkeypatch):
    actor, task, order, commits = workflow(monkeypatch)
    async def existing(*args):
        return SimpleNamespace(operation_id=uuid4())
    monkeypatch.setattr(repository, "find_report_by_idempotency", existing)
    with pytest.raises(AppException, match="其他生产任务"):
        asyncio.run(service.report(task.id, ProductionReportBody(version_no=1, idempotency_key="same-key-123"), actor))
    assert not commits


def test_dispatch_rejects_inactive_or_out_of_org_user(monkeypatch):
    actor, task, order, commits = workflow(monkeypatch)
    task.status_code = "pending"
    async def invalid(*args):
        return False
    monkeypatch.setattr(repository, "is_active_assignee", invalid)
    with pytest.raises(AppException, match="派工人员"):
        asyncio.run(service.dispatch(task.id, ProductionDispatchBody(version_no=1, assigned_user_id=uuid4()), actor))
    assert not commits
