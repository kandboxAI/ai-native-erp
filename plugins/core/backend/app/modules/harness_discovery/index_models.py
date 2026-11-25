"""租户内审核元数据索引；仅保存定义与向量，不保存业务记录。"""
from datetime import datetime
from pgvector.sqlalchemy import Vector
from sqlalchemy import CheckConstraint, Column, Text, UniqueConstraint
from sqlmodel import Field, SQLModel

from app.framework.db.models import (
    UUID, audit_user_field, created_at_field, flex_form_field, id_field, updated_at_field,
)


class AiResourceBundle(SQLModel, table=True):
    __tablename__ = "ai_resource_bundle"
    __table_args__ = (
        UniqueConstraint("namespace", "revision", name="uk_ai_resource_bundle_namespace_revision"),
        CheckConstraint("dimensions > 0", name="dimensions"),
        {"comment": "AI 资源索引版本：一行为当前租户一个命名空间的一次元数据索引发布；不包含业务记录"},
    )
    # Tenant technical metadata has no business organization scope.
    id: UUID = id_field()
    namespace: str = Field(max_length=128, sa_column_kwargs={"comment": "服务端定义的资源目录命名空间"})
    revision: str = Field(max_length=64, sa_column_kwargs={"comment": "目录与向量模型身份的 SHA256 版本摘要"})
    model: str = Field(sa_column=Column(Text, nullable=False, comment="向量模型身份；包含接口、模型、维度和文本版本，不含密钥"))
    dimensions: int = Field(sa_column_kwargs={"comment": "向量维度；正整数"})
    created_at: datetime = created_at_field()
    created_by: UUID | None = audit_user_field("创建人；维护脚本执行时为空", ondelete="SET NULL")
    updated_at: datetime = updated_at_field()
    updated_by: UUID | None = audit_user_field("修改人", ondelete="SET NULL")
    flex_form: dict = flex_form_field()


class AiResourceDocument(SQLModel, table=True):
    __tablename__ = "ai_resource_document"
    __table_args__ = (
        UniqueConstraint("bundle_id", "document_key", name="uk_ai_resource_document_bundle_id_document_key"),
        {"comment": "AI 资源索引定义：一行为一个版本内的已审核表、接口或指标定义的向量；不包含业务记录"},
    )
    id: UUID = id_field()
    bundle_id: UUID = Field(foreign_key="ai_resource_bundle.id", ondelete="CASCADE", sa_column_kwargs={"comment": "所属索引版本；引用 ai_resource_bundle.id，命名空间和版本摘要由该版本取得"})
    document_key: str = Field(sa_column=Column(Text, nullable=False, comment="索引定义标识；资源、接口或指标的稳定标识，不是业务记录编号"))
    content_hash: str = Field(max_length=64, sa_column_kwargs={"comment": "审核定义的 SHA256 摘要；检索时与当前授权定义核对"})
    embedding: list[float] = Field(sa_column=Column(Vector(), nullable=False, comment="审核元数据的稠密向量；维度由所属索引版本记录"))
    created_at: datetime = created_at_field()
    created_by: UUID | None = audit_user_field("创建人；维护脚本执行时为空", ondelete="SET NULL")
    updated_at: datetime = updated_at_field()
    updated_by: UUID | None = audit_user_field("修改人", ondelete="SET NULL")
    flex_form: dict = flex_form_field()


class AiResourceActive(SQLModel, table=True):
    __tablename__ = "ai_resource_active"
    __table_args__ = (
        UniqueConstraint("namespace", name="uk_ai_resource_active_namespace"),
        {"comment": "AI 资源活动索引：一行为当前租户一个目录命名空间的活动版本指针；发布事务原子切换"},
    )
    id: UUID = id_field()
    namespace: str = Field(max_length=128, sa_column_kwargs={"comment": "服务端定义的资源目录命名空间；租户内唯一"})
    bundle_id: UUID = Field(foreign_key="ai_resource_bundle.id", ondelete="RESTRICT", index=True,
                            sa_column_kwargs={"comment": "活动索引版本；引用 ai_resource_bundle.id，发布事务内原子切换"})
    created_at: datetime = created_at_field()
    created_by: UUID | None = audit_user_field("创建人；维护脚本执行时为空", ondelete="SET NULL")
    updated_at: datetime = updated_at_field()
    updated_by: UUID | None = audit_user_field("修改人", ondelete="SET NULL")
    flex_form: dict = flex_form_field()
