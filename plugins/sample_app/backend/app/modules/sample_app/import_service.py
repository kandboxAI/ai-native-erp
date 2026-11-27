"""整份整理版工作簿的原子导入；来源记录和业务映射同一事务提交。"""
from collections import Counter
from datetime import date
from decimal import Decimal
from pathlib import Path
from uuid import UUID

from app.framework.db.session import get_session_context
from app.framework.db.tenant import require_tenant_schema
from . import import_repository as repo
from . import repository
from .excel_source import read_source, number, is_note, ledger_difference
from .import_models import FinanceImportRow
from .models import SampleEmployee, SampleProject, SampleContract, SampleReceipt


async def organizations(user):
    async with get_session_context() as session:
        return await repo.organization_options(session, user)


async def history(user):
    async with get_session_context() as session:
        rows = await repo.source_rows(session, user, user.org_id)
        return [{"id": str(row.id), "sheet_name": row.sheet_name, "row_no": row.row_no,
                 "source_name": row.source_name, "source_cells": row.source_cells,
                 "handling_key": row.handling_key, "handling_note": row.handling_note} for row in rows]


def project_contract(cells):
    total, received, due = (number(cells.get(k)) for k in ["合同总价", "已回款", "应收(总价-已付)"])
    if total is not None and received is not None and due is not None and total - received == due:
        return "CNY", total, received
    if cells.get("合同总价") == "4K USD":
        return "USD", Decimal("4000"), None
    return None


async def import_workbook(path: Path, org_id: UUID, *, apply: bool = False):
    digest, rows = read_source(path)
    if not apply:
        return {"mode": "preview", "source_sha256": digest, "sheet_rows": dict(Counter(r.sheet for r in rows)),
                "source_rows": len(rows), "contracts_eligible": sum(bool(project_contract(r.cells)) for r in rows if r.sheet == "项目台账" and not is_note(r))}
    schema = require_tenant_schema()
    async with get_session_context() as session:
        await repo.lock_import(session, schema, org_id)
        existing = await repo.imported_rows(session, org_id)
        if existing:
            if {r.source_sha256 for r in existing} == {digest} and len(existing) == len(rows):
                return {"mode": "already_imported", "source_rows": len(existing)}
            raise ValueError("目标组织已有另一份或不完整的来源导入；请审核差异，不覆盖现有数据")
        if not await repo.business_is_empty(session, org_id):
            raise ValueError("目标组织已有业务记录，不能自动合并；请先审核重名和重复数据")
        employees = {}
        counts = Counter()
        # 姓名只在本次已审核工作簿内用于去重，不借此合并其他组织/既有人员。
        for source in rows:
            if source.sheet != "人员薪资" or is_note(source):
                continue
            cells = source.cells
            if cells["状态"] not in {"在职", "已离职"}:
                raise ValueError("人员薪资存在未知员工状态")
            hired = cells.get("入职时间")
            employee = await repo.insert(session, SampleEmployee, org_id,
                employee_no=f"KH-XLS-{source.row_no:03d}", full_name=cells["姓名"],
                employment_status_code="resigned" if cells["状态"] == "已离职" else "active",
                hire_date=None if number(hired) is not None or hired in {None, "—", ""} else date.fromisoformat(hired))
            if cells["姓名"] in employees:
                raise ValueError("来源名册有重名，需先确认人员身份")
            employees[cells["姓名"]] = employee
            counts["employees"] += 1
        details = []
        for source in rows:
            cells = source.cells
            state, note = "reference", "保留历史来源；未生成会影响正式账簿的业务单据。"
            employee_id = employees.get(cells.get("姓名") or cells.get("归属人"))
            employee_id = employee_id.id if employee_id else None
            project_id = None
            if is_note(source):
                state, note = "note", "说明或合计行，仅保留来源，不重复计入业务金额。"
            elif source.sheet == "人员薪资":
                state, note = "partial", "已建立员工档案；城市、工资、系数、补贴保留于来源记录，未明确生效期间，不自动定薪。"
                if cells.get("入职时间") in {None, "—", ""}:
                    note += " 入职日期待补。"
            elif source.sheet == "项目台账":
                name = cells["项目名称"]
                project = await repo.insert(session, SampleProject, org_id, project_name=name,
                    status_code="voided" if "废止" in name else "active",
                    pipeline_amount=number(cells["管道(在谈)"]) or Decimal("0"),
                    remark=str(cells.get("备注") or "") + "；未列金额不代表已确认零值，详见历史来源台账。")
                project_id = project.id
                counts["projects"] += 1
                contract = project_contract(cells)
                state, note = "partial", "已建立项目；单位、币种或合同金额尚不完整，未建立合同。"
                if contract:
                    currency, total, received = contract
                    document = await repo.insert(session, SampleContract, org_id, project_id=project.id,
                        contract_no=f"KH-XLS-{digest[:8]}-{source.row_no:03d}", currency_code=currency, total_amount=total)
                    counts["contracts"] += 1
                    note = "已导入项目、台账合同总额；合同编号为本系统导入编号。"
                    if received is not None and received != 0:
                        await repo.insert(session, SampleReceipt, org_id, contract_id=document.id, amount=received,
                            received_on=None, remark="历史累计已回款；具体到账日期未提供，月份说明详见项目备注；不生成资金流水。")
                        counts["cumulative_receipts"] += 1
                        note += " 已导入累计回款，具体日期留空；不重复记银行流水。"
                    state = "imported" if received is not None else "partial"
                    if received is None:
                        note += " 已回款金额未提供，不将页面推算应收视为确认余额。"
                if number(cells.get("管道(在谈)")) is None:
                    state = "partial"
                    note += " 管道未提供，页面零值仅为现有模型默认，确认以来源为准。"
            elif source.sheet == "工资概览":
                note = "保留发薪主体、基本工资、企业成本及项目任务；无工资月份及个税明细，未生成工资单。"
            elif source.sheet == "流水台账":
                delta = ledger_difference(cells)
                note = "保留月度汇总及月末余额；无明确账户、期初余额和逐笔日期，未拆造银行流水。"
                if delta:
                    note += f" 原表支出合计减分项合计差额 {delta:.2f} 元，待核对。"
            elif source.sheet == "银行账户":
                note = "保存银行账户来源资料，账号仅保留尾四位；无期初日期及余额，未作为已开账资金账户。"
            elif source.sheet == "奖金台账":
                note = "保留奖金归属、金额、说明及原始状态；缺少完整发放期间及已付拆分，不自动发放或重复记支出。"
            elif source.sheet == "云费用":
                note = "保留金额、月/年周期及范围说明；未指定扣款账户、生效时间，不自动周期扣款。"
            elif source.sheet == "社保公积金规则":
                note = "规则作为历史参考保留；不将合计比例或单人示例反推为所有员工缴费基数。"
            await repo.insert(session, FinanceImportRow, org_id, source_name=path.name, source_sha256=digest,
                sheet_name=source.sheet, row_no=source.row_no, source_cells=cells,
                handling_key=state, handling_note=note, employee_id=employee_id, project_id=project_id)
            details.append({"sheet": source.sheet, "row_no": source.row_no, "state": state, "note": note})
        await repository.ensure_defaults(session, org_id, None)
        await session.commit()
        return {"mode": "imported", "org_id": str(org_id), "source_sha256": digest,
                "source_rows": len(rows), "business_records": dict(counts),
                "sheet_rows": dict(Counter(r.sheet for r in rows)), "rows": details}
