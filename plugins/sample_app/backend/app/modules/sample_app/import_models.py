"""快盒财务来源台账。保留行级证据，不将汇总数冒充已入账的业务流水。"""
from typing import Any
from datetime import datetime
from uuid import UUID

from sqlalchemy import Index, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel

from app.framework.db.models import (
    id_field, org_field, created_at_field, updated_at_field, audit_user_field,
    deleted_at_field, flex_form_field,
)


class FinanceImportRow(SQLModel, table=True):
    __tablename__ = "sample_app_import_row"
    __table_args__ = (
        Index("uk_sample_app_import_row_org_id_source_sha256_sheet_name_row_no", "org_id", "source_sha256", "sheet_name", "row_no", unique=True,
              postgresql_where=text("deleted_at is null")),
        {"comment": "财务导入来源行：一行为一个组织某份来源文件的一行证据；不直接参与应收、工资及现金余额计算"},
    )
    id: UUID = id_field()
    org_id: UUID = org_field(index=False, ondelete="RESTRICT")
    source_name: str = Field(max_length=255, sa_column_kwargs={"comment": "来源文件名，不含本机绝对路径"})
    source_sha256: str = Field(max_length=64, sa_column_kwargs={"comment": "来源文件SHA256，用于重复导入识别"})
    sheet_name: str = Field(max_length=64, sa_column_kwargs={"comment": "来源工作表名称"})
    row_no: int = Field(sa_column_kwargs={"comment": "来源Excel行号，从1开始"})
    source_cells: dict[str, Any] = Field(sa_type=JSONB, sa_column_kwargs={"comment": "来源列名到单元格标量值的映射；仅字符串、数字或空值，无内部实体ID；账号脱敏；敏感：个人，不发布给AI"})
    handling_key: str = Field(max_length=32, sa_column_kwargs={"comment": "程序处理标识：imported、partial、reference、note；仅由导入器维护"})
    handling_note: str = Field(sa_type=Text, sa_column_kwargs={"comment": "业务映射结果、数据差异和待确认原因；敏感：内部"})
    employee_id: UUID | None = Field(default=None, foreign_key="sample_app_employee.id", ondelete="RESTRICT", sa_column_kwargs={"comment": "关联发薪员工；引用sample_app_employee；姓名仅留原始证据快照"})
    project_id: UUID | None = Field(default=None, foreign_key="sample_app_project.id", ondelete="RESTRICT", sa_column_kwargs={"comment": "关联项目；引用sample_app_project"})
    created_at: datetime = created_at_field()
    created_by: UUID | None = audit_user_field("创建人；本次离线导入为系统任务时为空", ondelete="RESTRICT")
    updated_at: datetime = updated_at_field()
    updated_by: UUID | None = audit_user_field("修改人", ondelete="RESTRICT")
    deleted_at: datetime | None = deleted_at_field()
    deleted_by: UUID | None = audit_user_field("删除人", ondelete="RESTRICT")
    flex_form: dict[str, Any] = flex_form_field()
