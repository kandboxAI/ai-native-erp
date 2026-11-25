"""通知中心接口模型（字段名与数据库字段一致）。"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.db.pagination import PageParams
from app.framework.datetime_pydantic import CoerceDatetimeQueryMixin, DisplayDatetimeJsonMixin

# 取值来自字典：ntf_channel、ntf_severity、ntf_fallback_policy、ntf_target_type、ntf_route_org_scope
CHANNEL_IN_APP = "in_app"
CHANNEL_WECHAT_SERVICE = "wechat_service"
CHANNEL_WECHAT_MINIAPP_SUBSCRIBE = "wechat_miniapp_subscribe"
EXTERNAL_CHANNELS = (CHANNEL_WECHAT_SERVICE, CHANNEL_WECHAT_MINIAPP_SUBSCRIBE)
ROUTE_TARGET_TYPES = ("all", "role", "user", "permission", "actor")


# ───────── 场景配置 ─────────
class SceneChannelWrite(BaseModel):
    channel_code: str = Field(..., max_length=64)
    is_active: bool = True


class TemplateWrite(BaseModel):
    channel_code: str = Field(..., max_length=64)
    title_template: str | None = Field(default=None, max_length=512)
    content_template: str | None = None
    wechat_template_no: str | None = Field(default=None, max_length=128)
    data_mapping_config: dict[str, Any] | None = None
    is_active: bool = True


class RouteWrite(BaseModel):
    target_type_code: str = Field(..., max_length=64)
    role_id: UUID | None = None
    user_id: UUID | None = None
    permission_id: UUID | None = None
    permission_key: str | None = Field(default=None, max_length=128, description="可代替 permission_id")
    actor_key: str | None = Field(default=None, max_length=128)
    org_scope_code: str = Field(default="none", max_length=64)
    is_active: bool = True

    @model_validator(mode="after")
    def _check_target(self):
        kind = self.target_type_code
        if kind not in ROUTE_TARGET_TYPES:
            raise ValueError("无效的接收对象类型")
        if kind == "role" and self.role_id is None:
            raise ValueError("请选择接收角色")
        if kind == "user" and self.user_id is None:
            raise ValueError("请选择接收用户")
        if kind == "permission" and self.permission_id is None and not (self.permission_key or "").strip():
            raise ValueError("请选择接收权限")
        if kind == "actor" and not (self.actor_key or "").strip():
            raise ValueError("请填写业务相关人标识")
        return self


class SceneBase(BaseModel):
    scene_key: str = Field(..., max_length=128)
    scene_name: str = Field(..., max_length=128)
    module_code: str = Field(..., max_length=64)
    description: str | None = None
    severity_code: str = Field(default="normal", max_length=64)
    fallback_policy_code: str = Field(default="none", max_length=64)
    is_active: bool = True


class SceneCreate(SceneBase):
    channels: list[SceneChannelWrite] = Field(default_factory=lambda: [SceneChannelWrite(channel_code=CHANNEL_IN_APP)])
    templates: list[TemplateWrite] = Field(default_factory=list)
    routes: list[RouteWrite] = Field(default_factory=list)


class SceneUpdate(BaseModel):
    scene_key: str | None = Field(default=None, max_length=128)
    scene_name: str | None = Field(default=None, max_length=128)
    module_code: str | None = Field(default=None, max_length=64)
    description: str | None = None
    severity_code: str | None = Field(default=None, max_length=64)
    fallback_policy_code: str | None = Field(default=None, max_length=64)
    is_active: bool | None = None
    channels: list[SceneChannelWrite] | None = None
    templates: list[TemplateWrite] | None = None
    routes: list[RouteWrite] | None = None


class SceneListQuery(PageParams):
    module_code: str | None = None
    is_active: bool | None = None


class SceneItem(DisplayDatetimeJsonMixin, SceneBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    channel_codes: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
    created_by: UUID | None = None
    updated_by: UUID | None = None


class SceneChannelItem(SceneChannelWrite):
    model_config = ConfigDict(from_attributes=True)

    id: UUID


class TemplateItem(TemplateWrite):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    scene_id: UUID


class RouteItem(BaseModel):
    id: UUID
    scene_id: UUID
    target_type_code: str
    role_id: UUID | None = None
    user_id: UUID | None = None
    permission_id: UUID | None = None
    actor_key: str | None = None
    org_scope_code: str
    is_active: bool
    role: dict[str, Any] | None = None
    user: dict[str, Any] | None = None
    permission: dict[str, Any] | None = None


class SceneConfig(BaseModel):
    scene: SceneItem
    channels: list[SceneChannelItem] = Field(default_factory=list)
    templates: list[TemplateItem] = Field(default_factory=list)
    routes: list[RouteItem] = Field(default_factory=list)


# ───────── 发送 ─────────
class PublishPayload(BaseModel):
    """接口发送通知（需 notification_center:publish）；业务代码请直接调用 service.notify。"""

    scene_key: str = Field(..., max_length=128)
    recipients: list[UUID] = Field(default_factory=list, description="直接指定的接收人 sys_user.id")
    actors: dict[str, list[UUID]] = Field(default_factory=dict, description="业务相关人：actor_key → sys_user.id 列表")
    business_type_code: str | None = Field(default=None, max_length=64)
    business_id: UUID | None = None
    event_key: str | None = Field(default=None, max_length=128)
    org_id: UUID | None = None
    redirect_url: str | None = Field(default=None, max_length=1024)
    payload: dict[str, Any] = Field(default_factory=dict)


class NotifyResult(BaseModel):
    notification_id: UUID | None = None
    created: bool = False
    recipient_count: int = 0
    delivery_count: int = 0
    skipped_reason: str | None = None


class DeliveryProcessResult(BaseModel):
    scanned_count: int = 0
    sent_count: int = 0
    failed_count: int = 0
    skipped_count: int = 0


# ───────── 查询 ─────────
class MineListQuery(BaseModel):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=10, ge=1, le=100)
    status_code: Literal["all", "unread", "read", "archived"] = "all"
    scene_key: str | None = Field(default=None, max_length=128)


class MineItem(DisplayDatetimeJsonMixin):
    requires_individual_read: bool = False
    targets: dict[str, str] = Field(default_factory=dict)
    __display_datetime_fields__ = ("occurred_at", "read_at", "created_at", "confirmed_at")

    recipient_id: UUID
    notification_id: UUID
    scene_key: str | None = None
    scene_name_snapshot: str | None = None
    title: str
    content: str | None = None
    severity_code: str
    status_code: str
    read_at: datetime | None = None
    requires_confirmation: bool = False
    confirmed_at: datetime | None = None
    business_type_code: str | None = None
    business_id: UUID | None = None
    redirect_url: str | None = None
    occurred_at: datetime | None = None
    created_at: datetime


class HistoryListQuery(CoerceDatetimeQueryMixin):
    __coerce_datetime_fields__ = ("occurred_start", "occurred_end")

    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=10, ge=1, le=100)
    keyword: str | None = Field(default=None, max_length=128)
    scene_id: UUID | None = None
    business_type_code: str | None = Field(default=None, max_length=64)
    severity_code: str | None = Field(default=None, max_length=64)
    status_code: str | None = Field(default=None, max_length=64)
    occurred_start: datetime | None = None
    occurred_end: datetime | None = None


class HistoryItem(DisplayDatetimeJsonMixin):
    __display_datetime_fields__ = ("occurred_at", "created_at")

    id: UUID
    org_id: UUID
    scene_id: UUID
    scene_key: str | None = None
    scene_name_snapshot: str | None = None
    title: str
    content: str | None = None
    severity_code: str
    status_code: str
    source_module_code: str | None = None
    business_type_code: str | None = None
    business_id: UUID | None = None
    event_key: str | None = None
    redirect_url: str | None = None
    recipient_count: int = 0
    read_count: int = 0
    unread_count: int = 0
    delivery_stats: dict[str, dict[str, int]] = Field(default_factory=dict, description="渠道 → 状态 → 数量")
    occurred_at: datetime | None = None
    created_at: datetime


class RecipientListQuery(BaseModel):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)
    status_code: Literal["all", "unread", "read", "archived"] = "all"


class RecipientItem(DisplayDatetimeJsonMixin):
    __display_datetime_fields__ = ("read_at", "created_at")

    id: UUID
    user_id: UUID
    display_name: str | None = None
    status_code: str
    read_at: datetime | None = None
    created_at: datetime


class DeliveryLogListQuery(CoerceDatetimeQueryMixin):
    __coerce_datetime_fields__ = ("created_start", "created_end")

    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=10, ge=1, le=100)
    keyword: str | None = Field(default=None, max_length=128)
    notification_id: UUID | None = None
    scene_id: UUID | None = None
    channel_code: str | None = Field(default=None, max_length=64)
    status_code: str | None = Field(default=None, max_length=64)
    provider_code: str | None = Field(default=None, max_length=64)
    created_start: datetime | None = None
    created_end: datetime | None = None


class DeliveryLogItem(DisplayDatetimeJsonMixin):
    id: UUID
    recipient_id: UUID
    notification_id: UUID | None = None
    scene_key: str | None = None
    title: str | None = None
    user_id: UUID | None = None
    display_name: str | None = None
    channel_code: str
    provider_code: str | None = None
    target_address: str | None = None
    status_code: str
    request_payload: Any | None = None
    response_payload: Any | None = None
    error_message: str | None = None
    created_at: datetime

    __display_datetime_fields__ = ("created_at",)


class EventLogListQuery(CoerceDatetimeQueryMixin):
    __coerce_datetime_fields__ = ("created_start", "created_end")

    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=10, ge=1, le=100)
    keyword: str | None = Field(default=None, max_length=128)
    scene_id: UUID | None = None
    business_type_code: str | None = Field(default=None, max_length=64)
    status_code: str | None = Field(default=None, max_length=64)
    created_start: datetime | None = None
    created_end: datetime | None = None


class EventLogItem(DisplayDatetimeJsonMixin):
    __display_datetime_fields__ = ("created_at",)

    id: UUID
    scene_id: UUID | None = None
    scene_key: str | None = None
    business_type_code: str | None = None
    business_id: UUID | None = None
    status_code: str
    message: str | None = None
    payload: Any | None = None
    created_at: datetime


# ───────── 偏好与渠道绑定 ─────────
class PreferenceItem(BaseModel):
    scene_id: UUID
    scene_key: str
    scene_name: str
    module_code: str
    channel_code: str
    is_enabled_by_user: bool = True


class PreferenceWrite(BaseModel):
    scene_id: UUID
    channel_code: str = Field(..., max_length=64)
    is_enabled_by_user: bool


class ChannelBindingCreate(BaseModel):
    channel_code: str = Field(default=CHANNEL_WECHAT_SERVICE, max_length=64)
    provider_code: str = Field(default="wechat", max_length=64)
    appid: str = Field(..., max_length=128)
    external_user_no: str = Field(..., max_length=128)
    unionid: str | None = Field(default=None, max_length=128)

    @model_validator(mode="after")
    def _check_channel(self):
        if self.channel_code not in EXTERNAL_CHANNELS:
            raise ValueError("仅支持绑定服务号或小程序订阅消息渠道")
        return self


class ChannelBindingItem(DisplayDatetimeJsonMixin):
    __display_datetime_fields__ = ("bound_at", "created_at", "updated_at")
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    channel_code: str
    provider_code: str
    appid: str
    external_user_no: str
    unionid: str | None = None
    bound_at: datetime | None = None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class WechatServiceBindUrlData(BaseModel):
    authorize_url: str
    expires_in: int


class WechatServiceBindingStatusData(BaseModel):
    bound: bool
    subscribed: bool | None = None
    needs_bind: bool = False
    needs_follow: bool = False


class WechatServiceBindCallbackResult(BaseModel):
    bound: bool = True
    message: str = "服务号通知绑定成功"
    redirect_url: str | None = None
