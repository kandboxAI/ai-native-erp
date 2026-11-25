"""离线 Excel 解析边界，不连接数据库、存储或模型。"""
from io import BytesIO
from zipfile import ZipFile, ZIP_DEFLATED

import pytest
from openpyxl import load_workbook

from app.core.exceptions import AppException
from app.modules.mes.quotation_imports import HEADERS, MAX_BYTES, SHEET, import_template, inspect_import


def filled(rows, mutate=None):
    book = load_workbook(BytesIO(import_template()))
    sheet = book[SHEET]
    for index, row in enumerate(rows, 2):
        for column, value in enumerate(row, 1):
            sheet.cell(index, column, value)
    if mutate:
        mutate(book, sheet)
    output = BytesIO()
    book.save(output)
    book.close()
    return output.getvalue()


def test_template_has_only_six_columns_no_sample_goods_and_preserves_leading_zero():
    book = load_workbook(BytesIO(import_template()))
    assert tuple(cell.value for cell in book[SHEET][1]) == HEADERS == ("图号", "描述", "数量", "客户材料", "表面处理", "客户备注")
    assert all(cell.value is None for row in book[SHEET].iter_rows(min_row=2) for cell in row)
    assert book[SHEET]["A2"].number_format == "@"
    assert book[SHEET]["B2"].number_format == "@"
    assert book[SHEET]["C2"].number_format == "0.###"
    assert book[SHEET]["F2"].number_format == "@"
    assert book[SHEET]["F2"].alignment.wrap_text is True
    assert book[SHEET].auto_filter.ref == "A1:F501"
    assert book[SHEET].sheet_view.showGridLines is True
    for address in ("A1", "F1", "A2", "C250", "F501"):
        for direction in ("left", "right", "top", "bottom"):
            assert getattr(book[SHEET][address].border, direction).style == "thin"
    assert any(str(item.sqref) == "C2:C501" and item.operator == "greaterThan"
        for item in book[SHEET].data_validations.dataValidation)
    assert "填写说明" in book.sheetnames
    preview = inspect_import(filled([("00123", "连接板", 10, "AL6082", "阳极氧化", "去毛刺\n单独包装"),
        ("00234", "支架", 1.5, "316L", None)]))
    assert preview["errors"] == [] and preview["total_rows"] == 2
    assert preview["items"][0]["drawing_no"] == "00123"
    assert preview["items"][0]["description"] == "连接板"
    assert preview["items"][0]["quantity"] == "10"
    assert preview["items"][0]["drawing_revision"] == "A"
    assert "weight_kg" not in preview["items"][0]
    assert preview["items"][0]["note"] == "去毛刺\n单独包装"
    assert preview["items"][1]["note"] == ""
    assert "engineering_note" not in preview["items"][0]
    assert "weight_kg" not in preview["items"][1]


@pytest.mark.parametrize("values,reason", [
    (("P1", "板", 0, "钢", "", None), "数量"),
    (("P1", "板", 1.2345, "钢", "", None), "数量"),
    (("P1", "板", 1, None, "", None), "必填"),
    (("P1", "板", "=10*2", "钢", "", None), "公式"),
    (("=1+1", "板", 1, "钢", "", None), "公式"),
    (("P1", "板", 1, "钢", "", "#VALUE!"), "错误值"),
    (("P1", "板", 1, "钢", "", "=1+1"), "公式"),
    (("P1", "板", 1, "钢", "", "备注"*501), "客户备注最多 1000 字"),
])
def test_rows_have_actionable_errors_before_any_draft_mutation(values, reason):
    preview = inspect_import(filled([values]))
    assert preview["items"] == []
    assert preview["errors"][0]["row_no"] == 2
    assert reason in preview["errors"][0]["message"]


def test_duplicate_casefold_and_blank_rows_keep_original_excel_row_number():
    preview = inspect_import(filled([("P1", "板", 2, "钢"), (), ("p1", "板", 3, "钢")]))
    assert len(preview["items"]) == 1
    assert preview["errors"] == [dict(row_no=4, message="图号重复，请合并同图号货品")]


@pytest.mark.parametrize("mutate,reason", [
    (lambda book, sheet: setattr(sheet, "title", "改名"), "工作表"),
    (lambda book, sheet: sheet.cell(1, 2, "错误列"), "列名"),
    (lambda book, sheet: sheet.cell(2, 8, "多余列"), "六列模板"),
    (lambda book, sheet: sheet.cell(502, 1, "太多行"), "最多导入 500"),
])
def test_requires_fixed_template_shape(mutate, reason):
    with pytest.raises(AppException, match=reason):
        inspect_import(filled([("P1", "板", 1, "钢")], mutate))


def test_empty_invalid_oversized_and_expansion_limits():
    for content in (b"", b"not an xlsx", b"x"*(MAX_BYTES+1)):
        with pytest.raises(AppException):
            inspect_import(content)
    with pytest.raises(AppException, match="没有货品"):
        inspect_import(import_template())
    output = BytesIO()
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        archive.writestr("large.xml", b"x"*(21*1024*1024))
    with pytest.raises(AppException, match="解压内容过大"):
        inspect_import(output.getvalue())


def test_macro_workbooks_are_rejected_before_loading():
    output = BytesIO()
    with ZipFile(output, "w") as archive:
        archive.writestr("xl/vbaProject.bin", b"macro")
    with pytest.raises(AppException, match="含宏"):
        inspect_import(output.getvalue())


def test_lazy_worksheet_corruption_becomes_actionable_error():
    output = BytesIO()
    with ZipFile(BytesIO(import_template())) as original, ZipFile(output, "w", ZIP_DEFLATED) as altered:
        for item in original.infolist():
            content = original.read(item.filename)
            if item.filename == "xl/worksheets/sheet1.xml":
                content = content.replace(b"</sheetData>", b"<broken></sheetData>")
            altered.writestr(item.filename, content)
    with pytest.raises(AppException, match="(损坏|无法读取)"):
        inspect_import(output.getvalue())


def test_existing_seven_column_workbook_keeps_customer_note_and_ignores_weight():
    def use_old_header(book, sheet):
        sheet.cell(1, 6, "重量（kg）")
        sheet.cell(1, 7, "客户备注")

    result = inspect_import(filled([("00123", "连接板", 10, "AL6082", "阳极氧化", 0.125, "单独包装")], use_old_header))
    assert result["errors"] == []
    assert result["items"][0]["note"] == "单独包装"
    assert "weight_kg" not in result["items"][0]
