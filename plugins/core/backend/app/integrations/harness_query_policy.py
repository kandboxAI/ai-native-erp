"""已登记查询资源的权限和范围声明；不再按个人信息分级拦截字段。"""

from app.framework.ai_catalog import registered_ai_resources

# 能力包的旧字段声明保留为兼容元数据；执行器使用实际模型字段。
AI_READ_FIELDS = {name: item.definition.fields for name, item in registered_ai_resources().items()}
RESOURCE_PERMISSIONS = {name: item.definition.permission for name, item in registered_ai_resources().items()}
TENANT_WIDE_RESOURCES: frozenset[str] = frozenset({"sys_dict", "sys_dict_item", "sys_miniapp_menu"})
