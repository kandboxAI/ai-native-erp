"""人员主数据（md_party / md_person / md_person_contact / md_organization）的数据访问。

会话须已切换到租户 schema。只提供系统管理与各业务模块共用的基本读写；
证件号（md_person_pii）等机密信息的加解密由专门的服务处理，这里不涉及。
"""

from __future__ import annotations

import hashlib
from uuid import UUID

from sqlalchemy import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.framework.db.models import utc_now

from .models import MdOrganization, MdParty, MdPerson, MdPersonContact

CONTACT_TYPE_MOBILE = "mobile"
CONTACT_TYPE_EMAIL = "email"


def contact_hash(value: str) -> str:
    return hashlib.sha256(value.strip().lower().encode("utf-8")).hexdigest()


class MasterdataRepository:
    async def existing_person_names(self, session, names):
        """精确重名检查；只返回输入集合内已有姓名，不据此判断或合并人员身份。"""
        if not names:
            return set()
        return set((await session.execute(select(MdPerson.full_name).join(MdParty, MdParty.id == MdPerson.party_id).where(
            MdPerson.full_name.in_(names), MdPerson.deleted_at.is_(None), MdParty.deleted_at.is_(None)))).scalars().all())

    async def persons_bound_to_user(self, session, user_id):
        statement = select(MdPerson).where(
            MdPerson.user_id == user_id, MdPerson.deleted_at.is_(None)).with_for_update()
        return (await session.execute(statement)).scalars().all()

    async def set_person_user(self, session, person, user_id, actor_id):
        person.user_id = user_id
        person.updated_by, person.updated_at = actor_id, utc_now()
        session.add(person)
        await session.flush()

    async def is_account_placeholder(self, session, person):
        """账号初始化人员的最小引用检查；物理外键只返回存在性，不读行业记录。"""
        if person.birth_date or person.gender_code or person.photo_file_id or person.flex_form:
            return False
        from sqlalchemy import inspect, Table, Column, MetaData, Uuid, literal
        from app.framework.db.tenant import get_tenant_schema
        def references(sync):
            inspector = inspect(sync.connection())
            schema = get_tenant_schema() if sync.bind.dialect.name == "postgresql" else None
            if sync.bind.dialect.name == "postgresql" and schema is None:
                from app.core.exceptions import AppException
                raise AppException("人员账号关联缺少租户上下文，操作已停止", 409)
            refs = []
            for (owner_schema, table), constraints in inspector.get_multi_foreign_keys(schema=schema).items():
                if table in {"md_person", "md_person_contact"}:
                    continue
                for fk in constraints:
                    if fk["referred_table"] in {"md_person", "md_party"} and fk.get("referred_schema") in {None, schema}:
                        refs.extend((owner_schema, table, column) for column in fk["constrained_columns"])
            return refs
        for schema, name, column in await session.run_sync(references):
            table = Table(name, MetaData(), Column(column, Uuid), schema=schema)
            if (await session.execute(select(literal(1)).select_from(table).where(
                    table.c[column] == person.party_id).limit(1))).first():
                return False
        return True

    # ───────── 人员 ─────────
    async def get_person(self, session: AsyncSession, party_id: UUID) -> MdPerson | None:
        person = await session.get(MdPerson, party_id)
        return person if person is not None and person.deleted_at is None else None

    async def get_person_by_user(self, session: AsyncSession, user_id: UUID) -> MdPerson | None:
        statement = select(MdPerson).where(MdPerson.user_id == user_id, MdPerson.deleted_at.is_(None))
        return (await session.execute(statement)).scalars().first()

    async def map_persons_by_user(self, session: AsyncSession, user_ids: list[UUID]) -> dict[UUID, MdPerson]:
        if not user_ids:
            return {}
        statement = select(MdPerson).where(MdPerson.user_id.in_(user_ids), MdPerson.deleted_at.is_(None))
        return {row.user_id: row for row in (await session.execute(statement)).scalars().all() if row.user_id}

    async def create_person(
        self,
        session: AsyncSession,
        *,
        full_name: str,
        user_id: UUID | None = None,
        gender_code: str | None = None,
        created_by: UUID | None = None,
    ) -> MdPerson:
        party = MdParty(party_type_code="person", display_name=full_name, created_by=created_by, updated_by=created_by)
        session.add(party)
        await session.flush()
        person = MdPerson(
            party_id=party.id,
            full_name=full_name,
            user_id=user_id,
            gender_code=gender_code,
            created_by=created_by,
            updated_by=created_by,
        )
        session.add(person)
        await session.flush()
        return person

    async def rename_person(self, session: AsyncSession, person: MdPerson, full_name: str, *, updated_by: UUID | None) -> None:
        person.full_name = full_name
        person.updated_by = updated_by
        person.updated_at = utc_now()
        session.add(person)
        party = await session.get(MdParty, person.party_id)
        if party is not None:
            party.display_name = full_name
            party.updated_by = updated_by
            party.updated_at = utc_now()
            session.add(party)

    # ───────── 联系方式 ─────────
    async def set_person_gender(self, session, person, gender_code, *, updated_by):
        person.gender_code = gender_code
        person.updated_by, person.updated_at = updated_by, utc_now()
        session.add(person)

    async def get_primary_contact(self, session: AsyncSession, party_id: UUID, contact_type_code: str) -> MdPersonContact | None:
        statement = (
            select(MdPersonContact)
            .where(
                MdPersonContact.party_id == party_id,
                MdPersonContact.contact_type_code == contact_type_code,
                MdPersonContact.deleted_at.is_(None),
            )
            .order_by(MdPersonContact.is_primary.desc(), MdPersonContact.created_at)
        )
        return (await session.execute(statement)).scalars().first()

    async def map_primary_contacts(self, session: AsyncSession, party_ids: list[UUID], contact_type_code: str) -> dict[UUID, str]:
        if not party_ids:
            return {}
        statement = (
            select(MdPersonContact.party_id, MdPersonContact.contact_value)
            .where(
                MdPersonContact.party_id.in_(party_ids),
                MdPersonContact.contact_type_code == contact_type_code,
                MdPersonContact.deleted_at.is_(None),
            )
            .order_by(MdPersonContact.party_id, MdPersonContact.is_primary.desc(), MdPersonContact.created_at)
        )
        result: dict[UUID, str] = {}
        for party_id, value in (await session.execute(statement)).all():
            result.setdefault(party_id, value)
        return result

    async def set_primary_contact(
        self,
        session: AsyncSession,
        party_id: UUID,
        contact_type_code: str,
        value: str | None,
        *,
        updated_by: UUID | None = None,
    ) -> MdPersonContact | None:
        """设置主要联系方式；value 为空时删除（软删除）现有的主要联系方式。"""
        current = await self.get_primary_contact(session, party_id, contact_type_code)
        value = (value or "").strip() or None
        if value is None:
            if current is not None:
                current.deleted_at = utc_now()
                current.deleted_by = updated_by
                session.add(current)
            return None
        if current is None:
            current = MdPersonContact(
                party_id=party_id,
                contact_type_code=contact_type_code,
                contact_value=value,
                contact_value_hash=contact_hash(value),
                purpose_code="general",
                is_primary=True,
                created_by=updated_by,
                updated_by=updated_by,
            )
        elif current.contact_value != value:
            current.contact_value = value
            current.contact_value_hash = contact_hash(value)
            current.is_verified = False
            current.verified_at = None
            current.updated_by = updated_by
            current.updated_at = utc_now()
        session.add(current)
        return current

    # ───────── 外部机构 ─────────
    async def get_organization(self, session: AsyncSession, party_id: UUID) -> MdOrganization | None:
        row = await session.get(MdOrganization, party_id)
        return row if row is not None and row.deleted_at is None else None

    async def create_organization(
        self,
        session: AsyncSession,
        *,
        legal_name: str,
        organization_type_code: str,
        credit_no: str | None = None,
        created_by: UUID | None = None,
    ) -> MdOrganization:
        party = MdParty(party_type_code="organization", display_name=legal_name, created_by=created_by, updated_by=created_by)
        session.add(party)
        await session.flush()
        row = MdOrganization(
            party_id=party.id,
            legal_name=legal_name,
            credit_no=credit_no,
            organization_type_code=organization_type_code,
            created_by=created_by,
            updated_by=created_by,
        )
        session.add(row)
        await session.flush()
        return row


repository = MasterdataRepository()
