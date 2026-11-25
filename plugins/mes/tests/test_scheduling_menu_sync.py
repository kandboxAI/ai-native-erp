"""旧排程占位菜单升级：保留 ID、客户配置及授权，只测试内存 SQLite。"""
import asyncio
from types import SimpleNamespace as NS

import pytest
from sqlalchemy.orm import Session

from app.modules.menu import public
from app.modules.menu.models import SysMenu
from app.modules.permission.models import SysPermission
from app.modules.mes.catalog import MENUS
from test_quality_menu_sync import store as menu_store, Adapter


@pytest.fixture
def store(menu_store, monkeypatch):
    definition = next(item for item in MENUS if item.key == "MesScheduling")
    monkeypatch.setattr(public, "collect_catalog", lambda: NS(menus=[definition]))
    with Session(menu_store.engine, expire_on_commit=False) as session:
        permission = SysPermission(permission_key="mes:schedule:list", permission_name="查询生产排程", module_code="mes")
        session.add(permission); session.flush()
        row = session.get(SysMenu, menu_store.menu)
        row.menu_key, row.path, row.menu_name = "MesScheduling", "/mes/scheduling", "生产排程"
        row.flex_form = {"customer_setting":"keep", "route":{"meta":{"mes_domain":"scheduling", "keepAlive":True}}}
        session.commit()
        menu_store.new = permission.id
    return menu_store


def run(store):
    with Session(store.engine) as session:
        changed = asyncio.run(public.upgrade_legacy_page(Adapter(session), menu_key="MesScheduling", expected_path="/mes/scheduling",
            previous_component="mes/capability/index", previous_permission_key="mes:operation_task:manage",
            obsolete_route_meta={"mes_domain":"scheduling"}, user_id=store.user_id))
        session.commit()
        return changed


def test_scheduling_menu_moves_from_roadmap_to_implemented_page_idempotently(store):
    assert run(store)
    with Session(store.engine) as session:
        row = session.get(SysMenu, store.menu)
        assert row.component == "mes/scheduling/index" and row.permission_id == store.new
        assert row.id == store.menu and row.menu_name == "生产排程"
        assert row.icon == "custom-icon" and row.sort_no == 88
        assert row.flex_form == {"customer_setting":"keep", "route":{"meta":{"keepAlive":True}}}
        updated_at = row.updated_at
    assert not run(store)
    with Session(store.engine) as session: assert session.get(SysMenu, store.menu).updated_at == updated_at


@pytest.mark.parametrize("field,value", [("component","custom/scheduling/index"), ("path","/custom/scheduling"), ("is_external",True)])
def test_custom_scheduling_navigation_is_not_overwritten(store, field, value):
    with Session(store.engine) as session:
        setattr(session.get(SysMenu, store.menu), field, value); session.commit()
    assert not run(store)
    with Session(store.engine) as session: assert getattr(session.get(SysMenu, store.menu), field) == value


def test_custom_permission_survives_known_placeholder_replacement(store):
    with Session(store.engine) as session:
        session.get(SysMenu, store.menu).permission_id = store.custom; session.commit()
    assert run(store)
    with Session(store.engine) as session:
        row = session.get(SysMenu, store.menu)
        assert row.component == "mes/scheduling/index" and row.permission_id == store.custom
