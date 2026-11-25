"""L1 navigation and selected plugin navigation extensions."""

import json
from pathlib import Path

from app.framework.catalog import MenuDef, iter_module_attr


MENUS = [
    MenuDef(**item)
    for item in json.loads(
        Path(__file__).with_name("core_catalog.json").read_text(encoding="utf-8")
    )
]
CORE_MENU_KEYS = frozenset(item.key for item in MENUS)
for module in iter_module_attr("navigation_catalog"):
    MENUS.extend(module.MENUS)
