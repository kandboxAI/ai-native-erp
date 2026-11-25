from __future__ import annotations

from app.framework.crud.service import CrudService
from app.framework.db.session import get_session_context

from .repository import repository


service = CrudService(repository=repository, session_getter=get_session_context)


async def ensure_catalog_entries(session, definitions, *, previous_names=None):
    """模块开通公共契约；调用方负责租户上下文和提交。"""
    from .repository import ensure_catalog_entries as ensure
    return await ensure(session, definitions, previous_names=previous_names)


async def merge_catalog_entry(session, definition, *, previous_key, previous_path):
    from .repository import merge_catalog_entry as merge
    await merge(session, definition, previous_key=previous_key, previous_path=previous_path)


async def retire_catalog_entry(session, portal_code, menu_key, path, *, actor_id=None):
    """停用明确退役的目录入口，保留原菜单与绑定记录。"""
    from .repository import retire_catalog_entry as retire
    await retire(session, portal_code, menu_key, path, actor_id=actor_id)
