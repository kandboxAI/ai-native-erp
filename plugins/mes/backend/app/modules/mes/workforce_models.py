"""制造生产人员身份及有效期工艺资格；自然人复用 L1，资格不代表登录授权。"""
from datetime import datetime
from uuid import UUID
from sqlalchemy import CheckConstraint, DateTime, Index, text
from sqlmodel import Field
from app.framework.db.models import org_field
from .archive_models import ArchiveFields


class MesProductionPerson(ArchiveFields, table=True):
    __tablename__ = "mes_production_person"
    __table_args__ = (
        Index("uk_mes_production_person_org_id_person_no", "org_id", "person_no", unique=True, postgresql_where=text("deleted_at is null")),
        Index("uk_mes_production_person_org_id_party_id", "org_id", "party_id", unique=True, postgresql_where=text("deleted_at is null")),
        {"comment": "制造生产人员身份；一行代表一名自然人在组织内的生产资源身份，不是登录账号或独立人员主档。"},
    )
    org_id: UUID = org_field(index=False, ondelete="RESTRICT")
    party_id: UUID = Field(foreign_key="md_person.party_id", ondelete="RESTRICT", sa_column_kwargs={"comment": "自然人；引用 L1 人员主数据，姓名及可空账号关联由主数据维护"})
    person_no: str = Field(max_length=64, sa_column_kwargs={"comment": "生产人员编号；组织内唯一，导入时可生成明确的临时编号，不冒充真实员工号"})
    job_title_snapshot: str | None = Field(default=None, max_length=128, sa_column_kwargs={"comment": "客户清单登记时的职务文本；不是系统岗位或权限，原清单无内部岗位外键"})


class MesPersonProcess(ArchiveFields, table=True):
    __tablename__ = "mes_person_process"
    __table_args__ = (
        # 依规范缩写索引列名部分 production_person_id 为 person_id，避免超过63字节。
        Index("uk_mes_person_process_person_id_process_id_valid_from", "production_person_id", "process_id", "valid_from", unique=True, postgresql_where=text("deleted_at is null")),
        CheckConstraint("valid_to IS NULL OR valid_to > valid_from", name="ck_mes_person_process_valid_period"),
        {"comment": "制造人员工艺资格；一行代表同组织一名生产人员在左闭右开有效期内经确认的一项工艺能力，不代替操作权限。"},
    )
    production_person_id: UUID = Field(foreign_key="mes_production_person.id", ondelete="RESTRICT", sa_column_kwargs={"comment": "生产人员身份；引用同组织生产人员，跨组织资源占用按其自然人统一校验"})
    process_id: UUID = Field(foreign_key="mes_process.id", ondelete="RESTRICT", sa_column_kwargs={"comment": "经客户确认可承担的工艺；引用同组织工艺档案"})
    valid_from: datetime = Field(sa_type=DateTime(timezone=True), sa_column_kwargs={"comment": "资格生效时间；左闭端，使用带时区时间；导入自登记时生效，不倒推历史"})
    valid_to: datetime | None = Field(default=None, sa_type=DateTime(timezone=True), sa_column_kwargs={"comment": "资格失效时间；右开端，空表示持续有效"})
