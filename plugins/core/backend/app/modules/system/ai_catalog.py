"""本模块审核过的 AI 查询字段与语义定义；新增字段默认不开放。"""

from pathlib import Path

from app.framework.ai_catalog import AiProvider, AiQueryResourceDef

READ_FIELDS = {'sys_org': ('id',
             'org_no',
             'org_name',
             'org_type_code',
             'parent_id',
             'province',
             'city',
             'district',
             'sort_no',
             'is_active'),
 'sys_department': ('id',
                    'org_id',
                    'department_no',
                    'department_name',
                    'parent_id',
                    'sort_no',
                    'is_active'),
 'sys_dict': ('id', 'dict_code', 'dict_name', 'is_tenant_extensible', 'is_active'),
 'sys_dict_item': ('id', 'dict_id', 'item_code', 'item_name', 'sort_no', 'is_builtin', 'is_active'),
 'sys_miniapp_menu': ('id',
                      'portal_code',
                      'menu_key',
                      'menu_name',
                      'group_key',
                      'group_name',
                      'path',
                      'sort_no',
                      'is_active')}

PERMISSIONS = {'sys_org': 'organization:list',
 'sys_department': 'department:list',
 'sys_dict': 'dictionary:list',
 'sys_dict_item': 'dictionary_item:list',
 'sys_miniapp_menu': 'miniapp_menu:list'}

PROVIDER = AiProvider(
    domain='system',
    resources=tuple(AiQueryResourceDef(name, PERMISSIONS[name], fields) for name, fields in READ_FIELDS.items()),
    semantics_path=Path(__file__).with_name("ai_semantics.json"),
)
