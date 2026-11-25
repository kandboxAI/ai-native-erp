"""SpiffWorkflow 3.x 封装：解析 BPMN、推进 UserTask、序列化/反序列化。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from lxml import etree
from SpiffWorkflow.bpmn.parser.BpmnParser import BpmnParser
from SpiffWorkflow.bpmn.serializer.workflow import BpmnWorkflowSerializer
from SpiffWorkflow.bpmn.workflow import BpmnWorkflow
from SpiffWorkflow.task import TaskState

from app.core.exceptions import AppException

BPMN_NS = "http://www.omg.org/spec/BPMN/20100524/MODEL"
SPIFF_ASSIGNEE_NS = "http://spiffworkflow.org/schema/1.0"
SPIFF_CORE_NS = "http://spiffworkflow.org/bpmn/schema/1.0/core"
NSMAP = {
    "bpmn": BPMN_NS,
    "spiff": SPIFF_ASSIGNEE_NS,
    "spiffworkflow": SPIFF_CORE_NS,
}
ALLOWED_ASSIGNEE_TYPES = {
    "user",
    "permission",
    "business_owner",
    "department_manager",
    "initiator_leader",
    "starter",
    "starter_select",
}


class BpmnValidationError(AppException):
    def __init__(self, message: str, *, details: list[str] | None = None) -> None:
        super().__init__(message, status_code=400)
        self.details = details or []


@dataclass(frozen=True)
class CcSpec:
    cc_type: str
    cc_value: str
    trigger: str = "task_arrived"
    node_key: str | None = None
    node_name: str | None = None


@dataclass(frozen=True)
class AssigneeSpec:
    task_key: str
    task_name: str | None
    assignee_type: str
    assignee_value: str
    approval_mode: str
    assignees: tuple[tuple[str, str], ...]
    cc: list[CcSpec]


@dataclass
class ParsedBpmn:
    bpmn_process_no: str
    user_tasks: list[AssigneeSpec]


@dataclass
class ReadyUserTask:
    spiff_task_no: UUID
    task_key: str
    task_name: str | None
    data: dict[str, Any]


def _bpmn_bytes(bpmn_xml: str) -> bytes:
    text = bpmn_xml.strip()
    if text.startswith("<?xml"):
        # lxml 不支持带 encoding 声明的 str 输入
        return text.encode("utf-8")
    return text.encode("utf-8")


def _parse_bpmn_root(bpmn_xml: str) -> etree._Element:
    try:
        return etree.fromstring(_bpmn_bytes(bpmn_xml))
    except etree.XMLSyntaxError as exc:
        raise BpmnValidationError(f"BPMN XML 解析失败: {exc}") from exc


def detect_executable_process_id(bpmn_xml: str, *, preferred: str | None = None) -> str:
    root = _parse_bpmn_root(bpmn_xml)
    processes = root.xpath(
        "//bpmn:process[@isExecutable='true']",
        namespaces=NSMAP,
    )
    if not processes:
        processes = root.xpath("//bpmn:process", namespaces=NSMAP)
    if not processes:
        raise BpmnValidationError("BPMN 中未找到 process 元素")
    if preferred:
        for proc in processes:
            if proc.get("id") == preferred:
                return preferred
        raise BpmnValidationError(f"未找到 process id={preferred}")
    if len(processes) > 1:
        ids = [p.get("id") for p in processes]
        raise BpmnValidationError(
            "BPMN 含多个可执行 process，请指定 process_id",
            details=[f"可选: {', '.join(i for i in ids if i)}"],
        )
    process_id = processes[0].get("id")
    if not process_id:
        raise BpmnValidationError("process 缺少 id 属性")
    return process_id


def extract_user_task_assignees(bpmn_xml: str) -> list[AssigneeSpec]:
    root = _parse_bpmn_root(bpmn_xml)
    specs: list[AssigneeSpec] = []
    for node in root.xpath("//bpmn:userTask", namespaces=NSMAP):
        task_key = node.get("id")
        if not task_key:
            raise BpmnValidationError("存在未设置 id 的 userTask")
        task_name = node.get("name")
        assignee_nodes = node.xpath(
            ".//bpmn:extensionElements/spiff:assignee",
            namespaces=NSMAP,
        )
        if not assignee_nodes:
            assignee_nodes = node.xpath(
                ".//bpmn:extensionElements//spiffworkflow:*[local-name()='assignee' or contains(local-name(), 'Assignee')]",
                namespaces=NSMAP,
            )
        if not assignee_nodes:
            raise BpmnValidationError(
                f"UserTask「{task_name or task_key}」缺少 spiff:assignee 扩展",
                details=[f"task_key={task_key}"],
            )
        parsed_assignees: list[tuple[str, str]] = []
        for assignee in assignee_nodes:
            assignee_type = (assignee.get("type") or assignee.get("assigneeType") or "").strip()
            assignee_value = (assignee.get("value") or assignee.get("assigneeValue") or "").strip()
            if not assignee_type or not assignee_value:
                raise BpmnValidationError(
                    f"UserTask「{task_name or task_key}」的 assignee 缺少 type/value",
                    details=[f"task_key={task_key}"],
                )
            if assignee_type not in ALLOWED_ASSIGNEE_TYPES:
                raise BpmnValidationError(
                    f"UserTask「{task_name or task_key}」的 assignee type 无效",
                    details=[f"type={assignee_type}"],
                )
            parsed_assignees.append((assignee_type, assignee_value))
        approval_nodes = node.xpath(
            ".//bpmn:extensionElements/spiff:approval",
            namespaces=NSMAP,
        )
        approval_mode = (
            (approval_nodes[0].get("mode") or "single").strip()
            if approval_nodes
            else "single"
        )
        if approval_mode not in {"single", "any", "all"}:
            raise BpmnValidationError(
                f"UserTask「{task_name or task_key}」的审批方式无效",
                details=[f"mode={approval_mode}"],
            )
        if approval_mode == "single" and len(parsed_assignees) != 1:
            raise BpmnValidationError(f"UserTask「{task_name or task_key}」单人审批只能配置一个审批对象")
        if approval_mode in {"any", "all"} and len(parsed_assignees) < 2:
            raise BpmnValidationError(f"UserTask「{task_name or task_key}」或签/会签至少需要两个审批对象")
        assignee_type, assignee_value = parsed_assignees[0]
        cc_specs: list[CcSpec] = []
        cc_nodes = node.xpath(
            ".//bpmn:extensionElements/spiff:cc",
            namespaces=NSMAP,
        )
        for cc in cc_nodes:
            cc_type = (cc.get("type") or "").strip()
            cc_value = (cc.get("value") or "").strip()
            if not cc_type or not cc_value:
                raise BpmnValidationError(
                    f"UserTask「{task_name or task_key}」的 cc 缺少 type/value",
                    details=[f"task_key={task_key}"],
                )
            if cc_type not in ALLOWED_ASSIGNEE_TYPES:
                raise BpmnValidationError(
                    f"UserTask「{task_name or task_key}」的 cc type 无效",
                    details=[f"type={cc_type}"],
                )
            trigger = (cc.get("trigger") or "task_arrived").strip()
            if trigger not in {"task_arrived", "task_completed"}:
                raise BpmnValidationError(
                    f"UserTask「{task_name or task_key}」的 cc trigger 无效",
                    details=[f"trigger={trigger}"],
                )
            cc_specs.append(
                CcSpec(
                    cc_type=cc_type,
                    cc_value=cc_value,
                    trigger=trigger,
                    node_key=(cc.get("nodeId") or "").strip() or None,
                    node_name=(cc.get("nodeName") or "").strip() or None,
                )
            )
        specs.append(
            AssigneeSpec(
                task_key=task_key,
                task_name=task_name,
                assignee_type=assignee_type,
                assignee_value=assignee_value,
                approval_mode=approval_mode,
                assignees=tuple(parsed_assignees),
                cc=cc_specs,
            )
        )
    if not specs:
        raise BpmnValidationError("BPMN 中未包含任何 UserTask，无法作为审批流程")
    return specs


def parse_bpmn_metadata(bpmn_xml: str, *, process_id: str | None = None) -> ParsedBpmn:
    pid = detect_executable_process_id(bpmn_xml, preferred=process_id)
    user_tasks = extract_user_task_assignees(bpmn_xml)
    return ParsedBpmn(bpmn_process_no=pid, user_tasks=user_tasks)


def _load_parser(bpmn_xml: str) -> BpmnParser:
    parser = BpmnParser()
    try:
        parser.add_bpmn_str(_bpmn_bytes(bpmn_xml))
    except Exception as exc:
        raise BpmnValidationError(f"Spiff 无法解析 BPMN: {exc}") from exc
    return parser


def create_workflow(
    bpmn_xml: str,
    *,
    process_id: str | None = None,
    bootstrap_variables: dict[str, Any] | None = None,
) -> tuple[BpmnWorkflow, str]:
    meta = parse_bpmn_metadata(bpmn_xml, process_id=process_id)
    parser = _load_parser(bpmn_xml)
    try:
        spec = parser.get_spec(meta.bpmn_process_no)
        subprocess_specs = parser.get_subprocess_specs(meta.bpmn_process_no)
    except Exception as exc:
        raise BpmnValidationError(f"无法加载流程定义 process_id={meta.bpmn_process_no}: {exc}") from exc
    workflow = BpmnWorkflow(spec, subprocess_specs)
    if bootstrap_variables:
        for task in workflow.get_tasks_iterator():
            task.data.update(bootstrap_variables)
    workflow.do_engine_steps()
    return workflow, meta.bpmn_process_no


def validate_bpmn(
    bpmn_xml: str,
    *,
    process_id: str | None = None,
    validation_variables: dict[str, Any] | None = None,
) -> ParsedBpmn:
    meta = parse_bpmn_metadata(bpmn_xml, process_id=process_id)
    workflow, _ = create_workflow(
        bpmn_xml,
        process_id=meta.bpmn_process_no,
        bootstrap_variables=validation_variables or {"leave_days": 1},
    )
    ready = get_ready_user_tasks(workflow)
    if not ready:
        raise BpmnValidationError("流程启动后无就绪 UserTask，请检查 BPMN 连线")
    return meta


def get_ready_user_tasks(workflow: BpmnWorkflow) -> list[ReadyUserTask]:
    result: list[ReadyUserTask] = []
    for task in workflow.get_tasks_iterator():
        if task.state != TaskState.READY:
            continue
        bpmn_id = getattr(task.task_spec, "bpmn_id", None)
        if not bpmn_id:
            continue
        result.append(
            ReadyUserTask(
                spiff_task_no=task.id,
                task_key=bpmn_id,
                task_name=getattr(task.task_spec, "name", None) or getattr(task.task_spec, "description", None),
                data=dict(task.data or {}),
            )
        )
    return result


def get_task_data(workflow: BpmnWorkflow, spiff_task_id: UUID) -> dict[str, Any]:
    task = workflow.get_task_from_id(spiff_task_id)
    if task is None:
        raise AppException("工作流任务不存在", status_code=404)
    return dict(task.data or {})


def complete_user_task(
    workflow: BpmnWorkflow,
    spiff_task_id: UUID,
    *,
    variables: dict[str, Any] | None = None,
) -> list[ReadyUserTask]:
    task = workflow.get_task_from_id(spiff_task_id)
    if task is None:
        raise AppException("工作流任务不存在", status_code=404)
    if task.state != TaskState.READY:
        raise AppException("任务当前不可办理", status_code=409)
    if variables:
        task.data.update(variables)
    workflow.run_task_from_id(spiff_task_id)
    workflow.do_engine_steps()
    return get_ready_user_tasks(workflow)


def workflow_is_completed(workflow: BpmnWorkflow) -> bool:
    return workflow.is_completed()


def workflow_is_rejected(workflow: BpmnWorkflow) -> bool:
    """根据 end event bpmn_id 粗略判断是否驳回终态。"""
    for task in workflow.get_tasks_iterator():
        if task.state != TaskState.COMPLETED:
            continue
        bpmn_id = getattr(task.task_spec, "bpmn_id", None) or ""
        if "reject" in str(bpmn_id).lower():
            return True
    return False


def serialize_workflow(workflow: BpmnWorkflow) -> dict[str, Any]:
    serializer = BpmnWorkflowSerializer()
    raw = serializer.serialize_json(workflow)
    if isinstance(raw, str):
        return json.loads(raw)
    return raw


def deserialize_workflow(
    bpmn_xml: str,
    workflow_state: dict[str, Any] | str,
    *,
    process_id: str | None = None,
) -> BpmnWorkflow:
    serializer = BpmnWorkflowSerializer()
    if isinstance(workflow_state, dict):
        return serializer.from_dict(workflow_state)
    if isinstance(workflow_state, str):
        return serializer.deserialize_json(workflow_state)
    raise BpmnValidationError("无效的 workflow_state")
