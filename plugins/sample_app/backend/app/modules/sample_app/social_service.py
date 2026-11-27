"""月度缴费与工资实付。现金按付款日，成本按所属月份；个人缴费不重复计成本。"""
from datetime import date
from decimal import Decimal, InvalidOperation
from uuid import UUID
from app.core.exceptions import AppException
from app.framework.db.models import utc_now
from app.framework.db.session import get_session_context
from . import repository as common
from . import social_repository as repo
from . import payroll_calc as calc
from .social_models import SocialBasis, SocialBill, SocialBillLine, PayrollPayment
from .models import SampleCashEntry

KINDS = ("pension_employer", "pension_employee", "unemployment_employer", "unemployment_employee", "injury_employer", "medical_employer", "medical_employee", "housing_employer", "housing_employee")
AMOUNTS = tuple(f"{key}_amount" for key in KINDS)
EMPLOYEE = tuple(key for key in AMOUNTS if "_employee_" in key)
EMPLOYER = tuple(key for key in AMOUNTS if "_employer_" in key)

def month(value):
    try:
        parsed = date.fromisoformat(str(value) + "-01")
    except (ValueError, TypeError):
        raise AppException(message="月份格式应为 YYYY-MM", status_code=422)
    return parsed

def amount(value):
    try:
        value = Decimal(str(value))
        if not value.is_finite() or value < 0 or value >= Decimal("10000000000000000") or value != value.quantize(Decimal(".01")):
            raise ValueError()
        return value.quantize(Decimal(".01"))
    except (ValueError, TypeError, InvalidOperation):
        raise AppException(message="金额和基数应为非负数，最多两位小数", status_code=422)

def total(rows, keys):
    return sum((Decimal(str(getattr(row, key))) for row in rows for key in keys), Decimal("0"))

def estimate(social_base, housing_base, plan):
    if any(not Decimal(str(plan.get(f"{key}_rate", 0))).is_finite() or not 0 <= Decimal(str(plan.get(f"{key}_rate", 0))) <= 100 for key in KINDS):
        raise AppException(message="缴费比例必须在0到100之间，请检查方案", status_code=422)
    values = calc.social_amounts(social_base, plan)
    for side in ("employee", "employer"):
        values[f"housing_{side}_amount"] = calc.percent_amount(housing_base, plan.get(f"housing_{side}_rate"))
    return values

async def social_bases(org_id):
    async with get_session_context() as session:
        rows = await repo.bases(session, org_id)
        names = await common.names_by_employee(session, [row.employee_id for row in rows])
        return [{**common.dump_model(row), **names.get(row.employee_id, {})} for row in rows]

async def save_social_basis(org_id, user_id, payload):
    start = month(payload["valid_from"])
    employee_id, plan_id = UUID(str(payload["employee_id"])), UUID(str(payload["social_plan_id"]))
    social_base, housing_base = amount(payload["social_base"]), amount(payload["housing_base"])
    async with get_session_context() as session:
        await repo.lock_org(session, org_id)
        person = await common.get_employee(session, org_id, employee_id)
        if person is None or person.personnel_type_code != "internal":
            raise AppException(message="请选择本公司内部员工", status_code=422)
        if getattr(person, "employment_end_on", None):
            raise AppException("员工已登记调出，请在新组织维护缴费基数", status_code=409)
        if await common.get_social_plan(session, org_id, plan_id) is None:
            raise AppException(message="缴费方案不属于该公司", status_code=422)
        existing = [row for row in await repo.bases(session, org_id) if row.employee_id == employee_id]
        if any(row.valid_from >= start for row in existing):
            raise AppException(message="新基数的生效月份必须晚于已有版本；历史月份不覆盖", status_code=409)
        for row in existing:
            if row.valid_to is None:
                row.valid_to = start
                row.updated_at, row.updated_by = utc_now(), user_id
                await repo.add(session, row)
        row = await repo.add(session, SocialBasis(org_id=org_id, employee_id=employee_id, social_plan_id=plan_id, social_base=social_base, housing_base=housing_base, valid_from=start, created_by=user_id, updated_by=user_id))
        await session.commit()
        return common.dump_model(row)

async def generate_social_bill(org_id, user_id, payload):
    period = month(payload["period_month"])
    async with get_session_context() as session:
        await repo.lock_org(session, org_id)
        existing = await repo.bill(session, org_id, period=period)
        if existing:
            return common.dump_model(existing)
        payroll = await common.get_payroll(session, org_id, period)
        if payroll and payroll.status_code == "closed":
            raise AppException(message="该月工资已封账，不能新增改变核算口径的缴费单", status_code=409)
        rows = []
        warnings = []
        for person in await common.list_employee_rows(session, org_id):
            if getattr(person, "employment_end_on", None) and person.employment_end_on <= period:
                continue
            if person.employment_status_code != "active" or (person.hire_date and person.hire_date >= date(period.year + (period.month == 12), 1 if period.month == 12 else period.month + 1, 1)):
                continue
            basis = await repo.current_basis(session, org_id, person.id, period)
            salary = None if basis else await common.current_salary(session, org_id, person.id, period)
            plan_id = basis.social_plan_id if basis else salary.social_plan_id if salary else None
            if plan_id is None:
                warnings.append(f"{person.full_name}未配置缴费基数，已跳过")
                continue
            plan = await common.get_social_plan(session, org_id, plan_id)
            if plan is None:
                raise AppException(message="缴费方案已失效，请先维护基数档案", status_code=422)
            social_base = basis.social_base if basis else salary.social_base
            housing_base = basis.housing_base if basis else salary.social_base
            rates = {f"{key}_rate": getattr(plan, f"{key}_rate") for key in KINDS}
            rows.append(dict(employee_id=person.id, basis_id=basis.id if basis else None, social_plan_id=plan_id, social_base_snapshot=social_base, housing_base_snapshot=housing_base, **{f"{key}_snapshot": value for key, value in rates.items()}, **estimate(social_base, housing_base, rates)))
            if basis is None:
                warnings.append(f"{person.full_name}暂用旧定薪基数，请补建独立基数档案")
        if not rows:
            raise AppException(message="没有可生成的参保人员，请先维护缴费基数", status_code=422)
        bill = await repo.add(session, SocialBill(org_id=org_id, period_month=period, created_by=user_id, updated_by=user_id))
        for values in rows:
            await repo.add(session, SocialBillLine(org_id=org_id, bill_id=bill.id, created_by=user_id, updated_by=user_id, **values))
        await session.commit()
        return {**common.dump_model(bill), "warnings": warnings}

async def require_bill(session, org_id, identity):
    row = await repo.bill(session, org_id, identity=identity)
    if row is None:
        raise AppException(message="缴费单不存在", status_code=404)
    return row

async def social_bill_detail(org_id, bill_id):
    async with get_session_context() as session:
        bill = await require_bill(session, org_id, bill_id)
        rows = await repo.lines(session, org_id, bill.id)
        names = await common.names_by_employee(session, [row.employee_id for row in rows])
        return {**common.dump_model(bill), "lines": [{**common.dump_model(row), **names.get(row.employee_id, {})} for row in rows]}

async def update_social_bill(org_id, user_id, bill_id, payload):
    async with get_session_context() as session:
        await repo.lock_org(session, org_id)
        bill = await require_bill(session, org_id, bill_id)
        if bill.status_code != "draft":
            raise AppException(message="已确认缴费单不能修改", status_code=409)
        rows = {str(row.id): row for row in await repo.lines(session, org_id, bill.id)}
        supplied = payload["lines"]
        if len(supplied) != len(rows) or {str(row["id"]) for row in supplied} != set(rows):
            raise AppException(message="缴费明细已变化，请刷新后重新核对", status_code=409)
        for values in supplied:
            row = rows[str(values["id"])]
            for key in AMOUNTS:
                setattr(row, key, amount(values[key]))
            row.updated_at, row.updated_by = utc_now(), user_id
            await repo.add(session, row)
        await session.commit()
        return {"saved": len(rows)}

async def assert_payroll_matches(session, org_id, payroll):
    bill = await repo.bill(session, org_id, period=payroll.period_month)
    if bill is None:
        return
    if bill.status_code != "confirmed":
        raise AppException(message="请先确认当月社保缴费单，再重新核算工资", status_code=409)
    rows = {row.employee_id: row for row in await repo.lines(session, org_id, bill.id)}
    for slip in await common.list_payslips(session, payroll.id):
        line = rows.get(slip.employee_id)
        expected = {key: getattr(line, key) if line else Decimal("0") for key in AMOUNTS}
        if any(getattr(slip, key) != expected[key] for key in AMOUNTS):
            raise AppException(message="工资中的社保与已确认缴费单不一致，请重新核算后再封账", status_code=409)

async def confirm_social_bill(org_id, user_id, bill_id, payload):
    async with get_session_context() as session:
        await repo.lock_org(session, org_id)
        bill = await require_bill(session, org_id, bill_id)
        if bill.status_code == "confirmed":
            return common.dump_model(bill)
        payroll = await common.get_payroll(session, org_id, bill.period_month)
        if payroll and payroll.status_code == "closed":
            raise AppException(message="工资已封账，不能更改当月缴费核算，请核对历史数据", status_code=409)
        bill.status_code = "confirmed"
        bill.updated_at, bill.updated_by = utc_now(), user_id
        await repo.add(session, bill)
        await session.commit()
        return common.dump_model(bill)

async def payment_entry(session, org_id, user_id, payload, expected, source, source_id, summary):
    if expected <= 0:
        raise AppException(message="支付金额应大于零", status_code=422)
    try:
        paid_on = date.fromisoformat(str(payload["paid_on"]))
        account_id = UUID(str(payload["account_id"]))
    except (ValueError, KeyError):
        raise AppException(message="请选择付款账户并填写实际付款日期", status_code=422)
    account = await common.get_account(session, org_id, account_id)
    if account is None or paid_on < account.opening_on:
        raise AppException(message="付款账户不存在，或付款日期早于账户期初日期", status_code=422)
    if payload.get("cash_entry_id"):
        entry = await repo.entry(session, org_id, UUID(str(payload["cash_entry_id"])))
        if entry is None or entry.source_id is not None or entry.source_type_code is not None or await repo.entry_used(session, org_id, entry.id):
            raise AppException(message="请选择本公司尚未关联业务的手工支出流水", status_code=422)
        if entry.direction_code != "expense" or entry.amount != expected or entry.account_id != account_id or entry.occurred_on != paid_on:
            raise AppException(message="流水金额、账户或日期与本次付款不一致", status_code=422)
        entry.source_type_code, entry.source_id = source, source_id
        entry.updated_at, entry.updated_by = utc_now(), user_id
    else:
        entry = SampleCashEntry(org_id=org_id, account_id=account_id, occurred_on=paid_on, direction_code="expense", category_code="payroll_social", amount=expected, summary=summary, source_type_code=source, source_id=source_id, created_by=user_id, updated_by=user_id)
    return await repo.add(session, entry)

async def pay_social_bill(org_id, user_id, bill_id, payload):
    async with get_session_context() as session:
        await repo.lock_org(session, org_id)
        bill = await require_bill(session, org_id, bill_id)
        if bill.cash_entry_id:
            existing = await repo.entry(session, org_id, bill.cash_entry_id)
            check_repeat(existing, payload)
            return {"cash_entry_id": str(bill.cash_entry_id)}
        if bill.status_code != "confirmed":
            raise AppException(message="请先核对并确认缴费单", status_code=409)
        rows = await repo.lines(session, org_id, bill.id)
        entry = await payment_entry(session, org_id, user_id, payload, total(rows, AMOUNTS), "social_bill", bill.id, f"{bill.period_month:%Y-%m}社保公积金缴费")
        bill.cash_entry_id = entry.id
        bill.updated_at, bill.updated_by = utc_now(), user_id
        await repo.add(session, bill)
        await session.commit()
        return {"cash_entry_id": str(entry.id)}

def check_repeat(entry, payload):
    if entry is None or str(entry.account_id) != str(payload.get("account_id")) or entry.occurred_on.isoformat() != str(payload.get("paid_on")) or (payload.get("cash_entry_id") and str(entry.id) != str(payload["cash_entry_id"])):
        raise AppException(message="该单据已付款，重复请求的付款信息不一致", status_code=409)

async def pay_payroll(org_id, user_id, payload):
    period = month(payload["period_month"])
    async with get_session_context() as session:
        await repo.lock_org(session, org_id)
        payroll = await common.get_payroll(session, org_id, period)
        if payroll is None or payroll.status_code != "closed":
            raise AppException(message="请先核算并封账当月工资", status_code=409)
        previous = await repo.payment(session, org_id, payroll.id)
        if previous:
            check_repeat(await repo.entry(session, org_id, previous.cash_entry_id), payload)
            return common.dump_model(previous)
        await assert_payroll_matches(session, org_id, payroll)
        rows = await common.list_payslips(session, payroll.id)
        if any(row.net_amount < 0 for row in rows):
            raise AppException(message="存在实发金额为负的工资行，不能整批付款", status_code=422)
        entry = await payment_entry(session, org_id, user_id, payload, total(rows, ("net_amount",)), "payroll", payroll.id, f"{period:%Y-%m}工资实付")
        payment = await repo.add(session, PayrollPayment(org_id=org_id, payroll_id=payroll.id, cash_entry_id=entry.id, created_by=user_id, updated_by=user_id))
        await session.commit()
        return common.dump_model(payment)

async def social_bills(org_id):
    async with get_session_context() as session:
        result = []
        # 同时列出尚未建立缴费单的工资月份，让历史工资成本仍可查询。
        bills = {row.period_month: row for row in await repo.bills(session, org_id)}
        payrolls = {row.period_month: row for row in await repo.payrolls(session, org_id)}
        for period in sorted(set(bills) | set(payrolls), reverse=True):
            bill, payroll = bills.get(period), payrolls.get(period)
            lines = await repo.lines(session, org_id, bill.id) if bill else []
            slips = await common.list_payslips(session, payroll.id) if payroll else []
            payment = await repo.payment(session, org_id, payroll.id) if payroll else None
            confirmed = bill is not None and bill.status_code == "confirmed"
            employer = total(lines, EMPLOYER)
            personal = total(lines, EMPLOYEE)
            recovered = Decimal("0")
            if payment and confirmed:
                slip_by_person = {row.employee_id: row for row in slips}
                for line in lines:
                    slip = slip_by_person.get(line.employee_id)
                    if slip:
                        recovered += min(total([line], EMPLOYEE), total([slip], EMPLOYEE))
            paid = bool(bill and bill.cash_entry_id)
            gross = total(slips, ("gross_amount",))
            cost = gross + (employer if confirmed else total(slips, EMPLOYER))
            result.append({"id": str(bill.id) if bill else f"payroll-{payroll.id}", "bill_id": str(bill.id) if bill else None, "period_month": period.isoformat(), "status_code": bill.status_code if bill else "missing", "employer_amount": str(employer), "employee_amount": str(personal), "total_amount": str(employer + personal), "paid_amount": str(employer + personal if paid else 0), "recovered_amount": str(recovered), "pending_recovery_amount": str(max(Decimal("0"), personal - recovered) if paid else 0), "gross_amount": str(gross), "labor_cost_amount": str(cost), "has_payroll": payroll is not None, "payroll_status_code": payroll.status_code if payroll else "", "payroll_paid": payment is not None, "payroll_net_amount": str(total(slips, ("net_amount",))), "is_paid": paid, "cash_entry_id": str(bill.cash_entry_id) if paid else None})
        return result
