from datetime import date
from decimal import Decimal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field


class InvoiceDescription(BaseModel):
    model_config = ConfigDict(extra="forbid")
    file_name: str = Field(min_length=1, max_length=255)
    content_type: str = Field(pattern=r"^(application/pdf|image/jpeg|image/png|image/webp)$")
    file_size: int = Field(gt=0, le=20 * 1024 * 1024)
    content_md5: str = Field(min_length=22, max_length=32)


class StrictBody(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PrepareBody(StrictBody):
    request_key: str = Field(min_length=8, max_length=64, description="为本次报销生成的唯一标识；重试保持不变，修改内容时换新标识")
    subject: str | None = Field(default=None, max_length=128, description="用户明确提供的报销事由；未提供则留空，必须询问，不可猜测")
    amount: Decimal | None = Field(default=None, gt=0, max_digits=18, decimal_places=2, description="用户认可的本次报销金额；建议用十进制字符串")
    occurred_on: date | None = Field(default=None, description="费用发生日期 YYYY-MM-DD；不确定则询问")
    invoice_title: str | None = Field(default=None, max_length=128, description="发票购买方名称，必须按发票原文抄录，不可改写成简称或猜测组织")
    invoice_manifest_hash: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    files: list[InvoiceDescription] = Field(default_factory=list, max_length=50, description="准备时声明的完整发票清单；没有原件信息时必须询问，不创建可变附件申请")
    previous_request_id: UUID | None = Field(default=None, description="整体重新准备时指定要取代的本人旧申请；旧申请会失效；新请求须使用新幂等标识")


class RequestBody(StrictBody):
    request_id: UUID


class ChangePasswordBody(StrictBody):
    current_password: str = Field(min_length=1, max_length=128, description="当前登录密码")
    new_password: str = Field(min_length=1, max_length=128, description="新密码")
    confirm_password: str = Field(min_length=1, max_length=128, description="再次输入新密码")


class TicketBody(RequestBody):
    files: list[InvoiceDescription] = Field(min_length=1, max_length=50)


class CompleteBody(RequestBody):
    file_id: UUID


class BindingBody(StrictBody):
    user_id: UUID
    employee_id: UUID
    previous_user_id: UUID | None = None


class SoftwareClaimItemBody(StrictBody):
    occurred_on: date | None = Field(default=None, description="凭证上显示的扣款或消费日期 YYYY-MM-DD；读取不到则留空，并询问用户")
    billing_month: str | None = Field(default=None, pattern=r"^\d{4}-(0[1-9]|1[0-2])$",
                                      description="凭证明确标注的所属账期 YYYY-MM（如账单周期）；有则优先，无则取扣款日期所在月")
    amount: Decimal = Field(gt=0, max_digits=18, decimal_places=2, description="本条金额（元）")
    merchant_name: str = Field(min_length=1, max_length=128, description="商户或订阅名称，按凭证原文")
    source_code: str = Field(pattern=r"^(wechat|alipay|bank_card|invoice)$", description="wechat / alipay / bank_card / invoice")
    note: str | None = Field(default=None, max_length=255, description="可选说明")


class SoftwareClaimPrepareBody(StrictBody):
    request_key: str = Field(min_length=8, max_length=64, description="幂等标识；重试保持不变")
    period_month: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$", description="工资月份 YYYY-MM；例如 2026-10")
    items: list[SoftwareClaimItemBody] = Field(min_length=1, max_length=50, description="AI 从微信/支付宝扣款或 invoice 摘录的明细")
    files: list[InvoiceDescription] = Field(default_factory=list, max_length=20, description="凭证截图或 invoice 原件清单；确认前必须传齐")
    evidence_manifest_hash: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
