from uuid import UUID

from sqlalchemy import false, select

from app.auth.data_scope import ORG_ACCESS_ALL
from app.auth.scope_filters import accessible_org_ids, alive_condition, scoped_conditions
from app.framework.db.models import utc_now
from app.modules.organization.service import service as organizations

from .models import SysMiniappBanner


def visible_conditions(user):
    """组织公开展示配置向下继承；不扩展用户的业务权限或其他分支的配置。"""
    conditions = [alive_condition(SysMiniappBanner), SysMiniappBanner.is_active.is_(True)]
    if user.org_access_mode_code != ORG_ACCESS_ALL:
        org_ids = accessible_org_ids(user)
        conditions.append(SysMiniappBanner.org_id.in_(organizations.ancestor_ids_query(org_ids)) if org_ids else false())
    return conditions


class BannerRepository:
    async def list(self, session, user, *, public: bool):
        conditions = visible_conditions(user) if public else scoped_conditions(SysMiniappBanner, user, "miniapp_menu:list")
        statement = select(SysMiniappBanner).where(*conditions).order_by(SysMiniappBanner.sort_no, SysMiniappBanner.id)
        return list((await session.exec(statement.limit(10 if public else 200))).scalars().all())

    async def get(self, session, banner_id: UUID, user, *, permission: str | None = None, lock=False):
        conditions = scoped_conditions(SysMiniappBanner, user, permission) if permission else visible_conditions(user)
        statement = select(SysMiniappBanner).where(SysMiniappBanner.id == banner_id, *conditions)
        if lock:
            statement = statement.with_for_update()
        return (await session.exec(statement)).scalars().first()

    async def create(self, session, *, banner_id, org_id, file_id, sort_no, is_active, user_id):
        # 标题已停止使用；保留旧非空列以兼容现有数据库，新记录写入空字符串。
        row = SysMiniappBanner(id=banner_id, org_id=org_id, image_file_id=file_id, title="", sort_no=sort_no, is_active=is_active,
                              created_by=user_id, updated_by=user_id)
        session.add(row)
        await session.flush()
        return row

    async def update(self, session, row, payload, user_id):
        for name in ("sort_no", "is_active"):
            setattr(row, name, getattr(payload, name))
        row.image_file_id = payload.file_id
        row.updated_at = utc_now()
        row.updated_by = user_id
        session.add(row)

    async def delete(self, session, row, user_id):
        row.deleted_at = utc_now()
        row.deleted_by = user_id
        row.updated_at = row.deleted_at
        row.updated_by = user_id
        session.add(row)


repository = BannerRepository()
