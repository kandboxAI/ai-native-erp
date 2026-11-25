"""客户出口样式：英文商务单据和四联中文报关资料。"""
from collections import defaultdict
from datetime import date
from decimal import Decimal
from io import BytesIO
from math import ceil
from unicodedata import east_asian_width

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.page import PageMargins

from .shipment_customs_form import customer_customs_workbook


MONEY = "#,##0.00"
PRICE = "#,##0.000###"
MEASURE = "#,##0.###"
SUBTLE = "E9EFF6"
INK = "1C2D43"


def document_row(sheet, values):
    sheet.append(list(values))
    for cell in sheet[sheet.max_row]:
        value = cell.value
        if isinstance(value, Decimal) and len(value.normalize().as_tuple().digits) > 15:
            value = format(value, "f")
            cell.value = value
        if isinstance(value, str):
            cell.data_type = "s"
        cell.alignment = Alignment(vertical="center", wrap_text=True)
    return sheet.max_row


def merged(sheet, start, end, value):
    if start < end:
        sheet.merge_cells(start_row=sheet.max_row, start_column=start, end_row=sheet.max_row, end_column=end)
    cell = sheet.cell(sheet.max_row, start)
    cell.value = value
    if isinstance(value, str):
        cell.data_type = "s"
    cell.alignment = Alignment(vertical="center", wrap_text=True)
    return cell


def sheet_with_title(book, name, title, widths, state=""):
    sheet = book.create_sheet(name)
    title_row = document_row(sheet, [""])
    title_cell = merged(sheet, 1, len(widths), title)
    title_cell.font = Font(name="Microsoft YaHei", bold=True, color=INK, size=17)
    title_cell.alignment = Alignment(horizontal="center", vertical="center")
    sheet.row_dimensions[title_row].height = 34
    for column, width in enumerate(widths, 1):
        sheet.column_dimensions[get_column_letter(column)].width = width
    sheet.sheet_view.showGridLines = False
    sheet.sheet_format.defaultRowHeight = 21
    sheet.page_setup.orientation = "landscape"
    sheet.page_setup.paperSize = sheet.PAPERSIZE_A4
    sheet.page_setup.fitToWidth = 1
    sheet.page_setup.fitToHeight = 0
    sheet.sheet_properties.pageSetUpPr.fitToPage = True
    sheet.page_margins = PageMargins(left=.25, right=.25, top=.35, bottom=.35)
    if state:
        note(sheet, state, len(widths), color="9C4E00")
    return sheet


def text_height(value, width):
    if not isinstance(value, str):
        return 1
    width = max(8, int(width) - 2)
    return sum(max(1, ceil(sum(2 if east_asian_width(char) in {"W", "F"} else 1 for char in line) / width))
               for line in value.split("\n"))


def note(sheet, text, columns, color=INK):
    if not text:
        return
    row = document_row(sheet, [""])
    cell = merged(sheet, 1, columns, text)
    cell.font = Font(name="Microsoft YaHei", color=color, size=10)
    width = sum(sheet.column_dimensions[get_column_letter(i)].width for i in range(1, columns + 1))
    sheet.row_dimensions[row].height = min(180, max(22, 15 * text_height(text, width) + 6))


def paired(sheet, left_label, left, right_label, right, columns):
    split = columns // 2
    values = [left_label, left or ""] + [None] * (split - 2) + [right_label, right or ""]
    row = document_row(sheet, values)
    for column, target, value in ((2, split, left), (split + 2, columns, right)):
        cell = merged(sheet, column, target, value or "")
        cell.alignment = Alignment(horizontal="left", vertical="center", wrap_text=True)
        if isinstance(value, date):
            cell.number_format = "yyyy-mm-dd"
    for column in (1, split + 1):
        cell = sheet.cell(row, column)
        cell.font = Font(name="Microsoft YaHei", color=INK, bold=True, size=10)
        cell.fill = PatternFill("solid", fgColor=SUBTLE)
    for column, target in ((1, 1), (2, split), (split + 1, split + 1), (split + 2, columns)):
        width = sum(sheet.column_dimensions[get_column_letter(i)].width for i in range(column, target + 1))
        height = 15 * text_height(sheet.cell(row, column).value, width) + 6
        sheet.row_dimensions[row].height = max(sheet.row_dimensions[row].height or 22, min(180, height))


def number_format(cell, style):
    if style == MEASURE and isinstance(cell.value, Decimal):
        places = max(0, -cell.value.normalize().as_tuple().exponent)
        style = "#,##0" + ("." + "0" * places if places else "")
    cell.number_format = style


def grid(sheet, headers, rows, formats, *, total=None):
    header_row = document_row(sheet, headers)
    for cell in sheet[header_row]:
        cell.fill = PatternFill("solid", fgColor=SUBTLE)
        cell.font = Font(name="Microsoft YaHei", bold=True, color=INK, size=10)
    sheet.row_dimensions[header_row].height = 34
    sheet.freeze_panes = f"A{header_row + 1}"
    sheet.print_title_rows = f"1:{header_row}"
    border = Border(bottom=Side(style="hair", color="C7CFD9"))
    for values in rows:
        row = document_row(sheet, values)
        lines = 1
        for index, cell in enumerate(sheet[row], 1):
            cell.font = Font(name="Microsoft YaHei", size=10, color=INK)
            cell.border = border
            if index in formats:
                number_format(cell, formats[index])
            lines = max(lines, text_height(cell.value, sheet.column_dimensions[cell.column_letter].width))
        sheet.row_dimensions[row].height = min(130, max(22, 15 * lines + 6))
    if total is not None:
        row = document_row(sheet, total)
        for index, cell in enumerate(sheet[row], 1):
            cell.font = Font(name="Microsoft YaHei", bold=True, size=10, color=INK)
            cell.fill = PatternFill("solid", fgColor=SUBTLE)
            if index in formats:
                number_format(cell, formats[index])


def joined(items):
    return ", ".join(dict.fromkeys(item for item in items if item))


def detail(row):
    return row["order_description"] or row["item_name"]


def english_unit(row):
    return "PCS" if row["unit_code"] == "piece" else row["unit"]


def total_of(rows, key):
    return sum((Decimal(row[key]) for row in rows), Decimal(0))


def dimensions(box):
    return " × ".join(box[key] for key in ("length_cm", "width_cm", "height_cm"))


def amount_in_chinese(total, currency):
    digits = str.maketrans("0123456789.", "零壹贰叁肆伍陆柒捌玖点")
    return f"{total:.2f}".translate(digits) + f" / {currency}"


def state_message(metadata, status, *, english=False):
    labels = ("Cancelled", "Superseded", "Shipment preview") if english else ("已取消", "历史版本", "出货预览")
    return " · ".join(
        label for label, show in zip(labels, (status == "cancelled", metadata["is_superseded"], metadata["is_preview"])) if show
    )


def optional_date(value):
    return date.fromisoformat(value) if value else None


def english_headers(sheet, header, export, business_date, columns):
    paired(sheet, "From", export["seller_name_en"] or header["seller_name"], "Date", business_date, columns)
    paired(sheet, "Address", export["seller_address_en"] or header["seller_address"], "Invoice No.", export["invoice_no"], columns)
    paired(sheet, "To", header["buyer_name"], "Contract No.", export["contract_no"], columns)
    paired(sheet, "Address", header["buyer_address"], "Transport No.", header["transport_no"], columns)
    paired(sheet, "Attn / Tel.", joined([export["buyer_contact"], export["buyer_phone"]]),
           "Contact / Tel.", joined([export["seller_contact"], export["seller_phone"]]), columns)


def commercial_invoice(book, snapshot, state):
    header, goods = snapshot["header"], snapshot["goods"]
    export, currency = header["export_details"], goods[0]["currency"]
    sheet = sheet_with_title(book, "INVOICE", "COMMERCIAL INVOICE", (13, 24, 29, 22, 18, 17, 13, 12, 16, 18), state)
    english_headers(sheet, header, export, date.fromisoformat(snapshot["business_date"]), 10)
    paired(sheet, "Customer PO", joined(row["customer_po_no"] for row in goods), "Currency", currency, 10)
    paired(sheet, "EORI / VAT", export["buyer_eori_vat"], "Delivery Term", header["trade_term"], 10)
    paired(sheet, "Destination", header["destination_country"], "Country of Origin",
           joined(row["customs"].get("origin_country") for row in goods), 10)
    paired(sheet, "Payment Terms", export["payment_terms"], "Shipment No.", snapshot["shipment_no"], 10)
    grid(sheet, ["Item", "PO Number", "Description", "Drawing No.", "Material", "Tariff No.", "Qty", "Unit", "Unit Price", "Amount"],
         ([row["line_no"], row["customer_po_no"], detail(row), row["drawing_no"], row["material"], row["customs"].get("customer_tariff_no"),
           Decimal(row["quantity"]), english_unit(row), Decimal(row["price"]), Decimal(row["amount"])] for row in goods),
         {7: MEASURE, 9: MONEY, 10: MONEY}, total=["TOTAL", None, None, None, None, None, None, None, currency, total_of(goods, "amount")])
    if export["payment_instructions"]:
        note(sheet, "Payment Instructions\n" + export["payment_instructions"], 10)
    note(sheet, "Issued by: " + export["seller_contact"] if export["seller_contact"] else "", 10)
    note(sheet, "For and on behalf of / Authorized Signature", 10)


def english_packing_list(book, snapshot, state):
    header, goods, boxes = snapshot["header"], snapshot["goods"], snapshot["boxes"]
    export = header["export_details"]
    sheet = sheet_with_title(book, "PACKING LIST", "PACKING LIST", (17, 21, 26, 22, 19, 15, 13, 15, 15, 19), state)
    english_headers(sheet, header, export, date.fromisoformat(snapshot["business_date"]), 10)
    paired(sheet, "Shipping Method", export["shipping_method"], "Destination", header["destination_country"], 10)
    paired(sheet, "From / To", joined([export["loading_port"], export["destination_port"]]), "Marks", export["marks"], 10)
    lookup = {row["line_no"]: row for row in goods}
    rows = []
    for box in boxes:
        for index, entry in enumerate(box["items"]):
            row = lookup[entry["line_no"]]
            rows.append([box["box_no"], row["customer_po_no"], detail(row), row["drawing_no"], row["material"],
                Decimal(entry["quantity"]), english_unit(row), Decimal(entry["net_weight_kg"]),
                Decimal(box["gross_weight_kg"]) if index == 0 else None, dimensions(box) if index == 0 else None])
    grid(sheet, ["Carton No.", "PO Number", "Description", "Drawing No.", "Material", "Qty", "Unit",
                 "N.W. (kg)", "G.W. (kg)", "L × W × H (cm)"],
         rows, {6: MEASURE, 8: MEASURE, 9: MEASURE},
         total=["TOTAL", f"{len(boxes)} package(s)", None, None, None, None, None, total_of(goods, "net_weight_kg"), total_of(boxes, "gross_weight_kg")])


def chinese_invoice(book, snapshot, state):
    header, groups = snapshot["header"], snapshot["customs_groups"]
    export, currency = header["export_details"], groups[0]["currency"]
    sheet = sheet_with_title(book, "发票", "发票 / INVOICE", (19, 44, 14, 12, 16, 12, 18), state)
    day = date.fromisoformat(snapshot["business_date"])
    paired(sheet, "购方 Sold to", header["buyer_name"], "编号 No.", export["invoice_no"], 7)
    paired(sheet, "地址 Address", header["buyer_address"], "日期 Date", day, 7)
    paired(sheet, "卖方 Seller", header["seller_name"], "合同号", export["contract_no"], 7)
    grid(sheet, ["标记号码", "货物名称、型号规格", "数量", "单位", "单价", "币种", "总金额"],
         ([export["marks"], group_description(row), Decimal(row["quantity"]), row["unit"],
           Decimal(row["unit_price"]), row["currency"], Decimal(row["amount"])] for row in groups),
         {3: MEASURE, 5: PRICE, 7: MONEY},
         total=["合计", amount_in_chinese(total_of(groups, "amount"), currency), None, None, None, currency, total_of(groups, "amount")])


def group_description(group):
    elements = group["customs"].get("declaration_elements")
    return f"{group['name']}\n{elements}" if elements else group["name"]


def chinese_contract(book, snapshot, state):
    header, groups = snapshot["header"], snapshot["customs_groups"]
    export, currency = header["export_details"], groups[0]["currency"]
    sheet = sheet_with_title(book, "合同", "合同 / CONTRACT", (26, 38, 15, 13, 17, 14, 18), state)
    day = date.fromisoformat(snapshot["business_date"])
    paired(sheet, "卖方 Sellers", header["seller_name"], "合同号码", export["contract_no"], 7)
    paired(sheet, "地址 Address", header["seller_address"], "电话 Tel.", export["seller_phone"], 7)
    paired(sheet, "买方 Buyers", header["buyer_name"], "签约日期", optional_date(export.get("contract_date")), 7)
    paired(sheet, "地址 Address", header["buyer_address"], "电话 Tel.", export["buyer_phone"], 7)
    paired(sheet, "签约地点 Signed at", export["signed_at"], "客户采购单号", joined(row["customer_po_no"] for row in snapshot["goods"]), 7)
    grid(sheet, ["货物名称", "规格及申报要素", "数量", "单位", "单价", "币种", "金额"],
         ([row["name"], row["customs"].get("declaration_elements"), Decimal(row["quantity"]), row["unit"],
           Decimal(row["unit_price"]), row["currency"], Decimal(row["amount"])] for row in groups),
         {3: MEASURE, 5: PRICE, 7: MONEY},
         total=["总值（大写）", amount_in_chinese(total_of(groups, "amount"), currency), None, None, None, currency, total_of(groups, "amount")])
    paired(sheet, "包装及唛头", joined([export["package_type"], export["marks"]]), "装运期", day, 7)
    paired(sheet, "装运口岸", export["loading_port"], "目的地", export["destination_port"] or header["destination_country"], 7)
    paired(sheet, "付款条件", export["payment_terms"], "成交方式", header["trade_term"], 7)
    note(sheet, export["contract_terms"], 7)
    paired(sheet, "买方签章", "", "卖方签章", "", 7)


def customs_declaration(book, snapshot, state):
    header, groups, boxes = snapshot["header"], snapshot["customs_groups"], snapshot["boxes"]
    export, currency = header["export_details"], groups[0]["currency"]
    widths = (14, 17, 22, 36, 12, 10, 18, 12, 16, 16, 17, 10, 13)
    columns = len(widths)
    sheet = sheet_with_title(book, "报关单 附1", "中华人民共和国海关出口货物报关单（草稿）", widths, state)
    destination = export.get("destination_name_zh") or header["destination_country"]
    paired(sheet, "海关编号", "", "预录入编号", "", columns)
    paired(sheet, "境内收发货人", header["seller_name"], "经营单位信用代码", export["seller_credit_no"], columns)
    paired(sheet, "境外收货人", joined([header["buyer_name"], header["buyer_address"]]), "运输方式", export["shipping_method"], columns)
    paired(sheet, "生产销售单位", export["producer_name"], "生产销售单位信用代码", export["producer_credit_no"], columns)
    paired(sheet, "出境关别", export["customs_office"], "出口日期", date.fromisoformat(snapshot["business_date"]), columns)
    declaration_date = optional_date(export["declaration_date"])
    paired(sheet, "申报日期", declaration_date, "提运单号", header["transport_no"], columns)
    paired(sheet, "运输工具名称", export.get("transport_vehicle"), "备案号", export.get("customs_record_no"), columns)
    paired(sheet, "监管方式", export["supervision_mode"], "征免性质", export["exemption_nature"], columns)
    paired(sheet, "许可证号", export.get("licence_no"), "EDI清单编号", export.get("edi_list_no"), columns)
    paired(sheet, "合同协议号", export["contract_no"], "贸易国（地区）", export["trade_country"], columns)
    paired(sheet, "运抵国（地区）", destination, "指运港", export["destination_port"], columns)
    paired(sheet, "境内货源地", export["domestic_source"], "包装种类 / 件数", joined([export["package_type"], str(len(boxes))]), columns)
    paired(sheet, "毛重（kg）", total_of(boxes, "gross_weight_kg"), "净重（kg）", total_of(groups, "net_weight_kg"), columns)
    paired(sheet, "成交方式", header["trade_term"], "随附单证", "发票、合同、装箱单", columns)
    paired(sheet, "运费", export.get("freight"), "保费", export.get("insurance"), columns)
    paired(sheet, "杂费", export.get("other_fees"), "出货单号", snapshot["shipment_no"], columns)
    paired(sheet, "标记唛码", export["marks"], "备注", export["customs_note"], columns)
    grid(sheet, ["项号", "商品编号", "商品名称、规格型号", "申报要素", "数量", "单位", "净重（kg）", "原产国",
                 "最终目的国", "单价", "总价", "币制", "征免"],
         ([row["group_no"], row["customs"].get("hs_code") or "待补", row["name"], row["customs"].get("declaration_elements") or "待补",
           Decimal(row["quantity"]), row["unit"], Decimal(row["net_weight_kg"]), row["customs"].get("origin_country") or "待补",
           destination, Decimal(row["unit_price"]), Decimal(row["amount"]), row["currency"],
           export["exemption_method"]] for row in groups),
         {5: MEASURE, 7: MEASURE, 10: PRICE, 11: MONEY},
         total=["合计", None, None, None, None, None, total_of(groups, "net_weight_kg"),
                None, None, None, total_of(groups, "amount"), currency, None])
    if snapshot["customs_issues"]:
        note(sheet, "\n".join(snapshot["customs_issues"]), columns, color="9C4E00")
    paired(sheet, "特殊关系确认", export.get("related_party_confirmation"), "价格影响确认", export.get("price_influence_confirmation"), columns)
    paired(sheet, "支付特许权使用费确认", export.get("royalty_confirmation"), "自报自缴", export.get("self_payment_confirmation"), columns)
    paired(sheet, "报关员及联系方式", export.get("declarant_contact"), "申报单位（签章）", "", columns)


def grouped_carton_rows(snapshot):
    groups, boxes = snapshot["customs_groups"], snapshot["boxes"]
    lookup = {line: group for group in groups for line in group["goods_line_nos"]}
    for box in boxes:
        contents = defaultdict(lambda: [Decimal(0), Decimal(0)])
        for item in box["items"]:
            group_no = lookup[item["line_no"]]["group_no"]
            contents[group_no][0] += Decimal(item["quantity"])
            contents[group_no][1] += Decimal(item["net_weight_kg"])
        for index, (group_no, (qty, net)) in enumerate(sorted(contents.items())):
            yield box, groups[group_no - 1], qty, net, index == 0


def chinese_packing_list(book, snapshot, state):
    header, groups, boxes = snapshot["header"], snapshot["customs_groups"], snapshot["boxes"]
    export = header["export_details"]
    sheet = sheet_with_title(book, "装箱单", "装箱单 / PACKING LIST", (15, 40, 13, 15, 13, 15, 15, 21), state)
    paired(sheet, "客户 / 地址", joined([header["buyer_name"], header["buyer_address"]]), "日期", date.fromisoformat(snapshot["business_date"]), 8)
    paired(sheet, "发票编号", export["invoice_no"], "合约号", export["contract_no"], 8)
    paired(sheet, "运输方式", export["shipping_method"], "运输单号", header["transport_no"], 8)
    paired(sheet, "由 / 至", joined([export["loading_port"], export["destination_port"] or header["destination_country"]]),
           "成交方式", header["trade_term"], 8)
    rows = ([box["box_no"], group_description(group), 1 if first else None, qty, group["unit"],
             Decimal(box["gross_weight_kg"]) if first else None, net, dimensions(box) if first else None]
            for box, group, qty, net, first in grouped_carton_rows(snapshot))
    grid(sheet, ["箱号", "货物名称及规格", "箱数", "实装数量", "单位", "毛重（kg）", "净重（kg）", "尺寸（cm）"],
         rows, {4: MEASURE, 6: MEASURE, 7: MEASURE},
         total=["合计", None, len(boxes), None, None, total_of(boxes, "gross_weight_kg"), total_of(groups, "net_weight_kg")])
    note(sheet, "唛头 / Marks: " + export["marks"] if export["marks"] else "", 8)


def xlsx_v2(snapshot, kind, metadata, shipment_status):
    book = Workbook()
    book.remove(book.active)
    state = state_message(metadata, shipment_status, english=kind != "customs_draft")
    if kind == "commercial_invoice":
        commercial_invoice(book, snapshot, state)
    elif kind == "packing_list":
        english_packing_list(book, snapshot, state)
    elif kind == "customs_draft":
        for populate in (chinese_invoice, chinese_contract, customs_declaration, chinese_packing_list):
            populate(book, snapshot, state)
    else:
        raise ValueError("出口模板不支持该单据类型")
    stream = BytesIO()
    book.save(stream)
    return stream.getvalue()


def xlsx_v3(snapshot, kind, metadata, shipment_status):
    if kind != "customs_draft":
        return xlsx_v2(snapshot, kind, metadata, shipment_status)
    state = state_message(metadata, shipment_status)
    book = customer_customs_workbook(snapshot, state)
    customs = book.active
    chinese_invoice(book, snapshot, state)
    chinese_contract(book, snapshot, state)
    chinese_packing_list(book, snapshot, state)
    book.move_sheet(customs, offset=2)
    book.active = customs
    stream = BytesIO()
    book.save(stream)
    return stream.getvalue()
