"""社保缴费基数、月度缴费和工资实付；与定薪独立。"""
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID
from sqlalchemy import Index, CheckConstraint, Numeric, text
from sqlmodel import SQLModel, Field
from app.framework.db.models import (id_field, org_field, created_at_field, updated_at_field, audit_user_field, deleted_at_field, flex_form_field)
from .model_fields import _money, _rate

class FinanceRow(SQLModel):
    id: UUID = id_field()
    org_id: UUID = org_field(ondelete="RESTRICT")
    created_at: datetime = created_at_field()
    created_by: UUID | None = audit_user_field("创建人", ondelete="SET NULL")
    updated_at: datetime = updated_at_field()
    updated_by: UUID | None = audit_user_field("修改人", ondelete="SET NULL")
    deleted_at: datetime | None = deleted_at_field()
    deleted_by: UUID | None = audit_user_field("删除人", ondelete="SET NULL")
    flex_form: dict[str, Any] = flex_form_field()

class SocialBasis(FinanceRow, table=True):
    __tablename__ = "sample_app_social_basis"
    __table_args__ = (
        Index("uk_sample_app_social_basis_employee_from", "employee_id", "valid_from", unique=True, postgresql_where=text("deleted_at is null")),
        CheckConstraint("social_base >= 0 and housing_base >= 0", name="nonnegative"),
        CheckConstraint("valid_to is null or valid_to > valid_from", name="validity"),
        {"comment": "员工缴费基数：一行为员工在左闭右开有效期间的社保和公积金基数；独立于工资版本。"},
    )
    employee_id: UUID = Field(foreign_key="sample_app_employee.id", nullable=False, ondelete="RESTRICT", sa_column_kwargs={"comment": "参保员工；敏感：内部"})
    social_plan_id: UUID = Field(foreign_key="sample_app_social_plan.id", nullable=False, ondelete="RESTRICT", sa_column_kwargs={"comment": "缴费比例方案"})
    social_base: Decimal = _money("自定义社保月缴费基数（元）；调薪不自动变化")
    housing_base: Decimal = _money("自定义公积金月缴费基数（元）；可与社保基数不同")
    valid_from: date = Field(nullable=False, sa_column_kwargs={"comment": "生效月份首日；含该月"})
    valid_to: date | None = Field(default=None, sa_column_kwargs={"comment": "失效月份首日；不含该月，空表示持续有效"})

class SocialBill(FinanceRow, table=True):
    __tablename__ = "sample_app_social_bill"
    __table_args__ = (
        Index("uk_sample_app_social_bill_org_month", "org_id", "period_month", unique=True, postgresql_where=text("deleted_at is null")),
        Index("uk_sample_app_social_bill_cash_entry", "cash_entry_id", unique=True, postgresql_where=text("deleted_at is null and cash_entry_id is not null")),
        {"comment": "月度社保公积金缴费单：一行为一个公司一个所属月份的缴费；确认后金额快照不再修改。"},
    )
    period_month: date = Field(nullable=False, sa_column_kwargs={"comment": "费用所属月份首日；不等于银行付款月份"})
    status_code: str = Field(default="draft", max_length=64, nullable=False, sa_column_kwargs={"comment": "单据状态；字典 sample_app_social_bill_status"})
    cash_entry_id: UUID | None = Field(default=None, foreign_key="sample_app_cash_entry.id", ondelete="RESTRICT", sa_column_kwargs={"comment": "实际缴费流水；同一流水不能关联其他缴费或工资支付"})

class SocialBillLine(FinanceRow, table=True):
    __tablename__ = "sample_app_social_bill_line"
    __table_args__ = (
        Index("uk_sample_app_social_bill_line_employee", "bill_id", "employee_id", unique=True),
        CheckConstraint("pension_employer_amount >= 0 and pension_employee_amount >= 0 and unemployment_employer_amount >= 0 and unemployment_employee_amount >= 0 and injury_employer_amount >= 0 and medical_employer_amount >= 0 and medical_employee_amount >= 0 and housing_employer_amount >= 0 and housing_employee_amount >= 0", name="nonnegative"),
        {"comment": "缴费单员工明细：一行为一名员工当月的缴费基数、比例快照及核对后的实际单位和个人金额。"},
    )
    bill_id: UUID = Field(foreign_key="sample_app_social_bill.id", nullable=False, ondelete="RESTRICT", sa_column_kwargs={"comment": "所属缴费单"})
    employee_id: UUID = Field(foreign_key="sample_app_employee.id", nullable=False, ondelete="RESTRICT", sa_column_kwargs={"comment": "参保员工；敏感：内部"})
    basis_id: UUID | None = Field(default=None, foreign_key="sample_app_social_basis.id", ondelete="RESTRICT", sa_column_kwargs={"comment": "基数档案；兼容旧定薪生成的首份快照时可空"})
    social_plan_id: UUID | None = Field(default=None, foreign_key="sample_app_social_plan.id", ondelete="RESTRICT", sa_column_kwargs={"comment": "生成时的缴费方案；实际采用比例另存快照"})
    social_base_snapshot: Decimal = _money("生成时社保缴费基数快照（元）")
    housing_base_snapshot: Decimal = _money("生成时公积金缴费基数快照（元）")
    pension_employer_rate_snapshot: Decimal = _rate("单位养老缴费比例快照（%）")
    pension_employer_amount: Decimal = _money("单位养老实际缴费金额（元）")
    pension_employee_rate_snapshot: Decimal = _rate("个人养老缴费比例快照（%）")
    pension_employee_amount: Decimal = _money("个人养老实际缴费金额（元）")
    unemployment_employer_rate_snapshot: Decimal = _rate("单位失业缴费比例快照（%）")
    unemployment_employer_amount: Decimal = _money("单位失业实际缴费金额（元）")
    unemployment_employee_rate_snapshot: Decimal = _rate("个人失业缴费比例快照（%）")
    unemployment_employee_amount: Decimal = _money("个人失业实际缴费金额（元）")
    injury_employer_rate_snapshot: Decimal = _rate("单位工伤缴费比例快照（%）")
    injury_employer_amount: Decimal = _money("单位工伤实际缴费金额（元）")
    medical_employer_rate_snapshot: Decimal = _rate("单位医疗缴费比例快照（%）")
    medical_employer_amount: Decimal = _money("单位医疗实际缴费金额（元）")
    medical_employee_rate_snapshot: Decimal = _rate("个人医疗缴费比例快照（%）")
    medical_employee_amount: Decimal = _money("个人医疗实际缴费金额（元）")
    housing_employer_rate_snapshot: Decimal = _rate("单位公积金缴费比例快照（%）")
    housing_employer_amount: Decimal = _money("单位公积金实际缴费金额（元）")
    housing_employee_rate_snapshot: Decimal = _rate("个人公积金缴费比例快照（%）")
    housing_employee_amount: Decimal = _money("个人公积金实际缴费金额（元）")

class PayrollPayment(FinanceRow, table=True):
    __tablename__ = "sample_app_payroll_payment"
    __table_args__ = (
        Index("uk_sample_app_payroll_payment_payroll", "payroll_id", unique=True, postgresql_where=text("deleted_at is null")),
        Index("uk_sample_app_payroll_payment_cash_entry", "cash_entry_id", unique=True, postgresql_where=text("deleted_at is null")),
        {"comment": "工资实付：一行为一份已封账工资册的整批实发付款；付款后才视为个人社保扣回。"},
    )
    payroll_id: UUID = Field(foreign_key="sample_app_payroll.id", nullable=False, ondelete="RESTRICT", sa_column_kwargs={"comment": "已封账工资册；不在重算时创建新付款"})
    cash_entry_id: UUID = Field(foreign_key="sample_app_cash_entry.id", nullable=False, ondelete="RESTRICT", sa_column_kwargs={"comment": "工资实际支付流水；付款日期以该流水为准"})
