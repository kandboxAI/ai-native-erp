"""核价工序到制造工艺档案的匹配；计价规则与生产档案保持独立。"""
import unicodedata
from copy import deepcopy
from app.core.exceptions import AppException

from .archive_repository import archive_repository
from .cnc.process_catalog import infer_process_type


def normalized(value):
    return "".join(unicodedata.normalize("NFKC", value).casefold().split())


def archive_category(name):
    # 检验放行标记可能挂在加工工序上，不能用该布尔值推断“这是一道检验工艺”。
    return "inspection" if normalized(name) in {"qa", "qc"} else infer_process_type(name)


def match_process(name, candidates, *, pricing_mode_code="hourly", process_type_code=None, process_id=None, process_no=None):
    """编号/名称优先；只有同类候选唯一时才按已定义工艺分类匹配，不按相似度猜测。"""
    key = normalized(name)
    if not key:
        return dict(status_code="unmatched", reason="工序名称为空", process=None)
    def compatible(process):
        actual=archive_category(process["process_name"])
        grinding={"grinding","surface_grinding","cylindrical_grinding"}
        return not process_type_code or not actual or actual==process_type_code or (actual in grinding and process_type_code=="grinding")
    eligible = [p for p in candidates if p["processing_type_code"] == ("outsourced" if pricing_mode_code == "external" else "in_house") and compatible(p)]
    if process_id or process_no:
        matches=[p for p in eligible if str(p["id"])==str(process_id)] if process_id else [p for p in eligible if normalized(p["process_no"])==normalized(process_no)]
        if len(matches)==1:return dict(status_code="matched",reason="按已选正式工艺绑定并重新校验",process=matches[0])
        return dict(status_code="unmatched",reason="选用工艺已停用、不在授权范围，或自制/委外及加工类别不符，请重新选择",process=None)
    matches = [p for p in eligible if normalized(p["process_no"]) == key]
    reason = "按工艺编号匹配"
    if not matches:
        matches = [p for p in eligible if normalized(p["process_name"]) == key]
        reason = "按工艺名称匹配"
    if not matches:
        category = process_type_code or infer_process_type(name)
        if category:
            matches = [p for p in eligible if archive_category(p["process_name"]) == category]
            reason = "按唯一工艺分类匹配，生产前请复核"
    if len(matches) == 1:
        return dict(status_code="matched", reason=reason, process=matches[0])
    if matches:
        labels = "、".join(f"{p['process_no']} {p['process_name']}" for p in matches[:3])
        return dict(status_code="ambiguous", reason=f"存在多个可选工艺：{labels}；请在配置工序时选择", process=None)
    return dict(status_code="unmatched", reason="未找到适用的启用工艺；请在配置工序时选择或维护档案", process=None)


def canonical_operations(operations,candidates,*,strict=False,require_selected=False):
    """绑定经授权的真实档案，不改计价规则及费率；模型只能建议编号，不能提供可信外键。"""
    result=[]
    for value in operations:
        row=deepcopy(value)
        if require_selected and not (row.get("process_id") or row.get("process_no") or row.get("process_no_snapshot")):
            raise AppException(f"工序“{row['name']}”必须从现有正式工艺档案选择，请重新分析或选择工艺后核价",422)
        match=match_process(row["name"],candidates,pricing_mode_code=row.get("pricing_mode_code","hourly"),
            process_type_code=row.get("process_type_code"),process_id=row.get("process_id"),
            process_no=row.get("process_no") or row.get("process_no_snapshot"))
        process=match["process"]
        if not process and (require_selected or (strict and (row.get("process_id") or row.get("process_no_snapshot")))):
            raise AppException("选用工艺不可用或与当前加工类别不符，请重新核对工艺档案及加工类别",409)
        if process and len(process["process_name"])>120:
            raise AppException("正式工艺名称超过核价工序支持长度，请先规范档案名称",422)
        row.pop("process_no",None)  # 模型建议不作为持久化字段；编号快照从服务端档案复制。
        row["process_id"]=str(process["id"]) if process else None
        row["process_no_snapshot"]=process["process_no"] if process else None
        if process:row["name"]=process["process_name"]
        result.append(row)
    return result


def validate_rule_bindings(config, candidates):
    """规则绑定只能选用当前组织、权限范围内的正式工艺，不信任客户端名称或属性。"""
    available = {str(row["id"]): row for row in candidates}
    for mode, rules in (("hourly", config.processes), ("external", config.external_processes)):
        for rule in rules:
            if not rule.process_id:
                raise AppException("工序规则必须从正式工艺档案选择，不支持通用规则", 422)
            process = available.get(str(rule.process_id))
            if not process or match_process(process["process_name"], candidates, pricing_mode_code=mode,
                    process_type_code=getattr(rule, "process_type_code", None), process_id=rule.process_id)["process"] is None:
                raise AppException(f"规则“{rule.name}”的正式工艺不可用，或自制/委外及工序类别不符，请重新选择", 422)
            if len(process["process_name"]) > 120:
                raise AppException("正式工艺名称超过报价规则支持长度，请先规范档案名称", 422)


async def matching_catalog(session, org_id, user, permission, *, lock=False):
    if lock:
        await archive_repository.lock_organization(session, org_id)
    return await archive_repository.matching_processes(session, org_id, user, permission)


def analysis_matches(operations, candidates):
    """分析辅助报告只保存编号/名称和判定依据，不保存内部外键或更改核价工时、名称。"""
    items = []
    for index, op in enumerate(operations, 1):
        match = match_process(op["name"], candidates, pricing_mode_code=op.get("pricing_mode_code", "hourly"),
            process_type_code=op.get("process_type_code"),process_id=op.get("process_id"),
            process_no=op.get("process_no") or op.get("process_no_snapshot"))
        process = match["process"]
        items.append(dict(sequence_no=index, operation_name=op["name"], status_code=match["status_code"],
            process_no=process["process_no"] if process else None,
            process_name=process["process_name"] if process else None, reason=match["reason"]))
    matched = sum(item["status_code"] == "matched" for item in items)
    return dict(items=items, matched_count=matched, pending_count=len(items) - matched)


def bind_production_operations(operations, source, candidates):
    """只绑定新建工单；保留重复工序、顺序和工时，未匹配的留待工程处理。"""
    for op, raw in zip(operations, source, strict=True):
        match = match_process(op.operation_name, candidates,
            pricing_mode_code=raw.get("pricing_mode_code", "hourly"), process_type_code=raw.get("process_type_code"),
            process_id=raw.get("process_id"),process_no=raw.get("process_no_snapshot"))
        process = match["process"]
        if process:
            if op.operation_name != process["process_name"]:
                op.operation_description += f"\n报价工序原名：{op.operation_name}"
            op.process_id = process["id"]
            op.operation_name = process["process_name"]
            op.is_quality_required = op.is_quality_required or process["is_quality_required"]
        else:
            op.operation_description += "\n生成工单时工艺档案待匹配：" + match["reason"]
    return operations
