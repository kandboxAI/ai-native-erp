"""真实询价导出；业务权限由调用方验证，只输出明确的对客字段。"""
from io import BytesIO
from decimal import Decimal
from openpyxl import Workbook


def workbook(data):
    book = Workbook()
    sheet = book.active
    sheet.title = "报价明细"
    status = {"quoted": "已审核", "voided": "已作废，仅供存档", "review": "待初审，仅内部预览",
              "final_review": "待复审，仅内部预览"}.get(data["status_code"], "草稿，仅内部预览")
    sheet.append(["报价单", data["quote_no"], "修订", data["revision"], "状态", status])
    sheet.append(["客户", data["customer_name_snapshot"], "币种", data["currency"], "价格口径", "未税单价；交期为自然日"])
    sheet.append(["序号", "图号", "图纸版本", "描述", "询价数量", "单位", "客户材料", "报价材料", "净重量(kg)", "单价", "交期(天)", "表面处理", "客户备注"])
    entries = []
    for line in data["lines"]:
        entries.append(line)
        entries.extend({**line, "quantity": tier["quantity"], "unit_price": tier["unit_price"]} for tier in line.get("quantity_tiers", []))
    for index, line in enumerate(entries, 1):
        sheet.append([index, line["drawing_no"], line["drawing_revision"], line["description"],
            Decimal(line["quantity"]), line["unit_name"], line["customer_material"], line["quoted_material"],
            Decimal(line["weight_kg"]) if line["weight_kg"] is not None else None,
            Decimal(line["unit_price"]) if line["unit_price"] is not None else None,
            line["lead_days"], line["surface_treatment"], line["note"]])
    for row in sheet:
        for cell in row:
            if isinstance(cell.value, str):
                cell.data_type = "s"  # 客户文本不能成为 Excel 公式。
    sheet.freeze_panes = "A4"
    sheet.auto_filter.ref = sheet.dimensions
    for column in sheet.columns:
        sheet.column_dimensions[column[0].column_letter].width = 22
    output = BytesIO()
    book.save(output)
    return output.getvalue()
