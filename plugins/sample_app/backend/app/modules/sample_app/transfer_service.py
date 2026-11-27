import hashlib
import json

from app.core.exceptions import AppException
from app.framework.db.models import utc_now
from app.framework.db.session import get_session_context

from . import models, repository, scoped_service, social_repository, transfer_repository
from .social_models import SocialBasis


async def transfer(scope, employee_id, target_org_id, period, target_plan_id, *, preview, preview_key=None):
    if period.day != 1:
        raise AppException("调动从工资和社保归属月的第一天生效", status_code=422)
    source_org_id = await scoped_service.owner(scope, models.SampleEmployee, employee_id)
    if target_org_id == source_org_id:
        raise AppException("请选择不同的目标组织", status_code=422)
    await scoped_service.new_org(scoped_service.BusinessScope(scope.user), target_org_id)

    async with get_session_context() as session:
        for org_id in sorted([source_org_id, target_org_id]):
            await social_repository.lock_org(session, org_id)
        employee = await transfer_repository.lock_employee(session, source_org_id, employee_id)
        if (employee is None or employee.personnel_type_code != "internal"
                or employee.employment_status_code != "active" or employee.employment_end_on):
            raise AppException("仅可调动尚未结束任职的内部员工", status_code=409)
        if employee.hire_date and period <= employee.hire_date:
            raise AppException("调动生效日必须晚于原入职日期", status_code=422)
        if await repository.find_employee_by_no(session, target_org_id, employee.employee_no):
            raise AppException("目标组织已有相同员工编号，请先核对名册", status_code=409)
        if await transfer_repository.has_period_conflict(session, source_org_id, target_org_id, employee_id, period):
            raise AppException("生效月或以后已有工资册、缴费单或原组织考勤，请先处理后再调动", status_code=409)
        plan = await repository.get_social_plan(session, target_org_id, target_plan_id)
        if plan is None:
            raise AppException("请选择目标组织的有效缴费方案", status_code=422)
        salary = await repository.current_salary(session, source_org_id, employee_id, period)
        basis = await social_repository.current_basis(session, source_org_id, employee_id, period)
        if salary is None or (basis is None and salary.social_plan_id is None):
            raise AppException("原组织在生效月缺少定薪或缴费基数，请先补齐", status_code=409)
        future = [row for row in await repository.list_salaries(session, source_org_id) if row.employee_id == employee_id]
        future += [row for row in await social_repository.bases(session, source_org_id) if row.employee_id == employee_id]
        if any(row.valid_from >= period for row in future):
            raise AppException("原组织有从生效月起生效的定薪或基数版本，请先处理", status_code=409)
        data = {
            "effective_on": period.isoformat(), "plan_name": plan.plan_name,
            "base_amount": str(salary.base_amount), "performance_amount": str(salary.performance_amount),
            "social_base": str(basis.social_base if basis else salary.social_base),
            "housing_base": str(basis.housing_base if basis else salary.social_base),
        }
        reviewed = [str(employee_id), str(source_org_id), str(target_org_id), str(plan.id), data]
        key = hashlib.sha256(json.dumps(reviewed, sort_keys=True).encode()).hexdigest()
        if preview:
            return {**data, "preview_key": key}
        if preview_key != key:
            raise AppException("调动内容已变化，请重新预览后确认", status_code=409)

        actor = scope.user_id
        now = utc_now()
        employee.employment_end_on = period
        for row in [employee, salary, *([basis] if basis else [])]:
            row.updated_at, row.updated_by = now, actor
            if row is not employee:
                row.valid_to = period
            session.add(row)
        target = await social_repository.add(session, models.SampleEmployee(
            org_id=target_org_id, employee_no=employee.employee_no, full_name=employee.full_name,
            personnel_type_code="internal", employment_status_code="active", hire_date=period,
            bank_name=employee.bank_name, account_no_masked=employee.account_no_masked,
            flex_form=dict(employee.flex_form or {}), created_by=actor, updated_by=actor,
        ))
        await social_repository.add(session, models.SampleSalary(
            org_id=target_org_id, employee_id=target.id, social_plan_id=plan.id,
            base_amount=salary.base_amount, performance_amount=salary.performance_amount,
            social_base=basis.social_base if basis else salary.social_base, valid_from=period,
            created_by=actor, updated_by=actor,
        ))
        await social_repository.add(session, SocialBasis(
            org_id=target_org_id, employee_id=target.id, social_plan_id=plan.id,
            social_base=basis.social_base if basis else salary.social_base,
            housing_base=basis.housing_base if basis else salary.social_base,
            valid_from=period, created_by=actor, updated_by=actor,
        ))
        await session.commit()
        return {**data, "employee_id": str(target.id)}
