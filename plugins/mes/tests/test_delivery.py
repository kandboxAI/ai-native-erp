"""出货/对账事务回归；真实 ORM + SQLite 内存库，无业务数据库或模型调用。"""
import asyncio
from contextlib import asynccontextmanager
from copy import copy, deepcopy
from datetime import date
from decimal import Decimal
from io import BytesIO
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError
from openpyxl import load_workbook
from sqlalchemy import Column, JSON, MetaData, Table, Uuid, create_engine, event, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.core.exceptions import AppException, register_exception_handlers
from app.modules.mes import delivery_service as module
from app.modules.mes import delivery_repository as delivery_queries
from app.modules.mes import shipment_document_service as documents
from app.modules.mes.api import router
from app.modules.mes.delivery_models import MesShipment, MesShipmentLine, MesReconciliation, MesReconciliationLine, MesShipmentDocumentRevision, MesShipmentInvoice
from app.modules.mes.delivery_repository import ShipmentDocumentSource, delivery_repository as repo
from app.modules.mes.delivery_schemas import DeliveryCommand, DeliveryQuery, ShipmentBody, ShipmentUpdate, ReconciliationBody
from app.modules.mes.delivery_service import delivery_service as service, amount
from app.modules.mes.report_service import report_service
from app.modules.mes.report_repository import report_repository
from app.modules.mes.repository import repository
from app.modules.mes.shipment_companion_forms import CUSTOMER_WORKBOOK
from app.modules.mes.shipment_customs_form import CUSTOMS_TEMPLATE, customer_customs_workbook
from app.modules.mes.shipment_document_exports import RENDERERS, xlsx_v1, xlsx_v2, xlsx_v3, xlsx_v4
from app.modules.mes.shipment_english_forms import INVOICE_TEMPLATE, PACKING_TEMPLATE, xlsx_v5
from app.modules.mes.shipment_document_schemas import CustomsLine, ShipmentDocumentBody, ShipmentInvoiceBody
from test_reporting import fixture as report_fixture


@pytest.fixture
def data(monkeypatch):
    actor, order, task, report, _, _, _, _, _ = report_fixture(monkeypatch)
    for key in ("mes:shipment:list", "mes:shipment:manage", "mes:reconciliation:list", "mes:reconciliation:manage"):
        actor.permissions.append(key); actor.permission_scopes[key] = "organization"
    order.status_code, task.status_code, task.good_quantity = "in_progress", "pending", Decimal(5)
    task.is_quality_required = False
    engine = create_engine("sqlite:///:memory:")
    @event.listens_for(engine, "connect")
    def foreign_keys(connection, _): connection.execute("PRAGMA foreign_keys=ON")
    metadata = MetaData()
    for name in ("sys_org", "sys_user", "md_item", "inv_warehouse", "file_attachment"):
        Table(name, metadata, Column("id", Uuid, primary_key=True))
    Table("mes_work_order", metadata, Column("id", Uuid, primary_key=True),
        Column("org_id", Uuid, nullable=False), Column("source_sales_order_line_id", Uuid))
    for model in (MesShipment, MesShipmentLine, MesReconciliation, MesReconciliationLine, MesShipmentDocumentRevision, MesShipmentInvoice):
        table = model.__table__.to_metadata(metadata)
        for column in table.columns:
            column.server_default = None
            if isinstance(column.type, JSONB): column.type = JSON()
        for index in table.indexes:
            if index.dialect_options["postgresql"].get("where") is not None:
                index.dialect_options["sqlite"]["where"] = index.dialect_options["postgresql"]["where"]
    metadata.create_all(engine)
    with engine.begin() as connection:
        for name, value in (("sys_org", actor.org_id), ("sys_user", actor.user_id), ("md_item", order.product_item_id)):
            connection.execute(metadata.tables[name].insert().values(id=value))
        connection.execute(metadata.tables["mes_work_order"].insert().values(id=order.id, org_id=actor.org_id))
    @asynccontextmanager
    async def sessions():
        with Session(engine) as current:
            async def execute(statement): return current.execute(statement)
            async def flush(): current.flush()
            async def commit(): current.commit()
            yield SimpleNamespace(add=current.add, execute=execute, flush=flush, commit=commit)
    async def orders(*args): return [order]
    async def no_project(*args): return None
    monkeypatch.setattr(module, "get_session_context", sessions)
    monkeypatch.setattr(repo, "lock_orders", orders)
    monkeypatch.setattr(repo, "project", no_project)
    # report_fixture replaced this method; restore real SQL against the in-memory shipment tables.
    monkeypatch.setattr(repo, "has_shipments", type(repo).has_shipments.__get__(repo))
    try: yield actor, order, task, report, sessions, engine, metadata
    finally: engine.dispose()


def ship_body(order, **changes):
    values = dict(shipment_no="S1", customer_no_snapshot="C1", customer_name_snapshot="客户甲", business_date="2026-10-24",
        lines=[dict(work_order_id=order.id, quantity="2.001", unit_price="2.50")], idempotency_key="ship-key-1")
    values.update(changes)
    return ShipmentBody(**values)


def rec_body(shipment, **changes):
    values = dict(reconciliation_no="R1", customer_no_snapshot="C1", customer_name_snapshot="客户甲",
        period_start="2026-10-01", period_end="2026-10-31", idempotency_key="reconcile-key-1",
        lines=[dict(shipment_line_id=shipment["lines"][0]["id"], adjustment_amount="-0.01", adjustment_reason="尾差")])
    values.update(changes)
    return ReconciliationBody(**values)


async def posted(data):
    user, order, *_ = data
    row = await service.save_shipment(ship_body(order), user)
    return await service.shipment_action(row["id"], "post", DeliveryCommand(version_no=row["version_no"]), user)


def test_export_documents_use_partial_shipment_currency_and_pack_weights():
    line_id = uuid4()
    shipment = SimpleNamespace(status_code="posted", version_no=2, shipment_no="SH-001", business_date=date(2026, 11, 18))
    line = SimpleNamespace(id=line_id, work_order_no_snapshot="WO-1", product_item_no_snapshot="P1",
        product_item_name_snapshot="=1+1", unit_code="piece", quantity=Decimal("4"), unit_price=Decimal("999.00"))
    sale = SimpleNamespace(drawing_no_snapshot="DW-1", unit_name_snapshot="件", quantity=Decimal("100"), unit_price=Decimal("7.50"))
    order = SimpleNamespace(order_no="SO-1", currency="EUR")
    boxes = [dict(box_no=f"B{index}", gross_weight_kg=3, length_cm=20, width_cm=10, height_cm=10,
        lines=[dict(shipment_line_id=line_id, quantity=2, net_weight_kg="1.25")]) for index in (1, 2)]
    body = ShipmentDocumentBody(version_no=2, trade_mode="export", seller_name="Sender", seller_address="China",
        buyer_name="Buyer", buyer_address="Berlin", destination_country="DE", boxes=boxes, include_commercial_invoice=True)
    source = ShipmentDocumentSource(line, sale, order)
    snapshot = documents.render_snapshot(shipment, [source], body)
    assert snapshot["kinds"] == ["packing_list", "customs_draft", "commercial_invoice"]
    assert snapshot["goods"][0]["quantity"] == "4"
    assert snapshot["goods"][0]["currency"] == "EUR"
    assert snapshot["goods"][0]["amount"] == "30.00"
    assert snapshot["goods"][0]["net_weight_kg"] == "2.50"
    metadata = {"revision_no": 1, "is_preview": False, "is_superseded": False}
    for kind in snapshot["kinds"]:
        sheet = load_workbook(BytesIO(xlsx_v1(snapshot, kind, metadata, "posted"))).active
        assert any(cell.value == "=1+1" and cell.data_type == "s" for row in sheet for cell in row)
        if kind == "customs_draft":
            assert any(cell.value == "待补" for row in sheet for cell in row)
    with pytest.raises(AppException, match="装箱数量"):
        documents.render_snapshot(shipment, [source], body.model_copy(update={"boxes": body.boxes[:1]}))
    with pytest.raises(AppException, match="成交币种"):
        documents.render_snapshot(shipment, [ShipmentDocumentSource(line, None, None)], body)


def test_customer_export_keeps_order_lines_and_reconciles_four_customs_sheets():
    shipment = SimpleNamespace(status_code="posted", version_no=1, order_currency_snapshot="EUR",
        shipment_no="SH-EXPORT", business_date=date(2026, 11, 20))
    order = SimpleNamespace(order_no="SO-1", customer_po_no="000-PO", currency="EUR")
    goods = []
    for number, (material, quantity, price) in enumerate([
        ("EN AW-6082 T6", 2, "5.00"),
        ("AL6061-T6", 1, "4.00"),
        ("440B", 1, "2.60"),
        ("赛钢 (POM-C)", 1, "0.90"),
        ("铝 / 钢组合", 1, "1.20"),
    ], 1):
        line = SimpleNamespace(id=uuid4(), work_order_no_snapshot=f"WO-{number}", product_item_no_snapshot=f"P{number}",
            product_item_name_snapshot=f"零件{number}", unit_code="piece", quantity=Decimal(quantity), unit_price=Decimal(price))
        sale = SimpleNamespace(drawing_no_snapshot=f"0000{number}", description_snapshot=f"=Description{number}",
            material_snapshot=material, unit_name_snapshot="件", unit_price=Decimal(price))
        goods.append((line, sale, order))
    body = ShipmentDocumentBody(
        version_no=1, trade_mode="export", seller_name="工厂", seller_address="中国", buyer_name="Customer",
        buyer_address="London", destination_country="GB", export_details=dict(
            seller_name_en="Seller Ltd", invoice_no="INV-1", payment_instructions="Pay to Seller Ltd",
            contract_date="2026-11-19", loading_port="青岛", destination_name_zh="英国", marks="MARK-1"),
        boxes=[dict(box_no=f"B-{index}", gross_weight_kg=weight, length_cm=20, width_cm=12, height_cm=8,
                    lines=[dict(shipment_line_id=line.id, quantity=line.quantity, net_weight_kg="0.25") for line, _, _ in rows])
               for index, (weight, rows) in enumerate([(1, goods[:3]), (2, goods[3:])], 1)],
        customs_profiles=[dict(material_group="aluminum", declared_name="铝支撑件", hs_code="7616991090",
            origin_country="CN", declaration_elements="工业用|铝制", customer_tariff_no="76169910")],
    )
    sources = [ShipmentDocumentSource(*row) for row in goods]
    snapshot = documents.render_snapshot(shipment, sources, body)
    aluminum, steel, plastic, unmatched = snapshot["customs_groups"]
    assert aluminum["goods_line_nos"] == [1, 2]
    assert (aluminum["quantity"], aluminum["amount"], aluminum["net_weight_kg"], aluminum["unit_price"]) == (
        "3", "14.00", "0.50", "4.666667")
    assert [group["material_group"] for group in (steel, plastic, unmatched)] == ["steel", "engineering_plastic", None]
    assert any("材料类别" in issue for issue in snapshot["customs_issues"])
    assert snapshot["header"]["export_details"]["contract_no"] == "000-PO"

    metadata = {"revision_no": 1, "is_preview": False, "is_superseded": False}
    def workbook(kind):
        return load_workbook(BytesIO(xlsx_v2(snapshot, kind, metadata, "posted")))

    invoice = workbook("commercial_invoice")["INVOICE"]
    first = next(row for row in invoice.rows if row[3].value == "00001")
    assert [cell.value for cell in first] == [1, "000-PO", "=Description1", "00001", "EN AW-6082 T6", "76169910", 2, "PCS", 5, 10]
    assert first[2].data_type == "s"
    assert first[6].number_format == "#,##0"
    assert next(row for row in invoice.values if row[0] == "TOTAL")[9] == 18.7
    packing = workbook("packing_list")["PACKING LIST"]
    assert [row[8] for row in packing.values if row[0] == "B-1"] == [1, None, None]
    assert next(row for row in packing.values if row[0] == "TOTAL")[7:9] == (1.25, 3)
    customs = workbook("customs_draft")
    assert customs.sheetnames == ["发票", "合同", "报关单 附1", "装箱单"]
    row = next(row for row in customs["报关单 附1"].values if row[1] == "7616991090")
    assert row[2:7] == ("铝支撑件", "工业用|铝制", 3, "个", .5)
    assert row[9:12] == (4.666667, 14, "EUR")
    for sheet in ("发票", "合同", "报关单 附1"):
        assert any(18.7 in row for row in customs[sheet].values)
    assert next(row for row in customs["装箱单"].values if row[0] == "合计")[5:7] == (3, 1.25)

    revised = load_workbook(BytesIO(xlsx_v3(snapshot, "customs_draft", metadata, "posted")))
    assert revised.sheetnames == customs.sheetnames
    form = revised.active
    layout = load_workbook(CUSTOMS_TEMPLATE).active
    assert form.title == "报关单 附1" and form["A3"].value == "中华人民共和国海关出口货物报关单"
    assert form.merged_cells == layout.merged_cells
    assert form.print_area == layout.print_area
    assert dict(form.page_setup) == dict(layout.page_setup)
    assert form.column_dimensions["O"].width == layout.column_dimensions["O"].width
    assert form.row_dimensions[24].height == layout.row_dimensions[24].height
    assert copy(form["B23"].fill) == copy(layout["B23"].fill)
    assert form["A7"].value == "工厂" and form["E8"].value == "Customer"
    assert form["O6"].value is None and form["J5"].value is None
    assert form["B23"].value == "7616991090" and form["I23"].value == "铝支撑件"
    assert form["B23"].data_type == "s" and form["B23"].number_format == "@"
    assert "原产国：CN" in form["I24"].value
    assert form["S24"].value == 3 and form["S25"].value == .5
    assert form["AA23"].value == 4.666667 and form["AD24"].value == 14
    assert form["AD29"].value == .9 and form["AD41"].value == 18.7
    assert form["P15"].value == 2 and form["R15"].value == 3 and form["V15"].value == 1.25

    multipage = deepcopy(snapshot)
    multipage["customs_groups"] += [
        dict(row, group_no=index) for index, row in enumerate(snapshot["customs_groups"], start=5)
    ]
    paged = customer_customs_workbook(multipage, "出货预览")
    stream = BytesIO()
    paged.save(stream)
    continued = load_workbook(stream).active
    assert "$A$3:$AK$49" in continued.print_area and "$A$52:$AK$98" in continued.print_area
    assert str(continued["A53"].value).endswith("第 2 / 2 页")
    assert "A52:AK52" in continued.merged_cells and "I73:O74" in continued.merged_cells
    assert continued["A72"].value == 7 and continued["AD73"].value == .9
    assert continued["AD90"].value == 2.1

    customer = load_workbook(BytesIO(xlsx_v4(snapshot, "customs_draft", metadata, "posted")))
    template = load_workbook(CUSTOMER_WORKBOOK)
    assert customer.sheetnames == ["报关单 附1", "装箱单", "发票", "合同"]
    assert customer.active.title == "报关单 附1"
    for sheet in customer:
        original = template[sheet.title]
        assert sheet.merged_cells == original.merged_cells
        assert sheet.print_area == original.print_area
        assert dict(sheet.page_setup) == dict(original.page_setup)
        assert not sheet._images
    packing, invoice, contract = (customer[name] for name in ("装箱单", "发票", "合同"))
    assert [packing[cell].value for cell in ("A9", "C9", "D9", "F9", "G9")] == ["B-1", 1, 3, 1, .5]
    assert [packing[cell].value for cell in ("A11", "C11", "F11")] == ["B-1", None, None]
    assert [packing[cell].value for cell in ("C37", "F37", "G37", "B39")] == [2, 3, 1.25, "MARK-1"]
    assert [invoice[cell].value for cell in ("G2", "C7", "C8", "F7", "H7", "H37")] == [
        "INV-1", "铝支撑件", "工业用|铝制", 4.666667, 14, 18.7,
    ]
    assert [contract[cell].value for cell in ("F6", "B3", "A19", "D19", "G28", "B42")] == [
        "000-PO", "工厂\nSeller Ltd", "铝支撑件", "个", 18.7, "MARK-1",
    ]
    assert contract["F9"].value.date() == date(2026, 11, 19)
    assert contract["D7"].value is None and contract["D13"].value is None
    assert copy(invoice["C7"].fill) == copy(template["发票"]["C7"].fill)

    for kind, template_path in (("commercial_invoice", INVOICE_TEMPLATE), ("packing_list", PACKING_TEMPLATE)):
        english = load_workbook(BytesIO(xlsx_v5(snapshot, kind, metadata, "posted")))
        expected = load_workbook(template_path).active
        output = english.active
        assert english.sheetnames == [expected.title] and not output._images
        assert dict(output.page_setup) == dict(expected.page_setup)
        assert output.column_dimensions["C"].width == expected.column_dimensions["C"].width
        assert "INV-1" in output["I3" if kind == "commercial_invoice" else "G3"].value
        if kind == "commercial_invoice":
            assert output["C2"].value.strip() == "COMMERCIAL INVOICE"
            assert [cell.value for cell in output[13]] == [1, "000-PO", "=Description1", "00001", "EN AW-6082 T6", "76169910", 2, 5, 10]
            assert output["C13"].data_type == "s"
            assert output["I18"].value == 18.7 and "Pay to Seller Ltd" in output["A23"].value
            assert "G18:H18" in output.merged_cells and "A23:G26" in output.merged_cells
        else:
            assert output["A2"].value == "PACKING LIST"
            assert "A11:A13" in output.merged_cells and "B11:B13" in output.merged_cells
            assert output["A11"].value == "B-1" and output["A14"].value == "B-2"
            assert output["B11"].value == "Size: 20 × 12 × 8 cm\nG.W.: 1 kg\nN.W.: 0.75 kg"
            assert output["B12"].value is None and output["G11"].value == 2
            assert "2 carton(s), G.W. 3 kg, N.W. 1.25 kg, 0.00384 CBM" in output["A16"].value

    many = dict(snapshot, customs_groups=[dict(aluminum, group_no=index, goods_line_nos=[index])
                 for index in range(1, 17)], boxes=[
        dict(snapshot["boxes"][0], box_no=f"B{index}", items=[dict(line_no=index, quantity="3", net_weight_kg="0.50")])
        for index in range(1, 17)
    ])
    pages = load_workbook(BytesIO(xlsx_v4(many, "customs_draft", metadata, "posted")))
    assert "$A$41:$G$80" in pages["装箱单"].print_area and pages["装箱单"]["A49"].value == "B15"
    assert pages["装箱单"]["C77"].value == 2 and pages["装箱单"]["G77"].value == 1
    assert "$A$41:$I$80" in pages["发票"].print_area and pages["发票"]["H77"].value == 14
    assert "$A$51:$H$100" in pages["合同"].print_area and pages["合同"]["G78"].value == 112

    invoice_lines = [dict(snapshot["goods"][0], line_no=index) for index in range(1, 46)]
    long_box = dict(snapshot["boxes"][0], items=[dict(line_no=index, quantity="2", net_weight_kg="0.25")
                                                    for index in range(1, 46)])
    long_shipment = dict(snapshot, goods=invoice_lines, boxes=[long_box])
    long_invoice = load_workbook(BytesIO(xlsx_v5(long_shipment, "commercial_invoice", metadata, "posted"))).active
    long_packing = load_workbook(BytesIO(xlsx_v5(long_shipment, "packing_list", metadata, "posted"))).active
    assert "$A$130:$I$172" in long_invoice.print_area and long_invoice["I154"].value == 90
    assert "450.00" in long_invoice["A155"].value
    assert "A11:A54" in long_packing.merged_cells and "$A$59:$G$116" in long_packing.print_area
    assert long_packing["A69"].value == "B-1 (cont.)" and long_packing["B69"].value is None
    assert long_packing["G69"].value == 2

    single_line_box = dict(long_box, items=long_box["items"][:1])
    single_line = dict(long_shipment, goods=invoice_lines[:1], boxes=[single_line_box])
    one_carton = load_workbook(BytesIO(xlsx_v5(single_line, "packing_list", metadata, "posted"))).active
    assert one_carton["B11"].value == "Size: 20 × 12 × 8 cm\nG.W.: 1 kg / N.W.: 0.25 kg"

    changed = body.model_copy(update={"customs": [
        CustomsLine(shipment_line_id=goods[1][0].id, origin_country="DE"),
    ]})
    split = documents.render_snapshot(shipment, sources, changed)["customs_groups"]
    assert [group["customs"]["origin_country"] for group in split[:2]] == ["CN", "DE"]


def test_shipment_sources_fall_back_to_confirmed_material_and_only_suggest_positive_unit_weight():
    line = SimpleNamespace(id=uuid4(), unit_code="piece", product_item_no_snapshot="P-001")
    sale = SimpleNamespace(material_snapshot=" EN AW-6082 ", drawing_no_snapshot="DRAW-001")
    source = ShipmentDocumentSource(line, sale, None, work_material="SUS304",
        quoted_material="POM-C", unit_net_weight=Decimal("0.000054"), item_specification="6061 / A / P-001")
    goods = documents.source_goods_details(source)
    assert (goods["material"], goods["material_source"], goods["suggested_material_group"]) == (
        "EN AW-6082", "sales_order", "aluminum")
    assert Decimal(goods["unit_net_weight_kg"]) == Decimal("0.000054")
    sale.material_snapshot = ""
    assert documents.shipment_material(source) == ("SUS304", "work_order")
    assert documents.shipment_material(ShipmentDocumentSource(line, sale, None, quoted_material="POM-C")) == (
        "POM-C", "quotation")
    assert documents.shipment_material(ShipmentDocumentSource(line, sale, None, item_specification="6061 / A / P-001")) == (
        "6061", "product")
    assert documents.shipment_material(ShipmentDocumentSource(line, sale, None, item_specification="铝 / 钢组合"), "POM-C") == (
        "POM-C", "manual")
    assert documents.source_goods_details(ShipmentDocumentSource(line, sale, None, unit_net_weight=Decimal(0)))["unit_net_weight_kg"] is None
    line.unit_code = "kg"
    assert documents.source_goods_details(source)["unit_net_weight_kg"] is None


def test_document_sources_use_scoped_quote_revision_and_batch_read_missing_item_specs(monkeypatch):
    shipment = SimpleNamespace(id=uuid4(), org_id=uuid4())
    known = SimpleNamespace(product_item_id=uuid4(), product_item_no_snapshot="P-1")
    legacy = SimpleNamespace(product_item_id=uuid4(), product_item_no_snapshot="P-2")

    async def execute(statement):
        sql = str(statement.compile(dialect=postgresql.dialect()))
        assert "mes_quotation.revision = mes_sales_order_line.quotation_revision_snapshot" in sql
        assert "mes_quotation_line.org_id = mes_shipment_line.org_id" in sql
        assert "mes_shipment_line.org_id =" in sql
        assert "coalesce(mes_work_order.source_sales_order_line_id, mes_sales_allocation.order_line_id)" in sql
        return SimpleNamespace(all=lambda: [
            (known, None, None, "SUS304", None, Decimal(".1")),
            (legacy, None, None, None, None, None),
        ])

    async def specs(session, numbers):
        assert numbers == ["P-2"]
        return [
            {"id": uuid4(), "specification": "6061"},
            {"id": legacy.product_item_id, "specification": "POM-C"},
        ]

    monkeypatch.setattr(delivery_queries, "find_active_items_by_numbers", specs)
    sources = asyncio.run(repo.shipment_document_lines(SimpleNamespace(execute=execute), shipment))
    assert sources[0].unit_net_weight == Decimal(".1")
    assert sources[1].item_specification == "POM-C"


def test_document_versions_invoice_binding_and_scope(data, monkeypatch):
    user, order, _, _, sessions, engine, metadata = data
    user.permissions.extend([documents.DOCUMENTS, documents.INVOICE])
    user.permission_scopes.update({documents.DOCUMENTS: "organization", documents.INVOICE: "organization"})
    monkeypatch.setattr(documents, "get_session_context", sessions)
    attachment_id = uuid4()
    with engine.begin() as connection:
        connection.execute(metadata.tables["file_attachment"].insert().values(id=attachment_id))
    async def rows(session, shipment):
        return [ShipmentDocumentSource(line, None, None) for line in await repo.shipment_lines(session, shipment.id)]
    async def bind(session, ids, **kwargs):
        assert ids == [attachment_id] and kwargs["scene_code"] == documents.INVOICE_SCENE
        return [SimpleNamespace(content_type="application/pdf")]
    monkeypatch.setattr(repo, "shipment_document_lines", rows)
    monkeypatch.setattr(documents.files, "bind", bind)

    async def run():
        shipment = await service.save_shipment(ship_body(order), user)
        body = ShipmentDocumentBody(version_no=1, trade_mode="domestic", seller_name="出货公司", buyer_name="购方",
            buyer_tax_no="TEST-TAX", domestic_details=dict(contract_no="TEST-01", contract_date="2026-11-18",
                                                            payment_terms="月结", signed_at="青岛", contract_terms="按批交付"))
        uncommitted = await documents.make_documents(shipment["id"], body, user, preview=True)
        assert uncommitted["kinds"] == ["domestic_invoice", "domestic_contract"]
        assert (await documents.document_set(shipment["id"], user))["versions"] == []
        preview = await documents.make_documents(shipment["id"], body, user)
        assert preview["is_preview"] is True
        assert (await documents.make_documents(shipment["id"], body, user))["id"] == preview["id"]
        shipment = await service.shipment_action(shipment["id"], "post", DeliveryCommand(version_no=1), user)
        invoice = ShipmentInvoiceBody(invoice_no="12345", issued_date="2026-11-18", attachment_id=attachment_id)
        with pytest.raises(AppException, match="国内发票"):
            await documents.register_invoice(shipment["id"], invoice, user)
        with pytest.raises(AppException, match="刷新"):
            await documents.make_documents(shipment["id"], body, user)
        body.version_no = shipment["version_no"]
        current = await documents.make_documents(shipment["id"], body, user)
        assert current["is_preview"] is False and current["revision_no"] == 2
        assert current["template_key"] == "shipment_xlsx_domestic_v1"
        for kind, title in (("domestic_invoice", "发票"), ("domestic_contract", "合同")):
            snapshot, meta, status = await documents.export_data(shipment["id"], current["id"], kind, user)
            workbook = load_workbook(BytesIO(RENDERERS[meta["template_key"]](snapshot, kind, meta, status)))
            assert workbook.sheetnames == [title]
            sheet = workbook.active
            assert sheet.merged_cells == load_workbook(CUSTOMER_WORKBOOK)[title].merged_cells
            if kind == "domestic_invoice":
                assert sheet["G2"].value == shipment["shipment_no"] and sheet["C3"].value == "购方"
                assert sheet["F4"].value == "购方税号 TEST-TAX" and sheet["H37"].value == 5
                assert "出货含税价" in sheet["A2"].value
            else:
                assert sheet["F6"].value == "TEST-01" and sheet["B3"].value == "出货公司"
                assert sheet["F9"].value.date() == date(2026, 11, 18)
                assert sheet["B40"].value == "月结" and sheet["A29"].value == "按批交付" and sheet["G28"].value == 5
        saved = await documents.register_invoice(shipment["id"], invoice, user)
        assert (await documents.register_invoice(shipment["id"], invoice, user))["id"] == saved["id"]
        async with sessions() as session:
            assert await documents.invoice_access(session, user, saved["id"])
            stranger = SimpleNamespace(**{**vars(user), "permissions": [documents.LIST]})
            assert not await documents.invoice_access(session, stranger, saved["id"])
        with pytest.raises(AppException, match="权限"):
            await documents.document_set(shipment["id"], stranger)
        assert (await documents.document_set(shipment["id"], user))["versions"][1]["is_superseded"]
        await service.shipment_action(shipment["id"], "cancel", DeliveryCommand(version_no=2, reason="取消"), user)
        snapshot, meta, status = await documents.export_data(shipment["id"], current["id"], "domestic_invoice", user)
        sheet = load_workbook(BytesIO(RENDERERS[meta["template_key"]](snapshot, "domestic_invoice", meta, status))).active
        assert "已取消" in sheet["A2"].value
        assert "已取消" in load_workbook(BytesIO(RENDERERS["shipment_xlsx_v1"](
            snapshot, "invoice_request", meta, status))).active["A1"].value

    asyncio.run(run())


def test_domestic_customer_forms_keep_order_prices_and_separate_currency_or_tax_basis():
    shipment = SimpleNamespace(status_code="posted", version_no=1, shipment_no="SH-001", business_date=date(2026, 11, 18))
    order = SimpleNamespace(order_no="SO-1", currency="CNY", customer_po_no="PO-0001")
    sale = SimpleNamespace(drawing_no_snapshot="DW-001", material_snapshot="6061", unit_name_snapshot="件",
                           description_snapshot="壳体", unit_price=Decimal("7.50"))
    lines = [SimpleNamespace(id=uuid4(), work_order_no_snapshot=f"WO-{index}", product_item_no_snapshot="P1",
                             product_item_name_snapshot="货品", unit_code="piece", quantity=Decimal(2), unit_price=Decimal(5))
             for index in range(17)]
    sources = [ShipmentDocumentSource(line, sale, order) for line in lines[:16]] + [ShipmentDocumentSource(lines[-1], None, None)]
    body = ShipmentDocumentBody(version_no=1, trade_mode="domestic", seller_name="销售方", buyer_name="购方")
    snapshot = documents.render_snapshot(shipment, sources, body)
    metadata = {"is_preview": False, "is_superseded": False}
    renderer = RENDERERS["shipment_xlsx_domestic_v1"]
    sheet = load_workbook(BytesIO(renderer(snapshot, "domestic_invoice", metadata, "posted"))).active
    assert sheet["C7"].value == "壳体" and sheet["C8"].value == "图号 DW-001, 材料 6061"
    assert sheet["F7"].value == 7.5 and sheet["H7"].value == 15
    assert sheet["H37"].value is None and sheet["H77"].value == 240
    assert sheet["H117"].value == 10 and "出货含税价" in sheet["A82"].value
    contract = load_workbook(BytesIO(renderer(snapshot, "domestic_contract", metadata, "posted"))).active
    assert contract["G28"].value is None and contract["G78"].value == 240 and contract["G128"].value == 10


def test_export_revision_selects_new_template_and_keeps_preview_downloadable(data, monkeypatch):
    user, order, _, _, sessions, *_ = data
    user.permissions.append(documents.DOCUMENTS)
    user.permission_scopes[documents.DOCUMENTS] = "organization"
    monkeypatch.setattr(documents, "get_session_context", sessions)

    async def rows(session, shipment):
        sale = SimpleNamespace(drawing_no_snapshot="D-1", material_snapshot="6061", unit_name_snapshot="件",
            unit_price=Decimal("7.75"))
        customer_order = SimpleNamespace(order_no="SO-1", customer_po_no="0001", currency="EUR")
        return [ShipmentDocumentSource(line, sale, customer_order) for line in await repo.shipment_lines(session, shipment.id)]

    monkeypatch.setattr(repo, "shipment_document_lines", rows)

    async def run():
        shipment = await service.save_shipment(ship_body(order, lines=[
            dict(work_order_id=order.id, quantity=2, unit_price="2.50"),
        ]), user)
        body = ShipmentDocumentBody(
            version_no=shipment["version_no"], trade_mode="export", seller_name="Seller",
            seller_address="China", buyer_name="Buyer", buyer_address="Berlin", destination_country="DE",
            boxes=[dict(box_no="1", gross_weight_kg="1", length_cm=15, width_cm=20, height_cm=10,
                        lines=[dict(shipment_line_id=shipment["lines"][0]["id"], quantity=2, net_weight_kg=".5")])],
        )
        preview = await documents.make_documents(shipment["id"], body, user)
        assert preview["is_preview"] and preview["template_key"] == "shipment_xlsx_v5"
        assert "commercial_invoice" in preview["kinds"]
        listing = await documents.document_set(shipment["id"], user)
        assert listing["source_goods"][0]["suggested_material_group"] == "aluminum"
        assert listing["source_goods"][0]["customer_po_no"] == "0001"
        assert (await documents.make_documents(shipment["id"], body, user))["id"] == preview["id"]

        posted_shipment = await service.shipment_action(shipment["id"], "post", DeliveryCommand(version_no=1), user)
        current = await documents.make_documents(shipment["id"], body.model_copy(update={
            "version_no": posted_shipment["version_no"],
        }), user)
        assert current["revision_no"] == 2 and not current["is_preview"]
        snapshot, metadata, status = await documents.export_data(shipment["id"], preview["id"], "customs_draft", user)
        assert metadata["is_superseded"] and metadata["is_preview"] and status == "posted"
        workbook = load_workbook(BytesIO(RENDERERS[metadata["template_key"]](snapshot, "customs_draft", metadata, status)))
        assert "历史版本" in workbook["报关单 附1"]["A4"].value
        assert "历史版本" in workbook["发票"]["A2"].value
        for kind, title in (("commercial_invoice", "INVOICE"), ("packing_list", "PACKING LIST")):
            snapshot, metadata, status = await documents.export_data(shipment["id"], preview["id"], kind, user)
            english = load_workbook(BytesIO(RENDERERS[metadata["template_key"]](snapshot, kind, metadata, status)))
            assert english.sheetnames == [title]
            assert english.active["A9"].value == "Superseded · Shipment preview"

    asyncio.run(run())


def test_complete_delivery_reconciliation_cancel_flow_preserves_facts(data):
    user, order, task, report, sessions, engine, metadata = data
    async def run():
        shipment = await posted(data)
        assert shipment["total_amount"] == "5.00" and shipment["status_code"] == "posted"
        # Only final operation output counts; creating/confirming delivery doesn't mutate production.
        assert task.good_quantity == 5 and order.status_code == "in_progress"
        original = shipment["lines"][0]["quantity"]
        rec = await service.save_reconciliation(rec_body(shipment), user)
        assert rec["total_amount"] == "4.99"
        assert (await service.save_reconciliation(rec_body(shipment), user))["id"] == rec["id"]
        with pytest.raises(AppException, match="占用"):
            await service.save_reconciliation(rec_body(shipment, reconciliation_no="R2", idempotency_key="another-rec-key"), user)
        with pytest.raises(AppException, match="先取消"):
            await service.shipment_action(shipment["id"], "cancel", DeliveryCommand(version_no=2, reason="撤销"), user)
        async with sessions() as session:
            with pytest.raises(AppException, match="有效出货"):
                await report_service.validate_change(session, report, task, order, SimpleNamespace())
        rec = await service.reconciliation_action(rec["id"], "confirm", DeliveryCommand(version_no=1), user)
        assert rec["status_code"] == "confirmed"
        rec = await service.reconciliation_action(rec["id"], "cancel", DeliveryCommand(version_no=2, reason="客户复核"), user)
        assert rec["status_code"] == "cancelled"
        # Cancellation releases the unique reservation and keeps prior reconciliation lines.
        replacement = await service.save_reconciliation(rec_body(shipment, reconciliation_no="R3", idempotency_key="replacement-key"), user)
        await service.reconciliation_action(replacement["id"], "cancel", DeliveryCommand(version_no=1, reason="取消"), user)
        shipment = await service.shipment_action(shipment["id"], "cancel", DeliveryCommand(version_no=2, reason="取消直发"), user)
        assert shipment["status_code"] == "cancelled" and shipment["lines"][0]["quantity"] == original
        async with sessions() as session: assert await repo.shipped_quantity(session, order.id) == 0
    asyncio.run(run())
    with engine.connect() as connection:
        assert len(connection.execute(select(metadata.tables["mes_reconciliation_line"])).all()) == 2


def test_draft_does_not_reserve_output_but_confirmation_rechecks_and_locks(data):
    user, order, *_ = data
    async def run():
        one = await service.save_shipment(ship_body(order), user)
        assert (await service.save_shipment(ship_body(order), user))["id"] == one["id"]
        with pytest.raises(AppException, match="幂等"):
            await service.save_shipment(ship_body(order, note="不同内容"), user)
        two = await service.save_shipment(ship_body(order, shipment_no="S2", idempotency_key="ship-key-2",
            lines=[dict(work_order_id=order.id, quantity=4, unit_price=1)]), user)
        await service.shipment_action(one["id"], "post", DeliveryCommand(version_no=1), user)
        with pytest.raises(AppException, match="数量不足"):
            await service.shipment_action(two["id"], "post", DeliveryCommand(version_no=1), user)
        with pytest.raises(AppException, match="刷新"):
            await service.shipment_action(one["id"], "cancel", DeliveryCommand(version_no=1, reason="旧版本"), user)
        await service.shipment_action(one["id"], "cancel", DeliveryCommand(version_no=2, reason="撤销"), user)
        assert (await service.shipment_action(two["id"], "post", DeliveryCommand(version_no=1), user))["status_code"] == "posted"
    asyncio.run(run())


@pytest.mark.parametrize("failure", ["customer", "period", "org", "cancelled", "adjustment"])
def test_reconciliation_rejects_invalid_source_and_rolls_back(data, failure):
    user, _, _, _, _, engine, metadata = data
    async def run():
        shipment = await posted(data)
        changes = {}
        if failure == "customer": changes["customer_no_snapshot"] = "C2"
        if failure == "period": changes.update(period_start="2026-09-01", period_end="2026-09-30")
        if failure == "org": changes["org_id"] = uuid4()
        if failure == "cancelled": await service.shipment_action(shipment["id"], "cancel", DeliveryCommand(version_no=2, reason="取消"), user)
        if failure == "adjustment": changes["lines"] = [dict(shipment_line_id=shipment["lines"][0]["id"], adjustment_amount=-10, adjustment_reason="扣减")]
        with pytest.raises(AppException): await service.save_reconciliation(rec_body(shipment, **changes), user)
    asyncio.run(run())
    with engine.connect() as connection:
        assert not connection.execute(select(metadata.tables["mes_reconciliation"])).all()
        assert not connection.execute(select(metadata.tables["mes_reconciliation_line"])).all()


@pytest.mark.parametrize("status,quality,available", [("pending", False, 5), ("in_progress", False, 0), ("waiting_quality", True, 0), ("completed", True, 5), ("cancelled", False, 0)])
def test_availability_is_final_eligible_good_output_only(data, monkeypatch, status, quality, available):
    user, order, task, _, sessions, *_ = data
    task.status_code, task.is_quality_required = status, quality
    async def operations(*args): return [SimpleNamespace(sequence_no=0, good_quantity=100), task]
    monkeypatch.setattr(repository, "work_order_operations", operations)
    async def run():
        async with sessions() as session:
            remaining, _, _ = await service.available(session, order)
            assert remaining == available
    asyncio.run(run())


def test_schema_money_scope_and_lock_contracts(data):
    user, order, *_ = data
    assert amount(Decimal("1.005")) == Decimal("1.01")
    with pytest.raises(AppException): amount(Decimal("10000000000000000"))
    with pytest.raises(ValidationError): ship_body(order, lines=[dict(work_order_id=order.id, quantity="1.0001", unit_price=1)])
    with pytest.raises(ValidationError): ship_body(order, lines=[dict(work_order_id=order.id, quantity=1, unit_price=-1)])
    with pytest.raises(ValidationError): ship_body(order, lines=[dict(work_order_id=order.id, quantity=1, unit_price=1)] * 2)
    with pytest.raises(ValidationError): rec_body({"lines": [{"id": uuid4()}]}, lines=[dict(shipment_line_id=uuid4(), adjustment_amount=1)])
    user.permission_scopes["mes:shipment:list"] = "self"
    sql = str(repo.documents_statement("shipments", DeliveryQuery(), user).compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))
    assert "mes_shipment.created_by" in sql and "t_test." not in sql and "tenant_id" not in sql
    source_sql = str(repo.source_lines_statement(user).compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))
    assert "reservation_released_at IS NULL" in source_sql and "posted" in source_sql


def test_draft_edit_and_scoped_detail_list(data, monkeypatch):
    user, order, *_ = data
    async def run():
        draft = await service.save_shipment(ship_body(order), user)
        edited = await service.save_shipment(ShipmentUpdate(**ship_body(order, note="更新").model_dump(), version_no=1), user, draft["id"])
        assert edited["version_no"] == 2 and edited["note"] == "更新" and len(edited["lines"]) == 1
        rows = await service.documents("shipments", DeliveryQuery(), user)
        assert rows["total"] == 1 and rows["items"][0]["total_amount"] == "5.00"
        user.permission_scopes["mes:shipment:list"] = "self"
        user.user_id = uuid4()
        assert (await service.documents("shipments", DeliveryQuery(), user))["total"] == 0
        with pytest.raises(AppException, match="无权"): await service.detail("shipments", draft["id"], user)
    asyncio.run(run())


def test_http_routes_and_permissions_do_not_bypass_service(data, monkeypatch):
    user, order, *_ = data
    app = FastAPI(); app.include_router(router); register_exception_handlers(app)
    app.dependency_overrides[get_current_user] = lambda: user
    async def sources(*args): return dict(items=[], total=0, page=1, page_size=10)
    monkeypatch.setattr(service, "sources", sources)
    # Use mocked source reads: actual lifecycle tests above run against isolated real ORM transactions.
    with TestClient(app) as client:
        assert client.get("/api/mes/shipments/sources").status_code == 200
        assert client.get("/api/mes/reconciliations/sources").status_code == 200
        user.permissions = []
        assert client.get("/api/mes/shipments").status_code == 403
        assert client.post("/api/mes/shipments", json=ship_body(order).model_dump(mode="json")).status_code == 403


def test_locking_sql_preserves_scope_and_stable_parent_order(data, monkeypatch):
    user, order, *_ = data
    user.permission_scopes["mes:shipment:manage"] = "self"
    user.permission_scopes["mes:reconciliation:manage"] = "self"
    statements = []
    monkeypatch.setattr(repo, "lock_orders", type(repo).lock_orders.__get__(repo))
    async def execute(statement):
        statements.append(str(statement.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})))
        return SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: []))
    async def run():
        session = SimpleNamespace(execute=execute)
        await repo.lock_orders(session, [order.id], user)
        await repo.lock_shipments_for_lines(session, [uuid4()], user)
    asyncio.run(run())
    assert "FOR UPDATE" in statements[0] and "ORDER BY mes_work_order.id" in statements[0]
    assert "mes_work_order.created_by" in statements[0] and "deleted_at IS NULL" in statements[0]
    assert "FOR UPDATE" in statements[1] and "ORDER BY mes_shipment.id" in statements[1]
    assert "mes_shipment.created_by" in statements[1]


def test_money_overflow_rolls_back_new_header(data):
    user, order, _, _, _, engine, metadata = data
    async def run():
        body = ship_body(order, lines=[dict(work_order_id=order.id, quantity=2, unit_price="9999999999999999.99")])
        with pytest.raises(AppException, match="金额超出"):
            await service.save_shipment(body, user)
    asyncio.run(run())
    with engine.connect() as connection:
        assert not connection.execute(select(metadata.tables["mes_shipment"])).all()
