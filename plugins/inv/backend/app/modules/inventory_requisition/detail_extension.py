"""行业插件在已鉴权的领用详情中补充只读摘要；不改变权限和库存。"""
_providers = {}


def register_detail_extension(plugin_key, provider):
    _providers[plugin_key] = provider


async def detail_fields(session, request, user):
    fields = []
    for key, provider in _providers.items():
        if key in user.enabled_plugin_keys:
            fields.extend(await provider(session, request, user))
    return fields
