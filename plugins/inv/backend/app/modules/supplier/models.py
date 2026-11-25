"""表模型（md_supplier、md_supplier_bank_account）。

初始版本由 docs/foundation-platform/data-dictionary/tools/gen_models.py 按数据字典生成，之后以本文件为准维护。
"""
from datetime import datetime
from typing import Any
from uuid import UUID
from sqlalchemy import Index, Text, text
from sqlmodel import Field, SQLModel
from app.framework.db.models import audit_user_field, bool_field, created_at_field, deleted_at_field, flex_form_field, id_field, updated_at_field

class MdSupplier(SQLModel, table=True):
    """供应商：一行为一个供应商。"""
    __tablename__ = 'md_supplier'
    __table_args__ = (Index('uk_md_supplier_supplier_no', 'supplier_no', unique=True, postgresql_where=text('deleted_at is null')), Index('uk_md_supplier_party_id', 'party_id', unique=True, postgresql_where=text('deleted_at is null')), {'comment': '供应商：一行为一个供应商（主体的供应商角色）。名称、主体类型取自 md_party；身份（法定名称、信用代码）在 md_organization。'})
    id: UUID = id_field()
    supplier_no: str = Field(max_length=64, nullable=False, sa_column_kwargs={'comment': '供应商编号'})
    party_id: UUID = Field(foreign_key='md_party.id', nullable=False, sa_column_kwargs={'comment': '主体；供应商是主体的角色，名称与主体类型取自主体（机构或个体户）'}, ondelete='RESTRICT')
    category_id: UUID | None = Field(default=None, foreign_key='md_supplier_category.id', index=True, nullable=True, sa_column_kwargs={'comment': '分类'}, ondelete='RESTRICT')
    contact_name: str | None = Field(default=None, max_length=64, nullable=True, sa_column_kwargs={'comment': '联系人；敏感：个人'})
    contact_phone: str | None = Field(default=None, max_length=32, nullable=True, sa_column_kwargs={'comment': '联系电话；敏感：个人'})
    settlement_method_code: str | None = Field(default=None, max_length=64, nullable=True, sa_column_kwargs={'comment': '结算方式；字典 md_settlement_method'})
    settlement_cycle_code: str | None = Field(default=None, max_length=64, nullable=True, sa_column_kwargs={'comment': '结算周期；字典 md_settlement_cycle'})
    is_active: bool = bool_field('是否启用', default=True)
    created_at: datetime = created_at_field()
    created_by: UUID | None = audit_user_field('创建人；系统任务创建时为空', ondelete='SET NULL')
    updated_at: datetime = updated_at_field()
    updated_by: UUID | None = audit_user_field('修改人', ondelete='SET NULL')
    deleted_at: datetime | None = deleted_at_field()
    deleted_by: UUID | None = audit_user_field('删除人；与删除时间同时出现', ondelete='SET NULL')
    flex_form: dict[str, Any] = flex_form_field('扩展字段；租户自定义字段，结构见动态表单定义；默认 {}')

class MdSupplierBankAccount(SQLModel, table=True):
    """供应商收款账户：一行为一个供应商的一个收款账户。"""
    __tablename__ = 'md_supplier_bank_account'
    __table_args__ = ({'comment': '供应商收款账户：一行为一个供应商的一个收款账户。商业机密，单独授权，加密存储。'},)
    id: UUID = id_field()
    supplier_id: UUID = Field(foreign_key='md_supplier.id', index=True, nullable=False, sa_column_kwargs={'comment': '供应商'}, ondelete='RESTRICT')
    account_name: str = Field(max_length=128, nullable=False, sa_column_kwargs={'comment': '户名；敏感：机密'})
    account_no_encrypted: str = Field(sa_type=Text, nullable=False, sa_column_kwargs={'comment': '账号（密文）；敏感：机密'})
    account_no_masked: str | None = Field(default=None, max_length=64, nullable=True, sa_column_kwargs={'comment': '账号（脱敏）；敏感：机密'})
    bank_name: str | None = Field(default=None, max_length=128, nullable=True, sa_column_kwargs={'comment': '开户行；敏感：机密'})
    is_primary: bool = bool_field('是否主要账户', default=False)
    created_at: datetime = created_at_field()
    created_by: UUID | None = audit_user_field('创建人；系统任务创建时为空', ondelete='SET NULL')
    updated_at: datetime = updated_at_field()
    updated_by: UUID | None = audit_user_field('修改人', ondelete='SET NULL')
    deleted_at: datetime | None = deleted_at_field()
    deleted_by: UUID | None = audit_user_field('删除人；与删除时间同时出现', ondelete='SET NULL')
    flex_form: dict[str, Any] = flex_form_field('扩展字段；租户自定义字段，结构见动态表单定义；默认 {}')
