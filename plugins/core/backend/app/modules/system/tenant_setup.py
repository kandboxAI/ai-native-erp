"""系统管理模块的租户开通数据：代码定义的系统参数（可重复执行，已存在的不覆盖）。

字典、权限、菜单、内置管理员由 tenant_template 统一生成。
"""

from app.modules.system_setting.repository import repository as setting_repository


async def setup_tenant(session, ctx) -> None:
    await setting_repository.ensure_defaults(session, ctx.admin_user_id)
