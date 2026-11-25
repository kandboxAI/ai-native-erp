"""业务单据可写组织的选择契约，不返回联系人等组织详情。"""
from .repository import writable_org_options


async def list_writable_org_options(session, user, permission: str, keyword: str = "", limit: int = 50):
    return [dict(row) for row in await writable_org_options(session, user, permission, keyword, min(max(limit, 1), 50))]
