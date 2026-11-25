"""表模型（audit_operation_log）。

初始版本由 docs/foundation-platform/data-dictionary/tools/gen_models.py 按数据字典生成，之后以本文件为准维护。
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import Index, Text
from sqlmodel import Field, SQLModel

from app.framework.db.models import (
    audit_user_field,
    bool_field,
    created_at_field,
    id_field,
    org_field,
)


class AuditOperationLog(SQLModel, table=True):
    """操作日志：一行为一次操作或已登记敏感数据访问；仅保存安全元数据。"""

    __tablename__ = "audit_operation_log"
    __table_args__ = (
        Index("idx_audit_operation_log_is_sensitive_created_at", "is_sensitive", "created_at"),
        {'comment': '操作日志：一行为一次操作或敏感数据查看、导出请求。只追加，不可修改、删除；敏感请求记录不保存业务原文。'},
    )

    id: UUID = id_field()
    org_id: UUID = org_field()
    module_code: str = Field(max_length=64, nullable=False, sa_column_kwargs={'comment': '模块；字典 sys_module'})
    action_code: str = Field(max_length=64, nullable=False, sa_column_kwargs={'comment': '操作类型；字典 audit_action'})
    target_type_code: str | None = Field(default=None, max_length=64, nullable=True, sa_column_kwargs={'comment': '操作对象类型；字典 audit_target_type'})
    target_id: UUID | None = Field(default=None, nullable=True, sa_column_kwargs={'comment': '操作对象；多态引用'})
    actor_user_id: UUID | None = Field(default=None, foreign_key="sys_user.id", index=True, nullable=True, sa_column_kwargs={'comment': '操作人'})
    is_agent_action: bool = bool_field('是否智能体代为操作', default=False)
    is_sensitive: bool = bool_field("是否为已登记的敏感数据操作", default=False)
    request_id: UUID | None = Field(default=None, nullable=True, sa_column_kwargs={"comment": "本次 HTTP 请求审计关联标识；服务端生成；非业务外键"})
    request_method: str | None = Field(default=None, max_length=8, nullable=True, sa_column_kwargs={"comment": "HTTP 请求方法"})
    request_path: str | None = Field(default=None, max_length=512, nullable=True, sa_column_kwargs={"comment": "HTTP 路由模板；不含查询参数、业务值或令牌"})
    http_status: int | None = Field(default=None, nullable=True, sa_column_kwargs={"comment": "HTTP 响应状态；不等同于客户端已完成下载"})
    content: str | None = Field(default=None, sa_type=Text, nullable=True, sa_column_kwargs={'comment': '操作摘要'})
    ip_address: str | None = Field(default=None, max_length=64, nullable=True, sa_column_kwargs={'comment': 'IP 地址；敏感：个人'})
    created_at: datetime = created_at_field()
    created_by: UUID | None = audit_user_field('创建人；系统任务创建时为空')
