"""领用申请的状态与只追加事件字典。"""
DICTIONARIES = [
    {"dict_code":"inv_material_requisition_status", "dict_name":"物资领用申请状态", "scope":"global", "items":[("submitted","待审批"),("approved","已审批"),("rejected","已驳回"),("issued","已发放"),("withdrawn","已撤回")]},
    {"dict_code":"inv_material_requisition_event_type", "dict_name":"物资领用操作类型", "scope":"global", "items":[("submit","提交"),("approve","通过"),("reject","驳回"),("withdraw","撤回"),("issue","发放")]},
]
DICTIONARIES[0]["items"] += [("pending_receipt", "待签收"), ("receipt_exception", "收货异常"), ("received", "已签收")]
DICTIONARIES[1]["items"] += [("receive", "确认收货"), ("receipt_exception", "收货异常"), ("resolve_exception", "异常处理")]
DICTIONARIES.append({"dict_code": "inv_requisition_receipt_exception_type", "dict_name": "领用收货异常类型", "scope": "global", "items": [("shortage", "少发"), ("wrong_item", "错发"), ("damaged", "破损"), ("not_received", "未收到")]})
DICT_ITEMS = {}
