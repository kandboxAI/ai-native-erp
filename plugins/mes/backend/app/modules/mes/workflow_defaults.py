"""MES 报工变更使用底座审批模板；按租户开通幂等创建，不覆盖客户配置。"""
from app.modules.workflow.design_models import FlowDesignV3, ApprovalNode, AssigneeConfig


def report_change_design():
    return FlowDesignV3(process_name="MES 报工变更审批", process_id="mes_report_change_process", nodes=[
        ApprovalNode(id="mes_report_review", name="生产报工复核", assignee=AssigneeConfig(type="permission", value="mes:production_report:approve")),
    ])


def process_change_design():
    return FlowDesignV3(process_name="MES 工艺变更审批", process_id="mes_process_change_process", nodes=[
        ApprovalNode(id="mes_process_review", name="工艺变更审批",
                     assignee=AssigneeConfig(type="permission", value="mes:process_change:approve")),
    ])


DEFAULT_DESIGNS = {"mes_report_change": report_change_design, "mes_process_change": process_change_design}
BUILTIN_DEFINITIONS = [{"definition_no": "mes_report_change", "definition_name": "MES 报工变更审批", "business_type_code": "mes_report_change",
                        "description": "更正或冲销报工，审批通过后追加事实并回算产量及工时"}]
BUILTIN_DEFINITIONS.append({"definition_no": "mes_process_change", "definition_name": "MES 工艺变更审批",
    "business_type_code": "mes_process_change", "description": "审批工艺切换及原工艺已加工件处置"})
