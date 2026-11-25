from app.auth.scope_filters import resolve_write_org_id
from app.core.exceptions import AppException
from app.framework.db.session import get_session_context
from app.framework.db.ids import uuid7
from app.modules.file.service import register_file_access, register_file_scene, service as files

from .banner_repository import repository
from .banner_schemas import BannerItem

BUSINESS_TYPE = "sys_miniapp_banner"
SCENE = "miniapp_banner"
BANNER_MAX_BYTES = 2 * 1024 * 1024
register_file_scene(SCENE, kinds={"image"}, max_bytes=BANNER_MAX_BYTES, max_count=1)


async def can_read_image(session, user, banner_id):
    if await repository.get(session, banner_id, user) is not None:
        return True
    if "miniapp_menu:list" in user.permissions:
        return await repository.get(session, banner_id, user, permission="miniapp_menu:list") is not None
    return False


register_file_access(BUSINESS_TYPE, can_read_image)


class BannerService:
    async def items(self, session, rows):
        images = await files.items_for_business(session, BUSINESS_TYPE, [row.id for row in rows], scene_code=SCENE)
        return [BannerItem(id=row.id, org_id=row.org_id, sort_no=row.sort_no,
                           is_active=row.is_active, image=next((image for image in images.get(row.id, [])
                           if str(image["id"]) == str(row.image_file_id)), None)) for row in rows]

    async def list(self, user, *, public=False):
        async with get_session_context() as session:
            rows = await repository.list(session, user, public=public)
            return await self.items(session, rows)

    async def save(self, payload, user, *, banner_id=None):
        permission = "miniapp_menu:update" if banner_id else "miniapp_menu:create"
        async with get_session_context() as session:
            if banner_id:
                row = await repository.get(session, banner_id, user, permission=permission, lock=True)
                if row is None:
                    raise AppException("轮播图不存在或无权修改", status_code=404)
                if row.image_file_id != payload.file_id:
                    await files.bind(session, [payload.file_id], user=user, org_id=row.org_id, scene_code=SCENE,
                                     business_type_code=BUSINESS_TYPE, business_id=row.id)
                await repository.update(session, row, payload, user.user_id)
            else:
                org_id = resolve_write_org_id(user, None, permission)
                banner_id = uuid7()
                await files.bind(session, [payload.file_id], user=user, org_id=org_id, scene_code=SCENE,
                                 business_type_code=BUSINESS_TYPE, business_id=banner_id)
                row = await repository.create(session, banner_id=banner_id, org_id=org_id, file_id=payload.file_id,
                                              sort_no=payload.sort_no,
                                              is_active=payload.is_active, user_id=user.user_id)
            result = (await self.items(session, [row]))[0]
            await session.commit()
            return result

    async def delete(self, banner_id, user):
        async with get_session_context() as session:
            row = await repository.get(session, banner_id, user, permission="miniapp_menu:delete", lock=True)
            if row is None:
                raise AppException("轮播图不存在或无权删除", status_code=404)
            # 软删除保留文件绑定；下载鉴权随配置删除而失效。
            await repository.delete(session, row, user.user_id)
            await session.commit()


service = BannerService()
