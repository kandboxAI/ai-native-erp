"""固定六列询价模板及受限解析；只预检，不写库，不执行工作簿公式。"""
from io import BytesIO
from zipfile import ZipFile
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill, Border, Side
from openpyxl.worksheet.datavalidation import DataValidation
from pydantic import ValidationError
from app.core.exceptions import AppException
from .quotation_schemas import QuotationLineBody

HEADERS = ("图号", "描述", "数量", "客户材料", "表面处理", "客户备注")
LEGACY_HEADERS = (*HEADERS[:-1], "重量（kg）", HEADERS[-1])
MAX_ROWS = 500
MAX_BYTES = 5 * 1024 * 1024
SHEET = "货品清单"


def import_template():
    book = Workbook()
    sheet = book.active
    sheet.title = SHEET
    sheet.append(HEADERS)
    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = "A1:F501"
    sheet.sheet_view.showGridLines = True
    edge = Side(style="thin", color="B8C6D8")
    cell_border = Border(left=edge, right=edge, top=edge, bottom=edge)
    for cell in sheet[1]:
        cell.fill = PatternFill("solid", fgColor="2366A8")
        cell.font = Font(name="微软雅黑", bold=True, color="FFFFFF")
        cell.alignment = Alignment(vertical="center")
        cell.border = cell_border
    sheet.row_dimensions[1].height = 28
    for row in sheet.iter_rows(min_row=2, max_row=501, max_col=len(HEADERS)):
        for cell in row:
            cell.font = Font(name="微软雅黑", size=11, color="2366A8")
            cell.border = cell_border
            cell.alignment = Alignment(wrap_text=True, vertical="center")
            cell.number_format = "0.###" if cell.column == 3 else "@"
    for key, width in zip("ABCDEF", (28, 36, 16, 24, 36, 42), strict=True):
        sheet.column_dimensions[key].width = width
    validation = DataValidation(type="decimal", operator="greaterThan", formula1="0", allow_blank=True)
    validation.errorTitle = "请核对数量"
    validation.error = "数量应大于 0，请填写实际数值。"
    validation.showErrorMessage = True
    sheet.add_data_validation(validation)
    validation.add("C2:C501")
    instructions = book.create_sheet("填写说明")
    for row in [
        ("填写说明", "只导入“货品清单”页，第 1 行列名和顺序不要修改。"),
        ("必填", "图号、描述、数量、客户材料。表面处理和客户备注可留空。"),
        ("客户备注", "填写客户对本项货品的补充要求，最多 1000 字；与工程内部说明分开保存。"),
        ("数量", "数量大于 0，最多 3 位小数，不超过 1000000。"),
        ("图号", "按文本填写以保留前导零；同一文件不能重复图号，最多 500 项，不填写公式。"),
        ("文件配对", "图号 00123 对应 00123.pdf、00123.stp 或 00123.step；可先导 Excel，也可先传图纸。"),
        ("示例（不要复制到正式业务）", "图号 00123，描述为连接板，数量 10，客户材料 AL6082，表面处理为阳极氧化。"),
    ]:
        instructions.append(row)
    instructions.column_dimensions["A"].width = 28
    instructions.column_dimensions["B"].width = 100
    for row in instructions:
        for cell in row:
            cell.alignment = Alignment(wrap_text=True, vertical="top")
    output = BytesIO()
    book.save(output)
    return output.getvalue()


def inspect_import(content):
    if not content or len(content) > MAX_BYTES:
        raise AppException("Excel 文件不能为空且不能超过 5MB", 422)
    try:
        with ZipFile(BytesIO(content)) as archive:
            if len(archive.infolist()) > 200 or sum(item.file_size for item in archive.infolist()) > 20*1024*1024:
                raise AppException("Excel 解压内容过大，请使用下载的模板", 422)
            if any(item.filename.lower().endswith("vbaproject.bin") for item in archive.infolist()):
                raise AppException("不支持含宏的 Excel 文件", 422)
        book = load_workbook(BytesIO(content), read_only=True, data_only=False, keep_links=False)
    except AppException:
        raise
    except Exception as error:
        raise AppException("无法读取 Excel，请使用系统提供的 .xlsx 模板", 422) from error
    try:
        if SHEET not in book.sheetnames:
            raise AppException("缺少“货品清单”工作表，请使用固定模板", 422)
        sheet = book[SHEET]
        if sheet.max_column not in (len(HEADERS), len(LEGACY_HEADERS)) or not sheet.max_row or sheet.max_row > MAX_ROWS+1:
            raise AppException("请使用系统下载的六列模板，最多导入 500 项货品", 422)
        header = tuple(str(cell.value or "").strip() for cell in next(sheet.iter_rows(min_row=1, max_row=1)))
        if header not in (HEADERS, LEGACY_HEADERS):
            raise AppException(f"列名或顺序不正确，请按：{'、'.join(HEADERS)}填写", 422)
        items, errors, seen = [], [], set()
        for row_no, cells in enumerate(sheet.iter_rows(min_row=2, max_col=len(header)), 2):
            if header == LEGACY_HEADERS:
                cells = (*cells[:5], cells[-1])
            if all(cell.value is None or str(cell.value).strip() == "" for cell in cells):
                continue
            if any(cell.data_type in {"f", "e"} for cell in cells):
                errors.append(dict(row_no=row_no, message="不支持公式或 Excel 错误值，请粘贴为实际数值/文本"))
                continue
            values = [cell.value for cell in cells]
            number, description, quantity, material, treatment, note = values
            def text(value):
                return "" if value is None else str(value).strip()
            key = text(number).casefold()
            if key in seen:
                errors.append(dict(row_no=row_no, message="图号重复，请合并同图号货品"))
                continue
            seen.add(key)
            if not all(text(value) for value in (number, description, material)):
                errors.append(dict(row_no=row_no, message="图号、描述、客户材料为必填项"))
                continue
            try:
                value = QuotationLineBody(drawing_no=text(number), quantity=quantity, description=text(description),
                    customer_material=text(material), surface_treatment=text(treatment), note=text(note))
                items.append(dict(row_no=row_no, **value.model_dump(mode="json", exclude={"id", "files"})))
            except ValidationError as error:
                labels = {"quantity": "数量须大于 0、最多 3 位小数且不超过 1000000", "note": "客户备注最多 1000 字"}
                messages = list(dict.fromkeys(labels.get(str(item["loc"][0]), f"{item['loc'][0]} 内容超长或格式不正确") for item in error.errors()))
                errors.append(dict(row_no=row_no, message="；".join(messages)))
        if not items and not errors:
            raise AppException("Excel 中没有货品，请从第 2 行开始填写", 422)
        return dict(items=items, errors=errors, total_rows=len(items)+len(errors))
    except AppException:
        raise
    except Exception as error:
        # read_only worksheets parse XML lazily, after load_workbook returned.
        raise AppException("Excel 内容损坏或格式不正确，请重新使用系统模板填写", 422) from error
    finally:
        book.close()
