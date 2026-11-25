"""业务插件显式登记独立仓库视图；默认显示普通仓库，inv 不反向导入业务插件。"""
from dataclasses import dataclass
from sqlalchemy import or_, true
from app.core.exceptions import AppException
from .models import InvWarehouse


@dataclass(frozen=True)
class WarehouseScope:
    key: str
    plugin_key: str
    types: frozenset[str]
    list_permission: str
    manage_permission: str
    legacy_numbers: tuple[str, ...] = ()


_scopes: dict[str, WarehouseScope] = {}


def register_warehouse_scope(definition: WarehouseScope):
    old = _scopes.get(definition.key)
    if old is not None and old != definition: raise ValueError("仓库视图重复登记")
    _scopes[definition.key] = definition


def get_scope(key, user=None):
    if not key: return None
    spec = _scopes.get(key)
    if spec is None: raise AppException("仓库视图未登记", 422)
    if user is not None and spec.plugin_key not in getattr(user, "enabled_plugin_keys", ()):
        raise AppException("所属业务插件未启用，不能访问该仓库视图", 403)
    return spec


def warehouse_condition(key=None, user=None):
    spec = get_scope(key, user)
    if spec is None:
        types = set().union(*(scope.types for scope in _scopes.values())) if _scopes else set()
        # 历史编号是业务视图的兼容入口，不能据此剥夺普通仓库的可见性。
        # 仓库可由其他行业继续使用，归属以明确的用途为准。
        return InvWarehouse.warehouse_type_code.notin_(types) if types else true()
    return or_(InvWarehouse.warehouse_type_code.in_(spec.types), InvWarehouse.warehouse_no.in_(spec.legacy_numbers))


def configurable_scope(warehouse):
    return next((spec for spec in _scopes.values() if warehouse.warehouse_type_code in spec.types), None)
