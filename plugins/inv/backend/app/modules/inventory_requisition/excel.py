from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill


STATUS_LABELS = {
    "submitted": "待审批",
    "approved": "待发放",
    "rejected": "已驳回",
    "issued": "已发放（未记录签收）",
    "withdrawn": "已撤回",
    "pending_receipt": "待签收",
    "receipt_exception": "收货异常",
    "received": "已签收",
}


def build_requisition_workbook(items: list[dict]) -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "物资领用台账"
    sheet.append(["提交批次", "申请单号", "仓库", "申请时间", "申请人", "部门", "用途", "物资编码", "物资名称", "规格", "申请数量", "单位", "状态", "审批意见", "审批时间", "发放时间", "出库单号", "实际发放数量", "签收人", "签收时间", "申请来源组织"])
    for item in items:
        for line in item.get("lines") or [{}]:
            sheet.append([
                item.get("submission_batch_no"), item.get("request_no"), item.get("warehouse_name"),
                item.get("created_at"), item.get("applicant_name_snapshot"),
                item.get("department_name_snapshot"), item.get("purpose"), line.get("item_no_snapshot"),
                line.get("item_name_snapshot"), line.get("specification_snapshot"), float(line.get("quantity") or 0),
                line.get("unit_name") or line.get("unit_code_snapshot"), STATUS_LABELS.get(item.get("status_code"), item.get("status_code")),
                item.get("approval_note"), item.get("approved_at"), item.get("issued_at"), item.get("stock_order_no"),
                float(line["issued_quantity"]) if line.get("issued_quantity") is not None else None,
                item.get("received_by_name_snapshot"), item.get("received_at"),
                item.get("applicant_org_name_snapshot"),
            ])
    fill = PatternFill("solid", fgColor="1F4E78")
    for cell in sheet[1]:
        cell.font = Font(color="FFFFFF", bold=True)
        cell.fill = fill
    sheet.freeze_panes = "A2"
    for column in sheet.columns:
        letter = column[0].column_letter
        sheet.column_dimensions[letter].width = min(36, max(12, max(len(str(cell.value or "")) for cell in column) + 2))
    stream = BytesIO()
    workbook.save(stream)
    return stream.getvalue()

