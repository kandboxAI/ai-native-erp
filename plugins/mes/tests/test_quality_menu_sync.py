"""旧质量说明页升级回归；只使用 SQLite 内存库，不写开发库。"""
import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy import Column, JSON, MetaData, Table, Uuid, create_engine, event
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session

from app.core.exceptions import AppException
from app.modules.menu import public
from app.modules.menu.models import SysMenu
from app.modules.permission.models import SysPermission
from app.modules.mes.catalog import MENUS


@pytest.fixture
def store(monkeypatch):
    from app.framework.db.registry import import_all_models
    import_all_models()
    definition = next(item for item in MENUS if item.key == "MesQuality")
    monkeypatch.setattr(public, "collect_catalog", lambda: NS(menus=[definition]))
    engine = create_engine("sqlite:///:memory:")
    @event.listens_for(engine, "connect")
    def foreign_keys(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")
    metadata = MetaData()
    models = (SysMenu, SysPermission)
    names = {model.__tablename__ for model in models}
    external = {fk.target_fullname.rsplit(".", 1)[0] for model in models for fk in model.__table__.foreign_keys} - names
    for name in external:
        Table(name, metadata, Column("id", Uuid, primary_key=True))
    for model in models:
        table = model.__table__.to_metadata(metadata)
        for column in table.columns:
            column.server_default = None
            if isinstance(column.type, JSONB): column.type = JSON()
    metadata.create_all(engine)
    user_id = uuid4()
    with engine.begin() as connection:
        connection.execute(metadata.tables["sys_user"].insert().values(id=user_id))
    with Session(engine, expire_on_commit=False) as session:
        permissions = [SysPermission(permission_key=key, permission_name=key, module_code="mes") for key in
            ("mes:operation_task:manage", "mes:quality:list", "custom:inspect")]
        session.add_all(permissions); session.flush()
        menu = SysMenu(menu_key="MesQuality", menu_name="工序检验", menu_type_code="menu", path="/mes/quality",
            component="mes/capability/index", permission_id=permissions[0].id, icon="custom-icon", sort_no=88,
            flex_form={"customer_setting": "keep", "route": {"meta": {"mes_domain": "quality", "keepAlive": True}, "custom_route": "keep"}})
        session.add(menu); session.commit()
    yield NS(engine=engine, user_id=user_id, menu=menu.id, old=permissions[0].id, new=permissions[1].id, custom=permissions[2].id)
    engine.dispose()


class Adapter:
    def __init__(self, session): self.session = session
    async def execute(self, statement): return self.session.execute(statement)
    async def get(self, model, identifier): return self.session.get(model, identifier)


async def upgrade(session, store):
    return await public.upgrade_legacy_page(session, menu_key="MesQuality", expected_path="/mes/quality",
        previous_component="mes/capability/index", previous_permission_key="mes:operation_task:manage",
        obsolete_route_meta={"mes_domain": "quality"}, user_id=store.user_id)


def run(store):
    with Session(store.engine) as session:
        result = asyncio.run(upgrade(Adapter(session), store))
        session.commit()
        return result


def test_legacy_component_permission_and_metadata_upgrade_idempotently(store):
    with Session(store.engine) as session:
        created_at = session.get(SysMenu, store.menu).created_at
    assert run(store)
    with Session(store.engine) as session:
        row = session.get(SysMenu, store.menu)
        assert row.component == "mes/quality/index" and row.permission_id == store.new
        assert row.id == store.menu and row.created_at == created_at
        assert row.icon == "custom-icon" and row.sort_no == 88 and row.is_active and row.is_visible
        assert row.flex_form == {"customer_setting": "keep", "route": {"meta": {"keepAlive": True}, "custom_route": "keep"}}
        assert row.updated_by == store.user_id
        updated_at = row.updated_at
    assert not run(store)
    with Session(store.engine) as session:
        assert session.get(SysMenu, store.menu).updated_at == updated_at


@pytest.mark.parametrize("field,value", [("component", "custom/quality/index"), ("path", "/custom/quality"), ("is_external", True)])
def test_tenant_custom_page_is_preserved(store, field, value):
    with Session(store.engine) as session:
        setattr(session.get(SysMenu, store.menu), field, value); session.commit()
    assert not run(store)
    with Session(store.engine) as session:
        row = session.get(SysMenu, store.menu)
        assert getattr(row, field) == value and row.permission_id == store.old
        assert row.flex_form["route"]["meta"]["mes_domain"] == "quality"


def test_custom_permission_and_custom_metadata_are_preserved(store):
    with Session(store.engine) as session:
        row = session.get(SysMenu, store.menu)
        row.permission_id = store.custom
        row.flex_form = {"route": {"meta": {"mes_domain": "custom"}}}
        session.commit()
    assert run(store)
    with Session(store.engine) as session:
        row = session.get(SysMenu, store.menu)
        assert row.component == "mes/quality/index" and row.permission_id == store.custom
        assert row.flex_form["route"]["meta"]["mes_domain"] == "custom"


def test_partially_fixed_menu_still_updates_old_permission(store):
    with Session(store.engine) as session:
        session.get(SysMenu, store.menu).component = "mes/quality/index"; session.commit()
    assert run(store)
    with Session(store.engine) as session:
        assert session.get(SysMenu, store.menu).permission_id == store.new


def test_missing_target_permission_does_not_partially_upgrade(store):
    with Session(store.engine) as session:
        session.get(SysPermission, store.new).is_active = False; session.commit()
    with pytest.raises(AppException, match="新权限尚未配置"):
        run(store)
    with Session(store.engine) as session:
        row = session.get(SysMenu, store.menu)
        assert row.component == "mes/capability/index" and row.permission_id == store.old


def test_caller_transaction_controls_commit_and_rollback(store):
    with Session(store.engine) as session:
        assert asyncio.run(upgrade(Adapter(session), store))
        session.rollback()
    with Session(store.engine) as session:
        assert session.get(SysMenu, store.menu).component == "mes/capability/index"


def test_mes_tenant_setup_registers_the_explicit_menu_upgrade(monkeypatch):
    from app.modules.mes.tenant_setup import setup_tenant
    from app.modules.inventory import public as stock
    monkeypatch.setattr(stock, "ensure_stock_order_types", AsyncMock())
    monkeypatch.setattr(public, "retire_empty_directory", AsyncMock())
    monkeypatch.setattr(public, "hide_legacy_entry", AsyncMock())
    upgrade_page = AsyncMock()
    monkeypatch.setattr(public, "upgrade_legacy_page", upgrade_page)
    session, ctx = object(), NS(admin_user_id=uuid4())
    asyncio.run(setup_tenant(session, ctx))
    upgrade_page.assert_any_await(session, menu_key="MesQuality", expected_path="/mes/quality",
        previous_component="mes/capability/index", previous_permission_key="mes:operation_task:manage",
        obsolete_route_meta={"mes_domain": "quality"}, user_id=ctx.admin_user_id)
    upgrade_page.assert_any_await(session, menu_key="MesScheduling", expected_path="/mes/scheduling",
        previous_component="mes/capability/index", previous_permission_key="mes:operation_task:manage",
        obsolete_route_meta={"mes_domain": "scheduling"}, user_id=ctx.admin_user_id)
