"""图纸修订及其文件清单：只追加，复用 L1 文件存储。"""
from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, Index, Text
from sqlmodel import Field, SQLModel

from app.framework.db.models import audit_user_field, created_at_field, id_field, org_field


class MesWorkOrderDrawingRevision(SQLModel, table=True):
    __tablename__ = "mes_work_order_drawing_revision"
    __table_args__ = (
        Index("uk_mes_work_order_drawing_revision_work_order_id_revision_no", "work_order_id", "revision_no", unique=True),
        CheckConstraint("revision_no > 0", name="ck_mes_work_order_drawing_revision_positive_revision"),
        {"comment": "MES 工单图纸修订；一行代表一次保存的完整图纸版本，只追加，最新修订生效。"},
    )
    id: UUID = id_field()
    org_id: UUID = org_field(index=False, ondelete="RESTRICT")
    work_order_id: UUID = Field(foreign_key="mes_work_order.id", ondelete="RESTRICT", nullable=False, sa_column_kwargs={"comment": "所属货品执行工单；权限及组织范围跟随父工单"})
    revision_no: int = Field(nullable=False, sa_column_kwargs={"comment": "系统修订序号；从1递增，显示为V1、V2；父工单锁内生成"})
    revision_label: str | None = Field(default=None, max_length=128, sa_column_kwargs={"comment": "本修订文件自身的图纸版次，如A/B；选填，不自动推断"})
    change_note: str = Field(sa_type=Text, nullable=False, sa_column_kwargs={"comment": "本次变更说明；自由文本不进入AI；原有附件归档时明确记录来源"})
    created_at: datetime = created_at_field()
    created_by: UUID | None = audit_user_field("修订保存人；原有附件归档时为归档人，不冒充历史上传人", ondelete="RESTRICT")


class MesWorkOrderDrawingFile(SQLModel, table=True):
    __tablename__ = "mes_work_order_drawing_file"
    __table_args__ = (
        Index("uk_mes_work_order_drawing_file_revision_id_attachment_id", "revision_id", "attachment_id", unique=True),
        CheckConstraint("sort_no >= 0", name="ck_mes_work_order_drawing_file_nonnegative_sort"),
        {"comment": "MES 图纸修订文件清单；一行关联一个不可变附件，可在后续修订沿用，不复制或删除文件本体。"},
    )
    id: UUID = id_field()
    org_id: UUID = org_field(index=False, ondelete="RESTRICT")
    revision_id: UUID = Field(foreign_key="mes_work_order_drawing_revision.id", ondelete="RESTRICT", nullable=False, sa_column_kwargs={"comment": "所属图纸修订；只追加的文件清单"})
    attachment_id: UUID = Field(foreign_key="file_attachment.id", ondelete="RESTRICT", nullable=False, sa_column_kwargs={"comment": "L1已绑定附件；沿用时复用ID，下载仍校验父工单权限"})
    sort_no: int = Field(nullable=False, sa_column_kwargs={"comment": "修订内文件显示顺序；从0开始"})
    created_at: datetime = created_at_field()
    created_by: UUID | None = audit_user_field("本次修订清单记录人", ondelete="RESTRICT")
