from sqlalchemy.exc import IntegrityError
from app.auth.scope_filters import has_global_access, resolve_write_org_id
from app.core.exceptions import AppException
from app.framework.db.ids import uuid7
from app.framework.db.models import utc_now
from app.framework.db.session import get_session_context
from .models import MdLocation
from .public import CONSUMERS, SELECTION_PERMISSIONS
from .repository import repository


def location_views(rows):
    """按名称发布独立位置；历史层级字段仅在存储中保留。"""
    result = []
    for row in rows:
        item = row.model_dump(mode="json", exclude={"flex_form", "created_by", "updated_by", "deleted_by", "deleted_at"})
        # 保留旧响应键供已加载的客户端兼容，不再发布或计算层级。
        item.update(parent_id=None, path_name=row.location_name,
                    is_selectable=row.is_active and row.deleted_at is None)
        result.append(item)
    return result


class LocationService:
    def can_change_org(self, user):
        return "md_location:manage" in user.permissions and has_global_access(user, "md_location:manage")

    def permission(self, user, permission):
        if permission not in SELECTION_PERMISSIONS or permission not in user.permissions:
            raise AppException("无权选择位置", status_code=403)

    async def choices(self, user, permission="md_location:list", org_id=None, *, selectable=False):
        self.permission(user, permission)
        async with get_session_context() as session:
            rows = await repository.rows(session, user, permission, org_id)
        if len(rows) > 10000:
            raise AppException("位置数量较多，请选择所属组织后查询")
        items = location_views(rows)
        if selectable:
            # 业务选取只发布位置标识、名称和坐标，不发布维护备注及审计信息。
            fields = {"id", "org_id", "location_no", "location_name", "location_type_code", "parent_id",
                      "latitude", "longitude", "coordinate_system_code", "path_name"}
            items = [{key: value for key, value in item.items() if key in fields}
                     for item in items if item["is_selectable"]]
        return {"items": items}

    async def metadata(self, user):
        permission = "md_location:manage" if "md_location:manage" in user.permissions else "md_location:list"
        self.permission(user, permission)
        async with get_session_context() as session:
            organizations = await repository.organizations(session, user, permission)
            account_org_id = str(user.org_id) if user.org_id else None
            allowed_ids = {item["id"] for item in organizations}
            default_org_id = account_org_id if account_org_id in allowed_ids else (
                organizations[0]["id"] if len(organizations) == 1 else None)
            return {"organizations": organizations, "default_org_id": default_org_id,
                    "can_change_org": self.can_change_org(user),
                    "location_types": await repository.dictionary_items(session, "md_location_type"),
                    "coordinate_systems": await repository.dictionary_items(session, "md_coordinate_system")}

    async def require_reference(self, session, location_id, org_id, *, for_update=False):
        if for_update:
            await repository.lock_org(session, org_id)
        row = await repository.get(session, location_id, for_update=for_update)
        if row is None or row.deleted_at is not None:
            raise AppException("位置不存在或已删除")
        if row.org_id != org_id or not row.is_active:
            raise AppException("位置已停用或组织不匹配")
        return row

    async def require_scoped_reference(self, session, location_id, user, permission, *, for_update=False):
        self.permission(user, permission)
        row = await repository.get(session, location_id, user=user, permission=permission)
        if row is None:
            raise AppException("位置不存在或不在当前账号可访问范围内", status_code=404)
        return await self.require_reference(session, location_id, row.org_id, for_update=for_update)

    async def validate(self, session, body, org_id, row_id=None, user=None):
        if not await repository.organization_exists(session, org_id):
            raise AppException("所属组织不存在或已停用")
        if await repository.number_exists(session, org_id, body.location_no, row_id):
            raise AppException("该组织下位置编号已存在", status_code=409)
        for field, code in (("location_type_code", "md_location_type"), ("coordinate_system_code", "md_coordinate_system")):
            items = await repository.dictionary_items(session, code)
            if getattr(body, field) not in {item["value"] for item in items}:
                raise AppException("位置类型或坐标系无效，请刷新字典选项")

    async def notify(self, session, row, user):
        for consumer in CONSUMERS.values():
            if consumer.changed and await repository.table_exists(session, consumer.table_name):
                await consumer.changed(session, row, user)

    async def is_referenced(self, session, location_id):
        for consumer in CONSUMERS.values():
            if await repository.table_exists(session, consumer.table_name) and await consumer.reference(session, location_id):
                return True
        return False

    async def save(self, body, user, location_id=None):
        self.permission(user, "md_location:manage")
        try:
            async with get_session_context() as session, session.begin():
                row = None
                if location_id:
                    row = await repository.get(session, location_id, user=user, permission="md_location:manage")
                    if row is None:
                        raise AppException("位置不存在或无权修改", status_code=404)
                original_org_id = row.org_id if row else None
                org_id = resolve_write_org_id(user, body.org_id or original_org_id, "md_location:manage")
                if row and original_org_id != org_id and not self.can_change_org(user):
                    raise AppException("修改位置所属组织需要全部数据范围的位置信息维护权限", status_code=403)
                # 归属调整同时锁定原组织及目标组织，顺序固定，协调业务引用与并发修改。
                for lock_org_id in sorted({org_id, original_org_id} - {None}, key=str):
                    await repository.lock_org(session, lock_org_id)
                if location_id:
                    row = await repository.get(session, location_id, user=user, permission="md_location:manage", for_update=True)
                    if row is None:
                        raise AppException("位置不存在或无权修改", status_code=404)
                    if row.org_id != original_org_id or row.version_no != body.expected_version:
                        raise AppException("位置已被他人修改，请刷新后重试", status_code=409)
                    if body.location_no is not None and body.location_no != row.location_no:
                        raise AppException("位置编号由系统维护，不能修改")
                    if row.org_id != org_id and await self.is_referenced(session, row.id):
                        raise AppException("位置已被仓库、资产或巡查引用，不能直接修改所属组织，请先处理相关业务关联", status_code=409)
                new_id = uuid7() if row is None else None
                body = body.model_copy(update={"location_no": row.location_no if row else (
                    body.location_no or f"LOC-{new_id.hex.upper()}")})
                await self.validate(session, body, org_id, location_id, user)
                values = body.model_dump(exclude={"org_id", "expected_version", "parent_id"})
                if row is None:
                    row = MdLocation(id=new_id, org_id=org_id, created_by=user.user_id, **values)
                else:
                    row.org_id = org_id
                    for key, value in values.items():
                        setattr(row, key, value)
                    row.version_no += 1
                row.updated_at, row.updated_by = utc_now(), user.user_id
                repository.add(session, row)
                await session.flush()
                await self.notify(session, row, user)
                result = {"id": str(row.id), "version_no": row.version_no}
            return result
        except IntegrityError as exc:
            if getattr(exc.orig, "sqlstate", None) == "23505":
                raise AppException("位置编号冲突，请刷新后重试", status_code=409) from exc
            raise

    async def delete(self, location_id, expected_version, user):
        self.permission(user, "md_location:manage")
        async with get_session_context() as session, session.begin():
            row = await repository.get(session, location_id, user=user, permission="md_location:manage")
            if row is None:
                raise AppException("位置不存在或无权删除", status_code=404)
            await repository.lock_org(session, row.org_id)
            row = await repository.get(session, location_id, user=user, permission="md_location:manage", for_update=True)
            if row is None or row.version_no != expected_version:
                raise AppException("位置已被修改，请刷新后重试", status_code=409)
            if await self.is_referenced(session, row.id):
                raise AppException("位置已被业务引用，请使用停用功能保留历史关联", status_code=409)
            row.deleted_at = row.updated_at = utc_now()
            row.deleted_by = row.updated_by = user.user_id
            row.is_active = False
            row.version_no += 1
            repository.add(session, row)


service = LocationService()
