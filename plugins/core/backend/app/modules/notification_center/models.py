"""表模型（ntf_scene、ntf_scene_channel、ntf_template、ntf_route、ntf_notification、ntf_recipient、ntf_preference、ntf_channel_binding、ntf_delivery_log、ntf_event_log）。

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


class NtfScene(SQLModel, table=True):
    """通知场景：一行为一个由业务代码触发的通知场景。"""

    __tablename__ = "ntf_scene"
    __table_args__ = (
        Index("uk_ntf_scene_scene_key", "scene_key", unique=True, postgresql_where=text("deleted_at is null")),
        {'comment': '通知场景：一行为一个由业务代码触发的通知场景。`scene_key` 由代码定义，如 leave_approved。'},
    )

    id: UUID = id_field()
    scene_key: str = Field(max_length=128, nullable=False, sa_column_kwargs={'comment': '场景标识'})
    scene_name: str = Field(max_length=128, nullable=False, sa_column_kwargs={'comment': '场景名称'})
    module_code: str = Field(max_length=64, nullable=False, sa_column_kwargs={'comment': '所属模块；字典 sys_module'})
    description: str | None = Field(default=None, sa_type=Text, nullable=True, sa_column_kwargs={'comment': '说明'})
    severity_code: str = Field(max_length=64, nullable=False, sa_column_kwargs={'comment': '重要程度；字典 ntf_severity'})
    fallback_policy_code: str = Field(max_length=64, nullable=False, sa_column_kwargs={'comment': '渠道降级策略；字典 ntf_fallback_policy'})
    is_active: bool = bool_field('是否启用', default=True)
    created_at: datetime = created_at_field()
    created_by: UUID | None = audit_user_field('创建人；系统任务创建时为空')
    updated_at: datetime = updated_at_field()
    updated_by: UUID | None = audit_user_field('修改人')
    deleted_at: datetime | None = deleted_at_field()
    deleted_by: UUID | None = audit_user_field('删除人；与删除时间同时出现')
    flex_form: dict[str, Any] = flex_form_field('扩展字段；租户自定义字段，结构见动态表单定义；默认 {}')


class NtfSceneChannel(SQLModel, table=True):
    """场景渠道：一行为一个通知场景启用的一个渠道。"""

    __tablename__ = "ntf_scene_channel"
    __table_args__ = (
        Index("uk_ntf_scene_channel_scene_id_channel_code", "scene_id", "channel_code", unique=True),
        {'comment': '场景渠道：一行为一个通知场景启用的一个渠道。'},
    )

    id: UUID = id_field()
    scene_id: UUID = Field(foreign_key="ntf_scene.id", nullable=False, sa_column_kwargs={'comment': '通知场景'})
    channel_code: str = Field(max_length=64, nullable=False, sa_column_kwargs={'comment': '渠道；字典 ntf_channel'})
    is_active: bool = bool_field('是否启用', default=True)
    created_at: datetime = created_at_field()
    created_by: UUID | None = audit_user_field('创建人；系统任务创建时为空')
    updated_at: datetime = updated_at_field()
    updated_by: UUID | None = audit_user_field('修改人')
    flex_form: dict[str, Any] = flex_form_field('扩展字段；租户自定义字段，结构见动态表单定义；默认 {}')


class NtfTemplate(SQLModel, table=True):
    """通知模板：一行为一个场景在一个渠道上的模板。"""

    __tablename__ = "ntf_template"
    __table_args__ = (
        Index("uk_ntf_template_scene_id_channel_code", "scene_id", "channel_code", unique=True, postgresql_where=text("deleted_at is null")),
        {'comment': '通知模板：一行为一个场景在一个渠道上的模板。'},
    )

    id: UUID = id_field()
    scene_id: UUID = Field(foreign_key="ntf_scene.id", nullable=False, sa_column_kwargs={'comment': '通知场景'})
    channel_code: str = Field(max_length=64, nullable=False, sa_column_kwargs={'comment': '渠道；字典 ntf_channel'})
    title_template: str | None = Field(default=None, max_length=512, nullable=True, sa_column_kwargs={'comment': '标题模板'})
    content_template: str | None = Field(default=None, sa_type=Text, nullable=True, sa_column_kwargs={'comment': '内容模板'})
    wechat_template_no: str | None = Field(default=None, max_length=128, nullable=True, sa_column_kwargs={'comment': '微信模板标识'})
    data_mapping_config: Any | None = Field(default=None, sa_type=JSONB, nullable=True, sa_column_kwargs={'comment': '字段映射配置'})
    is_active: bool = bool_field('是否启用', default=True)
    created_at: datetime = created_at_field()
    created_by: UUID | None = audit_user_field('创建人；系统任务创建时为空')
    updated_at: datetime = updated_at_field()
    updated_by: UUID | None = audit_user_field('修改人')
    deleted_at: datetime | None = deleted_at_field()
    deleted_by: UUID | None = audit_user_field('删除人；与删除时间同时出现')
    flex_form: dict[str, Any] = flex_form_field('扩展字段；租户自定义字段，结构见动态表单定义；默认 {}')


class NtfRoute(SQLModel, table=True):
    """通知路由：一行为一个场景的一条接收人规则。"""

    __tablename__ = "ntf_route"
    __table_args__ = (
        {'comment': '通知路由：一行为一个场景的一条接收人规则。'},
    )

    id: UUID = id_field()
    scene_id: UUID = Field(foreign_key="ntf_scene.id", index=True, nullable=False, sa_column_kwargs={'comment': '通知场景'})
    target_type_code: str = Field(max_length=64, nullable=False, sa_column_kwargs={'comment': '接收对象类型；字典 ntf_target_type'})
    role_id: UUID | None = Field(default=None, foreign_key="sys_role.id", index=True, nullable=True, sa_column_kwargs={'comment': '角色'})
    user_id: UUID | None = Field(default=None, foreign_key="sys_user.id", index=True, nullable=True, sa_column_kwargs={'comment': '用户'})
    permission_id: UUID | None = Field(default=None, foreign_key="sys_permission.id", index=True, nullable=True, sa_column_kwargs={'comment': '权限'})
    actor_key: str | None = Field(default=None, max_length=128, nullable=True, sa_column_kwargs={'comment': '业务相关人标识；如 applicant、homeroom_teacher'})
    org_scope_code: str = Field(max_length=64, nullable=False, sa_column_kwargs={'comment': '组织范围；字典 ntf_route_org_scope'})
    is_active: bool = bool_field('是否启用', default=True)
    created_at: datetime = created_at_field()
    created_by: UUID | None = audit_user_field('创建人；系统任务创建时为空')
    updated_at: datetime = updated_at_field()
    updated_by: UUID | None = audit_user_field('修改人')
    deleted_at: datetime | None = deleted_at_field()
    deleted_by: UUID | None = audit_user_field('删除人；与删除时间同时出现')
    flex_form: dict[str, Any] = flex_form_field('扩展字段；租户自定义字段，结构见动态表单定义；默认 {}')


class NtfNotification(SQLModel, table=True):
    """站内通知：一行为一次业务事件产生的一条通知。"""

    __tablename__ = "ntf_notification"
    __table_args__ = (
        Index("uk_ntf_notification_event_key", "event_key", unique=True),
        {'comment': '站内通知：一行为一次业务事件产生的一条通知。'},
    )

    id: UUID = id_field()
    org_id: UUID = org_field()
    scene_id: UUID = Field(foreign_key="ntf_scene.id", index=True, nullable=False, sa_column_kwargs={'comment': '通知场景'})
    scene_name_snapshot: str | None = Field(default=None, max_length=128, nullable=True, sa_column_kwargs={'comment': '场景名称；快照'})
    title: str = Field(max_length=256, nullable=False, sa_column_kwargs={'comment': '标题'})
    content: str | None = Field(default=None, sa_type=Text, nullable=True, sa_column_kwargs={'comment': '内容'})
    severity_code: str = Field(max_length=64, nullable=False, sa_column_kwargs={'comment': '重要程度；字典 ntf_severity'})
    status_code: str = Field(max_length=64, nullable=False, sa_column_kwargs={'comment': '状态；字典 ntf_notification_status'})
    source_module_code: str | None = Field(default=None, max_length=64, nullable=True, sa_column_kwargs={'comment': '来源模块；字典 sys_module'})
    business_type_code: str | None = Field(default=None, max_length=64, nullable=True, sa_column_kwargs={'comment': '业务类型；字典 wf_business_type'})
    business_id: UUID | None = Field(default=None, nullable=True, sa_column_kwargs={'comment': '业务单据；多态引用'})
    event_key: str | None = Field(default=None, max_length=128, nullable=True, sa_column_kwargs={'comment': '事件幂等键'})
    redirect_url: str | None = Field(default=None, max_length=1024, nullable=True, sa_column_kwargs={'comment': '跳转地址'})
    payload: Any | None = Field(default=None, sa_type=JSONB, nullable=True, sa_column_kwargs={'comment': '附加信息'})
    occurred_at: datetime = Field(sa_type=DateTime(timezone=True), nullable=False, sa_column_kwargs={'comment': '发生时间'})
    created_at: datetime = created_at_field()
    created_by: UUID | None = audit_user_field('创建人；系统任务创建时为空')
    updated_at: datetime = updated_at_field()
    updated_by: UUID | None = audit_user_field('修改人')
    flex_form: dict[str, Any] = flex_form_field('扩展字段；租户自定义字段，结构见动态表单定义；默认 {}')


class NtfRecipient(SQLModel, table=True):
    """通知接收人：一行为一条通知的一个接收人。"""

    __tablename__ = "ntf_recipient"
    __table_args__ = (
        Index("uk_ntf_recipient_notification_id_user_id", "notification_id", "user_id", unique=True),
        {'comment': '通知接收人：一行为一条通知的一个接收人。'},
    )

    id: UUID = id_field()
    org_id: UUID = org_field()
    notification_id: UUID = Field(foreign_key="ntf_notification.id", nullable=False, sa_column_kwargs={'comment': '通知'})
    user_id: UUID = Field(foreign_key="sys_user.id", index=True, nullable=False, sa_column_kwargs={'comment': '接收人'})
    status_code: str = Field(max_length=64, nullable=False, sa_column_kwargs={'comment': '阅读状态；字典 ntf_recipient_status'})
    read_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True), nullable=True, sa_column_kwargs={'comment': '阅读时间'})
    requires_confirmation: bool = bool_field('是否需要家长在小程序确认', default=False)
    confirmed_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True), nullable=True, sa_column_kwargs={'comment': '家长确认时间；打开消息不算确认'})
    confirm_due_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True), nullable=True, sa_column_kwargs={'comment': '最晚确认时间；超过后生成班主任电话联系任务'})
    created_at: datetime = created_at_field()
    created_by: UUID | None = audit_user_field('创建人；系统任务创建时为空')
    updated_at: datetime = updated_at_field()
    updated_by: UUID | None = audit_user_field('修改人')
    flex_form: dict[str, Any] = flex_form_field('扩展字段；租户自定义字段，结构见动态表单定义；默认 {}')


class NtfPreference(SQLModel, table=True):
    """通知偏好：一行为一个用户对一个场景一个渠道的偏好。"""

    __tablename__ = "ntf_preference"
    __table_args__ = (
        Index("uk_ntf_preference_user_id_scene_id_channel_code", "user_id", "scene_id", "channel_code", unique=True),
        {'comment': '通知偏好：一行为一个用户对一个场景一个渠道的偏好。'},
    )

    id: UUID = id_field()
    user_id: UUID = Field(foreign_key="sys_user.id", nullable=False, sa_column_kwargs={'comment': '用户'})
    scene_id: UUID = Field(foreign_key="ntf_scene.id", index=True, nullable=False, sa_column_kwargs={'comment': '通知场景'})
    channel_code: str = Field(max_length=64, nullable=False, sa_column_kwargs={'comment': '渠道；字典 ntf_channel'})
    is_enabled_by_user: bool = bool_field('是否接收', default=True)
    created_at: datetime = created_at_field()
    created_by: UUID | None = audit_user_field('创建人；系统任务创建时为空')
    updated_at: datetime = updated_at_field()
    updated_by: UUID | None = audit_user_field('修改人')
    flex_form: dict[str, Any] = flex_form_field('扩展字段；租户自定义字段，结构见动态表单定义；默认 {}')


class NtfChannelBinding(SQLModel, table=True):
    """通知渠道绑定：一行为一个用户在一个外部渠道的绑定。"""

    __tablename__ = "ntf_channel_binding"
    __table_args__ = (
        Index("uk_ntf_channel_binding_channel_code_provider_code_appid_externa", "channel_code", "provider_code", "appid", "external_user_no", unique=True, postgresql_where=text("deleted_at is null")),
        {'comment': '通知渠道绑定：一行为一个用户在一个外部渠道的绑定。'},
    )

    id: UUID = id_field()
    user_id: UUID = Field(foreign_key="sys_user.id", index=True, nullable=False, sa_column_kwargs={'comment': '用户'})
    channel_code: str = Field(max_length=64, nullable=False, sa_column_kwargs={'comment': '渠道；字典 ntf_channel'})
    provider_code: str = Field(max_length=64, nullable=False, sa_column_kwargs={'comment': '服务商；字典 ntf_provider'})
    appid: str = Field(max_length=128, nullable=False, sa_column_kwargs={'comment': '应用 ID'})
    external_user_no: str = Field(max_length=128, nullable=False, sa_column_kwargs={'comment': '外部用户标识；敏感：个人；如 openid'})
    unionid: str | None = Field(default=None, max_length=128, nullable=True, sa_column_kwargs={'comment': 'unionid；敏感：个人'})
    bound_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True), nullable=True, sa_column_kwargs={'comment': '绑定时间'})
    is_active: bool = bool_field('是否有效', default=True)
    created_at: datetime = created_at_field()
    created_by: UUID | None = audit_user_field('创建人；系统任务创建时为空')
    updated_at: datetime = updated_at_field()
    updated_by: UUID | None = audit_user_field('修改人')
    deleted_at: datetime | None = deleted_at_field()
    deleted_by: UUID | None = audit_user_field('删除人；与删除时间同时出现')
    flex_form: dict[str, Any] = flex_form_field('扩展字段；租户自定义字段，结构见动态表单定义；默认 {}')


class NtfDeliveryLog(SQLModel, table=True):
    """通知投递日志：一行为一次渠道投递尝试。"""

    __tablename__ = "ntf_delivery_log"
    __table_args__ = (
        {'comment': '通知投递日志：一行为一次渠道投递尝试。'},
    )

    id: UUID = id_field()
    org_id: UUID = org_field()
    recipient_id: UUID = Field(foreign_key="ntf_recipient.id", index=True, nullable=False, sa_column_kwargs={'comment': '通知接收人'})
    channel_code: str = Field(max_length=64, nullable=False, sa_column_kwargs={'comment': '渠道；字典 ntf_channel'})
    provider_code: str | None = Field(default=None, max_length=64, nullable=True, sa_column_kwargs={'comment': '服务商；字典 ntf_provider'})
    target_address: str | None = Field(default=None, max_length=255, nullable=True, sa_column_kwargs={'comment': '投递地址；敏感：个人；openid 或手机号'})
    status_code: str = Field(max_length=64, nullable=False, sa_column_kwargs={'comment': '投递状态；字典 ntf_delivery_status'})
    request_payload: Any | None = Field(default=None, sa_type=JSONB, nullable=True, sa_column_kwargs={'comment': '请求报文'})
    response_payload: Any | None = Field(default=None, sa_type=JSONB, nullable=True, sa_column_kwargs={'comment': '响应报文'})
    error_message: str | None = Field(default=None, sa_type=Text, nullable=True, sa_column_kwargs={'comment': '错误信息'})
    created_at: datetime = created_at_field()
    created_by: UUID | None = audit_user_field('创建人；系统任务创建时为空')


class NtfEventLog(SQLModel, table=True):
    """通知事件日志：一行为一次业务事件的处理记录。"""

    __tablename__ = "ntf_event_log"
    __table_args__ = (
        {'comment': '通知事件日志：一行为一次业务事件的处理记录。'},
    )

    id: UUID = id_field()
    org_id: UUID = org_field()
    scene_id: UUID | None = Field(default=None, foreign_key="ntf_scene.id", index=True, nullable=True, sa_column_kwargs={'comment': '通知场景'})
    business_type_code: str | None = Field(default=None, max_length=64, nullable=True, sa_column_kwargs={'comment': '业务类型；字典 wf_business_type'})
    business_id: UUID | None = Field(default=None, nullable=True, sa_column_kwargs={'comment': '业务单据；多态引用'})
    status_code: str = Field(max_length=64, nullable=False, sa_column_kwargs={'comment': '处理结果；字典 ntf_event_status'})
    message: str | None = Field(default=None, sa_type=Text, nullable=True, sa_column_kwargs={'comment': '说明'})
    payload: Any | None = Field(default=None, sa_type=JSONB, nullable=True, sa_column_kwargs={'comment': '事件内容'})
    created_at: datetime = created_at_field()
    created_by: UUID | None = audit_user_field('创建人；系统任务创建时为空')
