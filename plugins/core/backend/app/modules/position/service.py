from app.framework.crud.service import CrudService
from app.framework.db.session import get_session_context
from .repository import position_repository, reference_options as read_reference_options

position_service = CrudService(repository=position_repository, session_getter=get_session_context)


async def reference_options(user, permission):
    async with get_session_context() as session:
        return await read_reference_options(session, user, permission)



async def user_position_options(session, user, permission, org_id):
    """调用方已按用户维护动作校验目标组织，返回同范围内的岗位选项。"""
    from .repository import user_position_options as read_options
    return await read_options(session, user, permission, org_id)
