"""将可视化审批流设计编译为 Spiff 可执行的 BPMN 2.0 XML。"""

from __future__ import annotations

import re
import xml.sax.saxutils as saxutils

from app.core.exceptions import AppException

from .condition_fields import compile_condition_expression
from .design_models import (
    ApprovalNode,
    ApprovalStepV1,
    CcNode,
    ConditionBranch,
    ConditionBranchV1,
    ExclusiveGatewayNode,
    ParallelGatewayNode,
    FlowDesign,
    FlowDesignV1,
    FlowDesignV2,
    FlowDesignV3,
    FlowNode,
    FlowNodeV3,
)


def _esc(text: str) -> str:
    return saxutils.escape(text or "", {'"': "&quot;"})


def _slug_process_id(name: str) -> str:
    base = re.sub(r"[^a-zA-Z0-9_]", "_", name).strip("_") or "process"
    if base[0].isdigit():
        base = f"p_{base}"
    return base[:120]


def _extension_xml(
    assignees: list[tuple[str, str]],
    cc_nodes: list[str],
    *,
    approval_mode: str = "single",
) -> str:
    cc_block = "\n" + "\n".join(cc_nodes) if cc_nodes else ""
    assignee_block = "\n".join(
        f'        <spiff:assignee type="{_esc(item_type)}" value="{_esc(item_value)}"/>'
        for item_type, item_value in assignees
    )
    return f'        <spiff:approval mode="{_esc(approval_mode)}"/>\n{assignee_block}{cc_block}'


def _legacy_user_task_xml(step: ApprovalStepV1) -> str:
    cc_nodes = [
        f'        <spiff:cc type="{_esc(cc.type)}" value="{_esc(cc.value)}" trigger="task_arrived"/>'
        for cc in step.cc
    ]
    extension = _extension_xml([(step.assignee.type, step.assignee.value)], cc_nodes)
    return f"""    <userTask id="{_esc(step.id)}" name="{_esc(step.name)}">
      <extensionElements>
{extension}
      </extensionElements>
    </userTask>"""


def _user_task_xml(node: ApprovalNode, completed_cc: list[CcNode]) -> str:
    cc_nodes: list[str] = []
    for cc_node in completed_cc:
        for recipient in cc_node.recipients:
            cc_nodes.append(
                f'        <spiff:cc type="{_esc(recipient.type)}" '
                f'value="{_esc(recipient.value or "")}" trigger="task_completed" '
                f'nodeId="{_esc(cc_node.id)}" nodeName="{_esc(cc_node.name)}"/>'
            )
    extension = _extension_xml(
        [(item.type, item.value or "") for item in node.assignees],
        cc_nodes,
        approval_mode=node.approval_mode,
    )
    return f"""    <userTask id="{_esc(node.id)}" name="{_esc(node.name)}">
      <extensionElements>
{extension}
      </extensionElements>
    </userTask>"""


def _sequence_flow(flow_id: str, source: str, target: str, *, condition: str | None = None) -> str:
    condition_xml = ""
    if condition:
        condition_xml = f"""
      <conditionExpression xsi:type="tFormalExpression" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">{_esc(condition)}</conditionExpression>"""
    return f"""    <sequenceFlow id="{_esc(flow_id)}" sourceRef="{_esc(source)}" targetRef="{_esc(target)}">{condition_xml}
    </sequenceFlow>"""


def _group_nodes(nodes: list[FlowNode]) -> list[tuple[ApprovalNode, list[CcNode]]]:
    groups: list[tuple[ApprovalNode, list[CcNode]]] = []
    for node in nodes:
        if isinstance(node, ApprovalNode):
            groups.append((node, []))
        elif not groups:
            raise AppException("抄送节点必须放在审批节点之后", status_code=400)
        else:
            groups[-1][1].append(node)
    return groups


def _compile_serial_v1(design: FlowDesignV1, process_id: str) -> str:
    elements: list[str] = ['    <startEvent id="start"/>', '    <endEvent id="end_approved" name="通过"/>']
    flows: list[str] = []
    for step in design.steps:
        elements.append(_legacy_user_task_xml(step))
    previous = "start"
    for index, step in enumerate(design.steps):
        flows.append(_sequence_flow(f"flow_start_{index}", previous, step.id))
        previous = step.id
    flows.append(_sequence_flow("flow_to_end", previous, "end_approved"))
    return _wrap_process(process_id, design.process_name, elements, flows)


def _legacy_step_bpmn_id(step: ApprovalStepV1, branch_id: str) -> str:
    return f"{branch_id}__{step.id}"


def _compile_branch_v1(
    branch: ConditionBranchV1, gateway_id: str, branch_index: int
) -> tuple[list[str], list[str], str]:
    elements: list[str] = []
    flows: list[str] = []
    first_id = _legacy_step_bpmn_id(branch.steps[0], branch.id)
    flows.append(
        _sequence_flow(
            f"flow_gw_{gateway_id}_b{branch_index}", gateway_id, first_id, condition=branch.condition
        )
    )
    previous = first_id
    for index, step in enumerate(branch.steps):
        bpmn_id = _legacy_step_bpmn_id(step, branch.id)
        elements.append(_legacy_user_task_xml(step.model_copy(update={"id": bpmn_id})))
        if index:
            flows.append(_sequence_flow(f"flow_{branch.id}_{index}", previous, bpmn_id))
            previous = bpmn_id
    return elements, flows, previous


def _compile_conditional_v1(design: FlowDesignV1, process_id: str) -> str:
    gateway = design.gateway
    if gateway is None:
        raise AppException("条件模式缺少 gateway 配置", status_code=400)
    gateway_id = "gateway_conditions"
    default_id = gateway.default_branch_id or gateway.branches[-1].id
    elements = [
        '    <startEvent id="start"/>',
        f'    <exclusiveGateway id="{gateway_id}" default="flow_{gateway_id}_default"/>',
        '    <endEvent id="end_approved" name="通过"/>',
    ]
    flows = [_sequence_flow("flow_to_gw", "start", gateway_id)]
    end_sources: list[str] = []
    default_target: str | None = None
    for index, branch in enumerate(gateway.branches):
        branch_elements, branch_flows, last_id = _compile_branch_v1(branch, gateway_id, index)
        elements.extend(branch_elements)
        flows.extend(branch_flows)
        end_sources.append(last_id)
        if branch.id == default_id:
            default_target = _legacy_step_bpmn_id(branch.steps[0], branch.id)
    if default_target is None:
        raise AppException("默认分支不存在", status_code=400)
    flows.append(_sequence_flow(f"flow_{gateway_id}_default", gateway_id, default_target))
    for index, source in enumerate(end_sources):
        flows.append(_sequence_flow(f"flow_branch_{index}_end", source, "end_approved"))
    return _wrap_process(process_id, design.process_name, elements, flows)


def _compile_group_chain(
    groups: list[tuple[ApprovalNode, list[CcNode]]], *, id_prefix: str = ""
) -> tuple[list[str], list[str], str, str]:
    elements: list[str] = []
    flows: list[str] = []
    bpmn_ids: list[str] = []
    for node, cc_nodes in groups:
        bpmn_id = f"{id_prefix}{node.id}"
        bpmn_ids.append(bpmn_id)
        elements.append(_user_task_xml(node.model_copy(update={"id": bpmn_id}), cc_nodes))
    for index in range(1, len(bpmn_ids)):
        flows.append(_sequence_flow(f"flow_{bpmn_ids[index - 1]}_{index}", bpmn_ids[index - 1], bpmn_ids[index]))
    return elements, flows, bpmn_ids[0], bpmn_ids[-1]


def _compile_serial_v2(design: FlowDesignV2, process_id: str) -> str:
    groups = _group_nodes(design.nodes)
    task_elements, task_flows, first_id, last_id = _compile_group_chain(groups)
    elements = ['    <startEvent id="start"/>', '    <endEvent id="end_approved" name="通过"/>', *task_elements]
    flows = [
        _sequence_flow("flow_start", "start", first_id),
        *task_flows,
        _sequence_flow("flow_to_end", last_id, "end_approved"),
    ]
    return _wrap_process(process_id, design.process_name, elements, flows)


def _compile_branch_v2(branch: ConditionBranch) -> tuple[list[str], list[str], str, str]:
    return _compile_group_chain(_group_nodes(branch.nodes), id_prefix=f"{branch.id}__")


def _compile_conditional_v2(design: FlowDesignV2, process_id: str) -> str:
    gateway = design.gateway
    if gateway is None:
        raise AppException("条件模式缺少 gateway 配置", status_code=400)
    gateway_id = "gateway_conditions"
    default_flow_id = f"flow_{gateway_id}_default"
    elements = [
        '    <startEvent id="start"/>',
        f'    <exclusiveGateway id="{gateway_id}" default="{default_flow_id}"/>',
        '    <endEvent id="end_approved" name="通过"/>',
    ]
    flows = [_sequence_flow("flow_to_gw", "start", gateway_id)]
    for index, branch in enumerate(gateway.branches):
        branch_elements, branch_flows, first_id, last_id = _compile_branch_v2(branch)
        elements.extend(branch_elements)
        flows.extend(branch_flows)
        if branch.id == gateway.default_branch_id:
            flows.append(_sequence_flow(default_flow_id, gateway_id, first_id))
        else:
            if branch.condition is None:
                raise AppException(f"分支「{branch.name}」缺少条件", status_code=400)
            flows.append(
                _sequence_flow(
                    f"flow_{gateway_id}_{index}",
                    gateway_id,
                    first_id,
                    condition=compile_condition_expression(branch.condition),
                )
            )
        flows.append(_sequence_flow(f"flow_branch_{index}_end", last_id, "end_approved"))
    return _wrap_process(process_id, design.process_name, elements, flows)


def _v3_node_bpmn_id(node: ApprovalNode | ExclusiveGatewayNode | ParallelGatewayNode, id_prefix: str) -> str:
    return f"{id_prefix}{node.id}"


def _compile_v3_units(
    nodes: list[FlowNodeV3], *, id_prefix: str = ""
) -> tuple[list[str], list[str], str, str]:
    elements: list[str] = []
    flows: list[str] = []
    unit_first_ids: list[str] = []
    unit_last_ids: list[str] = []
    pending_cc: list[CcNode] = []
    last_approval: ApprovalNode | None = None

    def flush_approval() -> None:
        nonlocal pending_cc, last_approval
        if last_approval is None:
            return
        bpmn_id = _v3_node_bpmn_id(last_approval, id_prefix)
        unit_first_ids.append(bpmn_id)
        unit_last_ids.append(bpmn_id)
        elements.append(
            _user_task_xml(last_approval.model_copy(update={"id": bpmn_id}), pending_cc)
        )
        pending_cc = []
        last_approval = None

    for node in nodes:
        if isinstance(node, ApprovalNode):
            flush_approval()
            last_approval = node
        elif isinstance(node, CcNode):
            if last_approval is None:
                raise AppException("抄送节点必须放在审批节点之后", status_code=400)
            pending_cc.append(node)
        else:
            flush_approval()
            gateway_elements, gateway_flows, first_id, last_id = _compile_v3_gateway(
                node, id_prefix=id_prefix
            )
            elements.extend(gateway_elements)
            flows.extend(gateway_flows)
            unit_first_ids.append(first_id)
            unit_last_ids.append(last_id)
    flush_approval()

    if not unit_first_ids:
        raise AppException("流程至少需要一个可执行节点", status_code=400)
    for index in range(1, len(unit_first_ids)):
        flows.append(
            _sequence_flow(
                f"flow_{unit_last_ids[index - 1]}_{index}",
                unit_last_ids[index - 1],
                unit_first_ids[index],
            )
        )
    return elements, flows, unit_first_ids[0], unit_last_ids[-1]


def _compile_v3_gateway(
    gateway: ExclusiveGatewayNode | ParallelGatewayNode, *, id_prefix: str
) -> tuple[list[str], list[str], str, str]:
    split_id = f"{_v3_node_bpmn_id(gateway, id_prefix)}_split"
    merge_id = f"{_v3_node_bpmn_id(gateway, id_prefix)}_merge"
    parallel = isinstance(gateway, ParallelGatewayNode)
    tag = "parallelGateway" if parallel else "exclusiveGateway"
    default_flow_id = f"flow_{split_id}_default"
    default_attr = "" if parallel else f' default="{_esc(default_flow_id)}"'
    elements = [
        (
            f'    <{tag} id="{_esc(split_id)}" '
            f'name="{_esc(gateway.name)}"{default_attr}/>'
        ),
        (
            f'    <{tag} id="{_esc(merge_id)}" '
            f'name="{_esc(gateway.name)}汇合"/>'
        ),
    ]
    flows: list[str] = []
    for index, branch in enumerate(gateway.branches):
        branch_elements, branch_flows, first_id, last_id = _compile_v3_units(
            branch.nodes, id_prefix=f"{id_prefix}{branch.id}__"
        )
        elements.extend(branch_elements)
        flows.extend(branch_flows)
        if parallel:
            flows.append(_sequence_flow(f"flow_{split_id}_{index}", split_id, first_id))
        elif branch.id == gateway.default_branch_id:
            flows.append(_sequence_flow(default_flow_id, split_id, first_id))
        else:
            if branch.condition is None:
                raise AppException(f"分支「{branch.name}」缺少条件", status_code=400)
            flows.append(
                _sequence_flow(
                    f"flow_{split_id}_{index}",
                    split_id,
                    first_id,
                    condition=compile_condition_expression(branch.condition),
                )
            )
        flows.append(_sequence_flow(f"flow_{last_id}_{merge_id}", last_id, merge_id))
    return elements, flows, split_id, merge_id


def _compile_v3(design: FlowDesignV3, process_id: str) -> str:
    node_elements, node_flows, first_id, last_id = _compile_v3_units(design.nodes)
    elements = [
        '    <startEvent id="start"/>',
        '    <endEvent id="end_approved" name="通过"/>',
        *node_elements,
    ]
    flows = [
        _sequence_flow("flow_start", "start", first_id),
        *node_flows,
        _sequence_flow("flow_to_end", last_id, "end_approved"),
    ]
    return _wrap_process(process_id, design.process_name, elements, flows)


def _wrap_process(process_id: str, process_name: str, elements: list[str], flows: list[str]) -> str:
    body = "\n".join(elements + flows)
    return f"""<definitions xmlns="http://www.omg.org/spec/BPMN/20100524/MODEL"
             xmlns:spiff="http://spiffworkflow.org/schema/1.0"
             xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
             targetNamespace="urn:ai-native-erp:workflow:bpmn">
  <process id="{_esc(process_id)}" name="{_esc(process_name)}" isExecutable="true">
{body}
  </process>
</definitions>"""


def compile_flow_design(design: FlowDesign) -> tuple[str, str]:
    process_id = design.process_id or _slug_process_id(design.process_name)
    if isinstance(design, FlowDesignV1):
        xml = _compile_serial_v1(design, process_id) if design.mode == "serial" else _compile_conditional_v1(design, process_id)
    elif isinstance(design, FlowDesignV2):
        xml = _compile_serial_v2(design, process_id) if design.mode == "serial" else _compile_conditional_v2(design, process_id)
    else:
        xml = _compile_v3(design, process_id)
    return process_id, xml.strip()
