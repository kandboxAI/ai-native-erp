"""快盒考勤与薪酬。计算只读取已保存的参数和税率档。"""
from .reimbursement_files import BUSINESS_TYPE as REIMBURSEMENT_FILES, SCENE as INVOICE_SCENE
from app.modules.file.service import service as file_service
from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID

from app.core.exceptions import AppException
from app.framework.db.ids import uuid7
from app.framework.db.models import utc_now
from app.framework.db.session import get_session_context

from . import payroll_calc as calc
from . import repository
from .flex_values import FIELD_KEY, FORM_KEYS, VALUE_TYPES, normalize_flex_form, require_form_key
from .models import SampleFlexField, SamplePayroll


def _month(value: str) -> date:
    year, month = value.split("-")
    return date(int(year), int(month), 1)


def _line(slip, people: dict, banks: dict) -> dict:
    data = repository.dump_model(slip)
    data.update(people.get(slip.employee_id, {"employee_no": "", "full_name": ""}))
    data.update(banks.get(slip.employee_id, {"bank_name": "", "account_no_masked": ""}))
    return data


async def employees(org_id: UUID, personnel_type_code: str = "internal") -> list[dict]:
    if personnel_type_code not in {"internal", "outsourced"}:
        raise AppException(message="请选择有效的人员关系", status_code=422)
    async with get_session_context() as session:
        return await repository.list_employees(session, org_id, personnel_type_code)


async def save_employee(org_id: UUID, user_id: UUID | None, employee_id: UUID | None, payload: dict) -> dict:
    if payload["employment_status_code"] not in {"active", "resigned"}:
        raise AppException(message="员工状态只支持在职或离职", status_code=422)
    personnel_type = payload.get("personnel_type_code", "internal")
    project_id = UUID(str(payload["project_id"])) if payload.get("project_id") else None
    if personnel_type not in {"internal", "outsourced"} or (personnel_type == "outsourced" and not project_id) or (personnel_type == "internal" and project_id):
        raise AppException(message="内部员工不关联代管项目；外包项目人员必须选择所属项目", status_code=422)
    async with get_session_context() as session:
        if project_id and await repository.get_project(session, org_id, project_id) is None:
            raise AppException(message="项目不存在或不属于当前组织", status_code=422)
        if employee_id is not None and await repository.get_employee(session, org_id, employee_id) is None:
            raise AppException(message="员工不存在", status_code=404)
        same_no = await repository.find_employee_by_no(session, org_id, payload["employee_no"])
        if same_no is not None and same_no.id != employee_id:
            raise AppException(message="员工编号已存在", status_code=409)
        current = await repository.get_employee(session, org_id, employee_id) if employee_id else None
        form_key = "employee_outsourced" if personnel_type == "outsourced" else "employee_internal"
        flex_form = normalize_flex_form(await repository.list_flex_fields(session, form_key), payload.get("flex_form"), current.flex_form if current else {})
        row = await repository.save_employee(session, org_id, employee_id, {
            "personnel_type_code": personnel_type,
            "project_id": project_id,
            "employee_no": payload["employee_no"],
            "full_name": payload["full_name"],
            "employment_status_code": payload["employment_status_code"],
            "hire_date": date.fromisoformat(payload["hire_date"]) if payload.get("hire_date") else None,
            "bank_name": payload.get("bank_name") or None,
            "account_no_masked": payload.get("account_no_masked") or None,
            "flex_form": flex_form,
        }, user_id)
        await session.commit()
        return repository.dump_model(row)


async def read_setting(org_id: UUID, user_id: UUID | None) -> dict:
    async with get_session_context() as session:
        await repository.ensure_defaults(session, org_id, user_id)
        setting = await repository.get_setting(session, org_id)
        plans = await repository.list_plans(session, org_id)
        brackets = await repository.list_brackets(session, org_id)
        await session.commit()
        return {
            "setting": repository.dump_model(setting),
            "plans": [repository.dump_model(row) for row in plans],
            "brackets": [repository.dump_model(row) for row in brackets],
        }


def _decimals(payload: dict, keys: set[str]) -> dict:
    return {key: Decimal(str(value)) if key in keys and value is not None else value for key, value in payload.items()}


async def write_setting(org_id: UUID, user_id: UUID | None, payload: dict) -> dict:
    payload = _decimals(payload, {"standard_days", "overtime_multiplier", "tax_threshold"})
    async with get_session_context() as session:
        await repository.ensure_defaults(session, org_id, user_id)
        row = await repository.save_setting(session, org_id, payload, user_id)
        await session.commit()
        return repository.dump_model(row)


async def write_plan(org_id: UUID, user_id: UUID | None, plan_id: UUID | None, payload: dict) -> dict:
    payload = _decimals(payload, {key for key in payload if key.endswith("_rate")})
    async with get_session_context() as session:
        await repository.ensure_defaults(session, org_id, user_id)
        row = await repository.save_plan(session, org_id, plan_id, payload, user_id)
        await session.commit()
        return repository.dump_model(row)


async def attendance(org_id: UUID, month: str) -> list[dict]:
    period = _month(month)
    async with get_session_context() as session:
        people = {UUID(row["id"]): row for row in await repository.list_employees(session, org_id)}
        saved = {row.employee_id: row for row in await repository.list_attendance(session, org_id, period)}
        result = []
        for employee_id, person in people.items():
            if person.get("employment_end_on") and date.fromisoformat(person["employment_end_on"]) <= period:
                continue
            if person.get("hire_date") and date.fromisoformat(person["hire_date"]).replace(day=1) > period:
                continue
            row = saved.get(employee_id)
            result.append({
                "id": str(row.id) if row else None,
                "employee_id": str(employee_id),
                "employee_no": person["employee_no"],
                "full_name": person["full_name"],
                "expected_days": float(row.expected_days) if row else 0,
                "actual_days": float(row.actual_days) if row else 0,
                "overtime_days": float(row.overtime_days) if row else 0,
                "warning": bool(row and row.actual_days > row.expected_days and row.expected_days > 0),
            })
        return result


async def save_attendance(org_id: UUID, user_id: UUID | None, month: str, rows: list[dict]) -> dict:
    from .social_repository import lock_org

    period = _month(month)
    warnings = []
    async with get_session_context() as session:
        await lock_org(session, org_id)
        for row in rows:
            if row.get("employee_id"):
                employee = await repository.get_employee(session, org_id, UUID(str(row["employee_id"])))
            else:
                employee = await repository.find_employee_by_no(session, org_id, row.get("employee_no") or "")
            if employee is None or employee.personnel_type_code != "internal":
                raise AppException(message=f"找不到员工编号 {row.get('employee_no', '')}", status_code=422)
            if employee.employment_end_on and employee.employment_end_on <= period:
                raise AppException("员工在该月已调出，请在新组织登记考勤", status_code=409)
            if employee.hire_date and employee.hire_date.replace(day=1) > period:
                raise AppException("员工在该月尚未入职当前组织", status_code=409)
            employee_id = employee.id
            if Decimal(str(row["actual_days"])) > Decimal(str(row["expected_days"])) > 0:
                warnings.append(str(row.get("employee_no") or employee_id))
            await repository.upsert_attendance(session, org_id, employee_id, period, {
                "expected_days": Decimal(str(row["expected_days"])),
                "actual_days": Decimal(str(row["actual_days"])),
                "overtime_days": Decimal(str(row["overtime_days"])),
            }, user_id)
        await session.commit()
    return {"saved": len(rows), "warnings": warnings}


async def salaries(org_id: UUID) -> list[dict]:
    async with get_session_context() as session:
        people = await repository.names_by_employee(session, [row.employee_id for row in await repository.list_salaries(session, org_id)])
        rows = await repository.list_salaries(session, org_id)
        return [{**repository.dump_model(row), **people.get(row.employee_id, {})} for row in rows]


async def add_salary(org_id: UUID, user_id: UUID | None, payload: dict) -> dict:
    from .social_repository import lock_org

    async with get_session_context() as session:
        await lock_org(session, org_id)
        person = await repository.get_employee(session, org_id, UUID(str(payload["employee_id"])))
        if person is None or person.personnel_type_code != "internal":
            raise AppException(message="仅内部员工可登记内部定薪", status_code=422)
        if getattr(person, "employment_end_on", None):
            raise AppException("员工已登记调出，请在新组织维护定薪", status_code=409)
        if payload.get("social_plan_id") and await repository.get_social_plan(session, org_id, UUID(str(payload["social_plan_id"]))) is None:
            raise AppException(message="社保方案不属于员工所在组织", status_code=422)
        previous = await repository.latest_salary(session, org_id, person.id)
        row = await repository.save_salary(session, org_id, {
            "employee_id": UUID(str(payload["employee_id"])),
            "social_plan_id": previous.social_plan_id if previous else UUID(str(payload["social_plan_id"])) if payload.get("social_plan_id") else None,
            "social_base": previous.social_base if previous else Decimal(str(payload.get("social_base") or 0)),
            "base_amount": Decimal(str(payload["base_amount"])),
            "performance_amount": Decimal(str(payload.get("performance_amount") or 0)),
            "valid_from": date.fromisoformat(payload["valid_from"]),
            "valid_to": date.fromisoformat(payload["valid_to"]) if payload.get("valid_to") else None,
        }, user_id)
        await session.commit()
        return repository.dump_model(row)


async def calculate(org_id: UUID, user_id: UUID | None, month: str) -> dict:
    period = _month(month)
    async with get_session_context() as session:
        await repository.ensure_defaults(session, org_id, user_id)
        from . import social_repository, social_service
        await social_repository.lock_org(session, org_id)
        bill = await social_repository.bill(session, org_id, period=period)
        if bill and bill.status_code != "confirmed":
            raise AppException(message="请先核对并确认当月社保缴费单", status_code=409)
        bill_lines = {row.employee_id: row for row in await social_repository.lines(session, org_id, bill.id)} if bill else {}
        payroll = await repository.get_payroll(session, org_id, period)
        if payroll and payroll.status_code == "closed":
            raise AppException(message="该月工资已封账，不能重算", status_code=409)
        if payroll is None:
            payroll = SamplePayroll(org_id=org_id, period_month=period, status_code="draft", created_by=user_id, updated_by=user_id)
            session.add(payroll)
            await session.flush()
        payroll = await repository.lock_payroll(session, payroll)
        setting = await repository.get_setting(session, org_id)
        brackets = [repository.dump_model(row) for row in await repository.list_brackets(session, org_id)]
        plans = {row.id: repository.dump_model(row) for row in await repository.list_plans(session, org_id)}
        extras = await repository.draft_extras(session, payroll.id)
        attendance_rows = {row.employee_id: row for row in await repository.list_attendance(session, org_id, period)}
        from . import software_claim_service as software_claims
        claimed_software = await software_claims.applied_amounts_for_period(session, org_id, period)
        warnings = []
        lines = []
        for person in await repository.list_employees(session, org_id):
            if person.get("employment_end_on") and date.fromisoformat(person["employment_end_on"]) <= period:
                continue
            if person.get("hire_date") and date.fromisoformat(person["hire_date"]).replace(day=1) > period:
                continue
            if person["employment_status_code"] in {"resigned", "retired"}:
                continue
            employee_id = UUID(person["id"])
            salary = await repository.current_salary(session, org_id, employee_id, period)
            if salary is None:
                warnings.append(f"{person['full_name']}没有生效的定薪，已跳过")
                continue
            if not person.get("hire_date"):
                raise AppException(message="存在缺少入职日期的发薪员工，请补齐后再核算个税", status_code=422)
            attend = attendance_rows.get(employee_id)
            old = extras.get(employee_id)
            overtime = calc.overtime_pay(
                attend.overtime_days if attend else 0,
                salary.base_amount,
                attend.expected_days if attend else 0,
                setting.standard_days,
                setting.daily_wage_mode_code,
                setting.overtime_multiplier,
            )
            bonus = old.bonus_amount if old else Decimal("0")
            software = claimed_software.get(employee_id)
            if software is None:
                software = old.software_amount if old else Decimal("0")
            travel = old.travel_amount if old else Decimal("0")
            other = old.other_amount if old else Decimal("0")
            adjust = old.adjust_amount if old else Decimal("0")
            other_deduction = old.other_deduction_amount if old else Decimal("0")
            task_name = old.task_name if old else None
            project_id = old.project_id if old else None
            gross = calc.gross_pay(
                base_amount=salary.base_amount,
                performance_amount=salary.performance_amount,
                bonus_amount=bonus,
                overtime_amount=overtime,
                software_amount=software,
                travel_amount=travel,
                other_amount=other,
                adjust_amount=adjust,
            )
            if bill:
                line = bill_lines.get(employee_id)
                social = {key: getattr(line, key) if line else Decimal("0") for key in social_service.AMOUNTS}
            else:
                basis = await social_repository.current_basis(session, org_id, employee_id, period)
                if basis:
                    social = social_service.estimate(basis.social_base, basis.housing_base, plans.get(basis.social_plan_id, {}))
                else:
                    social = calc.social_amounts(salary.social_base, plans.get(salary.social_plan_id, {}))
                warnings.append(f"{person['full_name']}社保暂按基数预估，建议生成并确认当月缴费单")
            prior_gross, prior_tax, prior_special = await repository.prior_tax(session, org_id, employee_id, period.year, period)
            hired = date.fromisoformat(person["hire_date"])
            months = calc.tax_months(period.month, hired.year, hired.month, period.year)
            taxable = prior_gross + gross - prior_special - (social["pension_employee_amount"] + social["unemployment_employee_amount"] + social["medical_employee_amount"] + social["housing_employee_amount"]) - setting.tax_threshold * months
            tax = calc.bracket_tax(taxable, brackets) - prior_tax
            if tax < 0:
                tax = calc.money(0)
            net = calc.net_pay(
                gross=gross, tax=tax,
                pension_employee=social["pension_employee_amount"],
                unemployment_employee=social["unemployment_employee_amount"],
                medical_employee=social["medical_employee_amount"],
                housing_employee=social["housing_employee_amount"],
                other_deduction=other_deduction,
            )
            cost = calc.employer_cost(
                gross=gross,
                pension_employer=social["pension_employer_amount"],
                unemployment_employer=social["unemployment_employer_amount"],
                injury_employer=social["injury_employer_amount"],
                medical_employer=social["medical_employer_amount"],
                housing_employer=social["housing_employer_amount"],
            )
            lines.append({
                "employee_id": employee_id,
                "project_id": project_id,
                "task_name": task_name,
                "base_amount": salary.base_amount,
                "performance_amount": salary.performance_amount,
                "bonus_amount": bonus,
                "overtime_amount": overtime,
                "software_amount": software,
                "travel_amount": travel,
                "other_amount": other,
                "adjust_amount": adjust,
                "gross_amount": gross,
                "tax_amount": tax,
                "pension_employee_amount": social["pension_employee_amount"],
                "unemployment_employee_amount": social["unemployment_employee_amount"],
                "medical_employee_amount": social["medical_employee_amount"],
                "housing_employee_amount": social["housing_employee_amount"],
                "other_deduction_amount": other_deduction,
                "net_amount": net,
                "pension_employer_amount": social["pension_employer_amount"],
                "unemployment_employer_amount": social["unemployment_employer_amount"],
                "injury_employer_amount": social["injury_employer_amount"],
                "medical_employer_amount": social["medical_employer_amount"],
                "housing_employer_amount": social["housing_employer_amount"],
                "employer_cost_amount": cost,
            })
            if attend and attend.actual_days > attend.expected_days > 0:
                warnings.append(f"{person['full_name']}实出勤大于应出勤")
        await repository.replace_payslips(session, payroll, lines, user_id)
        slips = await repository.list_payslips(session, payroll.id)
        await software_claims.mark_applied_after_payroll(
            session, org_id, period, {row.employee_id: row.id for row in slips}, user_id)
        payroll.status_code = "draft"
        payroll.updated_by, payroll.updated_at = user_id, utc_now()
        session.add(payroll)
        await session.commit()
        return {"payroll_id": str(payroll.id), "count": len(lines), "warnings": warnings}


async def software_claims(org_id: UUID, month: str) -> list[dict]:
    from . import software_claim_service
    return await software_claim_service.admin_list(org_id, month)


async def payroll_lines(org_id: UUID, month: str) -> dict:
    period = _month(month)
    async with get_session_context() as session:
        payroll = await repository.get_payroll(session, org_id, period)
        if payroll is None:
            return {"status_code": "", "lines": []}
        slips = await repository.list_payslips(session, payroll.id)
        people = await repository.names_by_employee(session, [row.employee_id for row in slips])
        banks = await repository.bank_masks(session, [row.employee_id for row in slips])
        return {"payroll_id": str(payroll.id), "status_code": payroll.status_code, "lines": [_line(row, people, banks) for row in slips]}


async def update_line(org_id: UUID, user_id: UUID | None, payslip_id: UUID, payload: dict) -> dict:
    async with get_session_context() as session:
        from . import social_repository
        await social_repository.lock_org(session, org_id)
        slip = await repository.get_payslip(session, org_id, payslip_id)
        if slip is None:
            raise AppException(message="工资单不存在", status_code=404)
        payroll = await repository.payroll_by_id(session, org_id, slip.payroll_id)
        if payroll.status_code == "closed":
            raise AppException(message="该月工资已封账，不能修改", status_code=409)
        if "project_id" in payload:
            slip.project_id = UUID(str(payload["project_id"])) if payload["project_id"] else None
            if slip.project_id is not None:
                project = await repository.get_project(session, org_id, slip.project_id)
                if project is None:
                    raise AppException(message="项目不存在", status_code=422)
                slip.task_name = project.project_name
        for key in ("task_name", "bonus_amount", "software_amount", "travel_amount", "other_amount", "adjust_amount", "other_deduction_amount"):
            if key in payload and payload[key] is not None and not (key == "task_name" and slip.project_id is not None):
                setattr(slip, key, payload[key] if key == "task_name" else Decimal(str(payload[key])))
        gross = calc.gross_pay(
            base_amount=slip.base_amount, performance_amount=slip.performance_amount, bonus_amount=slip.bonus_amount,
            overtime_amount=slip.overtime_amount, software_amount=slip.software_amount, travel_amount=slip.travel_amount,
            other_amount=slip.other_amount, adjust_amount=slip.adjust_amount,
        )
        if payload.get("tax_amount") is not None:
            tax = calc.money(payload["tax_amount"])
            if tax < 0:
                raise AppException(message="个税不能为负数", status_code=422)
            slip.tax_amount = tax
        else:
            setting = await repository.get_setting(session, org_id)
            brackets = [repository.dump_model(row) for row in await repository.list_brackets(session, org_id)]
            people = await repository.names_by_employee(session, [slip.employee_id])
            if not people[slip.employee_id].get("hire_date"):
                raise AppException(message="该员工尚未填写入职日期，不能重新核算个税", status_code=422)
            hired = date.fromisoformat(people[slip.employee_id]["hire_date"])
            prior_gross, prior_tax, prior_special = await repository.prior_tax(session, org_id, slip.employee_id, payroll.period_month.year, payroll.period_month)
            special = slip.pension_employee_amount + slip.unemployment_employee_amount + slip.medical_employee_amount + slip.housing_employee_amount
            months = calc.tax_months(payroll.period_month.month, hired.year, hired.month, payroll.period_month.year)
            taxable = prior_gross + gross - prior_special - special - setting.tax_threshold * months
            tax = calc.bracket_tax(taxable, brackets) - prior_tax
            slip.tax_amount = tax if tax > 0 else calc.money(0)
        slip.gross_amount = gross
        slip.net_amount = calc.net_pay(
            gross=gross, tax=slip.tax_amount, pension_employee=slip.pension_employee_amount,
            unemployment_employee=slip.unemployment_employee_amount, medical_employee=slip.medical_employee_amount,
            housing_employee=slip.housing_employee_amount, other_deduction=slip.other_deduction_amount,
        )
        slip.employer_cost_amount = calc.employer_cost(
            gross=gross, pension_employer=slip.pension_employer_amount, unemployment_employer=slip.unemployment_employer_amount,
            injury_employer=slip.injury_employer_amount, medical_employer=slip.medical_employer_amount, housing_employer=slip.housing_employer_amount,
        )
        slip.updated_by, slip.updated_at = user_id, utc_now()
        session.add(slip)
        await session.commit()
        return repository.dump_model(slip)


async def close_payroll(org_id: UUID, user_id: UUID | None, month: str) -> dict:
    period = _month(month)
    async with get_session_context() as session:
        from . import social_repository, social_service
        await social_repository.lock_org(session, org_id)
        payroll = await repository.get_payroll(session, org_id, period)
        if payroll is None:
            raise AppException(message="请先核算该月工资", status_code=422)
        await social_service.assert_payroll_matches(session, org_id, payroll)
        payroll.status_code = "closed"
        payroll.updated_by, payroll.updated_at = user_id, utc_now()
        session.add(payroll)
        await session.commit()
        return {"status_code": "closed"}


async def export_csv(org_id: UUID, month: str) -> str:
    data = await payroll_lines(org_id, month)
    headers = ["员工编号", "姓名", "任务", "基本工资", "绩效", "奖金", "加班费", "软件报销", "出差补贴", "其他补贴", "补扣", "应发", "个税", "个人养老", "个人失业", "个人医疗", "个人公积金", "其他代扣", "实发", "企业成本", "开户行", "账号"]
    keys = ["employee_no", "full_name", "task_name", "base_amount", "performance_amount", "bonus_amount", "overtime_amount", "software_amount", "travel_amount", "other_amount", "adjust_amount", "gross_amount", "tax_amount", "pension_employee_amount", "unemployment_employee_amount", "medical_employee_amount", "housing_employee_amount", "other_deduction_amount", "net_amount", "employer_cost_amount", "bank_name", "account_no_masked"]
    def cell(value) -> str:
        text = "" if value is None else str(value)
        return '"' + text.replace('"', '""') + '"'

    lines = [",".join(cell(item) for item in headers)]
    for row in data["lines"]:
        lines.append(",".join(cell(row.get(key)) for key in keys))
    return "\ufeff" + "\n".join(lines)


PROJECT_STATUSES = {"active", "closed", "abandoned", "voided"}
CURRENCIES = {"CNY", "USD"}


def _currency_totals(contracts, receipts) -> dict[str, dict[str, Decimal]]:
    received = {}
    for row in receipts:
        received[row.contract_id] = received.get(row.contract_id, Decimal("0")) + row.amount
    totals: dict[str, dict[str, Decimal]] = {}
    for contract in contracts:
        bucket = totals.setdefault(contract.currency_code, {"total": Decimal("0"), "received": Decimal("0")})
        bucket["total"] += contract.total_amount
        bucket["received"] += received.get(contract.id, Decimal("0"))
    return totals


def _summary(project, contracts, receipts, costs, labor: Decimal) -> dict:
    totals = _currency_totals(contracts, receipts)
    direct = sum((row.amount for row in costs), Decimal("0"))
    received_cny = totals.get("CNY", {}).get("received", Decimal("0"))
    data = repository.dump_model(project)
    data.update({
        "labor_cost": float(labor),
        "direct_cost": float(direct),
        "received_cny": float(received_cny),
        "receivable_cny": float(calc.receivable(totals.get("CNY", {}).get("total", 0), received_cny)),
        "receivable_usd": float(calc.receivable(totals.get("USD", {}).get("total", 0), totals.get("USD", {}).get("received", 0))),
        "gross_profit_cny": float(calc.project_profit(received_cny, labor, direct)),
    })
    return data


def _clean_field_name(value: str) -> str:
    name = str(value or "").strip()
    if not name or len(name) > 64:
        raise AppException(message="请填写不超过 64 字的字段名称", status_code=422)
    return name


async def flex_fields(form_key: str) -> list[dict]:
    form_key = require_form_key(form_key)
    async with get_session_context() as session:
        return [repository.flex_field_payload(row) for row in await repository.list_flex_fields(session, form_key)]


async def create_flex_field(user_id: UUID | None, payload: dict) -> dict:
    form_key = require_form_key(payload["form_key"])
    field_key = str(payload["field_key"] or "").strip()
    if FIELD_KEY.fullmatch(field_key) is None:
        raise AppException(message="字段标识须为小写字母开头，只含小写字母、数字和下划线", status_code=422)
    if payload["value_type_code"] not in VALUE_TYPES:
        raise AppException(message="字段类型只支持文本、数值、日期或是否", status_code=422)
    async with get_session_context() as session:
        existing = await repository.list_flex_fields(session, form_key)
        if any(row.field_key == field_key for row in existing):
            raise AppException(message="该页面已有同名字段标识", status_code=409)
        row = SampleFlexField(
            form_key=form_key, field_key=field_key, field_name=_clean_field_name(payload["field_name"]),
            value_type_code=payload["value_type_code"], is_required=bool(payload.get("is_required")),
            sort_no=max((item.sort_no for item in existing), default=0) + 1, is_active=True,
            created_by=user_id, updated_by=user_id,
        )
        session.add(row)
        await session.commit()
        return repository.flex_field_payload(row)


async def update_flex_field(user_id: UUID | None, field_id: UUID, payload: dict) -> dict:
    async with get_session_context() as session:
        row = await repository.get_flex_field(session, field_id)
        if row is None or row.form_key not in FORM_KEYS:
            raise AppException(message="自定义字段不存在", status_code=404)
        row.field_name = _clean_field_name(payload["field_name"])
        row.is_required = bool(payload.get("is_required"))
        row.is_active = bool(payload.get("is_active", True))
        row.updated_by, row.updated_at = user_id, utc_now()
        session.add(row)
        await session.commit()
        return repository.flex_field_payload(row)


async def projects(org_id: UUID) -> list[dict]:
    async with get_session_context() as session:
        rows = await repository.list_projects(session, org_id)
        contracts = await repository.list_contracts(session, org_id)
        receipts = await repository.list_receipts_for(session, [row.id for row in contracts])
        costs = await repository.list_costs(session, org_id)
        labor = await repository.labor_cost_by_project(session, org_id)
        grouped_contracts: dict = {}
        grouped_receipts: dict = {}
        grouped_costs: dict = {}
        for row in contracts:
            grouped_contracts.setdefault(row.project_id, []).append(row)
        contract_project = {row.id: row.project_id for row in contracts}
        for row in receipts:
            grouped_receipts.setdefault(contract_project.get(row.contract_id), []).append(row)
        for row in costs:
            grouped_costs.setdefault(row.project_id, []).append(row)
        return [_summary(row, grouped_contracts.get(row.id, []), grouped_receipts.get(row.id, []), grouped_costs.get(row.id, []), labor.get(row.id, Decimal("0"))) for row in rows]


async def save_project(org_id: UUID, user_id: UUID | None, project_id: UUID | None, payload: dict) -> dict:
    if payload["status_code"] not in PROJECT_STATUSES:
        raise AppException(message="项目状态不正确", status_code=422)
    async with get_session_context() as session:
        current = await repository.get_project(session, org_id, project_id) if project_id is not None else None
        if project_id is not None and current is None:
            raise AppException(message="项目不存在", status_code=404)
        same_name = [row for row in await repository.list_projects(session, org_id) if row.project_name == payload["project_name"] and row.id != project_id]
        if same_name:
            raise AppException(message="已有同名项目", status_code=409)
        flex_form = normalize_flex_form(await repository.list_flex_fields(session, "project"), payload.get("flex_form"), current.flex_form if current else {})
        row = await repository.save_project(session, org_id, project_id, {
            "project_name": payload["project_name"],
            "customer_name": payload.get("customer_name") or None,
            "status_code": payload["status_code"],
            "pipeline_amount": Decimal(str(payload.get("pipeline_amount") or 0)),
            "flex_form": flex_form,
        }, user_id)
        await session.commit()
        return repository.dump_model(row)


async def project_detail(org_id: UUID, project_id: UUID) -> dict:
    async with get_session_context() as session:
        project = await repository.get_project(session, org_id, project_id)
        if project is None:
            raise AppException(message="项目不存在", status_code=404)
        contracts = await repository.list_contracts(session, org_id, project_id)
        plans = await repository.list_plans_for(session, [row.id for row in contracts])
        receipts = await repository.list_receipts_for(session, [row.id for row in contracts])
        costs = await repository.list_costs(session, org_id, project_id)
        labor = (await repository.labor_cost_by_project(session, org_id)).get(project_id, Decimal("0"))
        received = {}
        for row in receipts:
            received[row.contract_id] = received.get(row.contract_id, Decimal("0")) + row.amount
        contract_rows = []
        for row in contracts:
            got = received.get(row.id, Decimal("0"))
            contract_rows.append({
                **repository.dump_model(row),
                "received_amount": float(got),
                "receivable_amount": float(calc.receivable(row.total_amount, got)),
                "plans": [repository.dump_model(item) for item in plans if item.contract_id == row.id],
                "receipts": [repository.dump_model(item) for item in receipts if item.contract_id == row.id],
            })
        return {**_summary(project, contracts, receipts, costs, labor), "contracts": contract_rows, "costs": [repository.dump_model(row) for row in costs]}


async def add_contract(org_id: UUID, user_id: UUID | None, project_id: UUID, payload: dict) -> dict:
    if payload["currency_code"] not in CURRENCIES:
        raise AppException(message="币种只支持人民币或美元", status_code=422)
    async with get_session_context() as session:
        if await repository.get_project(session, org_id, project_id) is None:
            raise AppException(message="项目不存在", status_code=404)
        if any(row.contract_no == payload["contract_no"] for row in await repository.list_contracts(session, org_id)):
            raise AppException(message="合同编号已存在", status_code=409)
        row = await repository.save_contract(session, org_id, project_id, {
            "contract_no": payload["contract_no"],
            "currency_code": payload["currency_code"],
            "total_amount": Decimal(str(payload["total_amount"])),
        }, user_id)
        await session.commit()
        return repository.dump_model(row)


async def _require_contract(session, org_id: UUID, contract_id: UUID):
    row = await repository.get_contract(session, org_id, contract_id)
    if row is None:
        raise AppException(message="合同不存在", status_code=404)
    return row


async def add_plan(org_id: UUID, user_id: UUID | None, contract_id: UUID, payload: dict) -> dict:
    async with get_session_context() as session:
        await _require_contract(session, org_id, contract_id)
        month = _month(payload["plan_month"])
        row = await repository.add_receipt_plan(session, org_id, contract_id, {"plan_month": month, "amount": Decimal(str(payload["amount"]))}, user_id)
        await session.commit()
        return repository.dump_model(row)


async def add_project_receipt(org_id: UUID, user_id: UUID | None, contract_id: UUID, payload: dict) -> dict:
    async with get_session_context() as session:
        await _require_contract(session, org_id, contract_id)
        row = await repository.add_receipt(session, org_id, contract_id, {
            "received_on": date.fromisoformat(payload["received_on"]),
            "amount": Decimal(str(payload["amount"])),
            "remark": payload.get("remark") or None,
        }, user_id)
        await session.commit()
        return repository.dump_model(row)


async def add_project_cost(org_id: UUID, user_id: UUID | None, project_id: UUID, payload: dict) -> dict:
    async with get_session_context() as session:
        if await repository.get_project(session, org_id, project_id) is None:
            raise AppException(message="项目不存在", status_code=404)
        row = await repository.add_cost(session, org_id, project_id, {
            "cost_name": payload["cost_name"],
            "amount": Decimal(str(payload["amount"])),
            "occurred_on": date.fromisoformat(payload["occurred_on"]),
        }, user_id)
        await session.commit()
        return repository.dump_model(row)


INCOME_CATEGORIES = {"project_receipt", "outsourcing_income", "commission", "interest", "loan_repayment", "other_income"}
EXPENSE_CATEGORIES = {"payroll_social", "fixed_cost", "reimbursement", "fee_interest", "loan_disbursement", "other_expense", "employee_payable_settlement"}
ACCOUNT_TYPES = {"bank", "treasury"}
BALANCE_KINDS = {"month_end", "mid_month"}
FIXED_CATEGORIES = {"cloud", "rent", "property", "heating", "other"}


def _month_end(period: date) -> date:
    if period.month == 12:
        return date(period.year, 12, 31)
    return date(period.year, period.month + 1, 1) - timedelta(days=1)


def _sums(entries) -> tuple[Decimal, Decimal]:
    income = expense = Decimal("0")
    for row in entries:
        if row.direction_code == "income":
            income += row.amount
        else:
            expense += row.amount
    return income, expense


def _check_entry(direction: str, category: str, amount: Decimal) -> None:
    if amount <= 0:
        raise AppException(message="金额必须大于 0", status_code=422)
    if direction == "income" and category not in INCOME_CATEGORIES:
        raise AppException(message="收入分类不正确", status_code=422)
    if direction == "expense" and category not in EXPENSE_CATEGORIES:
        raise AppException(message="支出分类不正确", status_code=422)
    if direction not in {"income", "expense"}:
        raise AppException(message="收支方向不正确", status_code=422)


async def _account(session, org_id: UUID, account_id: UUID):
    row = await repository.get_account(session, org_id, account_id)
    if row is None:
        raise AppException(message="资金账户不存在", status_code=404)
    return row


async def _employee(session, org_id: UUID, employee_id: UUID):
    row = await repository.get_org_employee(session, org_id, employee_id)
    if row is None:
        raise AppException(message="员工不存在", status_code=404)
    return row


async def cash_ledger(org_id: UUID, month: str | None = None) -> dict:
    period = _month(month) if month else None
    end = _month_end(period) if period else None
    async with get_session_context() as session:
        accounts = await repository.list_accounts(session, org_id)
        entries = await repository.list_entries(session, org_id)
        checkpoints = await repository.list_checkpoints(session, org_id)
        names = {row.id: row.account_name for row in accounts}
        month_entries = [row for row in entries if period is None or period <= row.occurred_on <= end]
        month_income, month_expense = _sums(month_entries)
        account_rows = []
        for account in accounts:
            owned = [row for row in entries if row.account_id == account.id and account.opening_on <= row.occurred_on and (end is None or row.occurred_on <= end)]
            income, expense = _sums(owned)
            current_income, current_expense = _sums([row for row in owned if period is None or row.occurred_on >= period])
            account_rows.append({
                **repository.dump_model(account),
                "month_income": float(current_income),
                "month_expense": float(current_expense),
                "book_balance": float(calc.book_balance(account.opening_balance, income, expense)),
            })
        checks = []
        for row in checkpoints:
            if period is not None and not (period <= row.balance_on <= end):
                continue
            account = next((item for item in accounts if item.id == row.account_id), None)
            if account is None:
                continue
            owned = [item for item in entries if item.account_id == account.id and account.opening_on <= item.occurred_on <= row.balance_on]
            income, expense = _sums(owned)
            calculated = calc.book_balance(account.opening_balance, income, expense)
            checks.append({**repository.dump_model(row), "account_name": account.account_name, "calculated_balance": float(calculated), "difference": float(row.amount - calculated)})
        return {
            "month_income": float(month_income),
            "month_expense": float(month_expense),
            "month_net": float(calc.book_balance(0, month_income, month_expense)),
            "accounts": account_rows,
            "entries": [{**repository.dump_model(row), "account_name": names.get(row.account_id, "")} for row in month_entries],
            "checkpoints": checks,
        }


async def save_cash_account(org_id: UUID, user_id: UUID | None, payload: dict) -> dict:
    if payload["account_type_code"] not in ACCOUNT_TYPES:
        raise AppException(message="账户类型只支持银行账户或公司金库", status_code=422)
    async with get_session_context() as session:
        if any(row.account_name == payload["account_name"] for row in await repository.list_accounts(session, org_id)):
            raise AppException(message="已有同名账户", status_code=409)
        row = await repository.save_account(session, org_id, {
            "account_name": payload["account_name"],
            "account_type_code": payload["account_type_code"],
            "opening_balance": Decimal(str(payload.get("opening_balance") or 0)),
            "opening_on": date.fromisoformat(payload["opening_on"]),
        }, user_id)
        await session.commit()
        return repository.dump_model(row)


async def _write_entry(session, org_id: UUID, user_id: UUID | None, payload: dict):
    amount = Decimal(str(payload["amount"]))
    _check_entry(payload["direction_code"], payload["category_code"], amount)
    await _account(session, org_id, UUID(str(payload["account_id"])))
    project_id = UUID(str(payload["project_id"])) if payload.get("project_id") else None
    if project_id is not None and await repository.get_project(session, org_id, project_id) is None:
        raise AppException(message="项目不存在", status_code=404)
    occurred = payload["occurred_on"]
    return await repository.add_entry(session, org_id, {
        "account_id": UUID(str(payload["account_id"])),
        "occurred_on": date.fromisoformat(occurred) if isinstance(occurred, str) else occurred,
        "direction_code": payload["direction_code"],
        "category_code": payload["category_code"],
        "amount": amount,
        "summary": payload.get("summary") or None,
        "project_id": project_id,
        "source_type_code": payload.get("source_type_code"),
        "source_id": payload.get("source_id"),
    }, user_id)


async def add_cash_entry(org_id: UUID, user_id: UUID | None, payload: dict) -> dict:
    async with get_session_context() as session:
        row = await _write_entry(session, org_id, user_id, payload)
        await session.commit()
        return repository.dump_model(row)


async def import_cash_entries(org_id: UUID, user_id: UUID | None, rows: list[dict]) -> dict:
    async with get_session_context() as session:
        accounts = {row.account_name: row.id for row in await repository.list_accounts(session, org_id)}
        for row in rows:
            account_id = accounts.get(row["account_name"])
            if account_id is None:
                raise AppException(message=f"找不到账户 {row['account_name']}", status_code=422)
            await _write_entry(session, org_id, user_id, {**row, "account_id": account_id})
        await session.commit()
        return {"saved": len(rows)}


async def save_cash_checkpoint(org_id: UUID, user_id: UUID | None, payload: dict) -> dict:
    if payload["balance_kind_code"] not in BALANCE_KINDS:
        raise AppException(message="余额时点只支持月末或月中", status_code=422)
    async with get_session_context() as session:
        await _account(session, org_id, UUID(str(payload["account_id"])))
        row = await repository.save_checkpoint(session, org_id, {
            "account_id": UUID(str(payload["account_id"])),
            "balance_on": date.fromisoformat(payload["balance_on"]),
            "balance_kind_code": payload["balance_kind_code"],
            "amount": Decimal(str(payload["amount"])),
        }, user_id)
        await session.commit()
        return repository.dump_model(row)


async def loans(org_id: UUID) -> list[dict]:
    async with get_session_context() as session:
        rows = await repository.list_loans(session, org_id)
        repayments = await repository.list_repayments(session, org_id, [row.id for row in rows])
        people = await repository.financial_person_names(session, [row.employee_id for row in rows])
        repaid: dict[UUID, Decimal] = {}
        for row in repayments:
            repaid[row.loan_id] = repaid.get(row.loan_id, Decimal("0")) + row.amount
        result = []
        for row in rows:
            paid = repaid.get(row.id, Decimal("0"))
            result.append({**repository.dump_model(row), **people.get(row.employee_id, {}), "repaid_amount": float(paid), "outstanding_amount": float(calc.loan_outstanding(row.amount, paid)), "repayment_status_code": repayment_status(row.amount, paid)})
        return result


def repayment_status(amount: Decimal, paid: Decimal) -> str:
    return "settled" if paid >= amount else "partial" if paid > 0 else "unpaid"


def _debt_amount(value) -> Decimal:
    amount = Decimal(str(value))
    if not amount.is_finite() or amount <= 0 or amount >= Decimal("10000000000000000") or amount != calc.money(amount):
        raise AppException(message="金额须大于0，且最多保留两位小数", status_code=422)
    return amount


async def loan_repayments(org_id: UUID, loan_id: UUID) -> list[dict]:
    async with get_session_context() as session:
        if await repository.get_loan(session, org_id, loan_id) is None:
            raise AppException(message="往来款不存在", status_code=404)
        accounts = {row.id: row.account_name for row in await repository.list_accounts(session, org_id)}
        return [{**repository.dump_model(row), "account_name": accounts.get(row.account_id, "")} for row in await repository.list_repayments(session, org_id, [loan_id])]


async def create_loan(org_id: UUID, user_id: UUID | None, payload: dict, *, counterparty_org_id: UUID | None = None) -> dict:
    amount = _debt_amount(payload["amount"])
    debt_type = payload.get("debt_type_code", "employee_loan")
    if debt_type not in {"employee_loan", "company_payable"}:
        raise AppException(message="欠款类型不正确", status_code=422)
    if debt_type == "employee_loan" and not payload.get("account_id"):
        raise AppException(message="往来方欠公司须选择实际借出账户", status_code=422)
    if debt_type == "company_payable" and payload.get("account_id"):
        raise AppException(message="公司欠往来方登记时不指定资金账户，实际支付时选择付款账户", status_code=422)
    async with get_session_context() as session:
        await _employee(session, counterparty_org_id or org_id, UUID(str(payload["employee_id"])))
        account_id = UUID(str(payload["account_id"])) if payload.get("account_id") else None
        if account_id:
            await _account(session, org_id, account_id)
        loan = await repository.add_loan(session, org_id, {
            "employee_id": UUID(str(payload["employee_id"])),
            "account_id": account_id,
            "debt_type_code": debt_type,
            "amount": amount,
            "borrowed_on": date.fromisoformat(payload["borrowed_on"]),
            "remark": payload.get("remark") or None,
        }, user_id)
        if debt_type == "employee_loan":
            await _write_entry(session, org_id, user_id, {
                "account_id": loan.account_id,
                "occurred_on": loan.borrowed_on,
                "direction_code": "expense",
                "category_code": "loan_disbursement",
                "amount": amount,
                "summary": payload.get("remark") or "个人往来借款",
                "source_type_code": "loan",
                "source_id": loan.id,
            })
        await session.commit()
        return repository.dump_model(loan)


async def repay_loan(org_id: UUID, user_id: UUID | None, loan_id: UUID, payload: dict) -> dict:
    amount = _debt_amount(payload["amount"])
    async with get_session_context() as session:
        loan = await repository.lock_loan(session, org_id, loan_id)
        if loan is None:
            raise AppException(message="往来款不存在", status_code=404)
        if loan.debt_type_code not in {"employee_loan", "company_payable"}:
            raise AppException(message="欠款类型不支持偿还，请先核对", status_code=422)
        repaid_on = date.fromisoformat(payload["repaid_on"])
        if repaid_on < loan.borrowed_on:
            raise AppException(message="还款日期不能早于欠款发生日期", status_code=422)
        request_key = payload.get("request_key")
        if request_key:
            previous = await repository.repayment_by_request(session, org_id, request_key)
            if previous:
                if (previous.loan_id, previous.account_id, previous.amount, previous.repaid_on) != (loan_id, UUID(str(payload["account_id"])), amount, repaid_on):
                    raise AppException(message="该还款请求已使用，请刷新后重新登记", status_code=409)
                return repository.dump_model(previous)
        await _account(session, org_id, UUID(str(payload["account_id"])))
        paid = sum((row.amount for row in await repository.list_repayments(session, org_id, [loan_id])), Decimal("0"))
        if calc.loan_outstanding(loan.amount, paid) < amount:
            raise AppException(message="还款金额超过未还金额", status_code=422)
        repayment = await repository.add_repayment(session, org_id, {
            "loan_id": loan_id,
            "request_key": request_key,
            "account_id": UUID(str(payload["account_id"])),
            "amount": amount,
            "repaid_on": repaid_on,
        }, user_id)
        await _write_entry(session, org_id, user_id, {
            "account_id": repayment.account_id,
            "occurred_on": repayment.repaid_on,
            "direction_code": "expense" if loan.debt_type_code == "company_payable" else "income",
            "category_code": "employee_payable_settlement" if loan.debt_type_code == "company_payable" else "loan_repayment",
            "amount": amount,
            "summary": "公司偿还个人往来款" if loan.debt_type_code == "company_payable" else "个人归还借款",
            "source_type_code": "loan_repayment",
            "source_id": repayment.id,
        })
        await session.commit()
        return repository.dump_model(repayment)




async def reimbursements(org_id: UUID) -> list[dict]:
    async with get_session_context() as session:
        rows = await repository.list_reimbursements(session, org_id)
        people = await repository.financial_person_names(session, [row.employee_id for row in rows])
        attachments = await file_service.items_for_business(session, REIMBURSEMENT_FILES, [row.id for row in rows])
        return [{**repository.dump_model(row), **people.get(row.employee_id, {}), "attachments": attachments.get(row.id, [])} for row in rows]


async def create_reimbursement(org_id: UUID, user_id: UUID | None, payload: dict, *, claimant_org_id: UUID | None = None, actor=None) -> dict:
    subject = str(payload["subject"]).strip()
    if not subject or len(subject) > 128:
        raise AppException(message="请填写报销事由（最多128字）", status_code=422)
    amount = Decimal(str(payload["amount"]))
    if not amount.is_finite() or amount <= 0 or amount != amount.quantize(Decimal("0.01")):
        raise AppException(message="金额必须大于0且最多两位小数", status_code=422)
    async with get_session_context() as session:
        await _employee(session, claimant_org_id or org_id, UUID(str(payload["employee_id"])))
        row = await repository.add_reimbursement(session, org_id, {
            "employee_id": UUID(str(payload["employee_id"])),
            "amount": amount,
            "subject": subject,
            "status_code": "draft",
            "occurred_on": date.fromisoformat(payload["occurred_on"]),
        }, user_id)
        if payload.get("file_ids"):
            if actor is None or actor.user_id != user_id:
                raise AppException(message="附件绑定需要当前登录身份", status_code=403)
            await file_service.bind(session, payload["file_ids"], user=actor, org_id=org_id,
                                    scene_code=INVOICE_SCENE, business_type_code=REIMBURSEMENT_FILES, business_id=row.id)
        await session.commit()
        return repository.dump_model(row)


async def reimbursement_action(org_id: UUID, user_id: UUID | None, reimbursement_id: UUID, action: str, account_id: UUID | None) -> dict:
    async with get_session_context() as session:
        row = await repository.get_reimbursement(session, org_id, reimbursement_id)
        if row is None:
            raise AppException(message="报销单不存在", status_code=404)
        if action == "submit" and row.status_code in {"draft", "rejected"}:
            counts = await file_service.count_for_business(session, REIMBURSEMENT_FILES, [row.id])
            if not counts.get(row.id):
                raise AppException(message="请先添加发票附件再提交报销", status_code=422)
            row.status_code = "submitted"
        elif action == "reject" and row.status_code == "submitted":
            row.status_code = "rejected"
        elif action == "post" and row.status_code == "submitted":
            if account_id is None:
                raise AppException(message="入账需要选择付款账户", status_code=422)
            await _account(session, org_id, account_id)
            await _write_entry(session, org_id, user_id, {
                "account_id": account_id,
                "occurred_on": date.today(),
                "direction_code": "expense",
                "category_code": "reimbursement",
                "amount": row.amount,
                "summary": row.subject,
                "source_type_code": "reimbursement",
                "source_id": row.id,
            })
            row.account_id = account_id
            row.status_code = "posted"
        else:
            raise AppException(message="当前状态不能执行该操作", status_code=409)
        row.updated_by, row.updated_at = user_id, utc_now()
        session.add(row)
        await session.commit()
        return repository.dump_model(row)


async def fixed_costs(org_id: UUID) -> list[dict]:
    async with get_session_context() as session:
        return [repository.dump_model(row) for row in await repository.list_fixed_costs(session, org_id)]


async def create_fixed_cost(org_id: UUID, user_id: UUID | None, payload: dict) -> dict:
    if payload["category_code"] not in FIXED_CATEGORIES:
        raise AppException(message="固定成本类别不正确", status_code=422)
    amount = Decimal(str(payload["monthly_amount"]))
    if amount <= 0:
        raise AppException(message="金额必须大于 0", status_code=422)
    async with get_session_context() as session:
        await _account(session, org_id, UUID(str(payload["account_id"])))
        row = await repository.add_fixed_cost(session, org_id, {
            "account_id": UUID(str(payload["account_id"])),
            "cost_name": payload["cost_name"],
            "category_code": payload["category_code"],
            "monthly_amount": amount,
            "is_active": True,
        }, user_id)
        await session.commit()
        return repository.dump_model(row)


async def charge_fixed_cost(org_id: UUID, user_id: UUID | None, cost_id: UUID, month: str) -> dict:
    period = _month(month)
    async with get_session_context() as session:
        cost = await repository.get_fixed_cost(session, org_id, cost_id)
        if cost is None or not cost.is_active:
            raise AppException(message="固定成本不存在或已停用", status_code=404)
        if await repository.find_charge(session, cost_id, period) is not None:
            raise AppException(message="该月已经记过这笔固定成本", status_code=409)
        charge_id = uuid7()
        entry = await _write_entry(session, org_id, user_id, {
            "account_id": cost.account_id,
            "occurred_on": period,
            "direction_code": "expense",
            "category_code": "fixed_cost",
            "amount": cost.monthly_amount,
            "summary": cost.cost_name,
            "source_type_code": "fixed_cost",
            "source_id": charge_id,
        })
        await repository.add_charge(session, org_id, {"id": charge_id, "fixed_cost_id": cost_id, "period_month": period, "cash_entry_id": entry.id}, user_id)
        await session.commit()
        return repository.dump_model(entry)


async def social_plans(org_id: UUID) -> list[dict]:
    async with get_session_context() as session:
        return [repository.dump_model(row) for row in await repository.list_plans(session, org_id)]


from .social_service import (social_bases, save_social_basis, social_bills, generate_social_bill, social_bill_detail, update_social_bill, confirm_social_bill, pay_social_bill, pay_payroll)


async def add_reimbursement_files(org_id, user_id, reimbursement_id, payload, *, actor):
    async with get_session_context() as session:
        row = await repository.get_reimbursement(session, org_id, reimbursement_id)
        if row is None:
            raise AppException(message="报销单不存在", status_code=404)
        if row.status_code not in {"draft", "rejected"}:
            raise AppException(message="仅草稿或驳回的报销单可补充附件", status_code=409)
        counts = await file_service.count_for_business(session, REIMBURSEMENT_FILES, [row.id])
        await file_service.bind(session, payload["file_ids"], user=actor, org_id=org_id,
                                scene_code=INVOICE_SCENE, business_type_code=REIMBURSEMENT_FILES,
                                business_id=row.id, start_sort=counts.get(row.id, 0))
        row.updated_by, row.updated_at = user_id, utc_now()
        session.add(row)
        await session.commit()
        return repository.dump_model(row)
