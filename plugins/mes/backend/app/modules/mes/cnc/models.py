"""MES 询价模型；工序和规则为关系明细，历史核价输入为不可变快照。"""

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, Index, Numeric, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel
from app.framework.db.models import (
    id_field,
    org_field,
    created_at_field,
    updated_at_field,
    audit_user_field,
    deleted_at_field,
    flex_form_field,
)


class CncPart(SQLModel, table=True):
    __tablename__ = "mes_cnc_part"
    __table_args__ = (
        CheckConstraint("quantity > 0 and version_no > 0", name="positive_quantity_version"),
        {"comment": "一行代表一个组织中的询价零件及当前制造要求"},
    )
    id: UUID = id_field()
    org_id: UUID = org_field(ondelete="RESTRICT")
    created_at: datetime = created_at_field()
    created_by: UUID | None = audit_user_field("创建人；租户用户", ondelete="RESTRICT")
    updated_at: datetime = updated_at_field()
    updated_by: UUID | None = audit_user_field("修改人；租户用户", ondelete="RESTRICT")
    flex_form: dict[str, Any] = flex_form_field()
    name: str = Field(default="", max_length=200, sa_column_kwargs={"comment": "询价零件名称"})
    quantity: int = Field(default=1, sa_column_kwargs={"comment": "询价数量；件"})
    version_no: int = Field(default=1, sa_column_kwargs={"comment": "乐观锁版本；每次依据变更递增"})
    material: str = Field(default="", max_length=200, sa_column_kwargs={"comment": "材料牌号"})
    treatment: str = Field(default="", max_length=500, sa_column_kwargs={"comment": "处理要求"})
    hardness: str = Field(default="", max_length=200, sa_column_kwargs={"comment": "硬度要求"})
    tolerance: str = Field(default="", max_length=500, sa_column_kwargs={"comment": "公差要求"})
    notes: str = Field(
        default="", max_length=10000, sa_column_kwargs={"comment": "制造要求备注；内部信息不自动发布 AI"}
    )
    stock_length: Decimal | None = Field(
        default=None, sa_type=Numeric(18, 6), sa_column_kwargs={"comment": "毛坯长；mm"}
    )
    stock_width: Decimal | None = Field(
        default=None, sa_type=Numeric(18, 6), sa_column_kwargs={"comment": "毛坯宽；mm"}
    )
    stock_height: Decimal | None = Field(
        default=None, sa_type=Numeric(18, 6), sa_column_kwargs={"comment": "毛坯高；mm"}
    )
    density: Decimal | None = Field(
        default=None, sa_type=Numeric(18, 6), sa_column_kwargs={"comment": "密度；g/cm³"}
    )
    material_billing_length: Decimal | None = Field(
        default=None, sa_type=Numeric(18, 6), sa_column_kwargs={"comment": "材料计费长度；mm/件"}
    )
    material_price: Decimal | None = Field(
        default=None, sa_type=Numeric(18, 2), sa_column_kwargs={"comment": "材料参考单价；元/kg 或元/mm"}
    )
    external_unit_cost: Decimal = Field(
        default=Decimal("0"), sa_type=Numeric(18, 2), sa_column_kwargs={"comment": "其他外协费；元/件"}
    )
    other_batch_cost: Decimal = Field(
        default=Decimal("0"), sa_type=Numeric(18, 2), sa_column_kwargs={"comment": "其他批次费；元"}
    )
    material_rule_no: str | None = Field(
        default=None,
        max_length=60,
        sa_column_kwargs={"comment": "选用材料规则的业务编号；历史版本按来源快照解释，非内部 UUID"},
    )
    material_price_unit_code: str = Field(
        default="kg",
        max_length=20,
        sa_column_kwargs={"comment": "字典 mes_cnc_material_price_unit；材料计价单位"},
    )
    is_requirements_confirmed: bool = Field(
        default=False, sa_column_kwargs={"comment": "是否已人工确认制造要求及核价依据"}
    )
    parameter_sources: dict = Field(
        default_factory=dict,
        sa_type=JSONB,
        sa_column_kwargs={"comment": "材料及毛坯参数来源快照；字段名到规则编号、版本、当时值的映射"},
    )
    analysis: dict = Field(
        default_factory=dict,
        sa_type=JSONB,
        sa_column_kwargs={
            "comment": "解析结果；documents、geometry、ocr、ai、draft、pricing 的版本化证据结构；不进入通用 AI 目录"
        },
    )
    deleted_at: datetime | None = deleted_at_field()
    deleted_by: UUID | None = audit_user_field("删除人；租户用户", ondelete="RESTRICT")


class CncAnalysisJob(SQLModel, table=True):
    __tablename__ = "mes_cnc_analysis_job"
    __table_args__ = (
        Index(
            "uk_mes_cnc_analysis_job_active_part",
            "part_id",
            unique=True,
            postgresql_where=text("status_code in ('queued', 'running')"),
        ),
        Index("idx_mes_cnc_analysis_job_status_code_created_at", "status_code", "created_at"),
        {"comment": "一行代表一次用户明确请求的图纸解析任务"},
    )
    id: UUID = id_field()
    org_id: UUID = org_field(ondelete="RESTRICT")
    created_at: datetime = created_at_field()
    created_by: UUID | None = audit_user_field("创建人；租户用户", ondelete="RESTRICT")
    updated_at: datetime = updated_at_field()
    updated_by: UUID | None = audit_user_field("修改人；租户用户", ondelete="RESTRICT")
    flex_form: dict[str, Any] = flex_form_field()
    part_id: UUID = Field(
        foreign_key="mes_cnc_part.id", ondelete="RESTRICT", sa_column_kwargs={"comment": "所属询价零件"}
    )
    auth_user_id: UUID = Field(
        foreign_key="public.auth_user.id",
        ondelete="RESTRICT",
        sa_column_kwargs={"comment": "申请人的认证身份；执行前经认证 Service 重建当前租户权限"},
    )
    status_code: str = Field(
        default="queued", max_length=20, sa_column_kwargs={"comment": "字典 mes_cnc_job_status；解析任务状态"}
    )
    stage: str = Field(default="等待解析", max_length=200, sa_column_kwargs={"comment": "当前解析阶段"})
    error: str | None = Field(default=None, max_length=2000, sa_column_kwargs={"comment": "脱敏错误说明"})
    is_use_ai: bool = Field(default=False, sa_column_kwargs={"comment": "是否调用已确认的模型服务"})
    is_use_ocr: bool = Field(default=False, sa_column_kwargs={"comment": "是否调用已确认的文档解析服务"})
    lease_expires_at: datetime | None = Field(
        default=None,
        sa_type=DateTime(timezone=True),
        sa_column_kwargs={"comment": "执行租约终点；过期只标记中断，不自动重发云请求"},
    )


class CncOperation(SQLModel, table=True):
    __tablename__ = "mes_cnc_operation"
    __table_args__ = (
        Index("idx_mes_cnc_operation_part_id_sort_no", "part_id", "sort_no"),
        {"comment": "一行代表询价零件当前的一道工序及人工复核值"},
    )
    id: UUID = id_field()
    org_id: UUID = org_field(ondelete="RESTRICT")
    created_at: datetime = created_at_field()
    created_by: UUID | None = audit_user_field("创建人；租户用户", ondelete="RESTRICT")
    updated_at: datetime = updated_at_field()
    updated_by: UUID | None = audit_user_field("修改人；租户用户", ondelete="RESTRICT")
    flex_form: dict[str, Any] = flex_form_field()
    part_id: UUID = Field(
        foreign_key="mes_cnc_part.id", ondelete="RESTRICT", sa_column_kwargs={"comment": "所属询价零件"}
    )
    sort_no: int = Field(default=0, sa_column_kwargs={"comment": "工序顺序；从零开始"})
    name: str = Field(default="", max_length=120, sa_column_kwargs={"comment": "工序完整名称"})
    process_id: UUID | None = Field(default=None, foreign_key="mes_process.id", ondelete="RESTRICT", sa_column_kwargs={"comment": "工程核价选用的正式工艺档案；同组织并经范围校验，未确定时为空"})
    process_no_snapshot: str | None = Field(default=None, max_length=64, sa_column_kwargs={"comment": "选用时正式工艺编号快照；对应process_id，名称由现有name字段保存当时值"})
    machine: str = Field(default="", max_length=120, sa_column_kwargs={"comment": "设备说明"})
    note: str = Field(default="", max_length=1000, sa_column_kwargs={"comment": "人工备注；不自动发送 AI"})
    estimate_basis: str = Field(default="", max_length=2000, sa_column_kwargs={"comment": "工时估算依据"})
    process_type_code: str | None = Field(
        default=None, max_length=40, sa_column_kwargs={"comment": "字典 mes_cnc_process_type"}
    )
    pricing_mode_code: str = Field(
        default="hourly", max_length=40, sa_column_kwargs={"comment": "字典 mes_cnc_pricing_mode"}
    )
    external_weight_basis_code: str = Field(
        default="stock", max_length=40, sa_column_kwargs={"comment": "字典 mes_cnc_weight_basis"}
    )
    external_price_unit_code: str = Field(
        default="kg", max_length=40, sa_column_kwargs={"comment": "字典 mes_cnc_external_price_unit"}
    )
    origin_code: str = Field(
        default="manual", max_length=40, sa_column_kwargs={"comment": "字典 mes_cnc_origin"}
    )
    quote_rule_no: str | None = Field(
        default=None, max_length=60, sa_column_kwargs={"comment": "选用报价规则的业务编号；按来源快照解释"}
    )
    unit_hours: Decimal | None = Field(
        default=None, sa_type=Numeric(18, 6), sa_column_kwargs={"comment": "工时；小时/件"}
    )
    hourly_rate: Decimal | None = Field(
        default=None, sa_type=Numeric(18, 2), sa_column_kwargs={"comment": "小时费率；元/小时"}
    )
    external_rate: Decimal | None = Field(
        default=None, sa_type=Numeric(18, 2), sa_column_kwargs={"comment": "外协单价；元/kg 或元/m²"}
    )
    external_minimum_unit: Decimal = Field(
        default=Decimal("0"), sa_type=Numeric(18, 2), sa_column_kwargs={"comment": "外协最低收费；元/件"}
    )
    external_area_mm2: Decimal | None = Field(
        default=None, sa_type=Numeric(18, 6), sa_column_kwargs={"comment": "外协计费面积；mm²/件"}
    )
    source_job_id: UUID | None = Field(
        default=None,
        foreign_key="mes_cnc_analysis_job.id",
        ondelete="RESTRICT",
        sa_column_kwargs={"comment": "来源解析任务；人工工序为空"},
    )
    estimate_quantity: int | None = Field(
        default=None, sa_column_kwargs={"comment": "估时采用的询价数量；件"}
    )
    assumptions: list = Field(
        default_factory=list, sa_type=JSONB, sa_column_kwargs={"comment": "估时假设文本列表"}
    )
    evidence_refs: list = Field(
        default_factory=list,
        sa_type=JSONB,
        sa_column_kwargs={
            "comment": "解析证据标签列表；指向 source_job_id 下页面或几何标签，不是数据库 ID 数组"
        },
    )
    parameter_sources: dict = Field(
        default_factory=dict,
        sa_type=JSONB,
        sa_column_kwargs={"comment": "工序参数来源快照；字段名到规则编号、版本、当时值的映射"},
    )


class CncDrawingFile(SQLModel, table=True):
    __tablename__ = "mes_cnc_drawing_file"
    __table_args__ = (
        Index("uk_mes_cnc_drawing_file_part_id_kind_code", "part_id", "kind_code", unique=True),
        Index("uk_mes_cnc_drawing_file_attachment_id", "attachment_id", unique=True),
        {"comment": "一行代表询价零件绑定的一份图纸或模型原件"},
    )
    id: UUID = id_field()
    org_id: UUID = org_field(ondelete="RESTRICT")
    created_at: datetime = created_at_field()
    created_by: UUID | None = audit_user_field("创建人；租户用户", ondelete="RESTRICT")
    updated_at: datetime = updated_at_field()
    updated_by: UUID | None = audit_user_field("修改人；租户用户", ondelete="RESTRICT")
    flex_form: dict[str, Any] = flex_form_field()
    part_id: UUID = Field(
        foreign_key="mes_cnc_part.id", ondelete="RESTRICT", sa_column_kwargs={"comment": "所属询价零件"}
    )
    attachment_id: UUID = Field(
        foreign_key="file_attachment.id",
        ondelete="RESTRICT",
        sa_column_kwargs={"comment": "L1 文件原件；文件生命周期由文件服务管理"},
    )
    kind_code: str = Field(
        default="pdf", max_length=20, sa_column_kwargs={"comment": "字典 mes_cnc_file_kind；PDF 或 STEP"}
    )
    sha256: str = Field(default="", max_length=64, sa_column_kwargs={"comment": "已校验文件的 SHA256"})


class CncQuote(SQLModel, table=True):
    __tablename__ = "mes_cnc_quote"
    __table_args__ = (
        Index("idx_mes_cnc_quote_part_id_created_at", "part_id", "created_at"),
        {"comment": "一行代表一次不可覆盖的报价核算快照及其审核事实"},
    )
    id: UUID = id_field()
    org_id: UUID = org_field(ondelete="RESTRICT")
    created_at: datetime = created_at_field()
    created_by: UUID | None = audit_user_field("创建人；租户用户", ondelete="RESTRICT")
    updated_at: datetime = updated_at_field()
    updated_by: UUID | None = audit_user_field("修改人；租户用户", ondelete="RESTRICT")
    flex_form: dict[str, Any] = flex_form_field()
    part_id: UUID = Field(
        foreign_key="mes_cnc_part.id", ondelete="RESTRICT", sa_column_kwargs={"comment": "所属询价零件"}
    )
    version_no: int = Field(sa_column_kwargs={"comment": "核价时零件版本；与当前版本一致才可审核"})
    inputs_snapshot: dict = Field(
        default_factory=dict,
        sa_type=JSONB,
        sa_column_kwargs={"comment": "核价输入快照；零件、材料、工序及原件摘要；只追加不覆盖"},
    )
    result_snapshot: dict = Field(
        default_factory=dict,
        sa_type=JSONB,
        sa_column_kwargs={"comment": "计算结果快照；Decimal 字符串金额及逐工序明细；只追加不覆盖"},
    )
    unit_price: Decimal = Field(
        default=Decimal("0"), sa_type=Numeric(18, 2), sa_column_kwargs={"comment": "不含税单价；元/件"}
    )
    total_price: Decimal = Field(
        default=Decimal("0"), sa_type=Numeric(18, 2), sa_column_kwargs={"comment": "不含税总价；元"}
    )
    approved_by: UUID | None = audit_user_field(
        "审核人；当前登录租户用户，禁止手填姓名冒充", ondelete="RESTRICT"
    )
    approved_name_snapshot: str | None = Field(
        default=None,
        max_length=200,
        sa_column_kwargs={"comment": "审核时的用户显示名称快照；个人信息，不进入 AI"},
    )
    approved_at: datetime | None = Field(
        default=None, sa_type=DateTime(timezone=True), sa_column_kwargs={"comment": "人工审核时间"}
    )


class CncRuleSet(SQLModel, table=True):
    __tablename__ = "mes_cnc_rule_set"
    __table_args__ = (
        Index("uk_mes_cnc_rule_set_org_id", "org_id", unique=True),
        {"comment": "一行代表一个组织的当前报价规则控制参数"},
    )
    id: UUID = id_field()
    org_id: UUID = org_field(index=False, ondelete="RESTRICT")
    created_at: datetime = created_at_field()
    created_by: UUID | None = audit_user_field("创建人；租户用户", ondelete="RESTRICT")
    updated_at: datetime = updated_at_field()
    updated_by: UUID | None = audit_user_field("修改人；租户用户", ondelete="RESTRICT")
    flex_form: dict[str, Any] = flex_form_field()
    version_no: int = Field(default=1, sa_column_kwargs={"comment": "组织报价规则的乐观锁版本"})
    is_auto_apply: bool = Field(default=True, sa_column_kwargs={"comment": "是否自动补齐空白核价参数"})
    stock_allowance: Decimal | None = Field(
        default=None, sa_type=Numeric(18, 6), sa_column_kwargs={"comment": "每侧毛坯余量；mm"}
    )


class CncRuleEntry(SQLModel, table=True):
    __tablename__ = "mes_cnc_rule_entry"
    __table_args__ = (
        Index("uk_mes_cnc_rule_entry_rule_set_id_rule_no", "rule_set_id", "rule_no", unique=True),
        {"comment": "一行代表组织的一条材料、工序或外协规则"},
    )
    id: UUID = id_field()
    org_id: UUID = org_field(ondelete="RESTRICT")
    created_at: datetime = created_at_field()
    created_by: UUID | None = audit_user_field("创建人；租户用户", ondelete="RESTRICT")
    updated_at: datetime = updated_at_field()
    updated_by: UUID | None = audit_user_field("修改人；租户用户", ondelete="RESTRICT")
    flex_form: dict[str, Any] = flex_form_field()
    rule_set_id: UUID = Field(
        foreign_key="mes_cnc_rule_set.id",
        ondelete="RESTRICT",
        sa_column_kwargs={"comment": "所属组织报价规则"},
    )
    process_id: UUID | None = Field(default=None, foreign_key="mes_process.id", ondelete="RESTRICT",
        sa_column_kwargs={"comment": "本规则专属的正式生产工艺；引用同组织 mes_process，空为通用备用规则；材料规则必须为空"})
    rule_no: str = Field(
        default="",
        max_length=60,
        sa_column_kwargs={"comment": "组织规则内业务编号；可配置标识，不是内部 UUID"},
    )
    category_code: str = Field(
        default="materials", max_length=30, sa_column_kwargs={"comment": "字典 mes_cnc_rule_category"}
    )
    name: str = Field(default="", max_length=120, sa_column_kwargs={"comment": "规则名称"})
    is_active: bool = Field(default=True, sa_column_kwargs={"comment": "是否启用本规则"})
    sort_no: int = Field(default=0, sa_column_kwargs={"comment": "规则展示与匹配顺序"})
    definition: dict = Field(
        default_factory=dict,
        sa_type=JSONB,
        sa_column_kwargs={
            "comment": "规则定义；由 MaterialRule/ProcessRule/ExternalRule 校验的匹配词、单价、密度及来源"
        },
    )
