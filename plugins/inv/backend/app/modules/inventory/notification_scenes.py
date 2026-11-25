"""Notification scenes registered by the owning module."""
SCENES = [{'scene_key': 'inventory.stock_alert', 'scene_name': '库存预警', 'module_code': 'inventory', 'severity_code': 'important', 'description': '库存低于下限、缺货或超过上限时通知', 'templates': {'in_app': {'title_template': '库存预警：{product_name}', 'content_template': '{organization_name}的{product_name}当前库存{quantity}{unit}，{status_label}（{threshold_text}）'}}, 'routes': [{'target_type_code': 'actor', 'actor_key': 'operator', 'org_scope_code': 'event_organization'}, {'target_type_code': 'permission', 'permission_key': 'inventory_item:list', 'org_scope_code': 'event_organization'}]}]

SCENES += [{'scene_key': 'inventory.low_stock_alert',
 'inbox_category': 'alert',
  'scene_name': '低库存补货预警',
  'module_code': 'inventory',
  'severity_code': 'important',
  'description': '物资缺货或可用库存低于安全库存时，通知有权限的后勤人员尽快补货',
  'templates': {'in_app': {'title_template': '补货预警：{product_name}',
                           'content_template': '{organization_name}的{warehouse_name}中，{product_name}当前可用库存{quantity}{unit}，{status_label}（{threshold_text}），建议补货{suggested_replenishment_quantity}{unit}'}},
  'previous_templates': {'in_app': {'title_template': '补货预警：{product_name}',
                                    'content_template': '{organization_name}的{product_name}当前可用库存{quantity}{unit}，{status_label}（{threshold_text}），建议补货{suggested_replenishment_quantity}{unit}'}},
  'routes': [{'target_type_code': 'permission',
              'permission_key': 'inventory_stock_alert:list',
              'org_scope_code': 'event_organization'}]},
 {'scene_key': 'inventory.low_stock_recovered',
  'scene_name': '低库存恢复通知',
  'module_code': 'inventory',
  'severity_code': 'normal',
  'description': '物资补货后恢复到安全库存范围时，通知有权限的后勤人员',
  'templates': {'in_app': {'title_template': '库存已恢复：{product_name}',
                           'content_template': '{organization_name}的{warehouse_name}中，{product_name}当前可用库存{quantity}{unit}，已恢复正常（{threshold_text}）'}},
  'routes': [{'target_type_code': 'permission',
              'permission_key': 'inventory_stock_alert:list',
              'org_scope_code': 'event_organization'}]}]

PASS_THROUGH = {"title_template": "{title}", "content_template": "{content}"}

SCENES += [
    {
        "scene_key": "inventory.requisition_submitted",
        "inbox_category": "todo",
        "scene_name": "物资申领待审批",
        "module_code": "inventory",
        "severity_code": "important",
        "description": "物资申领提交后通知申请所属组织内有审批权限的人员",
        "templates": {"in_app": PASS_THROUGH},
        "routes": [
            {
                "target_type_code": "permission",
                "permission_key": "inventory_requisition:approve",
                "org_scope_code": "event_organization",
            }
        ],
    },
    {
        "scene_key": "inventory.requisition_approved",
        "scene_name": "物资申领待发放",
        "module_code": "inventory",
        "severity_code": "important",
        "description": "物资申领审批通过后通知申请所属组织内有发放权限的人员",
        "templates": {"in_app": PASS_THROUGH},
        "routes": [
            {
                "target_type_code": "permission",
                "permission_key": "inventory_requisition:issue",
                "org_scope_code": "event_organization",
            }
        ],
    },
    {
        "scene_key": "inventory.requisition_rejected",
        "scene_name": "物资申领已驳回",
        "module_code": "inventory",
        "severity_code": "normal",
        "description": "物资申领被驳回后通知申请人",
        "templates": {"in_app": PASS_THROUGH},
        "routes": [],
    },
    {
        "scene_key": "inventory.requisition_issued",
        "inbox_category": "todo",
        "scene_name": "物资申领已发放",
        "module_code": "inventory",
        "severity_code": "normal",
        "description": "物资发放完成后通知申请人",
        "templates": {"in_app": PASS_THROUGH},
        "routes": [],
    },
]

for _key, _name in (("receipt_exception", "收货异常待处理"), ("received", "物资申领已签收"), ("receipt_resolved", "收货异常已处理待签收")):
    SCENES.append({
        "scene_key": f"inventory.requisition_{_key}", "scene_name": _name,
        "module_code": "inventory", "severity_code": "important" if _key == "receipt_exception" else "normal",
        "description": _name, "templates": {"in_app": PASS_THROUGH},
        "routes": [] if _key == "receipt_resolved" else [{"target_type_code": "permission", "permission_key": "inventory_requisition:issue", "org_scope_code": "event_organization"}],
        **({"inbox_category": "todo"} if _key == "receipt_resolved" else {}),
    })
