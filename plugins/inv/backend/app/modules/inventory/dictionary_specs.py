"""Module-owned dictionary definitions and contributions."""
# 仓库用途仍是业务插件仓库视图的公开扩展点；普通仓库不限制为固定编号。
WAREHOUSE_TYPE_DICTIONARY = {'dict_code': 'inv_warehouse_type', 'dict_name': '仓库类型', 'scope': 'tenant',
    'items': [('general', '综合仓'), ('raw_material', '原料仓'), ('finished_goods', '成品仓'), ('quarantine', '待检仓')]}
DICTIONARIES = [{'dict_code': 'md_unit', 'dict_name': '计量单位', 'scope': 'global', 'items': [('piece', '件'), ('box', '箱'), ('pack', '包'), ('set', '套'), ('ream', '令'), ('bottle', '瓶'), ('kg', '千克'), ('meter', '米')]}, {'dict_code': 'md_currency', 'dict_name': '币种', 'scope': 'global', 'items': [('CNY', '人民币')]}, {'dict_code': 'md_settlement_method', 'dict_name': '结算方式', 'scope': 'tenant', 'items': [('bank_transfer', '银行转账'), ('cash', '现金'), ('online', '线上支付')]}, {'dict_code': 'md_settlement_cycle', 'dict_name': '结算周期', 'scope': 'tenant', 'items': [('per_order', '按单'), ('monthly', '月结'), ('quarterly', '季结')]},  {'dict_code': 'inv_location_type', 'dict_name': '库位类型', 'scope': 'tenant', 'items': [('storage', '存储'), ('staging', '暂存'), ('inspection', '检验'), ('production_line', '产线')]}, {'dict_code': 'inv_stock_status', 'dict_name': '库存状态', 'scope': 'global', 'items': [('available', '可用'), ('lent', '借出'), ('quarantine', '待检'), ('blocked', '冻结'), ('defective', '不合格')]}, {'dict_code': 'inv_stock_direction', 'dict_name': '库存方向', 'scope': 'global', 'items': [('in', '入库'), ('out', '出库'), ('move', '移位'), ('status', '状态转换'), ('adjust', '调整')]}, {'dict_code': 'inv_stock_order_status', 'dict_name': '库存单据状态', 'scope': 'global', 'items': [('draft', '草稿'), ('submitted', '待审批'), ('approved', '已审批'), ('confirmed', '已确认'), ('voided', '已作废')]}, {'dict_code': 'inv_handling_method', 'dict_name': '报损处理方式', 'scope': 'tenant', 'items': [('scrap', '报废'), ('repair', '维修'), ('return_supplier', '退回供应商'), ('other', '其他')]}, {'dict_code': 'inv_source_doc_type', 'dict_name': '上游业务单据类型', 'scope': 'global', 'items': [('pur_order', '采购订单'), ('canteen_plan', '菜谱采购计划'), ('inv_requisition', '领用申请'), ('inv_lend_request', '借用申请'), ('mes_work_order', '生产工单')]}, {'dict_code': 'inv_transaction_type', 'dict_name': '库存流水方向', 'scope': 'global', 'items': [('in', '入库'), ('out', '出库'), ('move', '移位'), ('status', '状态转换'), ('adjust', '调整')]}]
DICTIONARIES.append(WAREHOUSE_TYPE_DICTIONARY)
DICT_ITEMS = {'sys_module': [('inventory', '物资')], 'sys_setting_group': [('inventory', '物资')], 'wf_business_type': [('inventory_order', '库存单据')], 'audit_target_type': [('stock_order', '库存单据')], 'int_event_type': [('inv_stock_order_confirmed', '库存单据已确认')]}

DICTIONARIES += [{'dict_code': 'inv_requisition_status',
  'dict_name': '物资领用申请状态',
  'scope': 'global',
  'items': [('submitted', '待审批'),
            ('approved', '待发放'),
            ('rejected', '已驳回'),
            ('issued', '已发放'),
            ('withdrawn', '已撤回')]},
 {'dict_code': 'inv_requisition_event_type',
  'dict_name': '物资领用操作类型',
  'scope': 'global',
  'items': [('submit', '提交'), ('approve', '审批通过'), ('reject', '驳回'), ('withdraw', '撤回'), ('issue', '发放')]}]
for _code, _items in {}.items():
    DICT_ITEMS.setdefault(_code, []).extend(_items)

# 通用计量单位扩展；与 MES 无依赖，供刀具等按支管理的物资使用。
for _definition in DICTIONARIES:
    if _definition["dict_code"] == "md_unit":
        _definition["items"].append(("branch", "支"))
