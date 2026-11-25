"""Fill the original customer-facing invoice and packing list worksheets."""
from copy import copy
from datetime import date
from decimal import Decimal
from io import BytesIO
from itertools import groupby
from pathlib import Path

from openpyxl import load_workbook
from openpyxl.utils import column_index_from_string

from .shipment_companion_forms import compact_text, fill_fields, form_pages, xlsx_v4
from .shipment_customs_form import write
from .shipment_export_templates import detail, dimensions, english_unit, joined, state_message, total_of


INVOICE_TEMPLATE = Path(__file__).with_name("shipment_english_invoice_v5.xlsx")
PACKING_TEMPLATE = Path(__file__).with_name("shipment_english_packing_v5.xlsx")


def expand_detail(sheet, row, count, end_column):
    extra = count - 1
    if extra <= 0:
        return
    footer_merges = [(r.min_row, r.min_col, r.max_row, r.max_col)
                     for r in sheet.merged_cells.ranges if r.min_row > row]
    for first, left, last, right in footer_merges:
        sheet.unmerge_cells(start_row=first, start_column=left, end_row=last, end_column=right)
    for index in sorted(sheet.row_dimensions, reverse=True):
        if index > row:
            dimension = sheet.row_dimensions.pop(index)
            dimension.index = index + extra
            sheet.row_dimensions[dimension.index] = dimension
    sheet.insert_rows(row + 1, extra)
    for first, left, last, right in footer_merges:
        sheet.merge_cells(start_row=first + extra, start_column=left, end_row=last + extra, end_column=right)
    last_column = column_index_from_string(end_column)
    for new_row in range(row + 1, row + count):
        dimension = copy(sheet.row_dimensions[row])
        dimension.index = new_row
        sheet.row_dimensions[new_row] = dimension
        for col in range(1, last_column + 1):
            sheet.cell(new_row, col)._style = copy(sheet.cell(row, col)._style)


def labelled(label, value):
    return f"{label}: {value}" if value else f"{label}:"


def english_headers(sheet, snapshot, goods, state, offset, *, invoice):
    header = snapshot["header"]
    export = header["export_details"]
    right = "I" if invoice else "G"
    company = "\n".join(filter(None, (
        export["seller_name_en"] or header["seller_name"],
        labelled("Add", export["seller_address_en"] or header["seller_address"]),
        labelled("Phone", export["seller_phone"]) if export["seller_phone"] else "",
    )))
    date_text = date.fromisoformat(snapshot["business_date"]).strftime("%Y/%m/%d")
    fill_fields(sheet, {
        "A1": company, f"{right}3": labelled("CI No" if invoice else "PI No", export["invoice_no"]),
        f"{right}5": labelled("From", export["seller_contact"]), f"{right}6": labelled("Tel", export["seller_phone"]),
        f"{right}7": labelled("Date", date_text), "A9": state,
    }, offset)
    buyer = (header["buyer_name"], header["buyer_address"], export["buyer_contact"], export["buyer_phone"],
             joined(row["customer_po_no"] for row in goods))
    labels = ("To", "Add", "Attn", "Tel", "Customer Order No.")
    if invoice:
        fill_fields(sheet, {f"A{row}": labelled(label, value) for row, label, value in zip(range(3, 8), labels, buyer)}, offset)
        write(sheet, "A8", labelled("EORI/VAT", export["buyer_eori_vat"]), offset)
    else:
        fill_fields(sheet, {f"B{row}": value for row, value in enumerate(buyer, 3)}, offset)
        write(sheet, "D7", labelled("EORI/VAT", export["buyer_eori_vat"]), offset)


def decimal_text(value):
    return format(Decimal(value).normalize(), "f")


def write_quantity(sheet, address, quantity, item, offset):
    unit = english_unit(item)
    write(sheet, address, Decimal(quantity), offset, suffix=f" {unit}" if unit and unit != "PCS" else "")


def fill_english_invoice(sheet, snapshot, state):
    goods, boxes, header = snapshot["goods"], snapshot["boxes"], snapshot["header"]
    export = header["export_details"]
    first = 13
    capacity = min(12, len(goods))
    extra = capacity - 1
    expand_detail(sheet, first, capacity, "I")
    for offset, page in form_pages(sheet, goods, page_rows=32 + extra, end_column="I", capacity=capacity):
        english_headers(sheet, snapshot, page, state, offset, invoice=True)
        currency = page[0]["currency"]
        fill_fields(sheet, {
            "A11": joined(row["customs"].get("customer_tariff_no") for row in page),
            "C11": joined(detail(row) for row in page), "G11": currency, "H11": header["trade_term"],
            "I11": joined(row["customs"].get("origin_country") for row in page),
            "G12": "QTY/ PCS" if all(english_unit(row) == "PCS" for row in page) else "QTY",
            f"G{14 + extra}": f"{'TOTAL' if len(goods) == len(page) else 'PAGE TOTAL'} ({currency})",
            f"A{16 + extra}": labelled("ISSUED BY", export["seller_contact"]),
            f"D{17 + extra}": "Carton size: " + dimensions(boxes[0]) + " cm" if len(boxes) == 1 else f"Cartons: {len(boxes)}",
            f"D{18 + extra}": f"G.W.: {decimal_text(total_of(boxes, 'gross_weight_kg'))} kg",
        }, offset)
        for row, item in enumerate(page, first):
            fill_fields(sheet, {f"A{row}": item["line_no"], f"B{row}": item["customer_po_no"],
                f"C{row}": detail(item), f"D{row}": item["drawing_no"], f"E{row}": item["material"],
                f"F{row}": item["customs"].get("customer_tariff_no")}, offset)
            write_quantity(sheet, f"G{row}", item["quantity"], item, offset)
            write(sheet, f"H{row}", Decimal(item["price"]), offset, decimals=2)
            write(sheet, f"I{row}", Decimal(item["amount"]), offset, decimals=2)
        write(sheet, f"I{14 + extra}", total_of(page, "amount"), offset, decimals=2)
        if offset and page[-1]["line_no"] == goods[-1]["line_no"]:
            write(sheet, f"A{15 + extra}", f"Invoice total: {currency} {total_of(goods, 'amount'):,.2f}", offset)
        if export["payment_instructions"]:
            sheet.merge_cells(start_row=19 + extra + offset, start_column=1, end_row=22 + extra + offset, end_column=7)
            cell = write(sheet, f"A{19 + extra}", "Payment Instructions\n" + export["payment_instructions"], offset)
            alignment = copy(cell.alignment)
            alignment.wrap_text = True
            alignment.vertical = "top"
            cell.alignment = alignment


def fill_english_packing(sheet, snapshot, state):
    goods, boxes, header = snapshot["goods"], snapshot["boxes"], snapshot["header"]
    export = header["export_details"]
    by_line = {row["line_no"]: row for row in goods}
    entries = [(box, entry, index == 0) for box in boxes for index, entry in enumerate(box["items"])]
    first = 11
    capacity = min(44, len(entries))
    extra = capacity - 1
    gross_total = decimal_text(total_of(boxes, "gross_weight_kg"))
    net_total = decimal_text(total_of((entry for _, entry, _ in entries), "net_weight_kg"))
    cubic_meters = sum((Decimal(box["length_cm"]) * Decimal(box["width_cm"]) * Decimal(box["height_cm"])
                        for box in boxes), Decimal(0)) / 1_000_000
    quantity_label = "QTY/ PCS" if all(english_unit(item) == "PCS" for item in goods) else "QTY"
    expand_detail(sheet, first, capacity, "G")
    for offset, page in form_pages(sheet, entries, page_rows=15 + extra, end_column="G", capacity=capacity):
        english_headers(sheet, snapshot, [by_line[entry["line_no"]] for _, entry, _ in page], state, offset, invoice=False)
        row = first
        for _, carton in groupby(page, key=lambda line: line[0]["box_no"]):
            carton_lines = list(carton)
            box, _, first_in_box = carton_lines[0]
            if len(carton_lines) > 1:
                for column in (1, 2):
                    sheet.merge_cells(start_row=offset + row, start_column=column,
                                      end_row=offset + row + len(carton_lines) - 1, end_column=column)
            compact_text(sheet, f"A{row}", box["box_no"] if first_in_box else f"{box['box_no']} (cont.)", offset)
            if first_in_box:
                gross, net = decimal_text(box["gross_weight_kg"]), decimal_text(total_of(box["items"], "net_weight_kg"))
                weight_separator = "\n" if len(carton_lines) > 1 else " / "
                write(sheet, f"B{row}", f"Size: {dimensions(box)} cm\nG.W.: {gross} kg{weight_separator}N.W.: {net} kg", offset)
            for _, entry, _ in carton_lines:
                item = by_line[entry["line_no"]]
                fill_fields(sheet, {f"C{row}": item["customer_po_no"], f"D{row}": detail(item),
                    f"E{row}": item["drawing_no"], f"F{row}": item["material"]}, offset)
                write_quantity(sheet, f"G{row}", entry["quantity"], item, offset)
                row += 1
        fill_fields(sheet, {
            "G10": quantity_label,
            f"A{12 + extra}": f"Total: {len(boxes)} carton(s), G.W. {gross_total} kg, N.W. {net_total} kg, {decimal_text(cubic_meters)} CBM",
            f"A{14 + extra}": labelled("ISSUED BY", export["seller_contact"]),
            f"A{15 + extra}": joined([labelled("Marks", export["marks"]) if export["marks"] else "", header["transport_no"]]),
        }, offset)


def xlsx_v5(snapshot, kind, metadata, shipment_status):
    if kind not in ("commercial_invoice", "packing_list"):
        return xlsx_v4(snapshot, kind, metadata, shipment_status)
    template, fill = ((INVOICE_TEMPLATE, fill_english_invoice) if kind == "commercial_invoice"
                      else (PACKING_TEMPLATE, fill_english_packing))
    book = load_workbook(template, keep_links=False)
    fill(book.active, snapshot, state_message(metadata, shipment_status, english=True))
    stream = BytesIO()
    book.save(stream)
    return stream.getvalue()
