"""可视化审批流设计模型。

designer_v1 / designer_v2 仅用于兼容历史快照；新设计统一保存为 designer_v3。
"""

from __future__ import annotations

import re
from typing import Annotated, Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator, model_validator

SCHEMA_VERSION_V1 = 1
SCHEMA_VERSION_V2 = 2
SCHEMA_VERSION = 3
LEGACY_ASSIGNEE_TYPES = ("role", "user")
AssigneeTypeV1 = Literal["role", "user"]
# 审批人类型（字典 wf_assignee_type）。不按角色指定审批人（整改方案 §2.18）：
# - user：指定用户（sys_user.id）
# - permission：拥有某权限的用户
# - business_owner：业务关系人，由业务模块登记解析方式
# - department_manager：某部门（department_no）的负责人
# - initiator_leader：发起人所在部门的负责人
# - starter / starter_select：发起人本人 / 发起时由发起人选择
AssigneeType = Literal[
    "user",
    "permission",
    "business_owner",
    "department_manager",
    "initiator_leader",
    "starter",
    "starter_select",
]
ASSIGNEE_TYPE_LABELS: dict[str, str] = {
    "user": "指定用户",
    "permission": "拥有权限的用户",
    "business_owner": "业务负责人",
    "department_manager": "部门负责人",
    "initiator_leader": "发起人上级",
    "starter": "发起人本人",
    "starter_select": "发起人自选",
}
FlowMode = Literal["serial", "conditional"]
ConditionOperator = Literal["eq", "ne", "gt", "gte", "lt", "lte"]
ApprovalMode = Literal["single", "any", "all"]


def _validate_node_id(value: str) -> str:
    if not re.match(r"^[a-zA-Z][a-zA-Z0-9_]*$", value):
        raise ValueError("节点 id 仅允许字母、数字、下划线，且以字母开头")
    return value


class AssigneeConfigV1(BaseModel):
    type: AssigneeTypeV1
    value: str = Field(..., min_length=1, max_length=256)


class ApprovalStepV1(BaseModel):
    id: str = Field(..., min_length=1, max_length=64)
    name: str = Field(..., min_length=1, max_length=128)
    assignee: AssigneeConfigV1
    cc: list[AssigneeConfigV1] = Field(default_factory=list, max_length=20)

    _valid_id = field_validator("id")(_validate_node_id)


class ConditionBranchV1(BaseModel):
    id: str = Field(..., min_length=1, max_length=64)
    name: str = Field(..., min_length=1, max_length=128)
    condition: str = Field(..., min_length=1, max_length=256)
    steps: list[ApprovalStepV1] = Field(default_factory=list)

    _valid_id = field_validator("id")(_validate_node_id)


class ConditionalGatewayV1(BaseModel):
    variable: str = Field(default="leave_days", max_length=64)
    default_branch_id: str | None = None
    branches: list[ConditionBranchV1] = Field(..., min_length=2, max_length=8)


class FlowDesignV1(BaseModel):
    schema_version: Literal[1] = SCHEMA_VERSION_V1
    process_name: str = Field(..., min_length=1, max_length=128)
    process_id: str | None = Field(default=None, max_length=128)
    mode: FlowMode = "serial"
    steps: list[ApprovalStepV1] = Field(default_factory=list)
    gateway: ConditionalGatewayV1 | None = None

    @model_validator(mode="after")
    def validate_mode_payload(self) -> FlowDesignV1:
        if self.mode == "serial":
            if not self.steps:
                raise ValueError("串行模式至少需要一个审批节点")
            if self.gateway is not None:
                raise ValueError("串行模式不应包含条件分支")
        elif self.gateway is None or len(self.gateway.branches) < 2:
            raise ValueError("条件分支模式至少需要 2 条分支")
        return self


class AssigneeConfig(BaseModel):
    type: AssigneeType
    value: str | None = Field(default=None, max_length=256)

    @model_validator(mode="after")
    def validate_value(self) -> AssigneeConfig:
        if self.type in {
            "user",
            "permission",
            "business_owner",
            "department_manager",
            "starter_select",
        } and not (self.value or "").strip():
            raise ValueError(f"{self.type} 类型必须配置 value")
        if self.type == "starter":
            self.value = "starter"
        if self.type == "initiator_leader":
            self.value = "initiator_leader"
        return self


class ApprovalNode(BaseModel):
    type: Literal["approval"] = "approval"
    id: str = Field(..., min_length=1, max_length=64)
    name: str = Field(..., min_length=1, max_length=128)
    assignee: AssigneeConfig
    approval_mode: ApprovalMode = "single"
    assignees: list[AssigneeConfig] = Field(default_factory=list, max_length=20)

    _valid_id = field_validator("id")(_validate_node_id)

    @model_validator(mode="after")
    def normalize_assignees(self) -> ApprovalNode:
        if not self.assignees:
            self.assignees = [self.assignee]
        self.assignee = self.assignees[0]
        if self.approval_mode == "single" and len(self.assignees) != 1:
            raise ValueError("单人审批只能配置一个审批对象")
        if self.approval_mode in {"any", "all"} and len(self.assignees) < 2:
            raise ValueError("或签/会签至少需要配置两个审批对象")
        return self


class CcNode(BaseModel):
    type: Literal["cc"] = "cc"
    id: str = Field(..., min_length=1, max_length=64)
    name: str = Field(default="抄送人", min_length=1, max_length=128)
    recipients: list[AssigneeConfig] = Field(..., min_length=1, max_length=20)

    _valid_id = field_validator("id")(_validate_node_id)


FlowNode = Annotated[ApprovalNode | CcNode, Field(discriminator="type")]


class ConditionExpression(BaseModel):
    field: str = Field(..., min_length=1, max_length=64)
    operator: ConditionOperator
    value: str | int | float | bool


class ConditionBranch(BaseModel):
    id: str = Field(..., min_length=1, max_length=64)
    name: str = Field(..., min_length=1, max_length=128)
    condition: ConditionExpression | None = None
    nodes: list[FlowNode] = Field(..., min_length=1, max_length=50)

    _valid_id = field_validator("id")(_validate_node_id)


class ConditionalGateway(BaseModel):
    default_branch_id: str
    branches: list[ConditionBranch] = Field(..., min_length=2, max_length=8)

    @model_validator(mode="after")
    def validate_default_branch(self) -> ConditionalGateway:
        ids = [branch.id for branch in self.branches]
        if len(ids) != len(set(ids)):
            raise ValueError("条件分支 id 不能重复")
        if self.default_branch_id not in ids:
            raise ValueError("默认分支不存在")
        for branch in self.branches:
            if branch.id == self.default_branch_id and branch.condition is not None:
                raise ValueError("默认分支不能配置条件")
            if branch.id != self.default_branch_id and branch.condition is None:
                raise ValueError(f"分支「{branch.name}」必须配置条件")
        return self


class ConditionBranchV3(BaseModel):
    id: str = Field(..., min_length=1, max_length=64)
    name: str = Field(..., min_length=1, max_length=128)
    condition: ConditionExpression | None = None
    nodes: list["FlowNodeV3"] = Field(..., min_length=1, max_length=80)

    _valid_id = field_validator("id")(_validate_node_id)


class ExclusiveGatewayNode(BaseModel):
    type: Literal["exclusive_gateway"] = "exclusive_gateway"
    id: str = Field(..., min_length=1, max_length=64)
    name: str = Field(default="条件分支", min_length=1, max_length=128)
    default_branch_id: str
    branches: list[ConditionBranchV3] = Field(..., min_length=2, max_length=8)

    _valid_id = field_validator("id")(_validate_node_id)

    @model_validator(mode="after")
    def validate_default_branch(self) -> ExclusiveGatewayNode:
        ids = [branch.id for branch in self.branches]
        if len(ids) != len(set(ids)):
            raise ValueError("条件分支 id 不能重复")
        if self.default_branch_id not in ids:
            raise ValueError("默认分支不存在")
        for branch in self.branches:
            if branch.id == self.default_branch_id and branch.condition is not None:
                raise ValueError("默认分支不能配置条件")
            if branch.id != self.default_branch_id and branch.condition is None:
                raise ValueError(f"分支「{branch.name}」必须配置条件")
        return self


class ParallelGatewayNode(BaseModel):
    type: Literal["parallel_gateway"] = "parallel_gateway"
    id: str = Field(..., min_length=1, max_length=64)
    name: str = Field(default="并行审批", min_length=1, max_length=128)
    branches: list[ConditionBranchV3] = Field(..., min_length=2, max_length=8)

    _valid_id = field_validator("id")(_validate_node_id)

    @model_validator(mode="after")
    def unconditional_branches(self) -> ParallelGatewayNode:
        if any(branch.condition is not None for branch in self.branches):
            raise ValueError("并行分支不能配置条件")
        return self


FlowNodeV3 = Annotated[
    ApprovalNode | CcNode | ExclusiveGatewayNode | ParallelGatewayNode,
    Field(discriminator="type"),
]


def _validate_node_chain(nodes: list[FlowNode], label: str) -> None:
    ids = [node.id for node in nodes]
    if len(ids) != len(set(ids)):
        raise ValueError(f"{label}的节点 id 不能重复")
    approval_seen = False
    for node in nodes:
        if node.type == "approval":
            approval_seen = True
        elif not approval_seen:
            raise ValueError(f"{label}中的抄送节点必须放在审批节点之后")
    if not approval_seen:
        raise ValueError(f"{label}至少需要一个审批节点")


class FlowDesignV2(BaseModel):
    schema_version: Literal[2] = SCHEMA_VERSION_V2
    process_name: str = Field(..., min_length=1, max_length=128)
    process_id: str | None = Field(default=None, max_length=128)
    mode: FlowMode = "serial"
    nodes: list[FlowNode] = Field(default_factory=list, max_length=50)
    gateway: ConditionalGateway | None = None

    @model_validator(mode="after")
    def validate_mode_payload(self) -> FlowDesignV2:
        if self.mode == "serial":
            if self.gateway is not None:
                raise ValueError("串行模式不应包含条件分支")
            _validate_node_chain(self.nodes, "串行流程")
        else:
            if self.gateway is None:
                raise ValueError("条件分支模式缺少 gateway")
            if self.nodes:
                raise ValueError("条件分支模式不应包含串行节点")
            all_node_ids: list[str] = []
            for branch in self.gateway.branches:
                _validate_node_chain(branch.nodes, f"分支「{branch.name}」")
                all_node_ids.extend(node.id for node in branch.nodes)
            if len(all_node_ids) != len(set(all_node_ids)):
                raise ValueError("不同条件分支的节点 id 不能重复")
        return self


def _collect_v3_ids(nodes: list[FlowNodeV3], ids: list[str]) -> None:
    for node in nodes:
        ids.append(node.id)
        if isinstance(node, (ExclusiveGatewayNode, ParallelGatewayNode)):
            ids.extend(branch.id for branch in node.branches)
            for branch in node.branches:
                _collect_v3_ids(branch.nodes, ids)


def _validate_v3_node_chain(
    nodes: list[FlowNodeV3],
    label: str,
    *,
    approval_seen: bool = False,
) -> bool:
    if not nodes:
        raise ValueError(f"{label}至少需要一个流程节点")
    all_paths_have_approval = approval_seen
    can_place_cc = False
    for node in nodes:
        if isinstance(node, ApprovalNode):
            all_paths_have_approval = True
            can_place_cc = True
        elif isinstance(node, CcNode):
            if not can_place_cc:
                raise ValueError(f"{label}中的抄送节点必须放在审批节点之后")
        else:
            branch_results = [
                _validate_v3_node_chain(
                    branch.nodes,
                    f"{label} / 分支「{branch.name}」",
                    approval_seen=all_paths_have_approval,
                )
                for branch in node.branches
            ]
            all_paths_have_approval = all(branch_results)
            can_place_cc = False
    return all_paths_have_approval


class FlowDesignV3(BaseModel):
    schema_version: Literal[3] = SCHEMA_VERSION
    process_name: str = Field(..., min_length=1, max_length=128)
    process_id: str | None = Field(default=None, max_length=128)
    nodes: list[FlowNodeV3] = Field(..., min_length=1, max_length=80)

    @model_validator(mode="after")
    def validate_nodes(self) -> FlowDesignV3:
        ids: list[str] = []
        _collect_v3_ids(self.nodes, ids)
        if len(ids) != len(set(ids)):
            raise ValueError("流程节点、网关和分支 id 不能重复")
        if not _validate_v3_node_chain(self.nodes, "流程"):
            raise ValueError("每条流程路径至少需要一个审批节点")
        return self


FlowDesign = FlowDesignV1 | FlowDesignV2 | FlowDesignV3


def new_step_id() -> str:
    return f"user_task_{uuid4().hex[:8]}"


def new_cc_id() -> str:
    return f"cc_node_{uuid4().hex[:8]}"


def new_branch_id() -> str:
    return f"branch_{uuid4().hex[:8]}"


def new_gateway_id() -> str:
    return f"gateway_{uuid4().hex[:8]}"


def _legacy_condition_to_expression(condition: str, fallback_field: str) -> ConditionExpression:
    match = re.fullmatch(
        r"\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*(<=|>=|==|!=|<|>)\s*(-?\d+(?:\.\d+)?)\s*",
        condition,
    )
    if not match:
        return ConditionExpression(field=fallback_field, operator="gt", value=0)
    field_name, symbol, raw_value = match.groups()
    operator_map: dict[str, ConditionOperator] = {
        "==": "eq",
        "!=": "ne",
        ">": "gt",
        ">=": "gte",
        "<": "lt",
        "<=": "lte",
    }
    value: int | float = float(raw_value) if "." in raw_value else int(raw_value)
    return ConditionExpression(field=field_name, operator=operator_map[symbol], value=value)


def upgrade_v1_to_v2(design: FlowDesignV1) -> FlowDesignV2:
    def convert_steps(steps: list[ApprovalStepV1]) -> list[FlowNode]:
        nodes: list[FlowNode] = []
        for step in steps:
            nodes.append(
                ApprovalNode(
                    id=step.id,
                    name=step.name,
                    assignee=AssigneeConfig(type=step.assignee.type, value=step.assignee.value),
                )
            )
            if step.cc:
                cc_id = f"cc_{step.id}"[:64]
                nodes.append(
                    CcNode(
                        id=cc_id,
                        name=f"{step.name}抄送",
                        recipients=[
                            AssigneeConfig(type=item.type, value=item.value) for item in step.cc
                        ],
                    )
                )
        return nodes

    if design.mode == "serial":
        return FlowDesignV2(
            process_name=design.process_name,
            process_id=design.process_id,
            mode="serial",
            nodes=convert_steps(design.steps),
        )

    if design.gateway is None:
        raise ValueError("旧版条件流程缺少 gateway")
    default_id = design.gateway.default_branch_id or design.gateway.branches[-1].id
    branches = []
    for branch in design.gateway.branches:
        condition = None
        if branch.id != default_id:
            condition = _legacy_condition_to_expression(branch.condition, design.gateway.variable)
        branches.append(
            ConditionBranch(
                id=branch.id,
                name=branch.name,
                condition=condition,
                nodes=convert_steps(branch.steps),
            )
        )
    return FlowDesignV2(
        process_name=design.process_name,
        process_id=design.process_id,
        mode="conditional",
        gateway=ConditionalGateway(default_branch_id=default_id, branches=branches),
    )


def upgrade_v2_to_v3(design: FlowDesignV2) -> FlowDesignV3:
    if design.mode == "serial":
        return FlowDesignV3(
            process_name=design.process_name,
            process_id=design.process_id,
            nodes=design.nodes,
        )
    if design.gateway is None:
        raise ValueError("旧版条件流程缺少 gateway")
    return FlowDesignV3(
        process_name=design.process_name,
        process_id=design.process_id,
        nodes=[
            ExclusiveGatewayNode(
                id="gateway_conditions",
                name="条件分支",
                default_branch_id=design.gateway.default_branch_id,
                branches=[
                    ConditionBranchV3(
                        id=branch.id,
                        name=branch.name,
                        condition=branch.condition,
                        nodes=branch.nodes,
                    )
                    for branch in design.gateway.branches
                ],
            )
        ],
    )


def parse_flow_design(data: dict[str, Any] | BaseModel) -> FlowDesignV1 | FlowDesignV2 | FlowDesignV3:
    raw = data.model_dump(mode="json") if isinstance(data, BaseModel) else data
    if raw.get("schema_version") == SCHEMA_VERSION_V1:
        return FlowDesignV1.model_validate(raw)
    if raw.get("schema_version") == SCHEMA_VERSION:
        return FlowDesignV3.model_validate(raw)
    return FlowDesignV2.model_validate(raw)


def normalize_flow_design(data: dict[str, Any] | BaseModel) -> FlowDesignV3:
    design = parse_flow_design(data)
    if isinstance(design, FlowDesignV1):
        return upgrade_v2_to_v3(upgrade_v1_to_v2(design))
    if isinstance(design, FlowDesignV2):
        return upgrade_v2_to_v3(design)
    return design


def default_serial_design(
    *,
    process_name: str,
    process_id: str,
    step_name: str = "审批",
    assignee: AssigneeConfig | None = None,
) -> FlowDesignV3:
    return FlowDesignV3(
        process_name=process_name,
        process_id=process_id,
        nodes=[
            ApprovalNode(
                id="user_task_approval",
                name=step_name,
                assignee=assignee or AssigneeConfig(type="initiator_leader"),
            )
        ],
    )


def default_designs(only: set[str] | None = None):
    """业务插件通过 workflow_defaults.DEFAULT_DESIGNS 声明模板。"""
    from app.framework.catalog import iter_module_attr
    result = {}
    for module in iter_module_attr("workflow_defaults", only):
        values = getattr(module, "DEFAULT_DESIGNS", {})
        if result.keys() & values.keys():
            raise ValueError("审批模板业务类型重复")
        result.update(values)
    return result


ConditionBranchV3.model_rebuild()
ExclusiveGatewayNode.model_rebuild()
ParallelGatewayNode.model_rebuild()
FlowDesignV3.model_rebuild()
