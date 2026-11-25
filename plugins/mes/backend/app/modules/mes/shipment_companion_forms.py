"""将出货快照写入客户报关资料工作簿的四张原表。"""
from collections import defaultdict
from copy import copy
from datetime import date
from decimal import Decimal
from io import BytesIO
from pathlib import Path

from openpyxl import load_workbook
from openpyxl.utils import column_index_from_string

from .shipment_customs_form import copy_page, fill_customs_declaration, write
from .shipment_export_templates import (
    amount_in_chinese, grouped_carton_rows, joined, optional_date, state_message, total_of, xlsx_v2,
)


CUSTOMER_WORKBOOK = Path(__file__).with_name("shipment_customs_v4.xlsx")
CURRENCY_NAMES = {"EUR": "欧元", "USD": "美元", "CNY": "人民币", "GBP": "英镑", "HKD": "港币"}


def form_pages(sheet, rows, *, page_rows, end_column, capacity):
    pages = [rows[index:index + capacity] for index in range(0, len(rows), capacity)]
    return lay_out_pages(sheet, pages, page_rows=page_rows, end_column=end_column)


def lay_out_pages(sheet, pages, *, page_rows, end_column):
    end_index = column_index_from_string(end_column)
    offsets = [index * page_rows for index in range(len(pages))]
    for offset in offsets[1:]:
        copy_page(sheet, offset, last_row=page_rows, last_column=end_index)
    sheet.print_area = [f"A{offset + 1}:{end_column}{offset + page_rows}" for offset in offsets]
    return zip(offsets, pages)


def fill_fields(sheet, fields, offset):
    for address, value in fields.items():
        write(sheet, address, value or None, offset)


def compact_text(sheet, address, value, offset):
    cell = write(sheet, address, value or None, offset)
    alignment = copy(cell.alignment)
    alignment.shrink_to_fit = True
    cell.alignment = alignment


def payment_line(header, export):
    return joined([export["payment_terms"], header["trade_term"]])


def fill_packing(sheet, snapshot, state):
    header = snapshot["header"]
    export = header["export_details"]
    day = date.fromisoformat(snapshot["business_date"])
    destination = export["destination_port"] or export["destination_name_zh"] or header["destination_country"]
    route = "   ".join(f"{label} {place}" for label, place in (("From", export["loading_port"]), ("TO", destination)) if place)
    consignee = "\n".join(filter(None, (header["buyer_name"], "Add: " + header["buyer_address"] if header["buyer_address"] else "")))
    for offset, page in form_pages(sheet, list(grouped_carton_rows(snapshot)), page_rows=40, end_column="G", capacity=14):
        fill_fields(sheet, {
            "B4": consignee, "G3": day, "G4": export["invoice_no"], "G5": export["contract_no"],
            "C7": export["destination_name_zh"] if destination != export["destination_name_zh"] else None,
            "B38": joined([export["shipping_method"], header["transport_no"], state]), "B39": export["marks"],
        }, offset)
        compact_text(sheet, "B7", route, offset)
        compact_text(sheet, "F6", payment_line(header, export), offset)
        for row, (box, group, quantity, net, first) in zip(range(9, 37, 2), page):
            compact_text(sheet, f"A{row}", box["box_no"], offset)
            compact_text(sheet, f"B{row}", group["name"], offset)
            compact_text(sheet, f"B{row + 1}", group["customs"].get("declaration_elements"), offset)
            write(sheet, f"C{row}", 1 if first else None, offset)
            write(sheet, f"D{row}", quantity, offset)
            write(sheet, f"E{row}", group["unit"], offset)
            write(sheet, f"F{row}", Decimal(box["gross_weight_kg"]) if first else None, offset, decimals=2)
            write(sheet, f"G{row}", net, offset, decimals=2)
        write(sheet, "C37", sum(first for _, _, _, _, first in page), offset)
        write(sheet, "F37", sum((Decimal(box["gross_weight_kg"]) for box, _, _, _, first in page if first), Decimal(0)), offset, suffix="kg")
        write(sheet, "G37", sum((net for _, _, _, net, _ in page), Decimal(0)), offset, suffix="kg")


def commercial_pages(sheet, snapshot, *, page_rows, end_column, capacity):
    if "domestic_details" not in snapshot["header"]:
        for offset, page in form_pages(sheet, snapshot["customs_groups"], page_rows=page_rows, end_column=end_column, capacity=capacity):
            yield offset, page, total_of(page, "amount")
        return
    groups = defaultdict(list)
    for row in snapshot["goods"]:
        specification = joined([
            f"图号 {row['drawing_no']}" if row["drawing_no"] else "",
            f"材料 {row['material']}" if row["material"] else "",
        ])
        groups[row["currency"], row["price_basis"]].append(dict(
            row, name=row["order_description"] or row["item_name"], unit_price=row["price"],
            specification=specification,
        ))
    pages, totals = [], []
    for rows in groups.values():
        for index in range(0, len(rows), capacity):
            pages.append(rows[index:index + capacity])
            # 合计仅写在同一币种和计价口径的最后一页。
            totals.append(total_of(rows, "amount") if index + capacity >= len(rows) else None)
    for (offset, page), total in zip(lay_out_pages(sheet, pages, page_rows=page_rows, end_column=end_column), totals):
        yield offset, page, total


def fill_invoice(sheet, snapshot, state):
    header = snapshot["header"]
    domestic = "domestic_details" in header
    details = header["domestic_details"] if domestic else header["export_details"]
    day = date.fromisoformat(snapshot["business_date"])
    for offset, page, total in commercial_pages(sheet, snapshot, page_rows=40, end_column="I", capacity=15):
        currency = page[0]["currency"]
        fill_fields(sheet, {
            "A2": state, "C3": header["buyer_name"], "C4": "Add:" + header["buyer_address"] if header["buyer_address"] else None,
            "G2": details["invoice_no"], "G3": day, "C38": details.get("marks"),
            "C37": amount_in_chinese(total, CURRENCY_NAMES.get(currency, currency)) if total is not None else None,
            "G37": currency,
        }, offset)
        if domestic:
            compact_text(sheet, "A2", " · ".join(filter(None, (state, f"销售方 {header['seller_name']}", page[0]["price_basis"]))), offset)
            if header["buyer_tax_no"]:
                compact_text(sheet, "F4", f"购方税号 {header['buyer_tax_no']}", offset)
        for row, group in zip(range(7, 37, 2), page):
            compact_text(sheet, f"C{row}", group["name"], offset)
            compact_text(sheet, f"C{row + 1}", group["specification"] if domestic else group["customs"].get("declaration_elements"), offset)
            write(sheet, f"D{row}", Decimal(group["quantity"]), offset)
            write(sheet, f"E{row}", group["unit"], offset)
            write(sheet, f"F{row}", Decimal(group["unit_price"]), offset, decimals=2)
            write(sheet, f"G{row}", group["currency"], offset)
            write(sheet, f"H{row}", Decimal(group["amount"]), offset, decimals=2)
        write(sheet, "H37", total, offset, decimals=2)


def fill_contract(sheet, snapshot, state):
    header = snapshot["header"]
    domestic = "domestic_details" in header
    details = header["domestic_details"] if domestic else header["export_details"]
    day = date.fromisoformat(snapshot["business_date"])
    destination = details.get("destination_name_zh") or header["destination_country"]
    route = joined([details.get("loading_port"), details.get("destination_port") or destination])
    for offset, page, total in commercial_pages(sheet, snapshot, page_rows=50, end_column="H", capacity=8):
        currency = page[0]["currency"]
        fill_fields(sheet, {
            "A2": " · ".join(filter(None, (state, page[0]["price_basis"]))) if domestic else state,
            "B3": "\n".join(dict.fromkeys(filter(None, (header["seller_name"], details.get("seller_name_en"))))),
            "B5": "\n".join(dict.fromkeys(filter(None, (header["seller_address"], details.get("seller_address_en"))))),
            "B7": details["seller_phone"], "B9": header["buyer_name"], "B11": header["buyer_address"],
            "B13": details["buyer_phone"], "F6": details["contract_no"], "F9": optional_date(details["contract_date"]),
            "F11": details["signed_at"], "F28": currency,
            "D30": amount_in_chinese(total, CURRENCY_NAMES.get(currency, currency)) if total is not None else None,
            "B32": details.get("package_type"), "B35": day, "B42": details.get("marks"),
            "E46": header["seller_name"],
        }, offset)
        compact_text(sheet, "A46", f"            买  方：{header['buyer_name']}", offset)
        compact_text(sheet, "A29", details["contract_terms"], offset)
        if not domestic:
            compact_text(sheet, "C36", destination, offset)
            compact_text(sheet, "A37", f"Loading Port & Destination: {route}", offset)
            compact_text(sheet, "A39", "Insurance: " + details["insurance"], offset)
        compact_text(sheet, "B40", payment_line(header, details), offset)
        for row, group in zip(range(19, 27), page):
            compact_text(sheet, f"A{row}", joined([group["name"], group["specification"]]) if domestic else group["name"], offset)
            write(sheet, f"C{row}", Decimal(group["quantity"]), offset)
            write(sheet, f"D{row}", group["unit"], offset)
            write(sheet, f"E{row}", Decimal(group["unit_price"]), offset, decimals=2)
            write(sheet, f"F{row}", group["currency"], offset)
            write(sheet, f"G{row}", Decimal(group["amount"]), offset, decimals=2)
        write(sheet, "G28", total, offset, decimals=2)


def xlsx_domestic(snapshot, kind, metadata, shipment_status):
    title, fill = {"domestic_invoice": ("发票", fill_invoice), "domestic_contract": ("合同", fill_contract)}[kind]
    book = load_workbook(CUSTOMER_WORKBOOK, keep_links=False)
    for sheet in list(book):
        if sheet.title != title:
            book.remove(sheet)
    book.active = 0
    book.active.sheet_view.tabSelected = True
    fill(book.active, snapshot, state_message(metadata, shipment_status))
    stream = BytesIO()
    book.save(stream)
    return stream.getvalue()


def xlsx_v4(snapshot, kind, metadata, shipment_status):
    if kind != "customs_draft":
        return xlsx_v2(snapshot, kind, metadata, shipment_status)
    state = state_message(metadata, shipment_status)
    book = load_workbook(CUSTOMER_WORKBOOK, keep_links=False)
    fill_customs_declaration(book["报关单 附1"], snapshot, state)
    fill_packing(book["装箱单"], snapshot, state)
    fill_invoice(book["发票"], snapshot, state)
    fill_contract(book["合同"], snapshot, state)
    stream = BytesIO()
    book.save(stream)
    return stream.getvalue()
