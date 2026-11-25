"""表模型（md_supplier_category）。

初始版本由 docs/foundation-platform/data-dictionary/tools/gen_models.py 按数据字典生成，之后以本文件为准维护。
"""
from datetime import datetime
from typing import Any
from uuid import UUID
from sqlalchemy import Index, text
from sqlmodel import Field, SQLModel
from app.framework.db.models import audit_user_field, bool_field, created_at_field, deleted_at_field, flex_form_field, id_field, updated_at_field

class MdSupplierCategory(SQLModel, table=True):
    """供应商分类：一行为一个供应商分类。"""
    __tablename__ = 'md_supplier_category'
    __table_args__ = (Index('uk_md_supplier_category_category_name', 'category_name', unique=True, postgresql_where=text('deleted_at is null')), {'comment': '供应商分类：一行为一个供应商分类。'})
    id: UUID = id_field()
    category_name: str = Field(max_length=128, nullable=False, sa_column_kwargs={'comment': '分类名称'})
    is_active: bool = bool_field('是否启用', default=True)
    created_at: datetime = created_at_field()
    created_by: UUID | None = audit_user_field('创建人；系统任务创建时为空', ondelete='SET NULL')
    updated_at: datetime = updated_at_field()
    updated_by: UUID | None = audit_user_field('修改人', ondelete='SET NULL')
    deleted_at: datetime | None = deleted_at_field()
    deleted_by: UUID | None = audit_user_field('删除人；与删除时间同时出现', ondelete='SET NULL')
    flex_form: dict[str, Any] = flex_form_field('扩展字段；租户自定义字段，结构见动态表单定义；默认 {}')
