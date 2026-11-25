from typing import Any
from uuid import UUID

from app.auth.schemas import AuthenticatedUser
from app.framework.crud.service import CrudService
from app.framework.db.session import get_session_context

from .repository import entry_list_repository, repository
from .schemas import DictionaryEntryListQuery


class DictionaryService(CrudService):
    async def list_entries(self, params: DictionaryEntryListQuery, _current_user: AuthenticatedUser) -> dict[str, Any]:
        async with get_session_context() as session:
            return await entry_list_repository.list_entries(session, params)

    async def options(self, dict_codes: list[str], *, include_inactive: bool = False) -> dict[str, list[dict[str, Any]]]:
        async with get_session_context() as session:
            return await self.options_in_session(session, dict_codes, include_inactive=include_inactive)

    async def options_in_session(self, session, dict_codes: list[str], *, include_inactive: bool = False) -> dict[str, list[dict[str, Any]]]:
        """调用方事务内的字典选项读取；用于开通配置后的同事务业务校验。"""
        return await entry_list_repository.options(session, dict_codes, include_inactive=include_inactive)


service = DictionaryService(repository=repository, session_getter=get_session_context)


async def labels_for_values(session, pairs):
    """供业务保存可见公共选项的当时中文名称；不创建独立事务，不返回备注。"""
    from .label_repository import labels_for_values as labels
    return await labels(session, pairs)


async def ensure_builtin_definitions(session, definitions):
    """仅供租户开通调用；复用完整开通事务。"""
    from .repository import ensure_builtin_definitions as ensure
    await ensure(session, definitions)


async def validate_dictionary_item_reference(session, *, current_user, dict_code: str,
                                             item_code: str, lock: bool = False) -> bool:
    """当前事务内校验启用公共选项；与options一致，登录用户无需字典管理权限。

    返回存在性，不返回名称/备注；不flush/commit/rollback，不代替消费者权限。
    lock仅供写入消费者使用，锁持续到调用者事务结束。
    """
    from app.core.exceptions import AppException
    from app.framework.db.tenant import get_tenant_schema

    if (not isinstance(current_user.user_id, UUID) or not current_user.tenant_schema
            or get_tenant_schema() != current_user.tenant_schema):
        raise AppException("字典访问的租户身份不匹配", 403)
    if (type(lock) is not bool or any(not isinstance(value, str) or not value
            or value != value.strip() or len(value) > 64 or "\x00" in value
            for value in (dict_code, item_code))):
        raise AppException("字典编码或取值无效", 422)
    with session.no_autoflush:
        return await entry_list_repository.reference(session, dict_code, item_code, lock=lock) is not None
