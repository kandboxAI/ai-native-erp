from app.framework.crud.service import CrudService
from app.framework.db.session import get_session_context

from .repository import repository


class OrganizationService(CrudService):
    def descendant_ids_query(self, org_ids):
        """仅组织目录 ID 查询；调用模块须先校验起始组织的管理授权。"""
        return repository.descendant_ids_query(org_ids)

    def ancestor_ids_query(self, org_ids):
        """仅供组织级公开配置继承使用的 ID 查询契约；不授予祖先业务数据访问权。"""
        return repository.ancestor_ids_query(org_ids)

    async def list_with_departments(self, params, current_user):
        return await self._call("list_with_departments", params, current_user)

    async def tree(self, current_user):
        return await self._call("tree", current_user)


service = OrganizationService(repository=repository, session_getter=get_session_context)
