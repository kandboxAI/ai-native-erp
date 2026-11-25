"""供应商物料报价，由库存插件拥有，不改变存量单据计价。"""
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID
from sqlalchemy import CheckConstraint, Index, Numeric, Text, text
from sqlmodel import SQLModel, Field
from app.framework.db.models import (id_field, org_field, audit_user_field, created_at_field, updated_at_field,
    deleted_at_field, bool_field, flex_form_field)


class InvSupplierPrice(SQLModel, table=True):
    __tablename__ = "inv_supplier_price"
    __table_args__ = (
        Index("idx_inv_supplier_price_org_id_supplier_id_item_id", "org_id", "supplier_id", "item_id"),
        CheckConstraint("unit_price >= 0", name="ck_inv_supplier_price_nonnegative_price"),
        CheckConstraint("valid_to is null or valid_to > valid_from", name="ck_inv_supplier_price_valid_period"),
        {"comment": "供应商采购价格；一行代表组织内某供应商物料及币种在有效区间的基本单位单价。只供选价参考，不自动改写库存或历史单据。"})
    id: UUID = id_field()
    org_id: UUID = org_field(ondelete="RESTRICT")
    supplier_id: UUID = Field(foreign_key="md_supplier.id", ondelete="RESTRICT", sa_column_kwargs={"comment": "供应商；最小名称读取契约，不发布联系人或银行信息"})
    item_id: UUID = Field(foreign_key="md_item.id", ondelete="RESTRICT", sa_column_kwargs={"comment": "采购物料；与库存唯一物料目录一致"})
    unit_code: str = Field(max_length=64, sa_column_kwargs={"comment": "计价基本单位快照；字典 md_unit，保存时取物料基本单位"})
    currency_code: str = Field(default="CNY", max_length=64, sa_column_kwargs={"comment": "币种；字典 md_currency"})
    unit_price: Decimal = Field(sa_type=Numeric(18, 2), sa_column_kwargs={"comment": "每基本单位采购价格；商业机密，默认不发布到 AI"})
    valid_from: date = Field(sa_column_kwargs={"comment": "生效日期；有效区间含此日"})
    valid_to: date | None = Field(default=None, sa_column_kwargs={"comment": "失效日期；有效区间不含此日，空表示持续有效"})
    note: str | None = Field(default=None, sa_type=Text, sa_column_kwargs={"comment": "报价说明；商业机密，默认不发布到 AI"})
    is_active: bool = bool_field("是否启用该报价", default=True)
    version_no: int = Field(default=1, sa_column_kwargs={"comment": "并发更新修订号"})
    created_at: datetime = created_at_field()
    created_by: UUID | None = audit_user_field("创建人", ondelete="SET NULL")
    updated_at: datetime = updated_at_field()
    updated_by: UUID | None = audit_user_field("修改人", ondelete="SET NULL")
    deleted_at: datetime | None = deleted_at_field()
    deleted_by: UUID | None = audit_user_field("删除人", ondelete="SET NULL")
    flex_form: dict[str, Any] = flex_form_field()
