"""缴费、扣回与成本的组织内查询；调用者必须先通过 BusinessScope 授权。"""
from datetime import date
from uuid import UUID
from sqlmodel import select
from app.modules.organization.models import SysOrg
from .models import SampleCashEntry, SamplePayroll, SamplePayslip
from .social_models import SocialBasis, SocialBill, SocialBillLine, PayrollPayment

async def lock_org(session, org_id):
    return (await session.exec(select(SysOrg).where(SysOrg.id == org_id, SysOrg.deleted_at.is_(None)).with_for_update())).one()

async def bases(session, org_id):
    return list((await session.exec(select(SocialBasis).where(SocialBasis.org_id == org_id, SocialBasis.deleted_at.is_(None)).order_by(SocialBasis.valid_from.desc()))).all())

async def current_basis(session, org_id, employee_id, period):
    return (await session.exec(select(SocialBasis).where(SocialBasis.org_id == org_id, SocialBasis.employee_id == employee_id, SocialBasis.deleted_at.is_(None), SocialBasis.valid_from <= period, (SocialBasis.valid_to.is_(None)) | (SocialBasis.valid_to > period)).order_by(SocialBasis.valid_from.desc()))).first()

async def bills(session, org_id):
    return list((await session.exec(select(SocialBill).where(SocialBill.org_id == org_id, SocialBill.deleted_at.is_(None)).order_by(SocialBill.period_month.desc()))).all())

async def bill(session, org_id, *, identity=None, period=None):
    query = select(SocialBill).where(SocialBill.org_id == org_id, SocialBill.deleted_at.is_(None))
    query = query.where(SocialBill.id == identity) if identity else query.where(SocialBill.period_month == period)
    return (await session.exec(query)).first()

async def lines(session, org_id, bill_id):
    return list((await session.exec(select(SocialBillLine).where(SocialBillLine.org_id == org_id, SocialBillLine.bill_id == bill_id, SocialBillLine.deleted_at.is_(None)))).all())

async def payment(session, org_id, payroll_id):
    return (await session.exec(select(PayrollPayment).where(PayrollPayment.org_id == org_id, PayrollPayment.payroll_id == payroll_id, PayrollPayment.deleted_at.is_(None)))).first()

async def entry(session, org_id, identity):
    return (await session.exec(select(SampleCashEntry).where(SampleCashEntry.org_id == org_id, SampleCashEntry.id == identity, SampleCashEntry.deleted_at.is_(None)).with_for_update())).first()

async def entry_used(session, org_id, identity):
    # 与手工流水绑定的两种支付共用一次性关联规则；行锁串行化并发认领。
    a = (await session.exec(select(SocialBill.id).where(SocialBill.org_id == org_id, SocialBill.cash_entry_id == identity, SocialBill.deleted_at.is_(None)))).first()
    b = (await session.exec(select(PayrollPayment.id).where(PayrollPayment.org_id == org_id, PayrollPayment.cash_entry_id == identity, PayrollPayment.deleted_at.is_(None)))).first()
    return a is not None or b is not None

async def payrolls(session, org_id):
    return list((await session.exec(select(SamplePayroll).where(SamplePayroll.org_id == org_id, SamplePayroll.deleted_at.is_(None)).order_by(SamplePayroll.period_month.desc()))).all())

async def add(session, row):
    session.add(row)
    await session.flush()
    return row
