"""仅开放可撤回的录入数据；入账流水、支付、封账及历史导入不提供删除。"""
from app.core.exceptions import AppException
from app.framework.db.models import utc_now
from app.framework.db.session import get_session_context
from . import models, repository, deletion_repository as repo, access_repository
from .social_models import SocialBasis, SocialBill, SocialBillLine
from .social_repository import lock_org, lines as bill_lines

RESOURCES = {
    "employees": models.SampleEmployee, "projects": models.SampleProject,
    "social-plans": models.SampleSocialPlan, "salaries": models.SampleSalary,
    "social-bases": SocialBasis, "accounts": models.SampleAccount,
    "fixed-costs": models.SampleFixedCost, "reimbursements": models.SampleReimbursement,
    "contracts": models.SampleContract, "project-costs": models.SampleProjectCost,
    "receipt-plans": models.SampleReceiptPlan,
    "attendance": models.SampleAttendance,
    "social-bills": SocialBill,
    "payrolls": models.SamplePayroll,
    "account-balances": models.SampleAccountBalance,
}


async def delete_record(scope, resource, identity):
    model = RESOURCES.get(resource)
    if model is None:
        raise AppException("该类记录不支持删除", status_code=422)
    async with get_session_context() as session:
        org_id = await access_repository.record_org(session, scope.user, model, identity, scope.selected_org_id)
        if org_id is None:
            raise AppException("记录不存在或不在授权范围内", status_code=404)
        await lock_org(session, org_id)
        row = await repo.owned_row(session, model, scope.user, identity, scope.selected_org_id)
        if row is None:
            raise AppException("记录不存在或不在授权范围内", status_code=404)
        if resource == "reimbursements" and row.status_code not in {"draft", "rejected"}:
            raise AppException("只能删除草稿或已驳回的报销，已提交或入账单据不可删除", status_code=409)
        children = []
        child_model = None
        predecessor = None
        if resource == "social-bills":
            if row.status_code != "draft" or row.cash_entry_id:
                raise AppException("只能删除未确认且未付款的缴费单", status_code=409)
            children = await bill_lines(session, row.org_id, row.id)
            child_model = SocialBillLine
        elif resource == "payrolls":
            if row.status_code != "draft":
                raise AppException("只能删除草稿工资册，已封账工资册必须保留", status_code=409)
            children = await repository.list_payslips(session, row.id)
            child_model = models.SamplePayslip
        if child_model is not None:
            for child in children:
                if await repo.has_references(session, child_model, child.id):
                    raise AppException("单据明细已被引用，不能删除", status_code=409)
        if resource in {"salaries", "social-bases", "attendance"}:
            day = row.period_month if resource == "attendance" else row.valid_from
            if await repo.has_payroll_since(session, row.org_id, day.replace(day=1)):
                raise AppException("该期间已有工资核算，请保留核算依据，不能删除", status_code=409)
        if resource in {"salaries", "social-bases"}:
            versions = await repo.other_versions(session, model, row)
            if any(version.valid_from >= row.valid_from for version in versions):
                raise AppException("只能撤回最新版本，不能删除中间的历史版本", status_code=409)
            previous = [version for version in versions if version.valid_to == row.valid_from]
            if len(previous) > 1:
                raise AppException("历史版本有效期存在冲突，请先核对", status_code=409)
            predecessor = previous[0] if previous else None
        excluded = (child_model.__tablename__,) if child_model is not None else ()
        if await repo.has_references(session, model, row.id, exclude_tables=excluded):
            raise AppException("记录已有关联业务，请先处理关联记录；历史核算和资金记录不能级联删除", status_code=409)
        now = utc_now()
        if predecessor is not None:
            repo.restore_version_end(session, predecessor, row.valid_to, scope.user_id, now)
        for child in children:
            repo.mark_deleted(session, child, scope.user_id, now)
        repo.mark_deleted(session, row, scope.user_id, now)
        await session.commit()
        return {"id": str(row.id)}
