from sqlmodel import select

from .models import SampleAttendance, SampleEmployee, SamplePayroll
from .social_models import SocialBill


async def lock_employee(session, org_id, employee_id):
    query = select(SampleEmployee).where(
        SampleEmployee.id == employee_id, SampleEmployee.org_id == org_id,
        SampleEmployee.deleted_at.is_(None),
    ).with_for_update()
    return (await session.exec(query)).first()


async def has_period_conflict(session, source_org_id, target_org_id, employee_id, period):
    for model in (SamplePayroll, SocialBill):
        query = select(model.id).where(
            model.org_id.in_([source_org_id, target_org_id]), model.period_month >= period,
            model.deleted_at.is_(None),
        ).limit(1)
        if (await session.exec(query)).first() is not None:
            return True
    query = select(SampleAttendance.id).where(
        SampleAttendance.org_id == source_org_id, SampleAttendance.employee_id == employee_id,
        SampleAttendance.period_month >= period, SampleAttendance.deleted_at.is_(None),
    ).limit(1)
    return (await session.exec(query)).first() is not None
