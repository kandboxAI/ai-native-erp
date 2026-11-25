"""表模型（int_outbox_event）。

初始版本由 docs/foundation-platform/data-dictionary/tools/gen_models.py 按数据字典生成，之后以本文件为准维护。
"""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import DateTime, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel

from app.framework.db.models import (
    audit_user_field,
    created_at_field,
    flex_form_field,
    id_field,
    updated_at_field,
)


class IntOutboxEvent(SQLModel, table=True):
    """事件出站：一行为一个待发送或已发送的领域事件。"""

    __tablename__ = "int_outbox_event"
    __table_args__ = (
        {'comment': '事件出站：一行为一个待发送或已发送的领域事件。事务内写入，再由后台投递；通知、待办、智能体触发都从这里获取事件。'},
    )

    id: UUID = id_field()
    producer_module_code: str = Field(max_length=64, nullable=False, sa_column_kwargs={'comment': '生产模块；字典 sys_module'})
    event_type_code: str = Field(max_length=64, nullable=False, sa_column_kwargs={'comment': '事件类型；字典 int_event_type'})
    exchange: str = Field(max_length=128, nullable=False, sa_column_kwargs={'comment': '交换机'})
    routing_key: str = Field(max_length=128, nullable=False, sa_column_kwargs={'comment': '路由键'})
    payload: Any = Field(sa_type=JSONB, nullable=False, sa_column_kwargs={'comment': '事件内容'})
    header_meta: Any | None = Field(default=None, sa_type=JSONB, nullable=True, sa_column_kwargs={'comment': '报文头'})
    status_code: str = Field(max_length=64, nullable=False, sa_column_kwargs={'comment': '状态；字典 int_outbox_status'})
    retry_count: int = Field(default=0, nullable=False, sa_column_kwargs={"server_default": text("0"), "comment": '已重试次数'})
    max_retries: int = Field(nullable=False, sa_column_kwargs={'comment': '最多重试次数'})
    next_attempt_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True), nullable=True, sa_column_kwargs={'comment': '下次尝试时间'})
    last_error: str | None = Field(default=None, sa_type=Text, nullable=True, sa_column_kwargs={'comment': '最近错误'})
    published_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True), nullable=True, sa_column_kwargs={'comment': '发送时间'})
    created_at: datetime = created_at_field()
    created_by: UUID | None = audit_user_field('创建人；系统任务创建时为空')
    updated_at: datetime = updated_at_field()
    updated_by: UUID | None = audit_user_field('修改人')
    flex_form: dict[str, Any] = flex_form_field('扩展字段；租户自定义字段，结构见动态表单定义；默认 {}')
