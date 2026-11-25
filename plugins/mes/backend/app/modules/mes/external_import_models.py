"""外部台账导入追溯；原始行快照只作审计，不替代业务关系和库存流水。"""
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import CheckConstraint, Index, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel
from app.framework.db.models import (id_field, org_field, created_at_field, updated_at_field,
    audit_user_field, flex_form_field)


class MesExternalImportRow(SQLModel, table=True):
    __tablename__ = "mes_external_import_row"
    __table_args__ = (
        Index("uk_mes_external_import_row_source", "org_id", "source_system_key", "record_type_key", "source_record_no", unique=True),
        CheckConstraint("source_row_no > 1", name="valid_source_row"),
        {"comment": "外部导入追溯；一行代表一条已成功导入的原始数据行及其真实业务对象，不是运行时任务或演示数据。"},
    )
    id: UUID = id_field()
    org_id: UUID = org_field(index=False, ondelete="RESTRICT")
    source_system_key: str = Field(max_length=40, sa_column_kwargs={"comment": "已定义来源程序标识；gendanbao 为跟单宝导出，customer_roster 为客户确认人员清单，不接受任意代码导入"})
    record_type_key: str = Field(max_length=40, sa_column_kwargs={"comment": "固定行协议标识；route_step、production_order、work_order、stock_balance、equipment_archive、person_roster"})
    source_record_no: str = Field(max_length=256, sa_column_kwargs={"comment": "来源行的稳定外部编号；按行协议为工单号、货品编码、路线及顺序或库存规格组合摘要，不是内部外键"})
    source_file_name: str = Field(max_length=256, sa_column_kwargs={"comment": "原始 Excel 文件名；不保存本机绝对路径"})
    source_file_sha256: str = Field(max_length=64, sa_column_kwargs={"comment": "导入文件内容 SHA256，用于追溯原始文件"})
    source_sheet_name: str = Field(max_length=64, sa_column_kwargs={"comment": "原始工作表名称或 JSON 数组路径"})
    source_row_no: int = Field(sa_column_kwargs={"comment": "原始 Excel 行号；JSON 数组索引加2，保留第1行作结构标识"})
    source_row_sha256: str = Field(max_length=64, sa_column_kwargs={"comment": "规范化原始行摘要；重复导入值变化时拒绝覆盖"})
    source_values_snapshot: dict[str, Any] = Field(sa_type=JSONB, sa_column_kwargs={"comment": "按固定行协议保存原始列名到单元格值的只追加审计快照；含历史创建人姓名等个人信息，不进入 AI，不作为业务明细或统计事实使用"})
    production_order_id: UUID | None = Field(default=None, foreign_key="mes_production_order.id", ondelete="RESTRICT", sa_column_kwargs={"comment": "导入的生产项目；仅 production_order 行填写"})
    work_order_id: UUID | None = Field(default=None, foreign_key="mes_work_order.id", ondelete="RESTRICT", sa_column_kwargs={"comment": "导入的货品执行工单；仅 work_order 行填写"})
    template_operation_id: UUID | None = Field(default=None, foreign_key="mes_process_template_operation.id", ondelete="RESTRICT", sa_column_kwargs={"comment": "导入的路线工序；仅 route_step 行填写"})
    item_id: UUID | None = Field(default=None, foreign_key="md_item.id", ondelete="RESTRICT", sa_column_kwargs={"comment": "库存余额对应的真实物料；仅 stock_balance 行填写"})
    stock_order_id: UUID | None = Field(default=None, foreign_key="inv_stock_order.id", ondelete="RESTRICT", sa_column_kwargs={"comment": "本行期初余额对应的真实库存入账单；零余额行可空，不复制累计出入库数为流水"})
    equipment_id: UUID | None = Field(default=None, foreign_key="mes_equipment.id", ondelete="RESTRICT", sa_column_kwargs={"comment": "导入的物理设备；仅 equipment_archive 行填写，适用工艺由设备工艺关系表保存"})
    production_person_id: UUID | None = Field(default=None, foreign_key="mes_production_person.id", ondelete="RESTRICT", sa_column_kwargs={"comment": "导入的生产人员身份；仅 person_roster 行填写，工艺资格使用独立有效期关系表"})
    created_at: datetime = created_at_field()
    created_by: UUID | None = audit_user_field("实际导入人；租户用户，不冒充原系统创建人", ondelete="RESTRICT")
    updated_at: datetime = updated_at_field()
    updated_by: UUID | None = audit_user_field("实际导入人；追溯行成功后不覆盖", ondelete="RESTRICT")
    flex_form: dict[str, Any] = flex_form_field()
