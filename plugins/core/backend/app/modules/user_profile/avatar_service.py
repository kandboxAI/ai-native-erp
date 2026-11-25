"""当前租户用户头像：本人写入，文件模块保管上传原件和历史绑定版本。"""
from app.core.exceptions import AppException
from app.framework.db.session import get_session_context
from app.modules.file.service import PHOTO_MAX_BYTES, file_item, register_file_access, register_file_scene, service as files

from .repository import repository
from .schemas import AvatarSave

BUSINESS_TYPE = "sys_user"
SCENE = "user_avatar"
register_file_scene(SCENE, kinds={"image"}, max_bytes=PHOTO_MAX_BYTES, max_count=1)


async def can_read_avatar(session, user, user_id):
    if user_id == user.user_id:
        return await repository.get(session, user.user_id) is not None
    for permission in ("user_profile:list", "user_profile:detail"):
        if permission in user.permissions:
            # sys_user 的本人范围按 id 判断，不按创建人判断。
            from .service import scope_condition
            if await repository.get(session, user_id, scope_condition(user, permission)) is not None:
                return True
    return False


register_file_access(BUSINESS_TYPE, can_read_avatar)


class AvatarService:
    async def urls_for_users(self, session, legacy_urls):
        """为调用方已授权的账号批量解析头像，优先使用最新上传的头像。"""
        if not legacy_urls:
            return {}
        rows = await files.latest_for_businesses(session, BUSINESS_TYPE, legacy_urls.keys(), scene_code=SCENE)
        return {**legacy_urls, **{row.business_id: file_item(row)["url"] for row in rows}}

    async def url_for_user(self, session, user_id, *, legacy_url=None):
        """调用方已获权读取该租户用户；返回新签名，不把临时 URL 写入用户表。"""
        row = await files.latest_for_business(session, BUSINESS_TYPE, user_id, scene_code=SCENE)
        return file_item(row)["url"] if row is not None else legacy_url

    async def save(self, payload: AvatarSave, current_user):
        async with get_session_context() as session:
            user = await repository.get(session, current_user.user_id, for_update=True)
            if user is None or not user.is_active:
                raise AppException("当前账号不存在或已停用", status_code=403)
            # bind 校验上传人、场景、状态及有效期；不能挪用其他账号或业务的文件。
            rows = await files.bind(session, [payload.file_id], user=current_user, org_id=user.org_id,
                                    scene_code=SCENE, business_type_code=BUSINESS_TYPE, business_id=user.id)
            await repository.touch(session, user, current_user.user_id)
            result = {"avatar_url": file_item(rows[0])["url"], "file_id": str(rows[0].id)}
            await session.commit()
            return result


service = AvatarService()
