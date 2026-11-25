"""汇报线提供器（L1 扩展点）。

审批找上级、工单派单、数据范围需要“某人的主岗部门、直属上级、部门负责人、分管领导”。任职关系属于 L2 人事，
L1 不能引用 L2 的表，所以由人事模块向这里注册实现（register_reporting_line_provider）。
未安装人事模块时使用默认实现：主岗部门取 sys_user.department_id，上级取部门负责人 sys_department.manager_user_id。
分管领导全系统只有一处来源：sys_department.supervisor_party_id。

所有方法都以人员（md_person.party_id）为对象；需要账号时由调用方经 md_person.user_id 找到 sys_user。
"""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.modules.department.models import SysDepartment
from app.modules.masterdata.models import MdPerson
from app.modules.user_profile.models import SysUser


class ReportingLineProvider(Protocol):
    async def primary_department_id(self, session: AsyncSession, party_id: UUID) -> UUID | None: ...

    async def direct_manager_party_id(self, session: AsyncSession, party_id: UUID) -> UUID | None: ...


class DepartmentHeadProvider:
    """默认实现：只用部门与部门负责人。"""

    async def primary_department_id(self, session: AsyncSession, party_id: UUID) -> UUID | None:
        return (await session.exec(
            select(SysUser.department_id).join(MdPerson, MdPerson.user_id == SysUser.id).where(MdPerson.party_id == party_id)
        )).first()

    async def direct_manager_party_id(self, session: AsyncSession, party_id: UUID) -> UUID | None:
        department_id = await self.primary_department_id(session, party_id)
        if department_id is None:
            return None
        manager = (await session.exec(
            select(MdPerson.party_id).join(SysDepartment, SysDepartment.manager_user_id == MdPerson.user_id)
            .where(SysDepartment.id == department_id)
        )).first()
        return manager if manager != party_id else None


_provider: ReportingLineProvider = DepartmentHeadProvider()


def register_reporting_line_provider(provider: ReportingLineProvider) -> None:
    global _provider
    _provider = provider


def reporting_line() -> ReportingLineProvider:
    return _provider


async def supervisor_party_id(session: AsyncSession, party_id: UUID) -> UUID | None:
    """分管领导：申请人主岗部门的 sys_department.supervisor_party_id。"""
    department_id = await _provider.primary_department_id(session, party_id)
    if department_id is None:
        return None
    return (await session.exec(select(SysDepartment.supervisor_party_id).where(SysDepartment.id == department_id))).first()


__all__ = [
    "DepartmentHeadProvider", "ReportingLineProvider", "register_reporting_line_provider", "reporting_line", "supervisor_party_id",
]
