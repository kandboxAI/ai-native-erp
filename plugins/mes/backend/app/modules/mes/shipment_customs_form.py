"""将出货快照写入客户报关单原版式。坐标以「报关单 附1」为准。"""
from copy import copy
from datetime import date
from decimal import Decimal
from pathlib import Path

from openpyxl import load_workbook
from openpyxl.cell.cell import MergedCell
from openpyxl.utils.cell import coordinate_to_tuple


CUSTOMS_TEMPLATE = Path(__file__).with_name("customs_declaration_v3.xlsx")
ROWS_PER_PAGE = 49
ITEMS_PER_PAGE = 6
FIRST_ITEM_ROW = 23
ITEM_ROWS = 3


def copy_page(sheet, offset, *, last_row, last_column):
    cells = tuple(sheet.iter_rows(min_row=1, max_row=last_row, max_col=last_column))
    merges = tuple(r for r in sheet.merged_cells.ranges if r.max_row <= last_row)
    for row in cells:
        for cell in row:
            if isinstance(cell, MergedCell):
                continue
            sheet.cell(cell.row + offset, cell.column, cell.value)
    for row in range(1, last_row + 1):
        dimension = sheet.row_dimensions.get(row)
        if dimension is not None:
            target = copy(dimension)
            target.index = row + offset
            sheet.row_dimensions[target.index] = target
    for merged in merges:
        sheet.merge_cells(
            start_row=merged.min_row + offset, start_column=merged.min_col,
            end_row=merged.max_row + offset, end_column=merged.max_col,
        )
    for row in cells:
        for cell in row:
            if cell.has_style:
                sheet.cell(cell.row + offset, cell.column)._style = copy(cell._style)


def write(sheet, address, value, offset, *, decimals=0, suffix="", prefix=""):
    row, column = coordinate_to_tuple(address)
    cell = sheet.cell(row + offset, column)
    if isinstance(value, Decimal):
        normalized = value.normalize()
        if len(normalized.as_tuple().digits) > 15:
            value = f"{prefix}{value:f}{suffix}"
        else:
            places = max(decimals, -normalized.as_tuple().exponent)
            pattern = "#,##0" + ("." + "0" * places if places else "")
            cell.number_format = (f'"{prefix}"' if prefix else "") + pattern + (f'"{suffix}"' if suffix else "")
    elif isinstance(value, date):
        cell.number_format = "yyyy/mm/dd"
    cell.value = value
    if isinstance(value, str):
        cell.data_type = "s"
    return cell


def fill_page(sheet, snapshot, groups, offset, status, page, page_count):
    header, boxes = snapshot["header"], snapshot["boxes"]
    export = header["export_details"]
    business_date = date.fromisoformat(snapshot["business_date"])
    declaration_date = date.fromisoformat(export["declaration_date"]) if export.get("declaration_date") else None
    destination = export.get("destination_name_zh") or header["destination_country"]
    trade_country = export.get("trade_country")
    if trade_country == header["destination_country"]:
        trade_country = destination
    declarant = export.get("declarant_contact") or ""
    contact, separator, phone = declarant.partition(" / ")

    banner = " · ".join(part for part in ("报关资料草稿", status, f"第 {page} / {page_count} 页" if page_count > 1 else "") if part)
    banner_cell = write(sheet, "A4", banner, offset)
    banner_font = copy(banner_cell.font)
    banner_font.sz = 9
    banner_font.b = False
    banner_cell.font = banner_font
    remarks = [value for value in (export.get("marks"), export.get("customs_note")) if value]
    group_numbers = {row["group_no"] for row in groups}
    issues = [issue for issue in snapshot.get("customs_issues", ())
              if any(issue.startswith(f"第 {number} 项") for number in group_numbers)]
    if issues:
        remarks.append("；".join(issues))
    fields = {
        "A7": header["seller_name"], "O6": export.get("seller_credit_no"),
        "P7": export.get("customs_office"), "V7": business_date,
        "Z7": declaration_date, "AG7": export.get("customs_record_no"),
        "E8": header["buyer_name"], "A9": header["buyer_address"],
        "P9": export.get("shipping_method"), "V9": export.get("transport_vehicle"), "AA9": header["transport_no"],
        "A11": export.get("producer_name"), "O10": export.get("producer_credit_no"),
        "P11": export.get("supervision_mode"), "V11": export.get("exemption_nature"), "AG11": export.get("licence_no"),
        "A13": export.get("contract_no"), "S13": trade_country, "V13": destination,
        "AC13": export.get("destination_port"), "AE13": export.get("domestic_source"),
        "A15": export.get("package_type"), "P15": len(boxes), "AA15": header["trade_term"],
        "AC15": export.get("freight"), "AE15": export.get("insurance"), "AI15": export.get("other_fees"),
        "A17": export.get("edi_list_no"), "N16": "发票、合同、装箱单", "G18": "\n".join(remarks),
        "AC41": groups[0]["currency"],
        "F45": export.get("related_party_confirmation"), "N45": export.get("price_influence_confirmation"),
        "P45": export.get("royalty_confirmation"), "AA45": export.get("self_payment_confirmation"),
        "N47": contact if separator else None, "O47": phone if separator else contact,
        "O49": declaration_date or business_date,
    }
    for address, value in fields.items():
        write(sheet, address, value, offset)
    write(sheet, "R15", sum(Decimal(box["gross_weight_kg"]) for box in boxes), offset, suffix="kg")
    write(sheet, "V15", sum(Decimal(group["net_weight_kg"]) for group in snapshot["customs_groups"]), offset, suffix="kg")
    write(sheet, "AD41", sum(Decimal(group["amount"]) for group in groups), offset, decimals=2)

    for index, group in enumerate(groups):
        row = FIRST_ITEM_ROW + index * ITEM_ROWS
        customs = group["customs"]
        elements = customs.get("declaration_elements") or "申报要素待补"
        origin = customs.get("origin_country") or "待补"
        write(sheet, f"A{row}", group["group_no"], offset)
        code_cell = write(sheet, f"B{row}", customs.get("hs_code") or "待补", offset)
        code_cell.number_format = "@"
        write(sheet, f"I{row}", group["name"], offset)
        write(sheet, f"I{row + 1}", f"{elements}\n原产国：{origin}", offset)
        write(sheet, f"S{row + 1}", Decimal(group["quantity"]), offset, suffix=group["unit"])
        write(sheet, f"S{row + 2}", Decimal(group["net_weight_kg"]), offset, prefix="净重：", suffix="kg")
        write(sheet, f"V{row + 1}", destination, offset)
        write(sheet, f"AA{row}", Decimal(group["unit_price"]), offset, decimals=2)
        # 客户首两栏的总价在第二行，余下栏位合并在第一行。
        total_row = row + 1 if index < 2 else row
        write(sheet, f"AD{total_row}", Decimal(group["amount"]), offset, decimals=2)
        write(sheet, f"AI{row + 1}", group["currency"], offset)
        write(sheet, f"AK{row}", export.get("exemption_method"), offset)


def fill_customs_declaration(sheet, snapshot, status):
    groups = snapshot["customs_groups"]
    pages = [groups[index:index + ITEMS_PER_PAGE] for index in range(0, len(groups), ITEMS_PER_PAGE)]
    for index in range(1, len(pages)):
        copy_page(sheet, index * ROWS_PER_PAGE, last_row=ROWS_PER_PAGE, last_column=37)
    for index, page_groups in enumerate(pages):
        fill_page(sheet, snapshot, page_groups, index * ROWS_PER_PAGE, status, index + 1, len(pages))
    sheet.print_area = [f"A{3 + i * ROWS_PER_PAGE}:AK{(i + 1) * ROWS_PER_PAGE}" for i in range(len(pages))]


def customer_customs_workbook(snapshot, status):
    book = load_workbook(CUSTOMS_TEMPLATE, keep_links=False)
    fill_customs_declaration(book.active, snapshot, status)
    return book
