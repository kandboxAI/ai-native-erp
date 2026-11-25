from app.auth.scope_filters import resolve_write_org_id
from app.core.exceptions import AppException
from app.framework.db.models import utc_now
from app.framework.db.session import get_session_context
from .models import InvSupplierPrice
from .repository import price_repository as repo


class SupplierPriceService:
    async def save(self, body, user, identifier=None):
        if "inventory_supplier_price:manage" not in user.permissions: raise AppException("缺少采购价维护权限", 403)
        org_id = resolve_write_org_id(user, body.org_id, "inventory_supplier_price:manage")
        async with get_session_context() as session:
            await repo.lock(session, org_id)
            row = await repo.get(session, identifier, user) if identifier else None
            if identifier:
                if row is None: raise AppException("采购价不存在或无权修改", 404)
                if row.org_id != org_id: raise AppException("采购价所属组织不能变更", 409)
                if row.version_no != body.version_no: raise AppException("采购价已更新，请刷新后重试", 409)
            unchanged = row is not None and (row.supplier_id, row.item_id, row.currency_code) == (body.supplier_id, body.item_id, body.currency_code)
            unit_code = row.unit_code if unchanged else None
            if body.is_active or not unchanged:
                supplier, item, currency = await repo.references(session, body.supplier_id, body.item_id, body.currency_code)
                if not supplier or item is None or not currency: raise AppException("供应商、物料或币种不存在或已停用", 409)
                unit_code = item.unit_code
            if body.is_active and await repo.overlaps(session, body, identifier): raise AppException("同组织、供应商、物料及币种已有重叠有效期的采购价", 409)
            if row is None: row = InvSupplierPrice(org_id=org_id, created_by=user.user_id, updated_by=user.user_id)
            else: row.version_no += 1
            for key, value in body.model_dump(exclude={"org_id", "version_no"}).items(): setattr(row, key, value)
            row.unit_code = unit_code
            row.updated_at, row.updated_by = utc_now(), user.user_id
            repo.add(session, row)
            await session.flush()
            result = row.model_dump(exclude={"flex_form", "deleted_at", "deleted_by"})
            result["unit_price"] = str(row.unit_price)
            await session.commit()
            return result


price_service = SupplierPriceService()
