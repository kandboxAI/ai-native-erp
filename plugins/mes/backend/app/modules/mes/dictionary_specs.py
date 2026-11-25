"""MES 自有字典及底座模块字典扩展；不依赖行业组合。"""

CALENDAR_PERIOD_DEFINITION = ("mes_calendar_period_type", "制造资源日历时段类型", [("work", "工作"), ("lunch", "午休")])

DICTIONARIES = [{'dict_code': 'mes_quotation_status', 'dict_name': '销售询价报价状态', 'scope': 'global',
  'items': [('draft', '业务录入'), ('pending', '待工程报价'), ('pricing', '工程报价中'),
            ('review', '待初审'), ('final_review', '待复审'), ('quoted', '审核通过'), ('voided', '已作废')]},
 {'dict_code': 'mes_priority',
  'dict_name': '生产优先级',
  'scope': 'global',
  'items': [('urgent', '紧急'), ('high', '高'), ('normal', '普通'), ('low', '低')]},
 {'dict_code': 'mes_work_order_status',
  'dict_name': '生产工单状态',
  'scope': 'global',
  'items': [('draft', '未下单'),
            ('released', '已下单'),
            ('in_progress', '生产中（已下单）'),
            ('paused', '已暂停'),
            ('completed', '已完结'),
            ('cancelled', '已取消')]},
 {'dict_code': 'mes_operation_task_status',
  'dict_name': '工序任务状态',
  'scope': 'global',
  'items': [('draft', '待下单'), ('pending', '待执行'),
            ('dispatched', '已派工'),
            ('in_progress', '执行中'),
            ('paused', '已暂停'),
            ('waiting_quality', '待检验'),
            ('completed', '已完成'),
            ('cancelled', '已取消')]},
 {'dict_code': 'mes_execution_status',
  'dict_name': '工序执行状态',
  'scope': 'global',
  'items': [('in_progress', '执行中'), ('paused', '已暂停'), ('completed', '已完成'), ('cancelled', '已取消')]},
 {'dict_code': 'mes_execution_event_type',
  'dict_name': 'MES 执行事件类型',
  'scope': 'global',
  'items': [('created', '任务创建'),
            ('dispatched', '已派工'),
            ('tracked_in', '开工'),
            ('held', '暂停'),
            ('released', '恢复'),
            ('production_reported', '现场报工'),
            ('phase_changed', '执行阶段变更'),
            ('tracked_out', '完工'), ('scheduled', '计划时间调整'), ('report_corrected', '报工更正'),
            ('quality_released', '检验放行'), ('quality_rework_requested', '检验退回返工')]},
 {'dict_code': 'mes_exception_type',
  'dict_name': '生产异常类型',
  'scope': 'global',
  'items': [('material_shortage', '缺料'),
            ('equipment_failure', '设备故障'),
            ('quality_abnormal', '质量异常'),
            ('changeover', '换型'),
            ('other', '其他')]},
 {'dict_code': 'mes_report_source',
  'dict_name': '报工来源',
  'scope': 'global',
  'items': [('web', '管理端'), ('mini_program', '手机小程序'), ('device', '设备采集'), ('integration', '接口导入')]},
 {'dict_code': 'mes_report_status',
  'dict_name': '报工处理状态',
  'scope': 'global',
  'items': [('posted', '已入账'), ('pending_inventory', '待库存处理'), ('reversed', '已冲销')]}]

DICT_ITEMS = {"sys_module": [("mes", "制造执行")], "wf_business_type": [
    ("mes_report_change", "MES 报工变更"), ("mes_process_change", "MES 工艺变更")]}
DICTIONARIES.append({"dict_code": "mes_sales_order_status", "dict_name": "客户订单状态", "scope": "global",
    "items": [("confirmed", "待审核"), ("approved", "审核通过"), ("cancelled", "已取消")]})

from .cnc.process_catalog import process_catalog
for _code, _name, _items in [
    ("job_status", "询价解析任务状态", [("queued", "等待解析"), ("running", "解析中"), ("completed", "已完成"), ("failed", "失败可重试")]),
    ("file_kind", "询价原件类型", [("pdf", "二维 PDF"), ("step", "三维 STEP")]),
    ("process_type", "询价工序类型", [(row["process_type_code"], row["name"]) for row in process_catalog()]),
    ("pricing_mode", "询价工序计价方式", [("hourly", "按工时"), ("external", "外协")]),
    ("material_price_unit", "询价材料计价单位", [("kg", "元/公斤"), ("mm", "元/毫米")]),
    ("external_price_unit", "询价外协计价单位", [("kg", "元/公斤"), ("m2", "元/平方米")]),
    ("weight_basis", "询价计费重量口径", [("stock", "毛坯重量"), ("net", "模型净重量")]),
    ("origin", "询价工序来源", [("manual", "人工"), ("ai", "模型初稿")]),
    ("rule_category", "询价规则类别", [("materials", "材料"), ("processes", "工序"), ("external_processes", "外协")]),
    ("stock_form", "询价毛坯形式", [("any", "不限"), ("plate", "板材"), ("round", "圆料"), ("profile", "型材")]),
]:
    DICTIONARIES.append({"dict_code": f"mes_cnc_{_code}", "dict_name": _name, "scope": "global", "items": _items})
DICT_ITEMS["mes_shipment_status"] = [("awaiting_stock", "待库存办理")]
DICT_ITEMS["inv_warehouse_type"] = [("mes_raw", "制造原料仓"), ("mes_wip", "制造在制品仓"), ("mes_finished", "制造成品仓"), ("mes_tool", "制造刀具仓")]

DICTIONARIES.extend([
    {"dict_code": "mes_inventory_posting_type", "dict_name": "生产库存业务类型", "scope": "global", "items": [("issue", "生产领料"), ("return", "生产退料"), ("receipt", "成品入库"), ("shipment", "出货出库")]},
    {"dict_code": "mes_shipment_fulfillment_mode", "dict_name": "出货履约方式", "scope": "global", "items": [("direct", "生产直发"), ("stock", "仓储出货")]},
])

DICTIONARIES.extend([
    {"dict_code": "mes_shipment_status", "dict_name": "MES 出货状态", "scope": "global", "items": [("draft", "草稿"), ("posted", "已出货"), ("cancelled", "已取消")]},
    {"dict_code": "mes_reconciliation_status", "dict_name": "MES 对账状态", "scope": "global", "items": [("draft", "待确认"), ("confirmed", "已确认"), ("cancelled", "已取消")]},
])

DICTIONARIES.extend([
    {"dict_code": "mes_work_order_type", "dict_name": "生产工单类型", "scope": "global",
     "items": [("production", "普通生产"), ("repair", "返修生产")]},
    {"dict_code": "mes_work_order_event_type", "dict_name": "生产工单动作", "scope": "global",
     "items": [("created", "创建"), ("updated", "变更配置"), ("published", "发布"),
               ("paused", "暂停生产"), ("resumed", "恢复生产"), ("withdrawn", "撤回草稿"),
               ("completed", "完结"), ("cancelled", "取消"), ("deleted", "删除草稿"),
               ("scheduled", "排程调整"), ("drawing_updated", "图纸更新"), ("report_corrected", "报工更正"),
               ("process_change_requested", "发起工艺变更"), ("process_change_closed", "关闭工艺变更"),
               ("process_changed", "工艺变更生效")]},
    {"dict_code": "mes_process_change_disposition", "dict_name": "工艺变更已加工件处置", "scope": "global",
     "items": [("keep", "沿用"), ("reinspect", "复检"), ("rework", "返工")]},
    {"dict_code": "mes_process_change_status", "dict_name": "工艺变更单状态", "scope": "global",
     "items": [("draft", "待提交"), ("submitted", "审批中"), ("approved", "待处置"),
               ("rejected", "已驳回"), ("cancelled", "已撤回"), ("applied", "已生效")]},
])

DICTIONARIES.extend([
    {"dict_code": "mes_report_change_type", "dict_name": "报工变更类型", "scope": "global", "items": [("replace", "更正"), ("reverse", "冲销")]},
    {"dict_code": "mes_report_change_status", "dict_name": "报工变更状态", "scope": "global", "items": [("draft", "待提交"), ("submitted", "审批中"), ("approved", "已通过"), ("rejected", "已驳回"), ("cancelled", "已撤回")]},
])

DICTIONARIES.extend([
    {"dict_code": "mes_quality_result", "dict_name": "工序检验结论", "scope": "global", "items": [("pass", "合格放行"), ("fail", "不合格退回返工")]},
    {"dict_code": "mes_processing_type", "dict_name": "加工类型", "scope": "global", "items": [("in_house", "自制"), ("outsourced", "委外"), ("purchased", "采购")]},
    {"dict_code": "mes_reconciliation_mode", "dict_name": "客户对账展示方式", "scope": "global", "items": [("by_item", "按货品"), ("by_order", "按工单")]},
    {"dict_code": "mes_exception_status", "dict_name": "制造异常状态", "scope": "global", "items": [("pending", "待处理"), ("in_progress", "处理中"), ("waiting_confirmation", "待确认"), ("closed", "已关闭")]},
    {"dict_code": "mes_exception_action", "dict_name": "制造异常处理动作", "scope": "global", "items": [("created", "登记"), ("assign", "指派或调整期限"), ("start", "开始处理"), ("progress", "处理记录"), ("resolve", "提交处理结果"), ("approve", "复核关闭"), ("reject", "退回处理"), ("reopen", "重开"), ("reminded", "超时提醒")]},
])

DICTIONARIES.append({"dict_code": CALENDAR_PERIOD_DEFINITION[0], "dict_name": CALENDAR_PERIOD_DEFINITION[1], "scope": "global", "items": CALENDAR_PERIOD_DEFINITION[2]})
DICTIONARIES.extend([
    {"dict_code": "mes_schedule_readiness_kind", "dict_name": "生产就绪条件", "scope": "global", "items": [("material", "材料"), ("drawing", "图纸"), ("program", "程序"), ("tool", "刀具")]},
    {"dict_code": "mes_schedule_inspection_mode", "dict_name": "全路线检验安排", "scope": "global", "items": [("separate", "独立检验"), ("last_operation", "复用末道检验")]},
    {"dict_code": "mes_first_article_status", "dict_name": "全路线首件状态", "scope": "global", "items": [("pending", "待首件生产"), ("waiting_quality", "首件待检"), ("released", "首件合格放行"), ("rework", "首件返工")]},
    {"dict_code": "mes_quality_inspection_type", "dict_name": "制造检验类型", "scope": "global", "items": [("operation", "工序检验"), ("first_article", "全路线首件检验"), ("final", "最终检验"), ("external_return", "委外回厂检验")]},
])
DICTIONARIES.extend([
    {"dict_code": "mes_calendar_exception_type", "dict_name": "制造日历例外类型", "scope": "global", "items": [("extra_available", "临时可用/加班"), ("unavailable", "请假/停机/不可用")]},
    {"dict_code": "mes_schedule_plan_status", "dict_name": "自动排程方案状态", "scope": "global", "items": [("draft", "待计算"), ("calculating", "计算中"), ("ready", "待确认"), ("applied", "已应用"), ("superseded", "已被替代"), ("invalid", "已失效"), ("cancelled", "已取消"), ("failed", "计算失败")]},
    {"dict_code": "mes_schedule_solver_result", "dict_name": "自动排程求解结果", "scope": "global", "items": [("OPTIMAL", "已证明最优"), ("FEASIBLE", "可行但未证明最优"), ("INFEASIBLE", "无可行方案"), ("UNKNOWN", "未找到方案"), ("MODEL_INVALID", "模型无效"), ("PRECHECK_FAILED", "资料不完整")]},
    {"dict_code": "mes_schedule_segment_type", "dict_name": "排程阶段类型", "scope": "global", "items": [("preparation", "准备"), ("load", "装料"), ("run", "加工"), ("unload", "卸料"), ("waiting_unload", "占机等待卸料"), ("manual", "人工"), ("inspection", "检验"), ("external_wait", "委外加工/等待回厂"), ("external_return", "已确认回厂")]},
    {"dict_code": "mes_schedule_production_phase", "dict_name": "首件与生产批次", "scope": "global", "items": [("first", "首件"), ("remaining", "剩余批量")]},
    {"dict_code": "mes_schedule_execution_kind", "dict_name": "排程执行方式", "scope": "global", "items": [("machine", "机器加工"), ("manual", "人工"), ("inspection", "人工检验"), ("machine_inspection", "设备检验"), ("external", "委外")]},
])
