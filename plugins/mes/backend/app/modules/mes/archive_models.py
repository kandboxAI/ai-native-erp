"""制造档案；停用只影响新引用，已有工单保留提交时快照。"""
from datetime import datetime
from typing import Any
from uuid import UUID
from sqlalchemy import Index, Text, text
from sqlmodel import Field, SQLModel
from app.framework.db.models import (id_field, org_field, audit_user_field, created_at_field,
    updated_at_field, deleted_at_field, flex_form_field, bool_field)


class ArchiveFields(SQLModel):
    id: UUID = id_field()
    org_id: UUID = org_field(ondelete="RESTRICT")
    description: str | None = Field(default=None, sa_type=Text, sa_column_kwargs={"comment": "档案说明；自由文本，默认不发布到 AI"})
    sort_no: int = Field(default=0, sa_column_kwargs={"comment": "显示顺序；数值小的在前"})
    is_active: bool = bool_field("是否启用；停用不修改历史引用", default=True)
    version_no: int = Field(default=1, sa_column_kwargs={"comment": "修订号；并发更新校验"})
    created_at: datetime = created_at_field()
    created_by: UUID | None = audit_user_field("创建人", ondelete="SET NULL")
    updated_at: datetime = updated_at_field()
    updated_by: UUID | None = audit_user_field("修改人", ondelete="SET NULL")
    deleted_at: datetime | None = deleted_at_field()
    deleted_by: UUID | None = audit_user_field("删除人", ondelete="SET NULL")
    flex_form: dict[str, Any] = flex_form_field()


class MesCustomer(ArchiveFields, table=True):
    __tablename__ = "mes_customer"
    __table_args__ = (Index("uk_mes_customer_org_id_customer_no", "org_id", "customer_no", unique=True, postgresql_where=text("deleted_at is null")),
        {"comment": "制造客户档案；一行代表组织内一个业务客户代号，不保存真实身份或私人联系方式。"})
    customer_no: str = Field(max_length=64, sa_column_kwargs={"comment": "客户编号；组织内唯一，创建后不可变"})
    customer_name: str = Field(max_length=128, sa_column_kwargs={"comment": "业务显示简称；不得填写客户真实身份机密"})
    reconciliation_mode_code: str = Field(default="by_item", max_length=64, sa_column_kwargs={"comment": "对账展示方式；字典 mes_reconciliation_mode；当前对账仍以本司已出货数量为准"})


class MesProjectStage(ArchiveFields, table=True):
    __tablename__ = "mes_project_stage"
    __table_args__ = (Index("uk_mes_project_stage_org_id_stage_no", "org_id", "stage_no", unique=True, postgresql_where=text("deleted_at is null")),
        {"comment": "制造项目阶段；一行代表组织内一个工艺归类阶段，顺序用于项目进度分组。"})
    stage_no: str = Field(max_length=64, sa_column_kwargs={"comment": "阶段编号；组织内唯一，创建后不可变"})
    stage_name: str = Field(max_length=128, sa_column_kwargs={"comment": "阶段名称"})


class MesProcessRequirement(ArchiveFields, table=True):
    __tablename__ = "mes_process_requirement"
    __table_args__ = (Index("uk_mes_process_requirement_org_id_requirement_no", "org_id", "requirement_no", unique=True, postgresql_where=text("deleted_at is null")),
        {"comment": "制造工艺要求；一行代表可供工艺或路线复用的一项操作要求及定价说明。"})
    requirement_no: str = Field(max_length=64, sa_column_kwargs={"comment": "要求编号；组织内唯一，创建后不可变"})
    requirement_name: str = Field(max_length=128, sa_column_kwargs={"comment": "工艺要求名称"})
    pricing_description: str | None = Field(default=None, sa_type=Text, sa_column_kwargs={"comment": "定价标准说明；仅供人工参考，不自动计价；商业机密，默认不进入 AI"})


class MesProcess(ArchiveFields, table=True):
    __tablename__ = "mes_process"
    __table_args__ = (Index("uk_mes_process_org_id_process_no", "org_id", "process_no", unique=True, postgresql_where=text("deleted_at is null")),
        {"comment": "制造工艺档案；一行代表组织内可复用的一道加工工艺，不是工单执行事实。"})
    process_no: str = Field(max_length=64, sa_column_kwargs={"comment": "工艺编号；组织内唯一，创建后不可变"})
    process_name: str = Field(max_length=128, sa_column_kwargs={"comment": "工艺名称"})
    project_stage_id: UUID | None = Field(default=None, foreign_key="mes_project_stage.id", ondelete="RESTRICT", sa_column_kwargs={"comment": "所属项目阶段；引用本组织阶段档案"})
    requirement_id: UUID | None = Field(default=None, foreign_key="mes_process_requirement.id", ondelete="RESTRICT", sa_column_kwargs={"comment": "默认工艺要求；引用本组织要求档案"})
    processing_type_code: str = Field(default="in_house", max_length=64, sa_column_kwargs={"comment": "加工类型；字典 mes_processing_type；委外标记不代表已接入委外业务"})
    is_piecework: bool = bool_field("是否计件工艺；供档案标记，当前不生成工资", default=False)
    is_quality_required: bool = bool_field("是否需要工序检验；选用时复制到工单", default=False)
    is_equipment_required: bool | None = Field(default=None, sa_column_kwargs={"comment": "是否占用本厂机器；空为工程待确认，不根据工艺名称或已有设备关联猜测"})
    execution_kind_code: str | None = Field(default=None,max_length=64,sa_column_kwargs={"comment":"工艺执行类别；字典 mes_schedule_execution_kind；检验必须明确为检验工艺，空为待工程确认"})


class MesProcessDependency(ArchiveFields, table=True):
    __tablename__ = "mes_process_dependency"
    __table_args__ = (Index("uk_mes_process_dependency_process_id_previous_process_id", "process_id", "previous_process_id", unique=True, postgresql_where=text("deleted_at is null")),
        {"comment": "制造工艺前置关系；一行代表一道工艺的一项前置工艺，禁止自引用及循环。"})
    process_id: UUID = Field(foreign_key="mes_process.id", ondelete="RESTRICT", sa_column_kwargs={"comment": "后置工艺；本组织工艺档案"})
    previous_process_id: UUID = Field(foreign_key="mes_process.id", ondelete="RESTRICT", sa_column_kwargs={"comment": "前置工艺；本组织工艺档案"})


class MesEquipment(ArchiveFields, table=True):
    __tablename__ = "mes_equipment"
    __table_args__ = (Index("uk_mes_equipment_org_id_equipment_no", "org_id", "equipment_no", unique=True, postgresql_where=text("deleted_at is null")),
        {"comment": "制造设备档案；一行代表一台可选的生产设备，不承担资产财务或设备遥测。"})
    equipment_no: str = Field(max_length=64, sa_column_kwargs={"comment": "设备编号；组织内唯一，创建后不可变"})
    equipment_name: str = Field(max_length=128, sa_column_kwargs={"comment": "设备名称"})
    process_id: UUID | None = Field(default=None, foreign_key="mes_process.id", ondelete="RESTRICT", sa_column_kwargs={"comment": "所属工艺；引用同组织工艺档案"})
    work_center_name: str | None = Field(default=None, max_length=128, sa_column_kwargs={"comment": "所属工作中心名称；尚无工作中心主数据模型"})


class MesEquipmentProcess(ArchiveFields, table=True):
    __tablename__ = "mes_equipment_process"
    __table_args__ = (Index("uk_mes_equipment_process_equipment_id_process_id", "equipment_id", "process_id",
        unique=True, postgresql_where=text("deleted_at is null")),
        {"comment": "制造设备适用工艺；一行代表同组织一台设备可执行的一种工艺，不重复建立物理设备。"})
    equipment_id: UUID = Field(foreign_key="mes_equipment.id", ondelete="RESTRICT", sa_column_kwargs={"comment": "适用设备；引用同组织设备档案"})
    process_id: UUID = Field(foreign_key="mes_process.id", ondelete="RESTRICT", sa_column_kwargs={"comment": "设备可执行工艺；引用同组织工艺档案"})
