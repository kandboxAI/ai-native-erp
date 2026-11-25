"""制造收发复用 inv；全部使用模拟会话，不写真实库。"""
import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from app.auth.schemas import AuthenticatedUser
from app.core.exceptions import AppException
from app.modules.inventory import public as stock
from app.modules.inventory.stock_order import api
from app.modules.inventory.stock_order.schemas import OrderTypeOptionQuery
from app.modules.inventory.stock_order.service import require_type_permission
from app.modules.mes.warehouse_policy import allows
from app.modules.mes.warehouse_scenes import SCENES, type_specifications, validate_scene


def test_real_manufacturing_catalog_has_one_warehouse_entry_and_preserves_asset_pages():
    from app.framework.catalog import collect_catalog
    from app.framework.menu_composition import compose_menus
    from app.modules.menu.models import SysMenu
    from app.modules.menu.repository import build_tree
    definitions = collect_catalog().menus
    rows = {menu.key: SysMenu(menu_key=menu.key, menu_name=menu.name,
        menu_type_code=menu.menu_type_code, path=menu.path, component=menu.component,
        is_visible=menu.is_visible, sort_no=menu.sort_no) for menu in definitions}
    for menu in definitions:
        if menu.parent_key in rows:
            rows[menu.key].parent_id = rows[menu.parent_key].id
    tree = compose_menus(build_tree(list(rows.values()), {}), {"inv", "mes"})
    roots = {menu["menu_key"]: menu for menu in tree}
    assert roots["MesWarehouse"]["is_visible"] and not roots["Inventory"]["is_visible"]
    assert {"InventoryTransfer", "InventoryBorrow", "InventoryDamage", "InventoryStockSettings"} <= {
        menu["menu_key"] for menu in roots["MesWarehouse"]["children"]}
    assert any(menu["menu_key"] == "LocationRoot" for menu in roots["SystemManagement"]["children"])
    assets = next(menu for menu in roots["MesArchives"]["children"] if menu["menu_key"] == "AssetManagement")
    assert {menu["menu_key"] for menu in assets["children"]} == {"AssetManagementLedger", "AssetHandovers"}


@pytest.mark.parametrize("enabled,merged", [({"inv"}, False), ({"inv", "edu"}, False),
    ({"inv", "mes"}, True), ({"inv", "edu", "mes"}, False)])
def test_real_plugin_view_requirements_follow_tenant_activation(monkeypatch, enabled, merged):
    from app.framework import menu_composition as navigation
    from app.modules.mes import catalog as mes_catalog
    edu_catalog = pytest.importorskip("app.modules.education.catalog")
    monkeypatch.setattr(navigation, "iter_module_attr", lambda _: [mes_catalog, edu_catalog])
    def node(key, children=()):
        return dict(id=key, menu_key=key, is_visible=True, children=list(children))
    roots = [node("Inventory", [node("InventoryStock"), node("InventoryBorrow")]),
             node("MesWarehouse", [node("MesWarehouseStock")])]
    result = navigation.compose_menus(roots, enabled)
    assert result[0]["is_visible"] is not merged
    assert ("InventoryBorrow" in {item["menu_key"] for item in result[1]["children"]}) is merged


@pytest.fixture
def actor():
    return AuthenticatedUser(auth_user_id=uuid4(), tenant_id=uuid4(), tenant_no="test", tenant_schema="t_test",
        user_id=uuid4(), org_id=uuid4(), enabled_plugin_keys=["inv", "mes"],
        permissions=["inventory_inbound:create", "inventory_outbound:create"])


@pytest.mark.parametrize("number", SCENES)
def test_manual_scenes_allow_matching_org_and_warehouse_without_production_source(monkeypatch, actor, number):
    _, direction, kind = SCENES[number]
    warehouse_id = uuid4()
    warehouse = dict(org_id=actor.org_id, warehouse_type_code=kind)
    monkeypatch.setattr(stock, "get_stock_warehouse", AsyncMock(return_value=warehouse))
    order = NS(org_id=actor.org_id, from_warehouse_id=warehouse_id if direction == "out" else None,
               to_warehouse_id=warehouse_id if direction == "in" else None, source_doc_type_code=None)
    spec = next(row for row in type_specifications() if row["type_no"] == number)
    order_type = NS(**spec, is_negative_allowed=False)
    assert require_type_permission(actor, order_type, "create") == f"inventory_{'inbound' if direction == 'in' else 'outbound'}:create"
    asyncio.run(validate_scene(None, order, order_type, [], actor))
    assert not spec["required_field_config"].get("source_managed")
    warehouse["warehouse_type_code"] = "mes_finished"
    with pytest.raises(AppException, match="请选择同一组织"):
        asyncio.run(validate_scene(None, order, order_type, [], actor))
    warehouse["warehouse_type_code"], warehouse["org_id"] = kind, uuid4()
    with pytest.raises(AppException, match="请选择同一组织"):
        asyncio.run(validate_scene(None, order, order_type, [], actor))
    actor.enabled_plugin_keys = ["inv"]
    with pytest.raises(AppException, match="未启用"):
        require_type_permission(actor, order_type, "create")


def test_tool_warehouse_does_not_become_a_production_material_or_finished_warehouse():
    for purpose in ("issue", "return", "receipt", "shipment"):
        assert not allows(dict(warehouse_no="TOOL", warehouse_type_code="mes_tool"), purpose)


def test_line_warehouse_cannot_bypass_scene_and_reversal_keeps_same_warehouse_rule(monkeypatch, actor):
    order = NS(org_id=actor.org_id, from_warehouse_id=None, to_warehouse_id=uuid4(), reversal_of_order_id=uuid4())
    rows = [dict(org_id=actor.org_id, warehouse_type_code="mes_tool"), dict(org_id=actor.org_id, warehouse_type_code="mes_raw")]
    monkeypatch.setattr(stock, "get_stock_warehouse", AsyncMock(side_effect=rows))
    line = NS(from_warehouse_id=uuid4(), to_warehouse_id=None)
    kind = NS(type_no="MES_TOOL_IN", direction_code="in", is_negative_allowed=False)
    with pytest.raises(AppException, match="刀具仓库"):
        asyncio.run(validate_scene(None, order, kind, [line], actor))


def test_disabled_manufacturing_cannot_write_its_stock_thresholds(monkeypatch, actor):
    from app.modules.inventory.stock import service as stock_module
    from app.modules.inventory.warning.schemas import StockThresholdUpdate
    @asynccontextmanager
    async def session():
        yield None
    monkeypatch.setattr(stock_module, "get_session_context", session)
    monkeypatch.setattr(stock_module.warning_repository, "item_warehouse_setting", AsyncMock(return_value=(
        NS(id=uuid4()), NS(warehouse_type_code="mes_tool"), None)))
    save = AsyncMock()
    monkeypatch.setattr(stock_module.warning_repository, "save_setting", save)
    actor.enabled_plugin_keys = ["inv"]
    with pytest.raises(AppException, match="未启用"):
        asyncio.run(stock_module.service.configure_threshold(uuid4(), uuid4(),
            StockThresholdUpdate(min_quantity=1, max_quantity=10), actor))
    save.assert_not_awaited()


@pytest.mark.parametrize("scope,expected", [(None, ["ordinary"]), ("mes", ["ordinary", "manufacturing"])])
def test_type_options_do_not_leak_manufacturing_types_into_edu_or_standalone(monkeypatch, actor, scope, expected):
    from app.modules.inventory.stock_order import service as order_module
    @asynccontextmanager
    async def session():
        yield None
    types = [NS(required_field_config={}, model_dump=lambda **_: "ordinary"),
             NS(required_field_config={"warehouse_scope_key": "mes"}, model_dump=lambda **_: "manufacturing")]
    monkeypatch.setattr(order_module, "get_session_context", session)
    monkeypatch.setattr(api.type_repository, "options", AsyncMock(return_value=types))
    result = asyncio.run(api.order_type_options(OrderTypeOptionQuery(warehouse_scope_key=scope), actor))
    assert result["data"]["items"] == expected
    actor.enabled_plugin_keys = ["inv"]
    if scope:
        with pytest.raises(AppException, match="未启用"):
            asyncio.run(api.order_type_options(OrderTypeOptionQuery(warehouse_scope_key=scope), actor))
