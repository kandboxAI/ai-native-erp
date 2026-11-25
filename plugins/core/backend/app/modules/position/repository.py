"""岗位配置查询与关联校验，复用通用 CRUD 的范围和审计。"""
from sqlmodel import select

from app.auth.scope_filters import scoped_conditions
from app.core.exceptions import AppException
from app.framework.crud.repository import SqlModelCrudRepository
from app.modules.department.models import SysDepartment

from .models import SysPosition
from .schemas import PositionItem, PositionWrite


async def normalize_position(session, data, user, entity):
    permission = "position:update" if entity else "position:create"
    if entity and any(data[key] != getattr(entity, key) for key in ("org_id", "department_id")):
        raise AppException("岗位的组织和部门不可修改，请停用后新建", status_code=422)
    for key in ("position_no", "position_name"):
        data[key] = data[key].strip()
        if not data[key]:
            raise AppException("岗位编号和名称不能为空", status_code=422)
    department = (await session.exec(select(SysDepartment).where(
        SysDepartment.id == data["department_id"], SysDepartment.org_id == data["org_id"],
        SysDepartment.is_active.is_(True), *scoped_conditions(SysDepartment, user, permission)))).first()
    if department is None:
        raise AppException("部门不存在、已停用或不属于该组织", status_code=422)
    parent = data.get("parent_position_id")
    visited = {entity.id} if entity else set()
    while parent:
        if parent in visited:
            raise AppException("上级岗位不能形成循环", status_code=422)
        visited.add(parent)
        row = (await session.exec(select(SysPosition).where(SysPosition.id == parent,
            SysPosition.org_id == data["org_id"], SysPosition.is_active.is_(True),
            *scoped_conditions(SysPosition, user, permission)))).first()
        if row is None:
            raise AppException("上级岗位不存在或不属于该组织", status_code=422)
        parent = row.parent_position_id
    return data


class PositionRepository(SqlModelCrudRepository):
    async def before_commit(self, session, entity, user, action):
        from app.framework.catalog import iter_module_attr
        from app.framework.plugin import loaded_plugin_manifests
        if action == "delete":
            used = select(SysPosition.id).where(SysPosition.parent_position_id == entity.id, SysPosition.deleted_at.is_(None))
            if (await session.exec(used.limit(1))).first():
                raise AppException("仍有关联岗位，请先删除关联岗位", status_code=409)
        await session.flush()
        modules = {name for manifest in loaded_plugin_manifests() if manifest.key in user.enabled_plugin_keys
                   for name in manifest.module_names}
        for provider in iter_module_attr("position_lifecycle", only=modules):
            await provider.synchronize(session, entity, user, action)


position_repository = PositionRepository(table_model=SysPosition, item_model=PositionItem,
    writable_columns=list(PositionWrite.model_fields),
    searchable_columns=["position_no", "position_name"], filterable_columns=["org_id", "is_active"],
    create_payload_normalizer=normalize_position, update_payload_normalizer=normalize_position, scope_resource="position")


async def reference_options(session, user, permission):
    """岗位/人事配置的只读关联选项，始终使用调用动作的数据范围。"""
    from app.modules.organization.models import SysOrg
    organizations = (await session.exec(select(SysOrg).where(SysOrg.is_active.is_(True),
        *scoped_conditions(SysOrg, user, permission)).order_by(SysOrg.org_name))).all()
    departments = (await session.exec(select(SysDepartment).where(SysDepartment.is_active.is_(True),
        *scoped_conditions(SysDepartment, user, permission)).order_by(SysDepartment.department_name))).all()
    positions = (await session.exec(select(SysPosition).where(*scoped_conditions(SysPosition, user, permission))
        .order_by(SysPosition.position_name))).all()
    return {"organizations": [{"id": str(row.id), "name": row.org_name} for row in organizations],
        "departments": [{"id": str(row.id), "org_id": str(row.org_id), "name": row.department_name} for row in departments],
        "positions": [{"id": str(row.id), "org_id": str(row.org_id), "name": row.position_name, "is_active": row.is_active} for row in positions]}



async def user_position_options(session, user, permission, org_id):
    """用户维护可选岗位：按用户维护动作授权范围读取，仅投影选项字段。"""
    rows = (await session.exec(select(SysPosition, SysDepartment)
        .join(SysDepartment, SysDepartment.id == SysPosition.department_id)
        .where(SysPosition.org_id == org_id, SysDepartment.org_id == org_id,
            *scoped_conditions(SysPosition, user, permission))
        .order_by(SysDepartment.department_name, SysPosition.position_name, SysPosition.id))).all()
    return [{"id": row.id, "org_id": row.org_id, "name": row.position_name,
             "department_name": department.department_name,
             "is_active": bool(row.is_active and department.is_active and department.deleted_at is None)}
            for row, department in rows]
