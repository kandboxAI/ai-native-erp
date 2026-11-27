"""HTTP应用层的多组织编排：授权查询范围与单组织业务事务分开。"""
from dataclasses import dataclass
from uuid import UUID
import csv
import io
from app.auth.schemas import AuthenticatedUser
from app.auth.scope_filters import ensure_org_access
from app.core.exceptions import AppException
from app.framework.db.session import get_session_context
from . import access_repository as repo
from . import service as business
from . import models

@dataclass(frozen=True)
class BusinessScope:
    user: AuthenticatedUser
    selected_org_id: UUID | None = None
    @property
    def user_id(self):
        return self.user.user_id

async def organizations(scope, permission="sample_app:access"):
    async with get_session_context() as session:
        return await repo.organizations(session, scope.user, scope.selected_org_id, permission)

async def owner(scope, model, identity):
    async with get_session_context() as session:
        org = await repo.record_org(session, scope.user, model, UUID(str(identity)), scope.selected_org_id)
    if org is None:
        raise AppException(message="记录不存在或不在当前授权数据范围内", status_code=404)
    return org

async def new_org(scope, requested=None):
    selected = UUID(str(requested)) if requested else scope.selected_org_id
    if requested and scope.selected_org_id is not None and selected != scope.selected_org_id:
        raise AppException(message="表单组织与请求筛选组织不一致", status_code=422)
    if selected is not None:
        ensure_org_access(scope.user, selected, "sample_app:access")
        async with get_session_context() as session:
            found = await repo.organizations(session, scope.user, selected)
        if not found:
            raise AppException(message="所属组织不存在或不可访问", status_code=403)
        return selected
    choices = await organizations(scope)
    if len(choices) == 1:
        return choices[0]["id"]
    raise AppException(message="请选择本次操作的所属组织", status_code=422)

def tagged(value, org):
    if isinstance(value, list):
        return [tagged(row, org) for row in value]
    if isinstance(value, dict):
        nested = {**value}
        for key in ["contracts", "costs", "setting", "plans", "brackets", "receipts", "lines"]:
            if key in nested:
                nested[key] = tagged(nested[key], org)
        return {**nested, "org_id": str(org["id"]), "org_name": org["org_name"]}
    return value

READ_LISTS = {"employees", "attendance", "salaries", "projects", "loans", "reimbursements", "fixed_costs", "social_plans", "social_bases", "social_bills"}
# (业务模型, 位置参数中记录id的下标)；嵌套动作按父单据自身归属办理。
RECORDS = {
    "save_employee": (models.SampleEmployee, 1), "write_plan": (models.SampleSocialPlan, 1),
    "update_line": (models.SamplePayslip, 1), "save_project": (models.SampleProject, 1),
    "project_detail": (models.SampleProject, 0), "add_contract": (models.SampleProject, 1),
    "add_plan": (models.SampleContract, 1), "add_project_receipt": (models.SampleContract, 1),
    "add_project_cost": (models.SampleProject, 1), "repay_loan": (models.SampleLoan, 1),
    "loan_repayments": (models.SampleLoan, 0), "reimbursement_action": (models.SampleReimbursement, 1), "add_reimbursement_files": (models.SampleReimbursement, 1),
    "social_bill_detail": (models.SocialBill, 0),
    "update_social_bill": (models.SocialBill, 1),
    "confirm_social_bill": (models.SocialBill, 1),
    "pay_social_bill": (models.SocialBill, 1),
    "charge_fixed_cost": (models.SampleFixedCost, 1),
}
REFERENCES = {
    "save_social_basis": (models.SampleEmployee, "employee_id"),
    "add_salary": (models.SampleEmployee, "employee_id"),
    "add_cash_entry": (models.SampleAccount, "account_id"),
    "save_cash_checkpoint": (models.SampleAccount, "account_id"), "create_fixed_cost": (models.SampleAccount, "account_id"),
}

async def read(scope, name, args):
    choices = await organizations(scope)
    values = [(org, await getattr(business, name)(org["id"], *args)) for org in choices]
    if name in READ_LISTS:
        return [row for org, result in values for row in tagged(result, org)]
    if name == "cash_ledger":
        return {**{key: [row for org, result in values for row in tagged(result[key], org)] for key in ["accounts", "entries", "checkpoints"]}, **{key: sum(result[key] for _, result in values) for key in ["month_income", "month_expense", "month_net"]}}
    if name == "payroll_lines":
        states = {result["status_code"] for _, result in values if result["status_code"]}
        return {"status_code": next(iter(states)) if len(states) == 1 else "mixed" if states else "",
                "batches": [{"id": result["payroll_id"], "org_id": str(org["id"]),
                             "org_name": org["org_name"], "status_code": result["status_code"]}
                            for org, result in values if result.get("payroll_id")],
                "lines": [{**row, "payroll_status_code": result["status_code"]} for org, result in values for row in tagged(result["lines"], org)]}
    if name == "software_claims":
        return [row for org, result in values for row in tagged(result, org)]
    if name == "export_csv":
        output = io.StringIO(); writer = csv.writer(output); wrote = False
        for org, value in values:
            rows = list(csv.reader(io.StringIO(value.lstrip("\ufeff"))))
            if not rows: continue
            if not wrote: writer.writerow(["所属组织", *rows[0]]); wrote = True
            writer.writerows([[org["org_name"], *row] for row in rows[1:]])
        return "\ufeff" + output.getvalue()
    raise RuntimeError("未声明的跨组织查询")

async def history(scope):
    async with get_session_context() as session:
        rows = await repo.history(session, scope.user, scope.selected_org_id)
        orgs = {str(row["id"]): row["org_name"] for row in await repo.organizations(session, scope.user)}
    return [{"id": str(row.id), "org_id": str(row.org_id), "org_name": orgs.get(str(row.org_id), ""), "sheet_name": row.sheet_name, "row_no": row.row_no, "source_name": row.source_name, "source_cells": row.source_cells, "handling_key": row.handling_key, "handling_note": row.handling_note} for row in rows]

async def invoke(name, scope, *args):
    if name in READ_LISTS | {"cash_ledger", "payroll_lines", "export_csv", "software_claims"}:
        return await read(scope, name, args)
    args = list(args)
    payload = args[-1] if args and isinstance(args[-1], dict) else None
    requested = payload.get("org_id") if payload else None
    if payload is not None:
        args[-1] = {key: value for key, value in payload.items() if key != "org_id"}
    if name in RECORDS and args[RECORDS[name][1]] is not None:
        model, index = RECORDS[name]
        org_id = await owner(scope, model, args[index])
    elif name in REFERENCES:
        model, key = REFERENCES[name]
        org_id = await owner(scope, model, payload[key])
    else:
        org_id = await new_org(scope, requested)
    if requested and UUID(str(requested)) != org_id:
        raise AppException(message="所属组织必须与关联记录一致，不能通过编辑移动历史数据", status_code=422)
    if name in {"create_loan", "create_reimbursement"}:
        # 往来账归属和任职归属分别授权；筛选资金组织不能用于过滤往来对象的任职组织。
        counterparty_org = await owner(BusinessScope(scope.user), models.SampleEmployee, payload["employee_id"])
        person_argument = "counterparty_org_id" if name == "create_loan" else "claimant_org_id"
        result = await getattr(business, name)(org_id, *args, **{person_argument: counterparty_org}, **({"actor": scope.user} if name == "create_reimbursement" else {}))
    elif name == "add_reimbursement_files":
        result = await business.add_reimbursement_files(org_id, *args, actor=scope.user)
    else:
        result = await getattr(business, name)(org_id, *args)
    if isinstance(result, (dict, list)):
        matching = next((row for row in await organizations(scope) if row["id"] == org_id), {"id": org_id, "org_name": ""})
        return tagged(result, matching)
    return result

async def flex_fields(scope, form_key: str):
    return await business.flex_fields(form_key)


async def create_flex_field(scope, payload: dict):
    return await business.create_flex_field(scope.user_id, payload)


async def update_flex_field(scope, field_id, payload: dict):
    return await business.update_flex_field(scope.user_id, field_id, payload)


def _page_args(page: int, page_size: int) -> tuple[int, int]:
    page = max(1, int(page or 1))
    page_size = min(100, max(1, int(page_size or 20)))
    return page, page_size


async def page_reimbursements(
    scope,
    *,
    page: int = 1,
    page_size: int = 20,
    keyword: str | None = None,
    status_code: str | None = None,
    occurred_month: str | None = None,
):
    """费用报销后端分页；跨授权组织一次查询。"""
    from datetime import date as date_cls
    page, page_size = _page_args(page, page_size)
    month = None
    if occurred_month:
        try:
            year, mon = occurred_month.split("-")
            month = date_cls(int(year), int(mon), 1)
        except (TypeError, ValueError):
            raise AppException(message="发生账期格式应为 YYYY-MM", status_code=422)
    choices = await organizations(scope)
    org_map = {org["id"]: org for org in choices}
    async with get_session_context() as session:
        from . import repository
        from .reimbursement_files import BUSINESS_TYPE as REIMBURSEMENT_FILES
        from app.modules.file.service import service as file_service
        total, rows = await repository.page_reimbursements(
            session, list(org_map), page=page, page_size=page_size, keyword=keyword,
            status_code=status_code, occurred_month=month)
        people = await repository.financial_person_names(session, [row.employee_id for row in rows])
        attachments = await file_service.items_for_business(session, REIMBURSEMENT_FILES, [row.id for row in rows])
        items = []
        for row in rows:
            org = org_map.get(row.org_id, {"id": row.org_id, "org_name": ""})
            items.append(tagged({
                **repository.dump_model(row),
                **people.get(row.employee_id, {}),
                "attachments": attachments.get(row.id, []),
            }, org))
        return {"items": items, "total": total, "page": page, "page_size": page_size}


async def page_software_claims(scope, period_month: str, *, page: int = 1, page_size: int = 20):
    """软件报销后端分页；按工资月，跨授权组织一次查询。"""
    page, page_size = _page_args(page, page_size)
    choices = await organizations(scope)
    org_map = {org["id"]: org for org in choices}
    from . import software_claim_service as claims
    return await claims.admin_page(list(org_map), period_month, page=page, page_size=page_size, org_map=org_map)


_ALLOWED = READ_LISTS | set(RECORDS) | set(REFERENCES) | {"generate_social_bill", "pay_payroll", "create_loan", "create_reimbursement", "read_setting", "write_setting", "save_cash_account", "import_cash_entries", "save_attendance", "calculate", "close_payroll", "cash_ledger", "payroll_lines", "export_csv", "software_claims"}
def __getattr__(name):
    if name not in _ALLOWED:
        raise AttributeError(name)
    async def call(scope, *args):
        return await invoke(name, scope, *args)
    return call
