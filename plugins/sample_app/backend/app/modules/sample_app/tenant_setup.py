"""租户开通时补齐计薪参数、税率档和默认社保方案。已有数据不覆盖。"""
from . import repository


async def setup_tenant(session, ctx):
    if getattr(ctx, "root_org_id", None) is None:
        return
    await repository.ensure_defaults(session, ctx.root_org_id, None)
