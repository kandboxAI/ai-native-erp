"""按出货版本生成单据渲染快照，沿用出货及附件的数据权限。"""
from collections import defaultdict
from decimal import Decimal

from app.auth.scope_filters import resolve_write_org_id
from app.core.exceptions import AppException
from app.framework.db.session import get_session_context
from app.modules.file.service import DOCUMENT_MAX_BYTES, register_file_access, register_file_scene, service as files
from .delivery_models import MesShipment, MesShipmentDocumentRevision, MesShipmentInvoice
from .delivery_repository import ShipmentDocumentSource, delivery_repository as repo
from .delivery_service import amount, plain
from .shipment_customs import declaration_fields, declaration_groups, suggest_material_group
from .shipment_document_schemas import DomesticDetails, ExportDetails

LIST = "mes:shipment:list"
DOCUMENTS = "mes:shipment:documents"
MANAGE = "mes:shipment:manage"
INVOICE = "mes:shipment:invoice"
INVOICE_SCENE = "mes_shipment_invoice"
DOMESTIC_TEMPLATE_KEY = "shipment_xlsx_domestic_v1"
EXPORT_TEMPLATE_KEY = "shipment_xlsx_v5"

register_file_scene(INVOICE_SCENE, kinds={"document"}, max_bytes=DOCUMENT_MAX_BYTES, max_count=1)


async def invoice_access(session, user, identifier):
    if not {LIST, DOCUMENTS}.issubset(user.permissions):
        return False
    invoice = await repo.shipment_invoice(session, identifier)
    if invoice is None:
        return False
    shipment = await repo.document(session, MesShipment, invoice.shipment_id, user, LIST)
    return bool(shipment and shipment.org_id == invoice.org_id and
        await repo.document(session, MesShipment, invoice.shipment_id, user, DOCUMENTS))


register_file_access(INVOICE_SCENE, invoice_access)


async def authorized_shipment(session, identifier, user, operation=None):
    permissions = [LIST, DOCUMENTS]
    if operation:
        permissions.append(operation)
    if not set(permissions).issubset(user.permissions):
        raise AppException("缺少出货单据操作权限", 403)
    for permission in permissions:
        shipment = await repo.document(session, MesShipment, identifier, user, permission, lock=permission == operation)
        if shipment is None:
            raise AppException("出货单不存在或超出数据范围", 404)
    if operation:
        resolve_write_org_id(user, shipment.org_id, operation)
    return shipment


def order_goods(sale, order):
    return dict(
        drawing_no=sale.drawing_no_snapshot if sale else "",
        material=getattr(sale, "material_snapshot", ""),
        order_description=getattr(sale, "description_snapshot", ""),
        sales_order_no=order.order_no if order else "",
        customer_po_no=getattr(order, "customer_po_no", ""),
    )


def shipment_material(source: ShipmentDocumentSource, entered=""):
    for value, origin in (
        (getattr(source.sale, "material_snapshot", ""), "sales_order"),
        (source.work_material, "work_order"),
        (source.quoted_material, "quotation"),
    ):
        if value and value.strip():
            return value.strip(), origin
    spec = (source.item_specification or "").strip()
    if spec:
        # 订单自动建档的规格有固定结构：材料 / 图纸版本 / 本货品编号。
        pieces = spec.split(" / ")
        if len(pieces) == 3 and pieces[-1] == source.line.product_item_no_snapshot:
            spec = pieces[0].strip()
        if suggest_material_group(spec):
            return spec, "product"
    return (entered, "manual") if entered else ("", None)


def source_goods_details(source: ShipmentDocumentSource):
    material, origin = shipment_material(source)
    weight = source.unit_net_weight
    return {
        **order_goods(source.sale, source.order),
        "shipment_line_id": str(source.line.id),
        "material": material,
        "material_source": origin,
        "suggested_material_group": suggest_material_group(material),
        "unit_net_weight_kg": str(weight) if (weight and weight > 0 and source.line.unit_code in {"piece", "branch"}) else None,
    }


def render_snapshot(shipment, rows: list[ShipmentDocumentSource], body):
    if shipment.status_code == "cancelled":
        raise AppException("已取消出货单不能生成新单据", 409)
    if shipment.version_no != body.version_no:
        raise AppException("出货单已变化，请刷新出货详情后生成", 409)
    if not rows:
        raise AppException("出货单没有货品明细", 422)

    by_id = {source.line.id: i for i, source in enumerate(rows, 1)}
    customs = {row.shipment_line_id: row for row in body.customs}
    profiles = {profile.material_group: profile for profile in body.customs_profiles}
    if not customs.keys() <= by_id.keys():
        raise AppException("报关货品必须来自当前出货单", 422)
    packed_qty, net_kg = defaultdict(Decimal), defaultdict(Decimal)
    boxes = []
    for box in body.boxes:
        items = []
        for entry in box.lines:
            if entry.shipment_line_id not in by_id:
                raise AppException("箱内货品必须来自当前出货单", 422)
            line_no = by_id[entry.shipment_line_id]
            packed_qty[entry.shipment_line_id] += entry.quantity
            net_kg[entry.shipment_line_id] += entry.net_weight_kg
            items.append({"line_no": line_no, "quantity": str(entry.quantity), "net_weight_kg": str(entry.net_weight_kg)})
        boxes.append(dict(**box.model_dump(mode="json", exclude={"lines"}), items=items))

    goods = []
    for index, source_row in enumerate(rows, 1):
        line, sale, order = source_row.line, source_row.sale, source_row.order
        if body.trade_mode == "export" and packed_qty[line.id] != line.quantity:
            raise AppException(f"{line.work_order_no_snapshot} 的装箱数量合计须等于本次出货数量 {line.quantity}", 422)
        if body.trade_mode == "export" and not (sale and order):
            raise AppException(f"{line.work_order_no_snapshot} 缺少来源客户订单及成交币种，不能生成出口金额", 422)
        order_currency = getattr(shipment, "order_currency_snapshot", None)
        if order_currency:
            price, currency, price_basis = line.unit_price, order_currency, "订单未税价"
        elif sale and order:
            price, currency, price_basis = sale.unit_price, order.currency, "订单未税价"
        else:
            price, currency, price_basis = line.unit_price, "CNY", "出货含税价"
        declaration = customs.get(line.id)
        source = order_goods(sale, order)
        row = dict(
            line_no=index, work_order_no=line.work_order_no_snapshot,
            item_no=line.product_item_no_snapshot, item_name=line.product_item_name_snapshot,
            **source,
            unit=sale.unit_name_snapshot if sale else line.unit_code,
            quantity=str(line.quantity), price=str(price), currency=currency, price_basis=price_basis,
            amount=str(amount(line.quantity * price)), net_weight_kg=str(net_kg[line.id]),
            customs={},
        )
        if body.trade_mode == "export":
            material, _ = shipment_material(source_row, getattr(declaration, "material_name", ""))
            family = getattr(declaration, "material_group", None) or suggest_material_group(material)
            row.update(
                material=material, unit_code=line.unit_code, material_group=family,
                customs=declaration_fields(declaration, profiles.get(family)),
                customs_input=declaration.model_dump(mode="json", exclude={"shipment_line_id"}) if declaration else {},
            )
        goods.append(row)
    if body.trade_mode == "export" and len({row["currency"] for row in goods}) != 1:
        raise AppException("默认出口模板要求同一成交币种，请将不同币种的货品分别出货", 422)
    kinds = ["domestic_invoice", "domestic_contract"] if body.trade_mode == "domestic" else ["packing_list", "customs_draft", "commercial_invoice"]
    snapshot = dict(
        shipment_no=shipment.shipment_no, business_date=shipment.business_date.isoformat(),
        kinds=kinds,
        goods=goods, boxes=boxes,
        header=body.model_dump(mode="json", exclude={"version_no", "boxes", "customs", "customs_profiles", "export_details", "domestic_details"}),
    )
    if body.trade_mode == "export":
        header = snapshot["header"]
        header["include_commercial_invoice"] = True
        details = (body.export_details or ExportDetails()).model_dump(mode="json")
        customer_pos = {row["customer_po_no"] for row in goods}
        details["invoice_no"] = details["invoice_no"] or shipment.shipment_no
        if not details["contract_no"] and len(customer_pos) == 1:
            details["contract_no"] = next(iter(customer_pos))
        header["export_details"] = details
        groups = declaration_groups(goods)
        snapshot["customs_groups"] = groups
        snapshot["customs_profiles"] = [profile.model_dump(mode="json") for profile in body.customs_profiles]
        issues = []
        for group in groups:
            required = {
                "declared_name": "申报品名", "hs_code": "HS 编码",
                "origin_country": "原产国", "declaration_elements": "申报要素",
            }
            missing = [label for field, label in required.items() if not group["customs"].get(field)]
            if not group["material_group"]:
                missing.insert(0, "材料类别")
            if missing:
                issues.append(f"第 {group['group_no']} 项（{group['name']}）：{'、'.join(missing)}待补")
            hs_code = group["customs"].get("hs_code")
            if hs_code and len(hs_code) != 10:
                issues.append(f"第 {group['group_no']} 项（{group['name']}）：请核对中国申报商品编号是否为 10 位")
        snapshot["customs_issues"] = issues
    else:
        details = (body.domestic_details or DomesticDetails()).model_dump(mode="json")
        details["invoice_no"] = details["invoice_no"] or shipment.shipment_no
        customer_pos = {row["customer_po_no"] for row in goods}
        if not details["contract_no"] and len(customer_pos) == 1:
            details["contract_no"] = next(iter(customer_pos)) or ""
        snapshot["header"]["domestic_details"] = details
    return snapshot


def revision_details(row, shipment, latest_revision_no):
    return dict(**plain(row, ("id", "revision_no", "template_key", "is_preview", "created_at")),
        kinds=row.render_snapshot["kinds"],
        is_superseded=row.shipment_version_no_snapshot != shipment.version_no or row.revision_no != latest_revision_no)


def invoice_details(row):
    return plain(row, ("id", "invoice_no", "issued_date", "attachment_id", "created_at"))


async def document_set(identifier, user):
    async with get_session_context() as session:
        shipment = await authorized_shipment(session, identifier, user)
        revisions = await repo.shipment_document_revisions(session, shipment)
        latest = revisions[0] if revisions else None
        source_goods = [source_goods_details(source) for source in await repo.shipment_document_lines(session, shipment)]
        return dict(status_code=shipment.status_code,
            versions=[revision_details(row, shipment, latest.revision_no) for row in revisions],
            latest_snapshot=latest.render_snapshot if latest else None,
            source_goods=source_goods,
            invoices=[invoice_details(row) for row in await repo.shipment_invoices(session, shipment)])


async def make_documents(identifier, body, user, *, preview=False):
    async with get_session_context() as session:
        shipment = await authorized_shipment(session, identifier, user, MANAGE)
        snapshot = render_snapshot(shipment, await repo.shipment_document_lines(session, shipment), body)
        if body.trade_mode == "export" and await repo.shipment_invoices(session, shipment):
            raise AppException("出货单已登记正式发票，不能改为出口单据", 409)
        if preview:
            return snapshot
        template_key = EXPORT_TEMPLATE_KEY if body.trade_mode == "export" else DOMESTIC_TEMPLATE_KEY
        latest_rows = await repo.shipment_document_revisions(session, shipment, limit=1)
        latest = latest_rows[0] if latest_rows else None
        if (latest and latest.shipment_version_no_snapshot == shipment.version_no
                and latest.template_key == template_key and latest.render_snapshot == snapshot):
            return revision_details(latest, shipment, latest.revision_no)
        revision = MesShipmentDocumentRevision(org_id=shipment.org_id, shipment_id=shipment.id,
            revision_no=(latest.revision_no + 1 if latest else 1), shipment_version_no_snapshot=shipment.version_no,
            is_preview=shipment.status_code != "posted", template_key=template_key,
            render_snapshot=snapshot, created_by=user.user_id)
        repo.add(session, revision)
        await session.flush()
        result = revision_details(revision, shipment, revision.revision_no)
        await session.commit()
        return result


async def register_invoice(identifier, body, user):
    async with get_session_context() as session:
        shipment = await authorized_shipment(session, identifier, user, INVOICE)
        if shipment.status_code != "posted":
            raise AppException("出货确认后才能登记正式发票", 409)
        versions = await repo.shipment_document_revisions(session, shipment, limit=1)
        if (not versions or versions[0].shipment_version_no_snapshot != shipment.version_no
                or not {"domestic_invoice", "invoice_request"}.intersection(versions[0].render_snapshot["kinds"])):
            raise AppException("请先生成当前出货版本的国内发票", 409)
        for existing in await repo.shipment_invoices(session, shipment):
            if existing.invoice_no == body.invoice_no:
                if existing.issued_date != body.issued_date or existing.attachment_id != body.attachment_id:
                    raise AppException("该发票号码已在本出货单登记，请核对原记录", 409)
                return invoice_details(existing)
        row = MesShipmentInvoice(org_id=shipment.org_id, shipment_id=shipment.id,
            invoice_no=body.invoice_no, issued_date=body.issued_date,
            attachment_id=body.attachment_id, created_by=user.user_id)
        repo.add(session, row)
        await session.flush()
        attachments = await files.bind(session, [body.attachment_id], user=user, org_id=shipment.org_id,
            scene_code=INVOICE_SCENE, business_type_code=INVOICE_SCENE, business_id=row.id)
        if attachments[0].content_type != "application/pdf":
            raise AppException("请上传正式发票 PDF", 422)
        result = invoice_details(row)
        await session.commit()
        return result


async def export_data(identifier, revision_id, kind, user):
    async with get_session_context() as session:
        shipment = await authorized_shipment(session, identifier, user)
        revision = await repo.shipment_document_revision(session, shipment, revision_id)
        if revision is None or kind not in revision.render_snapshot["kinds"]:
            raise AppException("当前版本未生成该单据", 404)
        latest, = await repo.shipment_document_revisions(session, shipment, limit=1)
        metadata = revision_details(revision, shipment, latest.revision_no)
        return revision.render_snapshot, metadata, shipment.status_code
