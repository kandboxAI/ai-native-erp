"""供应商与收款账户的数据访问。"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import status
from sqlalchemy import func
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.auth.schemas import AuthenticatedUser
from app.core.exceptions import AppException
from app.framework.crud.repository import SqlModelCrudRepository
from app.framework.db.ids import uuid7
from app.framework.db.models import utc_now
from app.modules.masterdata.models import MdOrganization, MdParty, MdPerson
from app.modules.supplier_category.models import MdSupplierCategory

from .crypto import encrypt_account_no, mask_account_no
from .models import MdSupplier, MdSupplierBankAccount
from .schemas import SupplierBankAccountItem, SupplierItem, SupplierOption

PARTY_TYPE_ORGANIZATION = "organization"
PARTY_TYPE_PERSON = "person"


async def _normalize_supplier(session: AsyncSession, data: dict[str, Any], current_user: AuthenticatedUser, entity) -> dict[str, Any]:
    if entity is None and not data.get("supplier_no"):
        data["supplier_no"] = f"GYS-{uuid7().hex[-8:].upper()}"
    category_id = data.get("category_id")
    if category_id is not None:
        exists = (
            await session.exec(
                select(MdSupplierCategory.id).where(MdSupplierCategory.id == category_id, MdSupplierCategory.deleted_at.is_(None))
            )
        ).first()
        if exists is None:
            raise AppException("供应商分类不存在", status_code=status.HTTP_400_BAD_REQUEST)
    if entity is not None:
        data.pop("party_id", None)  # 供应商对应的主体创建后不改
    return data


async def ensure_supplier_party(session: AsyncSession, name: str, party_type: str, user_id: UUID | None) -> UUID:
    """为供应商建立主体：机构建 md_organization（机构类型为企业），个体户建 md_person。"""
    if party_type not in (PARTY_TYPE_ORGANIZATION, PARTY_TYPE_PERSON):
        raise AppException("主体类型只能是机构或自然人", status_code=status.HTTP_400_BAD_REQUEST)
    party = MdParty(party_type_code=party_type, display_name=name, created_by=user_id, updated_by=user_id)
    session.add(party)
    await session.flush()
    if party_type == PARTY_TYPE_ORGANIZATION:
        session.add(MdOrganization(party_id=party.id, legal_name=name, organization_type_code="enterprise", created_by=user_id, updated_by=user_id))
    else:
        session.add(MdPerson(party_id=party.id, full_name=name, created_by=user_id, updated_by=user_id))
    await session.flush()
    return party.id


async def rename_party(session: AsyncSession, party_id: UUID, name: str, user_id: UUID | None) -> None:
    party = await session.get(MdParty, party_id)
    if party is None or party.display_name == name:
        return
    party.display_name = name
    party.updated_by = user_id
    session.add(party)
    organization = await session.get(MdOrganization, party_id)
    if organization is not None:
        organization.legal_name = name
        organization.updated_by = user_id
        session.add(organization)


async def supplier_names(session: AsyncSession, supplier_ids: set[UUID]) -> dict[UUID, str]:
    """供应商名称取自主体 md_party.display_name。"""
    if not supplier_ids:
        return {}
    rows = (await session.exec(
        select(MdSupplier.id, MdParty.display_name).join(MdParty, MdParty.id == MdSupplier.party_id).where(MdSupplier.id.in_(supplier_ids))
    )).all()
    return {row[0]: row[1] for row in rows}


class SupplierRepository(SqlModelCrudRepository):

    async def create(self, session: AsyncSession, payload: dict[str, Any], current_user: AuthenticatedUser):
        """供应商名称、主体类型存放在主体上：新建时建立主体（机构或个体户）。"""
        payload = dict(payload)
        name, party_type = payload.pop("supplier_name", None), payload.pop("party_type_code", None)
        if payload.get("party_id") is None:
            if not name:
                raise AppException("请填写供应商名称", status_code=status.HTTP_400_BAD_REQUEST)
            payload["party_id"] = await ensure_supplier_party(session, name, party_type or PARTY_TYPE_ORGANIZATION, current_user.user_id)
        item = await super().create(session, payload, current_user)
        return SupplierItem.model_validate((await self._enrich(session, [item.model_dump(mode="json")]))[0])

    async def update(self, session: AsyncSession, item_id: str, payload: dict[str, Any], current_user: AuthenticatedUser):
        """修改名称时同步主体；主体类型创建后不改。"""
        payload = dict(payload)
        name = payload.pop("supplier_name", None)
        payload.pop("party_type_code", None)
        if name:
            entity = await self.get_alive(session, self._normalize_id(item_id))
            if entity is not None:
                await rename_party(session, entity.party_id, name, current_user.user_id)
        item = await super().update(session, item_id, payload, current_user)
        if item is None:
            return None
        return SupplierItem.model_validate((await self._enrich(session, [item.model_dump(mode="json")]))[0])
    async def _category_names(self, session: AsyncSession, ids: set[UUID]) -> dict[UUID, str]:
        if not ids:
            return {}
        rows = (
            await session.exec(select(MdSupplierCategory.id, MdSupplierCategory.category_name).where(MdSupplierCategory.id.in_(ids)))
        ).all()
        return {row[0]: row[1] for row in rows}

    async def _enrich(self, session: AsyncSession, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        names = await self._category_names(session, {UUID(str(item["category_id"])) for item in items if item.get("category_id")})
        party_ids = {UUID(str(item["party_id"])) for item in items if item.get("party_id")}
        parties = {row.id: row for row in (await session.exec(select(MdParty).where(MdParty.id.in_(party_ids)))).all()} if party_ids else {}
        for item in items:
            item["category_name"] = names.get(UUID(str(item["category_id"]))) if item.get("category_id") else None
            party = parties.get(UUID(str(item["party_id"]))) if item.get("party_id") else None
            item["supplier_name"] = party.display_name if party is not None else ""
            item["party_type_code"] = party.party_type_code if party is not None else PARTY_TYPE_ORGANIZATION
        return items

    def _search_expressions(self, params):
        if not params.keyword:
            return []
        keyword = f"%{params.keyword}%"
        names = select(MdParty.id).where(MdParty.display_name.ilike(keyword))
        return [MdSupplier.supplier_no.ilike(keyword), MdSupplier.contact_name.ilike(keyword), MdSupplier.party_id.in_(names)]

    def _filter_conditions(self, params):
        conditions = super()._filter_conditions(params)
        party_type = getattr(params, "party_type_code", None)
        if party_type:
            conditions.append(MdSupplier.party_id.in_(select(MdParty.id).where(MdParty.party_type_code == party_type)))
        return conditions

    async def list(self, session: AsyncSession, params, current_user: AuthenticatedUser) -> dict[str, Any]:
        result = await super().list(session, params, current_user)
        result["items"] = await self._enrich(session, result["items"])
        return result

    async def detail(self, session: AsyncSession, item_id: str, current_user: AuthenticatedUser):
        item = await super().detail(session, item_id, current_user)
        if item is None:
            return None
        data = (await self._enrich(session, [item.model_dump(mode="json")]))[0]
        return SupplierItem.model_validate(data)

    async def delete(self, session: AsyncSession, item_id: str, current_user: AuthenticatedUser) -> bool:
        from app.modules.inventory.models import InvLot, MdItem

        supplier_id = self._normalize_id(item_id)
        for column in (MdItem.default_supplier_id, InvLot.supplier_id):
            used = (await session.exec(select(column).where(column == supplier_id).limit(1))).first()
            if used is not None:
                raise AppException("供应商已被物料或批次引用，请改为停用", status_code=status.HTTP_409_CONFLICT)
        return await super().delete(session, item_id, current_user)

    async def options(self, session: AsyncSession, *, keyword: str | None, active_only: bool) -> list[SupplierOption]:
        statement = (
            select(MdSupplier, MdSupplierCategory.category_name, MdParty.display_name)
            .join(MdParty, MdParty.id == MdSupplier.party_id)
            .join(MdSupplierCategory, MdSupplierCategory.id == MdSupplier.category_id, isouter=True)
            .where(MdSupplier.deleted_at.is_(None))
            .order_by(MdParty.display_name)
        )
        if active_only:
            statement = statement.where(MdSupplier.is_active.is_(True))
        if keyword:
            statement = statement.where(MdParty.display_name.ilike(f"%{keyword.strip()}%"))
        rows = (await session.exec(statement.limit(500))).all()
        return [
            SupplierOption(id=s.id, supplier_no=s.supplier_no, supplier_name=name, category_name=cat)
            for s, cat, name in rows
        ]

    async def get_alive(self, session: AsyncSession, supplier_id: UUID) -> MdSupplier | None:
        return (
            await session.exec(select(MdSupplier).where(MdSupplier.id == supplier_id, MdSupplier.deleted_at.is_(None)))
        ).one_or_none()

    async def find_by_name(self, session: AsyncSession, name: str) -> MdSupplier | None:
        return (
            await session.exec(
                select(MdSupplier).join(MdParty, MdParty.id == MdSupplier.party_id)
                .where(func.lower(MdParty.display_name) == name.strip().lower(), MdSupplier.deleted_at.is_(None))
            )
        ).first()

    # ───────── 收款账户（机密，单独授权） ─────────
    async def list_bank_accounts(self, session: AsyncSession, supplier_id: UUID) -> list[SupplierBankAccountItem]:
        rows = (
            await session.exec(
                select(MdSupplierBankAccount)
                .where(MdSupplierBankAccount.supplier_id == supplier_id, MdSupplierBankAccount.deleted_at.is_(None))
                .order_by(MdSupplierBankAccount.is_primary.desc(), MdSupplierBankAccount.created_at)
            )
        ).all()
        return [SupplierBankAccountItem.model_validate(row) for row in rows]

    async def _clear_primary(self, session: AsyncSession, supplier_id: UUID, keep_id: UUID | None) -> None:
        rows = (
            await session.exec(
                select(MdSupplierBankAccount).where(
                    MdSupplierBankAccount.supplier_id == supplier_id,
                    MdSupplierBankAccount.deleted_at.is_(None),
                    MdSupplierBankAccount.is_primary.is_(True),
                )
            )
        ).all()
        for row in rows:
            if row.id != keep_id:
                row.is_primary = False
                session.add(row)

    async def save_bank_account(
        self,
        session: AsyncSession,
        supplier_id: UUID,
        payload: dict[str, Any],
        user_id: UUID,
        account_id: UUID | None = None,
    ) -> SupplierBankAccountItem:
        if account_id is None:
            entity = MdSupplierBankAccount(supplier_id=supplier_id, created_by=user_id, account_name="", account_no_encrypted="")
        else:
            entity = (
                await session.exec(
                    select(MdSupplierBankAccount).where(
                        MdSupplierBankAccount.id == account_id,
                        MdSupplierBankAccount.supplier_id == supplier_id,
                        MdSupplierBankAccount.deleted_at.is_(None),
                    )
                )
            ).one_or_none()
            if entity is None:
                raise AppException("收款账户不存在", status_code=status.HTTP_404_NOT_FOUND)
        account_no = str(payload["account_no"]).strip()
        entity.account_name = payload["account_name"]
        entity.account_no_encrypted = encrypt_account_no(account_no)
        entity.account_no_masked = mask_account_no(account_no)
        entity.bank_name = payload.get("bank_name")
        entity.is_primary = bool(payload.get("is_primary"))
        entity.updated_by = user_id
        entity.updated_at = utc_now()
        session.add(entity)
        await session.flush()
        if entity.is_primary:
            await self._clear_primary(session, supplier_id, entity.id)
        await session.commit()
        await session.refresh(entity)
        return SupplierBankAccountItem.model_validate(entity)

    async def delete_bank_account(self, session: AsyncSession, supplier_id: UUID, account_id: UUID, user_id: UUID) -> bool:
        entity = (
            await session.exec(
                select(MdSupplierBankAccount).where(
                    MdSupplierBankAccount.id == account_id,
                    MdSupplierBankAccount.supplier_id == supplier_id,
                    MdSupplierBankAccount.deleted_at.is_(None),
                )
            )
        ).one_or_none()
        if entity is None:
            return False
        entity.deleted_at = utc_now()
        entity.deleted_by = user_id
        entity.updated_by = user_id
        session.add(entity)
        await session.commit()
        return True


repository = SupplierRepository(
    table_model=MdSupplier,
    item_model=SupplierItem,
    writable_columns=[
        "supplier_no",
        "category_id",
        "party_id",
        "contact_name",
        "contact_phone",
        "settlement_method_code",
        "settlement_cycle_code",
        "is_active",
    ],
    searchable_columns=["supplier_no", "contact_name"],
    filterable_columns=["category_id", "is_active"],
    create_payload_normalizer=_normalize_supplier,
    update_payload_normalizer=_normalize_supplier,
    scope_resource="supplier",
)
