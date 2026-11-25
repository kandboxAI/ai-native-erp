from decimal import Decimal
from io import BytesIO
from xml.sax.saxutils import escape

from openpyxl import Workbook
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from typing import Any

Quote = Any


def export_rows(quote: Quote) -> list[list]:
    inputs, result = quote.inputs, quote.result
    rows = [
        ["状态", "已审核报价" if quote.approved_by else "内部评估（未审核）"],
        ["零件", inputs["name"]],
        ["报价编号", quote.id],
        ["依据修订", quote.version_no],
        ["数量", result["quantity"]],
        ["材料", inputs["specs"]["material"]],
        ["材料参考单价", inputs["specs"].get("material_price")],
        ["材料计价单位", "元/" + inputs["specs"].get("material_price_unit_code", "kg")],
        ["材料计费长度 mm/件", inputs["specs"].get("material_billing_length", "")],
        ["表面处理", inputs["specs"].get("treatment", "")],
        ["单件毛坯重量 kg", result["stock_weight_kg"]],
        ["单件材料费 元", result["material_unit"]],
        ["单件加工费 元", result["machining_unit"]],
        ["单件外协费 元", result["external_unit"]],
        ["其他批次费用 元", result["other_batch"]],
        ["单件制造成本 元", result["unit_cost"]],
        ["不含税单价 元", result["unit_price"]],
        ["不含税总价 元", result["total_price"]],
        ["核算口径", result["basis"]],
        ["审核人", quote.approved_by or "未审核"],
    ]
    if result.get("is_reference"):
        rows.append(["报价提示", "参考报价，请报价人员核对并调整"])
        rows.extend(["待核对", warning] for warning in result.get("warnings", []))
    weight = result.get("weight_estimate")
    if weight:
        label = "外形估重（未扣孔槽）" if weight["method_key"] == "model_bounds" else "预计净重"
        rows.extend([
            [f"单件{label} kg", weight["estimated_weight_kg"] if weight["estimated_weight_kg"] is not None else "待补充模型体积或密度"],
            [f"整批{label} kg", weight["estimated_total_weight_kg"] or "—"],
            ["整批毛坯重量 kg", weight["stock_total_weight_kg"] or "—"],
            ["重量计算密度 g/cm³", weight["density_g_cm3"] or "—"],
            ["重量计算依据", weight["basis"]],
        ])
    return rows


def xlsx_bytes(quote: Quote) -> bytes:
    workbook = Workbook()
    summary = workbook.active
    summary.title = "核价明细"
    for row in export_rows(quote):
        summary.append(row)
    summary.column_dimensions["A"].width = 26
    summary.column_dimensions["B"].width = 85
    sheet = workbook.create_sheet("工序依据")
    sheet.append(
        [
            "工序",
            "设备",
            "预估工时 h/件",
            "费率元/小时",
            "说明",
            "工时估算依据",
            "估算假设",
            "估算数量",
            "计价方式",
            "外协单价",
            "计费重量口径",
            "最低收费元/件",
            "外协计价单位",
            "计费面积mm²（空白用模型总面积）",
        ]
    )
    for operation in quote.inputs["operations"]:
        sheet.append(
            [
                operation["name"],
                operation.get("machine", ""),
                snapshot_hours(operation, quote.result["quantity"]),
                operation.get("hourly_rate", ""),
                operation.get("note", ""),
            ]
            + [
                operation.get("estimate_basis", ""),
                "；".join(operation.get("assumptions", [])),
                operation.get("estimate_quantity", ""),
                "外协按规则" if operation.get("pricing_mode_code") == "external" else "按工时",
                operation.get("external_rate", ""),
                operation.get("external_weight_method_key", ""),
                operation.get("external_minimum_unit", ""),
                operation.get("external_price_unit_code", "kg"),
                operation.get("external_area_mm2", ""),
            ]
        )
    for column in "ABCDEFGHIJKLMN":
        sheet.column_dimensions[column].width = 24
    # 图纸/人工输入作为文本导出，避免以等号开头的备注被 Excel 当作公式执行。
    for worksheet in workbook:
        worksheet.freeze_panes = "A2"
        for row in worksheet:
            for cell in row:
                if isinstance(cell.value, str):
                    cell.data_type = "s"
    output = BytesIO()
    workbook.save(output)
    return output.getvalue()


def snapshot_hours(operation: dict, quantity: int):
    if "unit_hours" in operation:
        return operation["unit_hours"]
    # 历史快照不改写，导出时按当时数量折算原有工时。
    if operation.get("setup_minutes") is None or operation.get("cycle_minutes") is None:
        return ""
    return str(
        (Decimal(str(operation["cycle_minutes"])) + Decimal(str(operation["setup_minutes"])) / quantity) / 60
    )


def pdf_bytes(quote: Quote) -> bytes:
    pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
    style = ParagraphStyle("Chinese", fontName="STSong-Light", fontSize=10, leading=15, wordWrap="CJK")
    heading = ParagraphStyle("Heading", parent=style, fontSize=18, leading=24, spaceAfter=16)
    output = BytesIO()
    document = SimpleDocTemplate(
        output, pagesize=A4, rightMargin=36, leftMargin=36, topMargin=32, bottomMargin=32
    )
    title = "加工报价核算单" if quote.approved_by else "内部评估核算单（未审核）"
    story = [Paragraph(title, heading)]
    rows = [[Paragraph(escape(str(value)), style) for value in row] for row in export_rows(quote)]
    table = Table(rows, colWidths=[135, 385], hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ROWBACKGROUNDS", (0, 0), (-1, -1), [colors.HexColor("#f3f5f7"), colors.white]),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
            ]
        )
    )
    story.extend([table, Spacer(1, 18), Paragraph("工序与估时依据", heading)])
    for index, operation in enumerate(quote.inputs["operations"], 1):
        if operation.get("pricing_mode_code") == "external":
            unit = operation.get("external_price_unit_code", "kg")
            line = f"{index}. {operation['name']}；外协单价 {operation.get('external_rate')} 元/{unit}，"
            line += (
                "按计费表面积"
                if unit == "m2"
                else "按毛坯重量"
                if operation.get("external_weight_method_key") == "stock"
                else "按模型净重量"
            )
            line += (
                f"，最低收费 {operation.get('external_minimum_unit', '0')} 元/件。{operation.get('note', '')}"
            )
        else:
            line = (
                f"{index}. {operation['name']} / {operation['machine']}；"
                f"预估工时 {snapshot_hours(operation, quote.result['quantity'])} 小时/件，"
                f"费率 {operation['hourly_rate']} 元/小时。{operation['note']}"
            )
        story.extend([Paragraph(escape(line), style), Spacer(1, 8)])
        if operation.get("estimate_basis"):
            basis = "工时为模型预估：" + operation["estimate_basis"]
            if operation.get("assumptions"):
                basis += "；假设：" + "；".join(operation["assumptions"])
            story.extend([Paragraph(escape(basis), style), Spacer(1, 8)])
    document.build(story)
    return output.getvalue()
