"""快盒发薪名册、考勤、薪酬、项目与资金业务表；组织引用底座。"""
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import Index, Numeric, Text, text
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


from .model_fields import _money, _rate


class SamplePaySetting(SQLModel, table=True):
    """发薪参数：一个组织一行当前有效口径。"""

    __tablename__ = "sample_app_pay_setting"
    __table_args__ = (
        Index("uk_sample_app_pay_setting_org", "org_id", unique=True, postgresql_where=text("deleted_at is null")),
        {"comment": "发薪参数：一个组织一行。日薪除数、加班倍率和个税起征点都在这里配置。"},
    )

    id: UUID = id_field()
    org_id: UUID = org_field(index=False)
    daily_wage_mode_code: str = Field(max_length=64, nullable=False, sa_column_kwargs={"comment": "日薪口径；字典 sample_app_daily_wage_mode"})
    standard_days: Decimal = Field(default=Decimal("21.75"), sa_type=Numeric(8, 2), nullable=False, sa_column_kwargs={"server_default": text("21.75"), "comment": "固定日薪除数；模式为固定天数时使用"})
    overtime_multiplier: Decimal = Field(default=Decimal("2"), sa_type=Numeric(8, 2), nullable=False, sa_column_kwargs={"server_default": text("2"), "comment": "加班倍率"})
    tax_threshold: Decimal = _money("每月减除费用（元）", default="5000")
    created_at: datetime = created_at_field()
    created_by: UUID | None = audit_user_field("创建人")
    updated_at: datetime = updated_at_field()
    updated_by: UUID | None = audit_user_field("修改人")
    deleted_at: datetime | None = deleted_at_field()
    deleted_by: UUID | None = audit_user_field("删除人")
    flex_form: dict[str, Any] = flex_form_field()


class SampleTaxBracket(SQLModel, table=True):
    """个税税率档：累计预扣法的一档。"""

    __tablename__ = "sample_app_tax_bracket"
    __table_args__ = (
        Index("uk_sample_app_tax_bracket_org_sort", "org_id", "sort_no", unique=True, postgresql_where=text("deleted_at is null")),
        {"comment": "个税税率档：一行为累计应纳税所得额的一个区间。下限不含、上限含。"},
    )

    id: UUID = id_field()
    org_id: UUID = org_field(index=False)
    sort_no: int = Field(nullable=False, sa_column_kwargs={"comment": "排序"})
    min_amount: Decimal = _money("区间下限（元）；不含本数")
    max_amount: Decimal | None = Field(default=None, sa_type=Numeric(18, 2), sa_column_kwargs={"comment": "区间上限（元）；含本数；空表示无上限"})
    rate: Decimal = _rate("税率（%）")
    quick_deduction: Decimal = _money("速算扣除数（元）")
    created_at: datetime = created_at_field()
    created_by: UUID | None = audit_user_field("创建人")
    updated_at: datetime = updated_at_field()
    updated_by: UUID | None = audit_user_field("修改人")
    deleted_at: datetime | None = deleted_at_field()
    deleted_by: UUID | None = audit_user_field("删除人")
    flex_form: dict[str, Any] = flex_form_field()


class SampleSocialPlan(SQLModel, table=True):
    """社保公积金方案：一个城市或口径一行，比例可改。"""

    __tablename__ = "sample_app_social_plan"
    __table_args__ = (
        Index("uk_sample_app_social_plan_org_name", "org_id", "plan_name", unique=True, postgresql_where=text("deleted_at is null")),
        {"comment": "社保公积金方案：一行为一套缴费比例。金额按工资版本上的缴费基数乘比例计算。"},
    )

    id: UUID = id_field()
    org_id: UUID = org_field(index=False)
    plan_name: str = Field(max_length=128, nullable=False, sa_column_kwargs={"comment": "方案名称"})
    pension_employer_rate: Decimal = _rate("养老保险企业比例（%）")
    pension_employee_rate: Decimal = _rate("养老保险个人比例（%）")
    unemployment_employer_rate: Decimal = _rate("失业保险企业比例（%）")
    unemployment_employee_rate: Decimal = _rate("失业保险个人比例（%）")
    injury_employer_rate: Decimal = _rate("工伤保险企业比例（%）")
    medical_employer_rate: Decimal = _rate("医疗保险企业比例（%）")
    medical_employee_rate: Decimal = _rate("医疗保险个人比例（%）")
    housing_employer_rate: Decimal = _rate("公积金企业比例（%）")
    housing_employee_rate: Decimal = _rate("公积金个人比例（%）")
    created_at: datetime = created_at_field()
    created_by: UUID | None = audit_user_field("创建人")
    updated_at: datetime = updated_at_field()
    updated_by: UUID | None = audit_user_field("修改人")
    deleted_at: datetime | None = deleted_at_field()
    deleted_by: UUID | None = audit_user_field("删除人")
    flex_form: dict[str, Any] = flex_form_field()


class SampleEmployee(SQLModel, table=True):
    """人员名册：区分内部劳动关系与外包项目代管关系。"""

    __tablename__ = "sample_app_employee"
    __table_args__ = (
        Index("uk_sample_app_employee_org_no", "org_id", "employee_no", unique=True, postgresql_where=text("deleted_at is null")),
        {"comment": "人员名册：一行为本组织管理的一名人员；仅internal表示本组织内部员工，outsourced表示代管项目人员，不代表劳动关系。"},
    )

    id: UUID = id_field()
    org_id: UUID = org_field(index=False)
    personnel_type_code: str = Field(default="internal", max_length=64, nullable=False, sa_column_kwargs={"server_default": text("'internal'"), "comment": "人员关系；字典 sample_app_personnel_type；internal为本组织内部员工，outsourced为代招聘管理的外部人员，不确认外部劳动关系主体"})
    project_id: UUID | None = Field(default=None, foreign_key="sample_app_project.id", ondelete="RESTRICT", sa_column_kwargs={"comment": "当前代管项目；引用sample_app_project；仅外包项目人员填写，历史薪资和项目核算保留原关联"})
    employee_no: str = Field(max_length=64, nullable=False, sa_column_kwargs={"comment": "员工编号"})
    full_name: str = Field(max_length=128, nullable=False, sa_column_kwargs={"comment": "姓名"})
    employment_status_code: str = Field(max_length=64, nullable=False, sa_column_kwargs={"comment": "在职状态；字典 sample_app_employment_status"})
    hire_date: date | None = Field(default=None, nullable=True, sa_column_kwargs={"comment": "入职日期；历史资料未提供时为空，不推断补造"})
    employment_end_on: date | None = Field(default=None, sa_column_kwargs={"comment": "本组织任职截止日，不含该日；组织调动时填写"})
    bank_name: str | None = Field(default=None, max_length=128, sa_column_kwargs={"comment": "开户行"})
    account_no_masked: str | None = Field(default=None, max_length=64, sa_column_kwargs={"comment": "账号脱敏显示；不保存完整账号"})
    created_at: datetime = created_at_field()
    created_by: UUID | None = audit_user_field("创建人")
    updated_at: datetime = updated_at_field()
    updated_by: UUID | None = audit_user_field("修改人")
    deleted_at: datetime | None = deleted_at_field()
    deleted_by: UUID | None = audit_user_field("删除人")
    flex_form: dict[str, Any] = flex_form_field()


class SampleSalary(SQLModel, table=True):
    """薪资版本：一名员工一段生效期的基本工资和绩效工资。"""

    __tablename__ = "sample_app_salary"
    __table_args__ = (
        {"comment": "薪资版本：一行为一名员工在一段日期内的定薪。左闭右开，结束日期为空表示仍有效。"},
    )

    id: UUID = id_field()
    org_id: UUID = org_field()
    employee_id: UUID = Field(foreign_key="sample_app_employee.id", index=True, nullable=False, sa_column_kwargs={"comment": "员工；引用 sample_app_employee"})
    social_plan_id: UUID | None = Field(default=None, foreign_key="sample_app_social_plan.id", index=True, sa_column_kwargs={"comment": "社保公积金方案"})
    social_base: Decimal = _money("社保公积金缴费基数（元）")
    base_amount: Decimal = _money("基本工资（元）")
    performance_amount: Decimal = _money("绩效工资（元）")
    valid_from: date = Field(nullable=False, sa_column_kwargs={"comment": "生效日期"})
    valid_to: date | None = Field(default=None, sa_column_kwargs={"comment": "失效日期；不含当天；空表示至今有效"})
    created_at: datetime = created_at_field()
    created_by: UUID | None = audit_user_field("创建人")
    updated_at: datetime = updated_at_field()
    updated_by: UUID | None = audit_user_field("修改人")
    deleted_at: datetime | None = deleted_at_field()
    deleted_by: UUID | None = audit_user_field("删除人")
    flex_form: dict[str, Any] = flex_form_field()


class SampleAttendance(SQLModel, table=True):
    """月度考勤：一名员工一个月份一行。"""

    __tablename__ = "sample_app_attendance"
    __table_args__ = (
        Index(
            "uk_sample_app_attendance_employee_month",
            "org_id",
            "employee_id",
            "period_month",
            unique=True,
            postgresql_where=text("deleted_at is null"),
        ),
        {"comment": "月度考勤：一行为一名员工某月的应出勤、实出勤和加班天数。天数允许半天。"},
    )

    id: UUID = id_field()
    org_id: UUID = org_field(index=False)
    employee_id: UUID = Field(foreign_key="sample_app_employee.id", index=True, nullable=False, sa_column_kwargs={"comment": "员工；引用 sample_app_employee"})
    period_month: date = Field(nullable=False, sa_column_kwargs={"comment": "工资月份；取该月1日"})
    expected_days: Decimal = Field(default=Decimal("0"), sa_type=Numeric(8, 2), nullable=False, sa_column_kwargs={"server_default": text("0"), "comment": "应出勤天数"})
    actual_days: Decimal = Field(default=Decimal("0"), sa_type=Numeric(8, 2), nullable=False, sa_column_kwargs={"server_default": text("0"), "comment": "实际出勤天数"})
    overtime_days: Decimal = Field(default=Decimal("0"), sa_type=Numeric(8, 2), nullable=False, sa_column_kwargs={"server_default": text("0"), "comment": "加班天数"})
    created_at: datetime = created_at_field()
    created_by: UUID | None = audit_user_field("创建人")
    updated_at: datetime = updated_at_field()
    updated_by: UUID | None = audit_user_field("修改人")
    deleted_at: datetime | None = deleted_at_field()
    deleted_by: UUID | None = audit_user_field("删除人")
    flex_form: dict[str, Any] = flex_form_field()


class SamplePayroll(SQLModel, table=True):
    """工资册：一个组织一个月份一份。"""

    __tablename__ = "sample_app_payroll"
    __table_args__ = (
        Index(
            "uk_sample_app_payroll_org_month",
            "org_id",
            "period_month",
            unique=True,
            postgresql_where=text("deleted_at is null"),
        ),
        {"comment": "工资册：一行为一个组织某月的一次薪酬核算。封账后不能重算。"},
    )

    id: UUID = id_field()
    org_id: UUID = org_field(index=False)
    period_month: date = Field(nullable=False, sa_column_kwargs={"comment": "工资月份；取该月1日"})
    status_code: str = Field(max_length=64, nullable=False, sa_column_kwargs={"comment": "状态；字典 sample_app_payroll_status"})
    created_at: datetime = created_at_field()
    created_by: UUID | None = audit_user_field("创建人")
    updated_at: datetime = updated_at_field()
    updated_by: UUID | None = audit_user_field("修改人")
    deleted_at: datetime | None = deleted_at_field()
    deleted_by: UUID | None = audit_user_field("删除人")
    flex_form: dict[str, Any] = flex_form_field()


class SamplePayslip(SQLModel, table=True):
    """工资单：一名员工在一份工资册中的核算结果。"""

    __tablename__ = "sample_app_payslip"
    __table_args__ = (
        Index("uk_sample_app_payslip_payroll_employee", "payroll_id", "employee_id", unique=True),
        {"comment": "工资单：一行为一名员工某月的应发、扣款、个税、实发和企业成本。"},
    )

    id: UUID = id_field()
    org_id: UUID = org_field()
    payroll_id: UUID = Field(foreign_key="sample_app_payroll.id", index=True, nullable=False, sa_column_kwargs={"comment": "工资册"})
    employee_id: UUID = Field(foreign_key="sample_app_employee.id", index=True, nullable=False, sa_column_kwargs={"comment": "员工；引用 sample_app_employee"})
    project_id: UUID | None = Field(default=None, foreign_key="sample_app_project.id", index=True, sa_column_kwargs={"comment": "本月投入项目；企业应发成本按它归集"})
    task_name: str | None = Field(default=None, max_length=128, sa_column_kwargs={"comment": "本月任务或项目名称；未选项目时保留手工备注"})
    base_amount: Decimal = _money("基本工资（元）")
    performance_amount: Decimal = _money("绩效工资（元）")
    bonus_amount: Decimal = _money("奖金（元）")
    overtime_amount: Decimal = _money("加班费（元）")
    software_amount: Decimal = _money("软件报销（元）")
    travel_amount: Decimal = _money("出差补贴（元）")
    other_amount: Decimal = _money("其他补贴（元）")
    adjust_amount: Decimal = _money("补扣（元）")
    gross_amount: Decimal = _money("应发工资（元）")
    tax_amount: Decimal = _money("个税（元）")
    pension_employee_amount: Decimal = _money("个人养老保险（元）")
    unemployment_employee_amount: Decimal = _money("个人失业保险（元）")
    medical_employee_amount: Decimal = _money("个人医疗保险（元）")
    housing_employee_amount: Decimal = _money("个人公积金（元）")
    other_deduction_amount: Decimal = _money("其他代扣（元）")
    net_amount: Decimal = _money("实发工资（元）")
    pension_employer_amount: Decimal = _money("企业养老保险（元）")
    unemployment_employer_amount: Decimal = _money("企业失业保险（元）")
    injury_employer_amount: Decimal = _money("企业工伤保险（元）")
    medical_employer_amount: Decimal = _money("企业医疗保险（元）")
    housing_employer_amount: Decimal = _money("企业公积金（元）")
    employer_cost_amount: Decimal = _money("企业应发成本（元）")
    created_at: datetime = created_at_field()
    created_by: UUID | None = audit_user_field("创建人")
    updated_at: datetime = updated_at_field()
    updated_by: UUID | None = audit_user_field("修改人")
    deleted_at: datetime | None = deleted_at_field()
    deleted_by: UUID | None = audit_user_field("删除人")
    flex_form: dict[str, Any] = flex_form_field()


class SampleFlexField(SQLModel, table=True):
    """自定义字段定义：一个表单页面的一个登记项。"""

    __tablename__ = "sample_app_flex_field"
    __table_args__ = (
        Index("uk_sample_app_flex_field_form_field", "form_key", "field_key", unique=True, postgresql_where=text("deleted_at is null")),
        {"comment": "自定义字段定义：一行为内部员工、外包项目人员或项目页面上的一个扩展项。值保存在对应记录的 flex_form，不参与核算。"},
    )

    id: UUID = id_field()
    form_key: str = Field(max_length=64, nullable=False, sa_column_kwargs={"comment": "表单标识；employee_internal、employee_outsourced 或 project"})
    field_key: str = Field(max_length=64, nullable=False, sa_column_kwargs={"comment": "字段标识；创建后不可修改，写入 flex_form 的键"})
    field_name: str = Field(max_length=64, nullable=False, sa_column_kwargs={"comment": "字段名称"})
    value_type_code: str = Field(max_length=64, nullable=False, sa_column_kwargs={"comment": "值类型；字典 sample_app_flex_value_type"})
    is_required: bool = bool_field("是否必填", default=False)
    sort_no: int = Field(default=0, nullable=False, sa_column_kwargs={"server_default": text("0"), "comment": "显示顺序"})
    is_active: bool = bool_field("是否启用", default=True)
    created_at: datetime = created_at_field()
    created_by: UUID | None = audit_user_field("创建人")
    updated_at: datetime = updated_at_field()
    updated_by: UUID | None = audit_user_field("修改人")
    deleted_at: datetime | None = deleted_at_field()
    deleted_by: UUID | None = audit_user_field("删除人")
    flex_form: dict[str, Any] = flex_form_field()


class SampleProject(SQLModel, table=True):
    """项目：一个组织下一笔经营项目。"""

    __tablename__ = "sample_app_project"
    __table_args__ = (
        Index("uk_sample_app_project_org_name", "org_id", "project_name", unique=True, postgresql_where=text("deleted_at is null")),
        {"comment": "项目：一行为一个客户项目。管道金额是尚未确认的潜在金额，不计入应收。"},
    )

    id: UUID = id_field()
    org_id: UUID = org_field(index=False)
    project_name: str = Field(max_length=128, nullable=False, sa_column_kwargs={"comment": "项目名称"})
    customer_name: str | None = Field(default=None, max_length=128, sa_column_kwargs={"comment": "客户名称"})
    status_code: str = Field(max_length=64, nullable=False, sa_column_kwargs={"comment": "状态；字典 sample_app_project_status"})
    pipeline_amount: Decimal = _money("管道金额（元）；尚未确认收入")
    remark: str | None = Field(default=None, sa_type=Text, sa_column_kwargs={"comment": "项目备注；保留来源台账说明及待确认事项，敏感：内部"})
    created_at: datetime = created_at_field()
    created_by: UUID | None = audit_user_field("创建人")
    updated_at: datetime = updated_at_field()
    updated_by: UUID | None = audit_user_field("修改人")
    deleted_at: datetime | None = deleted_at_field()
    deleted_by: UUID | None = audit_user_field("删除人")
    flex_form: dict[str, Any] = flex_form_field()


class SampleContract(SQLModel, table=True):
    """合同：一个项目下的一份合同总价。"""

    __tablename__ = "sample_app_contract"
    __table_args__ = (
        Index("uk_sample_app_contract_org_no", "org_id", "contract_no", unique=True, postgresql_where=text("deleted_at is null")),
        {"comment": "合同：一行为一个项目的一份合同。总价按合同币种保存，不换算。"},
    )

    id: UUID = id_field()
    org_id: UUID = org_field()
    project_id: UUID = Field(foreign_key="sample_app_project.id", index=True, nullable=False, sa_column_kwargs={"comment": "项目"})
    contract_no: str = Field(max_length=64, nullable=False, sa_column_kwargs={"comment": "合同编号"})
    currency_code: str = Field(max_length=64, nullable=False, sa_column_kwargs={"comment": "币种；字典 sample_app_currency"})
    total_amount: Decimal = _money("合同总价；币种见 currency_code")
    created_at: datetime = created_at_field()
    created_by: UUID | None = audit_user_field("创建人")
    updated_at: datetime = updated_at_field()
    updated_by: UUID | None = audit_user_field("修改人")
    deleted_at: datetime | None = deleted_at_field()
    deleted_by: UUID | None = audit_user_field("删除人")
    flex_form: dict[str, Any] = flex_form_field()


class SampleReceiptPlan(SQLModel, table=True):
    """回款计划：一份合同在某月的预计收款。"""

    __tablename__ = "sample_app_receipt_plan"
    __table_args__ = (
        {"comment": "回款计划：一行为一份合同在某月的预计收款，金额使用合同币种。"},
    )

    id: UUID = id_field()
    org_id: UUID = org_field()
    contract_id: UUID = Field(foreign_key="sample_app_contract.id", index=True, nullable=False, sa_column_kwargs={"comment": "合同"})
    plan_month: date = Field(nullable=False, sa_column_kwargs={"comment": "计划月份；取该月1日"})
    amount: Decimal = _money("计划金额；币种与合同一致")
    created_at: datetime = created_at_field()
    created_by: UUID | None = audit_user_field("创建人")
    updated_at: datetime = updated_at_field()
    updated_by: UUID | None = audit_user_field("修改人")
    deleted_at: datetime | None = deleted_at_field()
    deleted_by: UUID | None = audit_user_field("删除人")
    flex_form: dict[str, Any] = flex_form_field()


class SampleReceipt(SQLModel, table=True):
    """实际收款：一份合同的一笔到账。"""

    __tablename__ = "sample_app_receipt"
    __table_args__ = (
        {"comment": "实际收款：一笔到账。应收按合同总价减去同币种已收款计算。"},
    )

    id: UUID = id_field()
    org_id: UUID = org_field()
    contract_id: UUID = Field(foreign_key="sample_app_contract.id", index=True, nullable=False, sa_column_kwargs={"comment": "合同"})
    received_on: date | None = Field(default=None, nullable=True, sa_column_kwargs={"comment": "到账日期；历史累计回款未提供具体日期时为空，不代表新增银行流水"})
    amount: Decimal = _money("到账金额；币种与合同一致")
    remark: str | None = Field(default=None, max_length=255, sa_column_kwargs={"comment": "备注"})
    created_at: datetime = created_at_field()
    created_by: UUID | None = audit_user_field("创建人")
    updated_at: datetime = updated_at_field()
    updated_by: UUID | None = audit_user_field("修改人")
    deleted_at: datetime | None = deleted_at_field()
    deleted_by: UUID | None = audit_user_field("删除人")
    flex_form: dict[str, Any] = flex_form_field()


class SampleProjectCost(SQLModel, table=True):
    """项目直接成本：除工资归集以外的项目支出。"""

    __tablename__ = "sample_app_project_cost"
    __table_args__ = (
        {"comment": "项目直接成本：一笔非工资支出，金额为人民币。人力成本从工资单的企业应发成本归集。"},
    )

    id: UUID = id_field()
    org_id: UUID = org_field()
    project_id: UUID = Field(foreign_key="sample_app_project.id", index=True, nullable=False, sa_column_kwargs={"comment": "项目"})
    cost_name: str = Field(max_length=128, nullable=False, sa_column_kwargs={"comment": "费用名称"})
    amount: Decimal = _money("金额（元）")
    occurred_on: date = Field(nullable=False, sa_column_kwargs={"comment": "发生日期"})
    created_at: datetime = created_at_field()
    created_by: UUID | None = audit_user_field("创建人")
    updated_at: datetime = updated_at_field()
    updated_by: UUID | None = audit_user_field("修改人")
    deleted_at: datetime | None = deleted_at_field()
    deleted_by: UUID | None = audit_user_field("删除人")
    flex_form: dict[str, Any] = flex_form_field()


class SampleAccount(SQLModel, table=True):
    """资金账户：银行账户或公司金库。"""

    __tablename__ = "sample_app_account"
    __table_args__ = (
        Index("uk_sample_app_account_org_name", "org_id", "account_name", unique=True, postgresql_where=text("deleted_at is null")),
        {"comment": "资金账户：一行为一个银行账户或公司金库。期初余额是流水开始前的账面余额。"},
    )

    id: UUID = id_field()
    org_id: UUID = org_field(index=False)
    account_name: str = Field(max_length=128, nullable=False, sa_column_kwargs={"comment": "账户名称"})
    account_type_code: str = Field(max_length=64, nullable=False, sa_column_kwargs={"comment": "账户类型；字典 sample_app_account_type"})
    opening_balance: Decimal = _money("期初余额（元）")
    opening_on: date = Field(nullable=False, sa_column_kwargs={"comment": "期初日期；此前的流水不计入账面余额"})
    created_at: datetime = created_at_field()
    created_by: UUID | None = audit_user_field("创建人")
    updated_at: datetime = updated_at_field()
    updated_by: UUID | None = audit_user_field("修改人")
    deleted_at: datetime | None = deleted_at_field()
    deleted_by: UUID | None = audit_user_field("删除人")
    flex_form: dict[str, Any] = flex_form_field()


class SampleCashEntry(SQLModel, table=True):
    """资金流水：一笔收入或支出。"""

    __tablename__ = "sample_app_cash_entry"
    __table_args__ = (
        Index(
            "uk_sample_app_cash_entry_source",
            "source_type_code",
            "source_id",
            unique=True,
            postgresql_where=text("deleted_at is null and source_id is not null"),
        ),
        {"comment": "资金流水：一笔收入或支出。借款、还款、报销入账和固定成本入账各只生成一笔。"},
    )

    id: UUID = id_field()
    org_id: UUID = org_field()
    account_id: UUID = Field(foreign_key="sample_app_account.id", index=True, nullable=False, sa_column_kwargs={"comment": "资金账户"})
    occurred_on: date = Field(nullable=False, sa_column_kwargs={"comment": "发生日期"})
    direction_code: str = Field(max_length=64, nullable=False, sa_column_kwargs={"comment": "方向；字典 sample_app_cash_direction"})
    category_code: str = Field(max_length=64, nullable=False, sa_column_kwargs={"comment": "收支分类；字典 sample_app_cash_category"})
    amount: Decimal = _money("金额（元）")
    summary: str | None = Field(default=None, max_length=255, sa_column_kwargs={"comment": "摘要"})
    project_id: UUID | None = Field(default=None, foreign_key="sample_app_project.id", index=True, sa_column_kwargs={"comment": "关联项目；只作备注，不冲减合同应收"})
    source_type_code: str | None = Field(default=None, max_length=64, sa_column_kwargs={"comment": "来源类型；字典 sample_app_cash_source；手工流水为空"})
    source_id: UUID | None = Field(default=None, sa_column_kwargs={"comment": "来源单据UUID；按sample_app_cash_source指向借款、还款、报销、固定成本入账、缴费单或工资册，属多态引用无法声明统一外键"})
    created_at: datetime = created_at_field()
    created_by: UUID | None = audit_user_field("创建人")
    updated_at: datetime = updated_at_field()
    updated_by: UUID | None = audit_user_field("修改人")
    deleted_at: datetime | None = deleted_at_field()
    deleted_by: UUID | None = audit_user_field("删除人")
    flex_form: dict[str, Any] = flex_form_field()


class SampleAccountBalance(SQLModel, table=True):
    """账户余额核对：月末或月中的账面余额。"""

    __tablename__ = "sample_app_account_balance"
    __table_args__ = (
        Index(
            "uk_sample_app_account_balance_day",
            "account_id",
            "balance_on",
            "balance_kind_code",
            unique=True,
            postgresql_where=text("deleted_at is null"),
        ),
        {"comment": "账户余额核对：一行为某账户在某一天的月末或月中余额，用来和流水推算的账面余额对照。"},
    )

    id: UUID = id_field()
    org_id: UUID = org_field()
    account_id: UUID = Field(foreign_key="sample_app_account.id", index=True, nullable=False, sa_column_kwargs={"comment": "资金账户"})
    balance_on: date = Field(nullable=False, sa_column_kwargs={"comment": "余额日期"})
    balance_kind_code: str = Field(max_length=64, nullable=False, sa_column_kwargs={"comment": "余额时点；字典 sample_app_balance_kind"})
    amount: Decimal = _money("余额（元）")
    created_at: datetime = created_at_field()
    created_by: UUID | None = audit_user_field("创建人")
    updated_at: datetime = updated_at_field()
    updated_by: UUID | None = audit_user_field("修改人")
    deleted_at: datetime | None = deleted_at_field()
    deleted_by: UUID | None = audit_user_field("删除人")
    flex_form: dict[str, Any] = flex_form_field()


class SampleLoan(SQLModel, table=True):
    """员工往来款：一笔员工借款或公司对员工的待付欠款。"""

    __tablename__ = "sample_app_loan"
    __table_args__ = (
        {"comment": "员工往来款：一行为员工欠公司或公司欠员工的一笔本金；未还金额为本金减累计偿还。公司欠员工建档不产生资金流水。"},
    )

    id: UUID = id_field()
    org_id: UUID = org_field()
    employee_id: UUID = Field(foreign_key="sample_app_employee.id", index=True, nullable=False, sa_column_kwargs={"comment": "往来员工；引用 sample_app_employee；按欠款类型确定债权债务方向"})
    debt_type_code: str = Field(default="employee_loan", max_length=64, nullable=False, sa_column_kwargs={"server_default": text("'employee_loan'"), "comment": "欠款类型；字典 sample_app_debt_type；employee_loan为员工欠公司，company_payable为公司欠员工"})
    account_id: UUID | None = Field(default=None, foreign_key="sample_app_account.id", index=True, nullable=True, sa_column_kwargs={"comment": "员工借款的借出账户；公司欠员工登记时为空，实际支付另选付款账户"})
    amount: Decimal = _money("往来款原始本金（元）")
    borrowed_on: date = Field(nullable=False, sa_column_kwargs={"comment": "欠款发生日期；字段名兼容原借款登记"})
    remark: str | None = Field(default=None, max_length=255, sa_column_kwargs={"comment": "备注"})
    created_at: datetime = created_at_field()
    created_by: UUID | None = audit_user_field("创建人")
    updated_at: datetime = updated_at_field()
    updated_by: UUID | None = audit_user_field("修改人")
    deleted_at: datetime | None = deleted_at_field()
    deleted_by: UUID | None = audit_user_field("删除人")
    flex_form: dict[str, Any] = flex_form_field()


class SampleLoanRepayment(SQLModel, table=True):
    """借款还款：一笔归还。"""

    __tablename__ = "sample_app_loan_repayment"
    __table_args__ = (
        Index("uk_sample_app_loan_repayment_org_id_request_key", "org_id", "request_key", unique=True, postgresql_where=text("deleted_at is null and request_key is not null")),
        {"comment": "员工往来款偿还：一行为一笔实际收付；员工还公司记收入，公司还员工记支出。"},
    )

    id: UUID = id_field()
    org_id: UUID = org_field()
    loan_id: UUID = Field(foreign_key="sample_app_loan.id", index=True, nullable=False, sa_column_kwargs={"comment": "借款"})
    request_key: str | None = Field(default=None, max_length=64, sa_column_kwargs={"comment": "还款请求幂等标识；同一确认请求重试不重复记账；历史记录可空"})
    account_id: UUID = Field(foreign_key="sample_app_account.id", index=True, nullable=False, sa_column_kwargs={"comment": "实际收付账户；公司偿还员工时为付款账户，员工归还公司时为收款账户"})
    amount: Decimal = _money("还款金额（元）")
    repaid_on: date = Field(nullable=False, sa_column_kwargs={"comment": "还款日期"})
    created_at: datetime = created_at_field()
    created_by: UUID | None = audit_user_field("创建人")
    updated_at: datetime = updated_at_field()
    updated_by: UUID | None = audit_user_field("修改人")
    deleted_at: datetime | None = deleted_at_field()
    deleted_by: UUID | None = audit_user_field("删除人")
    flex_form: dict[str, Any] = flex_form_field()


class SampleReimbursement(SQLModel, table=True):
    """费用报销：提交后入账，入账时记一笔支出。"""

    __tablename__ = "sample_app_reimbursement"
    __table_args__ = (
        {"comment": "费用报销：一笔报销。草稿可提交，提交后入账并生成资金支出。"},
    )

    id: UUID = id_field()
    org_id: UUID = org_field()
    employee_id: UUID = Field(foreign_key="sample_app_employee.id", index=True, nullable=False, sa_column_kwargs={"comment": "报销员工；引用 sample_app_employee"})
    account_id: UUID | None = Field(default=None, foreign_key="sample_app_account.id", index=True, sa_column_kwargs={"comment": "付款账户；入账时填写"})
    amount: Decimal = _money("报销金额（元）")
    subject: str = Field(max_length=128, nullable=False, sa_column_kwargs={"comment": "报销事由"})
    status_code: str = Field(max_length=64, nullable=False, sa_column_kwargs={"comment": "状态；字典 sample_app_reimbursement_status"})
    occurred_on: date = Field(nullable=False, sa_column_kwargs={"comment": "费用发生日期"})
    created_at: datetime = created_at_field()
    created_by: UUID | None = audit_user_field("创建人")
    updated_at: datetime = updated_at_field()
    updated_by: UUID | None = audit_user_field("修改人")
    deleted_at: datetime | None = deleted_at_field()
    deleted_by: UUID | None = audit_user_field("删除人")
    flex_form: dict[str, Any] = flex_form_field()


class SampleFixedCost(SQLModel, table=True):
    """固定成本：按月发生的云资源、房租等费用。"""

    __tablename__ = "sample_app_fixed_cost"
    __table_args__ = (
        {"comment": "固定成本：一项按月支出。记入某月时生成一笔资金支出，同一个月不重复记。"},
    )

    id: UUID = id_field()
    org_id: UUID = org_field()
    account_id: UUID = Field(foreign_key="sample_app_account.id", index=True, nullable=False, sa_column_kwargs={"comment": "付款账户"})
    cost_name: str = Field(max_length=128, nullable=False, sa_column_kwargs={"comment": "费用名称"})
    category_code: str = Field(max_length=64, nullable=False, sa_column_kwargs={"comment": "费用类别；字典 sample_app_fixed_cost_category"})
    monthly_amount: Decimal = _money("每月金额（元）")
    is_active: bool = bool_field("是否仍按月记入", default=True)
    created_at: datetime = created_at_field()
    created_by: UUID | None = audit_user_field("创建人")
    updated_at: datetime = updated_at_field()
    updated_by: UUID | None = audit_user_field("修改人")
    deleted_at: datetime | None = deleted_at_field()
    deleted_by: UUID | None = audit_user_field("删除人")
    flex_form: dict[str, Any] = flex_form_field()


class SampleFixedCostCharge(SQLModel, table=True):
    """固定成本入账：一项固定成本在某月的一次支出。"""

    __tablename__ = "sample_app_fixed_cost_charge"
    __table_args__ = (
        Index(
            "uk_sample_app_fixed_cost_charge_month",
            "fixed_cost_id",
            "period_month",
            unique=True,
            postgresql_where=text("deleted_at is null"),
        ),
        {"comment": "固定成本入账：一项固定成本在某月只记一次，并对应一笔资金流水。"},
    )

    id: UUID = id_field()
    org_id: UUID = org_field()
    fixed_cost_id: UUID = Field(foreign_key="sample_app_fixed_cost.id", index=True, nullable=False, sa_column_kwargs={"comment": "固定成本"})
    period_month: date = Field(nullable=False, sa_column_kwargs={"comment": "入账月份；取该月1日"})
    cash_entry_id: UUID = Field(foreign_key="sample_app_cash_entry.id", nullable=False, sa_column_kwargs={"comment": "对应资金流水"})
    created_at: datetime = created_at_field()
    created_by: UUID | None = audit_user_field("创建人")
    updated_at: datetime = updated_at_field()
    updated_by: UUID | None = audit_user_field("修改人")
    deleted_at: datetime | None = deleted_at_field()
    deleted_by: UUID | None = audit_user_field("删除人")
    flex_form: dict[str, Any] = flex_form_field()


from .social_models import SocialBasis, SocialBill, SocialBillLine, PayrollPayment  # noqa: E402,F401
