"""员工端账号绑定与待确认报销；租户 schema 内保存。"""
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID
from sqlalchemy import CheckConstraint, DateTime, Index, Numeric, text
from sqlmodel import Field
from .social_models import FinanceRow


class EmployeeUser(FinanceRow, table=True):
    __tablename__ = "sample_app_employee_user"
    __table_args__ = (
        Index("uk_sample_app_employee_user_user", "user_id", unique=True, postgresql_where=text("deleted_at is null and valid_to is null")),
        Index("uk_sample_app_employee_user_employee", "employee_id", unique=True, postgresql_where=text("deleted_at is null and valid_to is null")),
        CheckConstraint("valid_to is null or valid_to > valid_from", name="validity"),
        {"comment": "员工账号关联：一行为一个账号与名册员工的有效关联；结束旧关联后才可换绑，历史保留。"},
    )
    user_id: UUID = Field(foreign_key="sys_user.id", ondelete="RESTRICT", sa_column_kwargs={"comment": "关联租户用户；不是登录认证账号；敏感：内部"})
    employee_id: UUID = Field(foreign_key="sample_app_employee.id", ondelete="RESTRICT", sa_column_kwargs={"comment": "本人名册员工；不按姓名推断；敏感：个人"})
    valid_from: datetime = Field(sa_type=DateTime(timezone=True), sa_column_kwargs={"comment": "关联生效时间；含本时刻"})
    valid_to: datetime | None = Field(default=None, sa_type=DateTime(timezone=True), sa_column_kwargs={"comment": "关联结束时间；不含本时刻；空表示当前关联"})


class EmployeeExpenseRequest(FinanceRow, table=True):
    __tablename__ = "sample_app_employee_expense_request"
    __table_args__ = (
        Index("uk_sample_app_employee_expense_request_key", "user_id", "request_key", unique=True),
        Index("uk_sample_app_employee_expense_request_result", "reimbursement_id", unique=True),
        Index("uk_sample_app_employee_expense_request_previous", "previous_request_id", unique=True,
              postgresql_where=text("previous_request_id is not null")),
        CheckConstraint("amount > 0", name="positive_amount"),
        {"comment": "员工报销待确认申请：一行为本人整理的一批发票；人工确认后仅能生成一条报销，重试返回原结果。"},
    )
    user_id: UUID = Field(foreign_key="sys_user.id", ondelete="RESTRICT", sa_column_kwargs={"comment": "本人租户用户；敏感：内部"})
    employee_id: UUID = Field(foreign_key="sample_app_employee.id", ondelete="RESTRICT", sa_column_kwargs={"comment": "准备时的本人名册关联；提交时重新核对；敏感：个人"})
    request_key: str = Field(max_length=64, sa_column_kwargs={"comment": "客户端生成的幂等标识；同一用户同一标识仅一份申请"})
    subject: str = Field(max_length=128, sa_column_kwargs={"comment": "用户提供的报销事由；敏感：未确认自由文本"})
    source_code: str = Field(default="legacy", max_length=16, sa_column_kwargs={"server_default": text("'legacy'"), "comment": "字典 sample_app_expense_source：manual本人手动、mcp工具、legacy历史未声明来源；服务端指定"})
    status_code: str = Field(default="legacy", max_length=24, sa_column_kwargs={"server_default": text("'legacy'"), "comment": "字典 sample_app_expense_request_status；历史默认legacy，未提交旧申请须重新准备；不影响已生成报销单"})
    previous_request_id: UUID | None = Field(default=None, foreign_key="sample_app_employee_expense_request.id", ondelete="RESTRICT", sa_column_kwargs={"comment": "本次整体重新准备所取代的本人旧申请；一份旧申请最多被一个新版本取代"})
    invoice_manifest_hash: str | None = Field(default=None, max_length=64, sa_column_kwargs={"comment": "预定发票清单SHA256摘要；新申请必须声明完整清单，进入核对及提交时复核；历史可空"})
    amount: Decimal = Field(sa_type=Numeric(18, 2), nullable=False, sa_column_kwargs={"comment": "用户确认的报销金额（元）；必填且大于0"})
    occurred_on: date = Field(sa_column_kwargs={"comment": "费用发生日期"})
    expires_at: datetime = Field(sa_type=DateTime(timezone=True), sa_column_kwargs={"comment": "待确认申请截止时间；确认后仍需在此时间内提交"})
    approved_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True), sa_column_kwargs={"comment": "本人在登录页面明确确认摘要的时间；空表示未确认"})
    reimbursement_id: UUID | None = Field(default=None, foreign_key="sample_app_reimbursement.id", ondelete="RESTRICT", sa_column_kwargs={"comment": "成功提交的报销单；非空时重试返回该单"})


class EmployeeExpenseFile(FinanceRow, table=True):
    __tablename__ = "sample_app_employee_expense_file"
    __table_args__ = (
        Index("uk_sample_app_employee_expense_file_request_file", "request_id", "file_id", unique=True),
        {"comment": "待确认报销附件关联：一行为申请内一个已完成上传的发票；确认后不可修改；核心关联不存 JSON。"},
    )
    request_id: UUID = Field(foreign_key="sample_app_employee_expense_request.id", ondelete="RESTRICT", sa_column_kwargs={"comment": "所属待确认申请"})
    file_id: UUID = Field(foreign_key="file_attachment.id", ondelete="CASCADE", sa_column_kwargs={"comment": "本人已完成上传的发票；提交时绑定报销单；未绑定文件过期清理时自动移除临时关联"})


class EmployeeExpenseInvoice(FinanceRow, table=True):
    __tablename__ = "sample_app_employee_expense_invoice"
    __table_args__ = (
        Index("uk_sample_app_expense_invoice_request_md5", "request_id", "content_md5", unique=True),
        Index("uk_sample_app_expense_invoice_file", "file_id", unique=True,
              postgresql_where=text("file_id is not null")),
        CheckConstraint("file_size > 0", name="positive_size"),
        {"comment": "预定报销发票清单：一行为准备时声明的一份原件；文件名、类型、字节数及MD5不可修改；票据重试仅能更新该行文件引用。"},
    )
    request_id: UUID = Field(foreign_key="sample_app_employee_expense_request.id", ondelete="RESTRICT", sa_column_kwargs={"comment": "所属本人报销申请"})
    file_name: str = Field(max_length=255, sa_column_kwargs={"comment": "准备时声明的原件文件名；敏感：未确认自由文本"})
    content_type: str = Field(max_length=128, sa_column_kwargs={"comment": "声明的文件MIME类型；仅允许发票PDF和图片"})
    file_size: int = Field(sa_column_kwargs={"comment": "声明的原件大小（字节）；必须与完成上传时一致"})
    content_md5: str = Field(max_length=32, sa_column_kwargs={"comment": "声明的原件MD5摘要（Base64）；同一申请内不可重复"})
    file_id: UUID | None = Field(default=None, foreign_key="file_attachment.id", ondelete="SET NULL", sa_column_kwargs={"comment": "为本条清单签发的当前上传票据文件；重试更新；临时文件过期后置空，声明清单保留"})


class SoftwareClaim(FinanceRow, table=True):
    __tablename__ = "sample_app_software_claim"
    __table_args__ = (
        Index("uk_sample_app_software_claim_key", "user_id", "request_key", unique=True),
        Index(
            "uk_sample_app_software_claim_employee_month",
            "employee_id",
            "period_month",
            unique=True,
            postgresql_where=text("deleted_at is null and status_code in ('ready', 'approved', 'applied')"),
        ),
        CheckConstraint("claimed_amount >= 0", name="non_negative_claimed"),
        CheckConstraint("applied_amount >= 0", name="non_negative_applied"),
        {"comment": "软件报销申请：一行为内部员工某月的软件订阅/工具费用申报；确认后写入当月工资单软件报销。"},
    )
    user_id: UUID = Field(foreign_key="sys_user.id", ondelete="RESTRICT", sa_column_kwargs={"comment": "本人租户用户；敏感：内部"})
    employee_id: UUID = Field(foreign_key="sample_app_employee.id", ondelete="RESTRICT", sa_column_kwargs={"comment": "本人名册员工；敏感：个人"})
    request_key: str = Field(max_length=64, sa_column_kwargs={"comment": "客户端幂等标识；同一用户同一标识仅一份申请"})
    period_month: date = Field(sa_column_kwargs={"comment": "申报工资月份；取该月1日；明细所属账期须与之一致（扣款日不决定归属）"})
    status_code: str = Field(max_length=24, sa_column_kwargs={"comment": "字典 sample_app_software_claim_status"})
    claimed_amount: Decimal = Field(sa_type=Numeric(18, 2), nullable=False, sa_column_kwargs={"comment": "申报合计（元）"})
    applied_amount: Decimal = Field(sa_type=Numeric(18, 2), nullable=False, sa_column_kwargs={"comment": "写入工资单的金额（元）；与申报合计一致"})
    evidence_manifest_hash: str | None = Field(default=None, max_length=64, sa_column_kwargs={"comment": "凭证原件清单SHA256；有声明时确认前必须传齐"})
    expires_at: datetime = Field(sa_type=DateTime(timezone=True), sa_column_kwargs={"comment": "待确认截止时间"})
    approved_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True), sa_column_kwargs={"comment": "本人确认时间"})
    payslip_id: UUID | None = Field(default=None, foreign_key="sample_app_payslip.id", ondelete="SET NULL", sa_column_kwargs={"comment": "已写入的工资单；空表示待工资核算时带入"})


class SoftwareClaimItem(FinanceRow, table=True):
    __tablename__ = "sample_app_software_claim_item"
    __table_args__ = (
        Index("idx_sample_app_software_claim_item_claim", "claim_id"),
        CheckConstraint("amount > 0", name="positive_amount"),
        {"comment": "软件报销明细：一行为一条微信/支付宝扣款或 invoice 记录；由 AI 从凭证摘录，服务端校验日期与金额。"},
    )
    claim_id: UUID = Field(foreign_key="sample_app_software_claim.id", ondelete="RESTRICT", sa_column_kwargs={"comment": "所属软件报销申请"})
    occurred_on: date | None = Field(default=None, sa_column_kwargs={"comment": "凭证上显示的扣款或消费日期；凭证读取不到时为空，此时须有 billing_month"})
    billing_month: str = Field(max_length=7, sa_column_kwargs={"comment": "所属工资月 YYYY-MM：凭证标注的账期优先，否则取扣款日期所在月；必须等于申报工资月"})
    amount: Decimal = Field(sa_type=Numeric(18, 2), nullable=False, sa_column_kwargs={"comment": "本条金额（元）"})
    merchant_name: str = Field(max_length=128, sa_column_kwargs={"comment": "商户或订阅名称；敏感：未确认自由文本"})
    source_code: str = Field(max_length=16, sa_column_kwargs={"comment": "字典 sample_app_software_claim_source：wechat、alipay、bank_card、invoice"})
    note: str | None = Field(default=None, max_length=255, sa_column_kwargs={"comment": "补充说明；敏感：未确认自由文本"})
    sort_no: int = Field(default=0, sa_column_kwargs={"comment": "显示顺序"})


class SoftwareClaimFile(FinanceRow, table=True):
    __tablename__ = "sample_app_software_claim_file"
    __table_args__ = (
        Index("uk_sample_app_software_claim_file", "claim_id", "file_id", unique=True),
        Index("uk_sample_app_software_claim_file_md5", "claim_id", "content_md5", unique=True),
        CheckConstraint("file_size > 0", name="positive_size"),
        {"comment": "软件报销凭证：一行为申请内一份截图或 invoice；核心关联不存 JSON。"},
    )
    claim_id: UUID = Field(foreign_key="sample_app_software_claim.id", ondelete="RESTRICT", sa_column_kwargs={"comment": "所属软件报销申请"})
    file_name: str = Field(max_length=255, sa_column_kwargs={"comment": "声明的文件名；敏感：未确认自由文本"})
    content_type: str = Field(max_length=128, sa_column_kwargs={"comment": "MIME 类型；仅 PDF 与图片"})
    file_size: int = Field(sa_column_kwargs={"comment": "声明的字节数"})
    content_md5: str = Field(max_length=32, sa_column_kwargs={"comment": "声明的 MD5（Base64）"})
    file_id: UUID | None = Field(default=None, foreign_key="file_attachment.id", ondelete="SET NULL", sa_column_kwargs={"comment": "当前上传票据；过期后置空"})
