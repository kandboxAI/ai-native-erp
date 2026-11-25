"""跨模块契约：引用只读位置元数据，调用者按业务动作权限验证组织。
处理器在同一事务执行，仅由数据所有者写自己的表；不反向导入业务。
"""
from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class LocationConsumer:
    table_name: str
    reference: Callable
    changed: Callable | None = None


CONSUMERS: dict[str, LocationConsumer] = {}
SELECTION_PERMISSIONS: set[str] = {"md_location:list", "md_location:manage"}


def register_consumer(key, *, table_name, reference, permissions=(), changed=None):
    CONSUMERS[key] = LocationConsumer(table_name, reference, changed)
    SELECTION_PERMISSIONS.update(permissions)


async def require_location(session, location_id, org_id, *, for_update=False):
    from .service import service
    return await service.require_reference(session, location_id, org_id, for_update=for_update)


async def selectable_locations(user, permission_key):
    """按业务动作权限及范围选取启用位置，仅返回选择器允许的元数据。"""
    from .service import service
    return (await service.choices(user, permission_key, selectable=True))["items"]


async def require_location_for_user(session, location_id, user, permission_key, *, for_update=False):
    from .service import service
    return await service.require_scoped_reference(session, location_id, user, permission_key, for_update=for_update)


async def read_location_metadata(session, location_id, org_id):
    """由业务对象授权后的组织读取位置元数据；允许展示已停用位置的历史关联。"""
    from .repository import repository
    row = await repository.get(session, location_id)
    return row if row is not None and row.org_id == org_id else None


def location_name_matches(location_id_column, org_id_column, pattern):
    """供已按业务对象鉴权和过滤范围的查询匹配关联位置名称；同时匹配组织。"""
    from .repository import repository
    return repository.name_matches(location_id_column, org_id_column, pattern)
