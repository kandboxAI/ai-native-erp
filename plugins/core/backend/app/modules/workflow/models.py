"""表模型（wf_definition、wf_definition_version、wf_instance、wf_task、wf_task_candidate、wf_task_action、wf_cc_record）。

初始版本由 docs/foundation-platform/data-dictionary/tools/gen_models.py 按数据字典生成，之后以本文件为准维护。
"""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import DateTime, Index, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel

from app.framework.db.models import (
    audit_user_field,
    bool_field,
    created_at_field,
    deleted_at_field,
    flex_form_field,
    id_field,
    org_field,
    updated_at_field,
)


class WfDefinition(SQLModel, table=True):
    """流程定义：一行为一个审批流程。"""

    __tablename__ = "wf_definition"
    __table_args__ = (
        Index("uk_wf_definition_definition_no", "definition_no", unique=True, postgresql_where=text("deleted_at is null")),
        {'comment': '流程定义：一行为一个审批流程。'},
    )

    id: UUID = id_field()
    org_id: UUID = org_field()
    definition_no: str = Field(max_length=64, nullable=False, sa_column_kwargs={'comment': '流程编号'})
    definition_name: str = Field(max_length=128, nullable=False, sa_column_kwargs={'comment': '流程名称'})
    business_type_code: str = Field(max_length=64, nullable=False, sa_column_kwargs={'comment': '业务类型；字典 wf_business_type'})
    description: str | None = Field(default=None, sa_type=Text, nullable=True, sa_column_kwargs={'comment': '说明'})
    is_default: bool = bool_field('是否为组织同业务类型的默认流程；非默认启用流程仅供明确指定使用', default=True)
    current_version_id: UUID | None = Field(default=None, foreign_key="wf_definition_version.id", index=True, nullable=True, sa_column_kwargs={'comment': '当前版本'})
    is_active: bool = bool_field('是否启用', default=True)
    created_at: datetime = created_at_field()
    created_by: UUID | None = audit_user_field('创建人；系统任务创建时为空')
    updated_at: datetime = updated_at_field()
    updated_by: UUID | None = audit_user_field('修改人')
    deleted_at: datetime | None = deleted_at_field()
    deleted_by: UUID | None = audit_user_field('删除人；与删除时间同时出现')
    flex_form: dict[str, Any] = flex_form_field('扩展字段；租户自定义字段，结构见动态表单定义；默认 {}')


class WfDefinitionVersion(SQLModel, table=True):
    """流程版本：一行为流程的一个版本。"""

    __tablename__ = "wf_definition_version"
    __table_args__ = (
        Index("uk_wf_definition_version_definition_id_version_no", "definition_id", "version_no", unique=True),
        {'comment': '流程版本：一行为流程的一个版本。'},
    )

    id: UUID = id_field()
    definition_id: UUID = Field(foreign_key="wf_definition.id", nullable=False, sa_column_kwargs={'comment': '流程定义'})
    version_no: int = Field(nullable=False, sa_column_kwargs={'comment': '版本号'})
    bpmn_process_no: str = Field(max_length=128, nullable=False, sa_column_kwargs={'comment': 'BPMN 流程标识'})
    bpmn_xml: str | None = Field(default=None, sa_type=Text, nullable=True, sa_column_kwargs={'comment': 'BPMN 定义'})
    spiff_spec_snapshot: Any | None = Field(default=None, sa_type=JSONB, nullable=True, sa_column_kwargs={'comment': '引擎规格快照；快照'})
    status_code: str = Field(max_length=64, nullable=False, sa_column_kwargs={'comment': '状态；字典 wf_definition_version_status'})
    published_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True), nullable=True, sa_column_kwargs={'comment': '发布时间'})
    created_at: datetime = created_at_field()
    created_by: UUID | None = audit_user_field('创建人；系统任务创建时为空')
    updated_at: datetime = updated_at_field()
    updated_by: UUID | None = audit_user_field('修改人')
    flex_form: dict[str, Any] = flex_form_field('扩展字段；租户自定义字段，结构见动态表单定义；默认 {}')


class WfInstance(SQLModel, table=True):
    """流程实例：一行为一次审批流程的运行。"""

    __tablename__ = "wf_instance"
    __table_args__ = (
        {'comment': '流程实例：一行为一次审批流程的运行。'},
    )

    id: UUID = id_field()
    org_id: UUID = org_field()
    definition_id: UUID = Field(foreign_key="wf_definition.id", index=True, nullable=False, sa_column_kwargs={'comment': '流程定义'})
    version_id: UUID = Field(foreign_key="wf_definition_version.id", index=True, nullable=False, sa_column_kwargs={'comment': '流程版本'})
    business_type_code: str = Field(max_length=64, nullable=False, sa_column_kwargs={'comment': '业务类型；字典 wf_business_type'})
    business_id: UUID = Field(nullable=False, sa_column_kwargs={'comment': '业务单据；多态引用，类型见业务类型'})
    status_code: str = Field(max_length=64, nullable=False, sa_column_kwargs={'comment': '状态；字典 wf_instance_status'})
    ai_analysis_status_code: str = Field(default="not_applicable", max_length=32, sa_column_kwargs={"server_default": "not_applicable", "comment": "AI分析状态；字典 wf_ai_analysis_status；不参与审批状态判断"})
    ai_analysis: str = Field(default="", sa_type=Text, sa_column_kwargs={"server_default": "", "comment": "本次业务申请的AI参考分析，各审批节点共用；与人工审批意见分开，不向无业务读取权限的用户公开"})
    ai_analysis_model: str = Field(default="", max_length=128, sa_column_kwargs={"server_default": "", "comment": "生成分析的模型名称；不保存密钥"})
    ai_analysis_source_hash: str = Field(default="", max_length=64, sa_column_kwargs={"server_default": "", "comment": "脱敏分析事实的SHA-256；用于变更及并发校验，不保存原始事实"})
    ai_analysis_generated_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True), sa_column_kwargs={"comment": "AI参考分析生成时间"})
    ai_analysis_started_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True), sa_column_kwargs={"comment": "AI分析本次执行租约开始时间；超时后可重新领取"})
    ai_analysis_error: str = Field(default="", max_length=300, sa_column_kwargs={"server_default": "", "comment": "脱敏后的分析失败原因，不保存模型原始响应或业务原文"})
    bpmn_activity_no: str | None = Field(default=None, max_length=128, nullable=True, sa_column_kwargs={'comment': '当前节点'})
    workflow_state_snapshot: Any | None = Field(default=None, sa_type=JSONB, nullable=True, sa_column_kwargs={'comment': '引擎状态；快照'})
    started_by: UUID = Field(foreign_key="sys_user.id", index=True, nullable=False, sa_column_kwargs={'comment': '发起人'})
    started_at: datetime = Field(sa_type=DateTime(timezone=True), nullable=False, sa_column_kwargs={'comment': '发起时间'})
    ended_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True), nullable=True, sa_column_kwargs={'comment': '结束时间'})
    created_at: datetime = created_at_field()
    created_by: UUID | None = audit_user_field('创建人；系统任务创建时为空')
    updated_at: datetime = updated_at_field()
    updated_by: UUID | None = audit_user_field('修改人')
    flex_form: dict[str, Any] = flex_form_field('扩展字段；租户自定义字段，结构见动态表单定义；默认 {}')


class WfTask(SQLModel, table=True):
    """审批任务：一行为流程中的一个待办审批任务。"""

    __tablename__ = "wf_task"
    __table_args__ = (
        {'comment': '审批任务：一行为流程中的一个待办审批任务。'},
    )

    id: UUID = id_field()
    org_id: UUID = org_field()
    instance_id: UUID = Field(foreign_key="wf_instance.id", index=True, nullable=False, sa_column_kwargs={'comment': '流程实例'})
    task_key: str = Field(max_length=128, nullable=False, sa_column_kwargs={'comment': '节点标识；BPMN 中的任务节点'})
    task_name: str = Field(max_length=128, nullable=False, sa_column_kwargs={'comment': '任务名称'})
    spiff_task_no: str | None = Field(default=None, max_length=64, nullable=True, sa_column_kwargs={'comment': '引擎任务标识'})
    assignee_type_code: str = Field(max_length=64, nullable=False, sa_column_kwargs={'comment': '审批人类型；字典 wf_assignee_type'})
    assignee_value: str | None = Field(default=None, max_length=256, nullable=True, sa_column_kwargs={'comment': '审批人配置'})
    approval_mode_code: str = Field(max_length=64, nullable=False, sa_column_kwargs={'comment': '多人审批方式；字典 wf_approval_mode'})
    assignee_user_id: UUID | None = Field(default=None, foreign_key="sys_user.id", index=True, nullable=True, sa_column_kwargs={'comment': '处理人'})
    status_code: str = Field(max_length=64, nullable=False, sa_column_kwargs={'comment': '状态；字典 wf_task_status'})
    arrived_at: datetime = Field(sa_type=DateTime(timezone=True), nullable=False, sa_column_kwargs={'comment': '到达时间'})
    completed_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True), nullable=True, sa_column_kwargs={'comment': '完成时间'})
    completed_by: UUID | None = Field(default=None, foreign_key="sys_user.id", index=True, nullable=True, sa_column_kwargs={'comment': '完成人'})
    outcome_code: str | None = Field(default=None, max_length=64, nullable=True, sa_column_kwargs={'comment': '审批结果；字典 wf_task_outcome'})
    comment: str | None = Field(default=None, sa_type=Text, nullable=True, sa_column_kwargs={'comment': '审批意见'})
    created_at: datetime = created_at_field()
    created_by: UUID | None = audit_user_field('创建人；系统任务创建时为空')
    updated_at: datetime = updated_at_field()
    updated_by: UUID | None = audit_user_field('修改人')
    flex_form: dict[str, Any] = flex_form_field('扩展字段；租户自定义字段，结构见动态表单定义；默认 {}')


class WfTaskCandidate(SQLModel, table=True):
    """审批候选人：一行为一个审批任务的一个候选处理人。"""

    __tablename__ = "wf_task_candidate"
    __table_args__ = (
        Index("uk_wf_task_candidate_task_id_user_id", "task_id", "user_id", unique=True),
        {'comment': '审批候选人：一行为一个审批任务的一个候选处理人。'},
    )

    id: UUID = id_field()
    org_id: UUID = org_field()
    task_id: UUID = Field(foreign_key="wf_task.id", nullable=False, sa_column_kwargs={'comment': '审批任务'})
    user_id: UUID = Field(foreign_key="sys_user.id", index=True, nullable=False, sa_column_kwargs={'comment': '候选人'})
    created_at: datetime = created_at_field()
    created_by: UUID | None = audit_user_field('创建人；系统任务创建时为空')
    updated_at: datetime = updated_at_field()
    updated_by: UUID | None = audit_user_field('修改人')
    flex_form: dict[str, Any] = flex_form_field('扩展字段；租户自定义字段，结构见动态表单定义；默认 {}')


class WfTaskAction(SQLModel, table=True):
    """审批记录：一行为一次审批动作。"""

    __tablename__ = "wf_task_action"
    __table_args__ = (
        {'comment': '审批记录：一行为一次审批动作。'},
    )

    id: UUID = id_field()
    org_id: UUID = org_field()
    instance_id: UUID = Field(foreign_key="wf_instance.id", index=True, nullable=False, sa_column_kwargs={'comment': '流程实例'})
    task_id: UUID | None = Field(default=None, foreign_key="wf_task.id", index=True, nullable=True, sa_column_kwargs={'comment': '审批任务'})
    action_code: str = Field(max_length=64, nullable=False, sa_column_kwargs={'comment': '动作；字典 wf_action'})
    actor_user_id: UUID = Field(foreign_key="sys_user.id", index=True, nullable=False, sa_column_kwargs={'comment': '操作人'})
    comment: str | None = Field(default=None, sa_type=Text, nullable=True, sa_column_kwargs={'comment': '意见'})
    payload: Any | None = Field(default=None, sa_type=JSONB, nullable=True, sa_column_kwargs={'comment': '附加信息'})
    created_at: datetime = created_at_field()
    created_by: UUID | None = audit_user_field('创建人；系统任务创建时为空')


class WfCcRecord(SQLModel, table=True):
    """抄送记录：一行为一次抄送给一个人。"""

    __tablename__ = "wf_cc_record"
    __table_args__ = (
        {'comment': '抄送记录：一行为一次抄送给一个人。'},
    )

    id: UUID = id_field()
    org_id: UUID = org_field()
    instance_id: UUID = Field(foreign_key="wf_instance.id", index=True, nullable=False, sa_column_kwargs={'comment': '流程实例'})
    task_id: UUID | None = Field(default=None, foreign_key="wf_task.id", index=True, nullable=True, sa_column_kwargs={'comment': '审批任务'})
    task_key: str | None = Field(default=None, max_length=128, nullable=True, sa_column_kwargs={'comment': '节点标识'})
    business_type_code: str = Field(max_length=64, nullable=False, sa_column_kwargs={'comment': '业务类型；字典 wf_business_type'})
    business_id: UUID = Field(nullable=False, sa_column_kwargs={'comment': '业务单据；多态引用'})
    cc_type_code: str = Field(max_length=64, nullable=False, sa_column_kwargs={'comment': '抄送对象类型；字典 wf_cc_type'})
    recipient_user_id: UUID = Field(foreign_key="sys_user.id", index=True, nullable=False, sa_column_kwargs={'comment': '接收人'})
    status_code: str = Field(max_length=64, nullable=False, sa_column_kwargs={'comment': '阅读状态；字典 wf_read_status'})
    read_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True), nullable=True, sa_column_kwargs={'comment': '阅读时间'})
    payload: Any | None = Field(default=None, sa_type=JSONB, nullable=True, sa_column_kwargs={'comment': '附加信息'})
    created_at: datetime = created_at_field()
    created_by: UUID | None = audit_user_field('创建人；系统任务创建时为空')
    updated_at: datetime = updated_at_field()
    updated_by: UUID | None = audit_user_field('修改人')
    flex_form: dict[str, Any] = flex_form_field('扩展字段；租户自定义字段，结构见动态表单定义；默认 {}')
