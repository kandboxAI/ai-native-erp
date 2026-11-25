"""内置出货 Excel 模板。已发布的模板版本保留渲染口径。"""
from collections import defaultdict
from decimal import Decimal
from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.page import PageMargins

from .shipment_companion_forms import xlsx_domestic, xlsx_v4
from .shipment_english_forms import xlsx_v5
from .shipment_export_templates import xlsx_v2, xlsx_v3

TITLES = {
    "packing_list": "装箱单 Packing List",
    "customs_draft": "出口报关资料草稿 Customs Declaration Draft",
    "invoice_request": "开票申请单",
    "commercial_invoice": "商业发票 Commercial Invoice",
    "domestic_invoice": "发票",
    "domestic_contract": "合同",
}


def write_row(sheet, values):
    sheet.append([
        format(value, "f") if isinstance(value, Decimal) and len(value.normalize().as_tuple().digits) > 15 else value
        for value in values
    ])
    for cell in sheet[sheet.max_row]:
        if isinstance(cell.value, str):
            cell.data_type = "s"
        cell.alignment = Alignment(vertical="center", wrap_text=True)


def packing_rows(snapshot):
    goods = {row["line_no"]: row for row in snapshot["goods"]}
    for box in snapshot["boxes"]:
        for index, entry in enumerate(box["items"]):
            line = goods[entry["line_no"]]
            yield [
                box["box_no"], line["item_no"], line["item_name"], line["drawing_no"],
                Decimal(entry["quantity"]), line["unit"], Decimal(entry["net_weight_kg"]),
                Decimal(box["gross_weight_kg"]) if index == 0 else None,
                " × ".join(box[key] for key in ("length_cm", "width_cm", "height_cm")) if index == 0 else "",
            ]


def customs_rows(snapshot):
    for row in snapshot["goods"]:
        details = row["customs"]
        yield [
            details.get("hs_code") or "待补", details.get("declared_name") or row["item_name"],
            details.get("origin_country") or "待补", details.get("declaration_elements") or "待补",
            row["drawing_no"], Decimal(row["quantity"]), row["unit"], Decimal(row["net_weight_kg"]),
            row["currency"], Decimal(row["price"]), Decimal(row["amount"]),
        ]


def invoice_rows(snapshot):
    for row in snapshot["goods"]:
        yield [
            row["sales_order_no"], row["item_no"], row["item_name"], row["drawing_no"],
            Decimal(row["quantity"]), row["unit"], row["currency"], row["price_basis"],
            Decimal(row["price"]), Decimal(row["amount"]),
        ]


def xlsx_v1(snapshot, kind, metadata, shipment_status):
    book = Workbook()
    sheet = book.active
    sheet.title = TITLES[kind].split(" ")[0]
    header = snapshot["header"]
    state = "已取消" if shipment_status == "cancelled" else "历史版本" if metadata["is_superseded"] else ""
    indicators = [item for item in (state, "出货预览" if metadata["is_preview"] else "") if item]
    write_row(sheet, [" · ".join([TITLES[kind], *indicators])])
    write_row(sheet, ["出货单号 Shipment No.", snapshot["shipment_no"], "出货日期 Date", snapshot["business_date"], "版本 Revision", metadata["revision_no"]])
    write_row(sheet, ["发货方 Shipper", header["seller_name"], "地址 Address", header["seller_address"]])
    write_row(sheet, ["收货方 Consignee", header["buyer_name"], "地址 Address", header["buyer_address"]])
    if header["trade_mode"] == "export":
        write_row(sheet, ["目的地 Destination", header["destination_country"], "贸易术语 Trade Term", header["trade_term"], "运输单号 Transport No.", header["transport_no"]])
    else:
        write_row(sheet, ["购方税号", header["buyer_tax_no"], "用途", "财务开票资料 · 未开票"])
    if kind == "customs_draft":
        write_row(sheet, ["由报关人员核对申报要素及所需随附资料后办理申报"])
    if kind == "packing_list":
        write_row(sheet, ["箱数 Boxes", len(snapshot["boxes"]), "总净重 Net kg", sum(Decimal(row["net_weight_kg"]) for row in snapshot["goods"]),
                          "总毛重 Gross kg", sum(Decimal(box["gross_weight_kg"]) for box in snapshot["boxes"])])
        headers = ["箱号 Box", "货号 Item No.", "货品 Description", "图号 Drawing", "数量 Qty", "单位 Unit",
                   "净重 Net kg", "箱毛重 Gross kg", "箱尺寸 L×W×H cm"]
        data = packing_rows(snapshot)
    elif kind == "customs_draft":
        headers = ["HS 编码", "申报品名 Description", "原产国 Origin", "申报要素", "图号 Drawing", "数量 Qty", "单位 Unit",
                   "净重 Net kg", "币种 Currency", "单价 Unit Price", "金额 Amount"]
        data = customs_rows(snapshot)
    else:
        headers = ["订单号 Order No.", "货号 Item No.", "货品 Description", "图号 Drawing", "数量 Qty", "单位 Unit",
                   "币种 Currency", "价格口径 Price Basis", "单价 Unit Price", "金额 Amount"]
        data = invoice_rows(snapshot)
    write_row(sheet, headers)
    header_row = sheet.max_row
    for row in data:
        write_row(sheet, row)
    if kind != "packing_list":
        totals = defaultdict(Decimal)
        for row in snapshot["goods"]:
            totals[row["currency"], row["price_basis"]] += Decimal(row["amount"])
        for (currency, basis), total in totals.items():
            write_row(sheet, ["合计 Total", currency, basis, total])
    sheet.merge_cells(start_row=1, start_column=1, end_row=1, end_column=len(headers))
    for cell in [sheet["A1"], *sheet[header_row]]:
        cell.font = Font(bold=True, color="FFFFFF", size=13 if cell.row == 1 else 11)
        cell.fill = PatternFill("solid", fgColor="20557D")
    for index in range(1, len(headers) + 1):
        sheet.column_dimensions[get_column_letter(index)].width = 29 if index <= 4 else 15
    sheet.row_dimensions[1].height = 28
    sheet.row_dimensions[header_row].height = 29
    sheet.freeze_panes = f"A{header_row + 1}"
    sheet.print_title_rows = f"1:{header_row}"
    sheet.page_setup.orientation = "landscape"
    sheet.page_setup.paperSize = sheet.PAPERSIZE_A4
    sheet.page_setup.fitToWidth = 1
    sheet.page_setup.fitToHeight = 0
    sheet.sheet_properties.pageSetUpPr.fitToPage = True
    sheet.page_margins = PageMargins(left=.25, right=.25, top=.35, bottom=.35)
    stream = BytesIO()
    book.save(stream)
    return stream.getvalue()


RENDERERS = {
    "shipment_xlsx_v1": xlsx_v1,
    "shipment_xlsx_v2": xlsx_v2,
    "shipment_xlsx_v3": xlsx_v3,
    "shipment_xlsx_v4": xlsx_v4,
    "shipment_xlsx_v5": xlsx_v5,
    "shipment_xlsx_domestic_v1": xlsx_domestic,
}
