"""本人报销事务。MCP 只能准备/查询/消费，人工确认入口使用正常登录鉴权。"""
from datetime import timedelta
from uuid import UUID
from sqlalchemy.exc import IntegrityError
from app.auth.scope_filters import ensure_org_access
from app.core.exceptions import AppException
from app.framework.db.models import utc_now
from app.framework.db.session import get_session_context
from app.modules.file.service import service as files
from app.modules.user_profile.service import service as users
from app.modules.user_profile.schemas import UserListQuery
from . import employee_mcp_repository as repo, repository
from .employee_mcp_models import EmployeeUser, EmployeeExpenseRequest, EmployeeExpenseFile, EmployeeExpenseInvoice
from .reimbursement_files import SCENE, BUSINESS_TYPE
from .employee_mcp_manifest import manifest_hash

SELF_PERMISSION = "sample_app:reimbursement:self"


def normalize_party_name(value: str) -> str:
    """发票抬头与组织名称比对：忽略空白，并把全角括号折成半角。"""
    return "".join(value.replace("（", "(").replace("）", ")").split()).casefold()


def expense_org_for_title(rows, title: str):
    wanted = normalize_party_name(title)
    if not wanted:
        return None
    matched = [row for row in rows if normalize_party_name(row.org_name) == wanted]
    return matched[0] if len(matched) == 1 else None


def authorize(user):
    if "sample_app" not in user.enabled_plugin_keys or SELF_PERMISSION not in user.permissions:
        raise AppException("未开通快盒员工报销权限", status_code=403)


async def identity(session, user):
    authorize(user)
    bindings = await repo.current_binding(session, user.user_id, lock=True)
    if len(bindings) != 1:
        raise AppException("请管理员在快盒管理端的“内部员工”页面维护唯一的员工账号绑定", status_code=403)
    binding = bindings[0]
    person = await repo.active_employee(session, binding.employee_id)
    if person is None or person.org_id != binding.org_id or person.personnel_type_code != "internal":
        raise AppException("本人名册关联已失效，请联系管理员", status_code=403)
    ensure_org_access(user, binding.org_id, SELF_PERMISSION)
    if await repo.own_org_name(session, binding.org_id) is None:
        raise AppException("本人关联的企业已停用或不存在", status_code=403)
    return person


def authorize_binding_admin(admin):
    if "sample_app:access" not in admin.permissions or "user_profile:detail" not in admin.permissions:
        raise AppException("无权维护员工账号关联", status_code=403)


async def binding_accounts(admin, keyword=""):
    authorize_binding_admin(admin)
    if "user_profile:list" not in admin.permissions:
        raise AppException("无权查询可关联账号", status_code=403)
    result = await users.list(UserListQuery(page=1, page_size=100, is_active=True, keyword=keyword or None), admin)
    return [{"id": row["id"], "name": row["full_name"] or row["display_name"], "org_name": row.get("org_name", "")} for row in result["items"] if row.get("account_is_active", True)]


async def bindings(admin):
    authorize_binding_admin(admin)
    async with get_session_context() as session:
        rows = await repo.visible_bindings(session, admin)
    result = []
    for binding, employee_name in rows:
        account = await users.detail(str(binding.user_id), admin)
        result.append({"employee_id": str(binding.employee_id), "employee_name": employee_name,
                       "user_id": str(binding.user_id), "account_name": (account.full_name or account.display_name) if account else "账号不可见或已删除",
                       "is_active": bool(account and account.is_active and getattr(account, "account_is_active", True)), "org_id": str(binding.org_id)})
    return result


async def bind_account(admin, user_id, employee_id, previous_user_id=None):
    authorize_binding_admin(admin)
    target = await users.detail(str(user_id), admin)
    if target is None or not target.is_active or not getattr(target, "account_is_active", True):
        raise AppException("账号不存在、已停用或不可访问", status_code=403)
    try:
        async with get_session_context() as session:
            person = await repo.active_employee(session, employee_id)
            if person is None or person.personnel_type_code != "internal":
                raise AppException("只能绑定内部员工", status_code=422)
            ensure_org_access(admin, person.org_id, "sample_app:access")
            # 一个账号当前只绑定一位员工；换绑保留历史。
            # 按账号稳定顺序加锁，换绑同时结束旧账号/旧员工的关联。
            locked = {}
            for identity_id in sorted({user_id, *([previous_user_id] if previous_user_id else [])}, key=str):
                locked[identity_id] = await repo.current_binding(session, identity_id, lock=True)
            current = locked[user_id]
            previous = locked.get(previous_user_id, []) if previous_user_id and previous_user_id != user_id else []
            for old in current:
                ensure_org_access(admin, old.org_id, "sample_app:access")
            if len(current) == 1 and current[0].employee_id == employee_id:
                return {"user_id": str(user_id), "employee_id": str(employee_id)}
            if previous_user_id and previous_user_id != user_id and (len(previous) != 1 or previous[0].employee_id != employee_id):
                raise AppException("原关联已变化，请刷新后重新操作", status_code=409)
            for old in previous:
                ensure_org_access(admin, old.org_id, "sample_app:access")
            now = utc_now()
            for old in [*current, *previous]:
                old.valid_to, old.updated_at, old.updated_by = now, now, admin.user_id
                session.add(old)
            await session.flush()
            await repo.insert(session, EmployeeUser(org_id=person.org_id, user_id=user_id, employee_id=employee_id,
                              valid_from=now, created_by=admin.user_id, updated_by=admin.user_id))
            await session.commit()
    except IntegrityError:
        raise AppException("该账号或员工已有当前关联，请刷新后核对", status_code=409) from None
    return {"user_id": str(user_id), "employee_id": str(employee_id)}


async def unbind_account(admin, user_id, employee_id):
    authorize_binding_admin(admin)
    async with get_session_context() as session:
        current = await repo.current_binding(session, user_id, lock=True)
        if not current:
            return {"unbound": False}
        if len(current) != 1 or current[0].employee_id != employee_id:
            raise AppException("关联已变化，请刷新后重新操作", status_code=409)
        row = current[0]
        ensure_org_access(admin, row.org_id, "sample_app:access")
        row.valid_to, row.updated_at, row.updated_by = utc_now(), utc_now(), admin.user_id
        session.add(row)
        await session.commit()
        return {"unbound": True}


def summary(row, attachments=()):
    return {"request_id": str(row.id), "subject": row.subject, "amount": str(row.amount),
            "occurred_on": row.occurred_on.isoformat(), "org_id": str(row.org_id),
            "expires_at": row.expires_at.isoformat(), "approved": row.approved_at is not None,
            "reimbursement_id": str(row.reimbursement_id) if row.reimbursement_id else None,
            "attachments": list(attachments), "source": row.source_code,
            "request_status": row.status_code,
            "previous_request_id": str(row.previous_request_id) if row.previous_request_id else None}


async def request_in_session(session, user, request_id, *, allow_result=True, allow_inactive=False):
    person = await identity(session, user)
    row = await repo.own_request(session, user.user_id, request_id)
    if row is None:
        raise AppException("本人报销申请不存在", status_code=404)
    if row.employee_id != person.id:
        raise AppException("人员关联已经变化，请重新准备报销", status_code=409)
    if await repo.own_org_name(session, row.org_id) is None:
        raise AppException("费用企业已停用或不存在，请重新准备报销", status_code=409)
    if not allow_inactive and row.status_code == "superseded":
        raise AppException("本次申请已失效，请使用重新准备后的申请", status_code=409)
    if not allow_inactive and not (allow_result and row.reimbursement_id) and row.expires_at <= utc_now():
        raise AppException("报销申请已过期，请重新准备", status_code=410)
    return row


def invoice_data(row):
    return {key: getattr(row, key) for key in ("file_name", "content_type", "file_size", "content_md5")}


def preparing_only(row):
    if row.status_code != "preparing" or row.approved_at or row.reimbursement_id:
        raise AppException("申请已进入只读核对或已失效，不能再更改发票；请整体重新准备", status_code=409)


async def verified_invoices(session, user, row):
    expected = await repo.invoice_manifest(session, row.id)
    links = await repo.request_files(session, row.id)
    ids = [link.file_id for link in links]
    if (not expected or not row.invoice_manifest_hash or len(expected) != len(ids)
            or {item.file_id for item in expected} != set(ids)):
        raise AppException("原定发票尚未全部上传或已变化，请重新准备申请", status_code=409)
    actual = await files.pending_items(session, ids, user=user, scene_code=SCENE, include_integrity=True)
    if (manifest_hash(actual) != row.invoice_manifest_hash
            or {tuple(invoice_data(item).values()) for item in expected}
            != {tuple(item[key] for key in ("file_name", "content_type", "file_size", "content_md5")) for item in actual}):
        raise AppException("实际发票与准备时声明的清单不同，请重新准备申请", status_code=409)
    return links


async def prepare(user, body, *, source="mcp"):
    authorize(user)
    if not body.subject or not body.subject.strip():
        return {"status": "needs_input", "missing_fields": ["subject"], "question": "这批发票用于什么事项？请提供报销事由。"}
    missing = [key for key in ("amount", "occurred_on") if getattr(body, key) is None]
    if missing:
        question = ("请确认报销金额和费用发生日期。" if source == "manual"
                    else "请确认报销金额、费用发生日期，以及从发票购买方原文抄录的抬头。")
        return {"status": "needs_input", "missing_fields": missing, "question": question}
    if not body.files:
        return {"status": "needs_input", "missing_fields": ["files"], "question": "请提供本次完整发票原件清单；无法上传时请在员工端新建手动报销。"}
    descriptions = [item.model_dump() for item in body.files]
    fingerprint = manifest_hash(descriptions)
    if len({item["content_md5"] for item in descriptions}) != len(descriptions):
        raise AppException("同一份发票原件不能重复提交", status_code=422)
    if body.invoice_manifest_hash and fingerprint != body.invoice_manifest_hash:
        raise AppException("发票清单与声明的摘要不一致，请重新准备", status_code=422)
    if source not in {"manual", "mcp"}:
        raise AppException("不支持的报销来源", status_code=422)
    if source != "manual" and not (body.invoice_title and body.invoice_title.strip()):
        return {"status": "needs_input", "missing_fields": ["invoice_title"],
                "question": "请从发票购买方原文抄录抬头。"}
    try:
        async with get_session_context() as session:
            person = await identity(session, user)
            if source == "manual":
                expense_org_id = person.org_id
            else:
                expense = expense_org_for_title(await repo.active_org_names(session), body.invoice_title)
                if expense is None:
                    return {"status": "needs_input", "missing_fields": ["invoice_title"],
                            "question": "发票抬头没有对应到唯一的启用组织。请把组织名称改为与发票购买方全称一致后再试。"}
                expense_org_id = expense.id
            row = await repo.request_by_key(session, user.user_id, body.request_key)
            if row is not None:
                declared = await repo.invoice_manifest(session, row.id)
                if (row.employee_id != person.id or row.org_id != expense_org_id or row.subject != body.subject.strip()
                        or row.amount != body.amount or row.occurred_on != body.occurred_on
                        or row.invoice_manifest_hash != fingerprint or row.source_code != source
                        or row.previous_request_id != body.previous_request_id
                        or sorted(tuple(invoice_data(item).values()) for item in declared)
                        != sorted(tuple(item.values()) for item in descriptions)):
                    raise AppException("幂等标识已用于另一份内容，请使用新的标识", status_code=409)
                if row.expires_at <= utc_now() and not row.reimbursement_id:
                    raise AppException("申请已过期，请使用新的幂等标识", status_code=410)
                if row.status_code in {"superseded", "legacy"} and not row.reimbursement_id:
                    raise AppException("旧申请已失效，请重新准备并使用新的幂等标识", status_code=409)
            else:
                previous = None
                if body.previous_request_id:
                    previous = await request_in_session(session, user, body.previous_request_id, allow_inactive=True)
                    if (previous.source_code != source or previous.reimbursement_id
                            or previous.status_code not in {"preparing", "ready", "approved", "superseded"}):
                        raise AppException("只能整体重新准备同一来源的本人未提交申请", status_code=409)
                    if await repo.next_request(session, previous.id) is not None:
                        raise AppException("该申请已有新版本，请打开最新版本修改", status_code=409)
                    previous.status_code, previous.updated_at, previous.updated_by = "superseded", utc_now(), user.user_id
                    session.add(previous)
                row = await repo.insert(session, EmployeeExpenseRequest(org_id=expense_org_id, user_id=user.user_id,
                    employee_id=person.id, request_key=body.request_key, subject=body.subject.strip(), amount=body.amount,
                    invoice_manifest_hash=fingerprint, source_code=source, status_code="preparing",
                    previous_request_id=body.previous_request_id,
                    occurred_on=body.occurred_on, expires_at=utc_now() + timedelta(hours=24),
                    created_by=user.user_id, updated_by=user.user_id))
                for item in descriptions:
                    await repo.insert(session, EmployeeExpenseInvoice(org_id=expense_org_id, request_id=row.id,
                        **item, created_by=user.user_id, updated_by=user.user_id))
                await session.commit()
            return {"status": row.status_code, **summary(row)}
    except IntegrityError:
        # 并发创建由唯一约束保护；客户端使用同一 key 重试即可读取原申请。
        raise AppException("同一申请正在准备，请使用相同标识重试", status_code=409) from None


async def recent_requests(user, *, page: int = 1, page_size: int = 20):
    """员工门户费用报销：待提交申请始终附带；正式报销单后端分页。"""
    page = max(1, int(page or 1))
    page_size = min(100, max(1, int(page_size or 20)))
    async with get_session_context() as session:
        person = await identity(session, user)
        drafts = await repo.own_recent_requests(session, user.user_id, person.id, person.org_id)
        total, receipts = await repo.page_own_reimbursements(
            session, person.id, page=page, page_size=page_size)
        draft_items = []
        for row in drafts:
            state = "awaiting_confirmation" if row.status_code == "ready" else row.status_code
            draft_items.append({"request_id": str(row.id), "subject": row.subject, "amount": str(row.amount),
                                "occurred_on": row.occurred_on.isoformat(), "status": state,
                                "reimbursement_id": None, "source": row.source_code})
        items = [reimbursement_data(row) for row in receipts]
        # 首页第一页把待确认申请放在正式单据前面，便于本人继续处理。
        if page == 1:
            items = draft_items + items
        return {"employee_name": person.full_name, "org_name": await repo.own_org_name(session, person.org_id),
                "items": items, "drafts": draft_items, "total": total, "page": page, "page_size": page_size}


def reimbursement_data(row):
    """正式单据展示只取正式表，不从准备申请复制金额、事由或状态。"""
    return {"request_id": None, "reimbursement_id": str(row.id), "subject": row.subject,
            "amount": str(row.amount), "occurred_on": row.occurred_on.isoformat(),
            "status": row.status_code, "org_id": str(row.org_id)}


async def reimbursement_detail_in_session(session, person, result):
    bound = await files.list_for_business(session, BUSINESS_TYPE, [result.id], scene_code=SCENE)
    attachments = [{"id": str(item.id), "file_name": item.original_file_name,
                    "file_size": item.file_size, "content_type": item.content_type} for item in bound]
    return {**reimbursement_data(result), "attachments": attachments, "employee_name": person.full_name,
            "org_name": await repo.own_org_name(session, result.org_id)}


async def reimbursement_detail(user, reimbursement_id):
    async with get_session_context() as session:
        person = await identity(session, user)
        result = await repo.own_reimbursement(session, person.id, reimbursement_id)
        if result is None:
            raise AppException("本人报销单不存在", status_code=404)
        return await reimbursement_detail_in_session(session, person, result)


async def detail(user, request_id):
    async with get_session_context() as session:
        row = await request_in_session(session, user, request_id, allow_inactive=True)
        if row.reimbursement_id:
            result = await repo.own_result(session, row, user)
            if result is None:
                raise AppException("本人报销结果不存在", status_code=404)
            person = await repo.active_employee(session, row.employee_id)
            return {**summary(row), **await reimbursement_detail_in_session(session, person, result),
                    "request_id": str(row.id)}
        inactive = row.status_code in {"superseded", "legacy"} or row.expires_at <= utc_now()
        links = await repo.request_files(session, row.id) if not inactive else []
        items = await files.pending_items(session, [link.file_id for link in links], user=user, scene_code=SCENE, include_integrity=True) if links else []
        person = await repo.active_employee(session, row.employee_id)
        state = row.status_code if row.status_code != "ready" else "awaiting_confirmation"
        if row.expires_at <= utc_now() and row.status_code != "superseded":
            state = "expired"
        return {**summary(row, items), "status": state,
                "employee_name": person.full_name, "org_name": await repo.own_org_name(session, row.org_id)}


async def revise_manual(user, request_id):
    """回到完整填写页前先使旧版本失效；已提交的真实报销不允许修订。"""
    async with get_session_context() as session:
        row = await request_in_session(session, user, request_id, allow_inactive=True)
        if (row.source_code != "manual" or row.reimbursement_id
                or row.status_code not in {"preparing", "ready", "approved", "superseded"}):
            raise AppException("只有本人手动创建且尚未提交的申请可以返回修改；MCP申请请让AI整体重新准备", status_code=409)
        if await repo.next_request(session, row.id) is not None:
            raise AppException("旧申请已有新版本，请打开最新版本修改", status_code=409)
        row.status_code, row.updated_at, row.updated_by = "superseded", utc_now(), user.user_id
        session.add(row)
        await session.commit()
        return summary(row)


async def upload_tickets(user, request_id, descriptions):
    async with get_session_context() as session:
        row = await request_in_session(session, user, request_id, allow_result=False)
        preparing_only(row)
        declared = await repo.invoice_manifest(session, row.id)
        by_digest = {item.content_md5: item for item in declared}
        if len({item.content_md5 for item in descriptions}) != len(descriptions):
            raise AppException("不能重复申请同一份发票的上传票据", status_code=422)
        for item in descriptions:
            expected = by_digest.get(item.content_md5)
            if expected is None or invoice_data(expected) != item.model_dump():
                raise AppException("只能上传准备时已声明的原件，增删或替换发票须整体重新准备", status_code=409)
        links = await repo.request_files(session, row.id)
        if len(links) + len(descriptions) > 50:
            raise AppException("每单最多50份发票", status_code=422)
        completed = {link.file_id for link in links}
        if any(by_digest[item.content_md5].file_id in completed for item in descriptions):
            raise AppException("原件已经完成上传，请刷新申请后继续，不要重复追加", status_code=409)
        # 每个票据由公共文件服务保存；在声明清单上记住所属票据，拒绝跨申请或旧票据混入。
        tickets = []
        for item in descriptions:
            ticket = await files.create_upload_ticket(scene_code=SCENE, user=user, **item.model_dump())
            expected = by_digest[item.content_md5]
            expected.file_id, expected.updated_at, expected.updated_by = UUID(str(ticket["id"])), utc_now(), user.user_id
            session.add(expected)
            tickets.append(ticket)
        await session.commit()
        return tickets


async def complete_upload(user, request_id, file_id):
    async with get_session_context() as session:
        row = await request_in_session(session, user, request_id, allow_result=False)
        links = await repo.request_files(session, row.id)
        if file_id in [link.file_id for link in links] and row.status_code in {"preparing", "ready", "approved"}:
            return {"file_id": str(file_id), "attached": True, "reused": True}
        preparing_only(row)
        expected = next((item for item in await repo.invoice_manifest(session, row.id) if item.file_id == file_id), None)
        if expected is None:
            raise AppException("此文件不是本次预定清单的有效上传票据，请重新准备", status_code=409)
        await files.complete_upload(file_id, user)
        uploaded = await files.pending_items(session, [file_id], user=user, scene_code=SCENE, include_integrity=True)
        if not uploaded or any(uploaded[0].get(key) != value for key, value in invoice_data(expected).items()):
            raise AppException("上传原件与预定清单不一致，请重新准备", status_code=409)
        await repo.insert(session, EmployeeExpenseFile(org_id=row.org_id, request_id=row.id, file_id=file_id,
                          created_by=user.user_id, updated_by=user.user_id))
        declared = await repo.invoice_manifest(session, row.id)
        if len(links) + 1 == len(declared):
            await verified_invoices(session, user, row)
            row.status_code, row.updated_at, row.updated_by = "ready", utc_now(), user.user_id
            session.add(row)
        await session.commit()
        return {"file_id": str(file_id), "attached": True}


async def approve(user, request_id):
    """只能由正常登录页面调用；MCP 凭证不得调用此动作。"""
    async with get_session_context() as session:
        row = await request_in_session(session, user, request_id)
        if row.reimbursement_id:
            return summary(row)
        if row.status_code not in {"ready", "approved"}:
            raise AppException("只有完整清单上传后的只读申请可以确认，请先整体重新准备", status_code=409)
        await verified_invoices(session, user, row)
        if row.approved_at:
            return summary(row)
        row.status_code = "approved"
        row.approved_at, row.updated_at, row.updated_by = utc_now(), utc_now(), user.user_id
        session.add(row)
        await session.commit()
        return summary(row)


async def submit(user, request_id):
    async with get_session_context() as session:
        row = await request_in_session(session, user, request_id)
        if row.reimbursement_id:
            result = await repo.own_result(session, row, user)
            if result is None:
                raise AppException("本人报销结果不存在", status_code=404)
            return {"reimbursement_id": str(result.id), "status": result.status_code, "amount": str(result.amount), "replayed": True}
        if row.approved_at is None:
            if row.status_code != "ready":
                raise AppException("本次预定清单尚未准备完整，请完成上传或重新准备", status_code=409)
            return {"status": "needs_confirmation", "request_id": str(row.id), "message": "请本人在登录页面只读核对完整发票、金额与事由并确认。"}
        if row.status_code != "approved":
            raise AppException("申请状态已变化，请使用最新的申请", status_code=409)
        links = await verified_invoices(session, user, row)
        result = await repository.add_reimbursement(session, row.org_id, {"employee_id": row.employee_id,
                    "amount": row.amount, "subject": row.subject, "occurred_on": row.occurred_on,
                    "status_code": "submitted"}, user.user_id)
        await files.bind(session, [link.file_id for link in links], user=user, org_id=row.org_id,
                         scene_code=SCENE, business_type_code=BUSINESS_TYPE, business_id=result.id)
        row.reimbursement_id, row.updated_by, row.updated_at = result.id, user.user_id, utc_now()
        row.status_code = "submitted"
        session.add(row)
        await session.commit()
        return {"reimbursement_id": str(result.id), "status": result.status_code, "amount": str(result.amount),
                "attachment_count": len(links), "replayed": False}


async def can_read_own_reimbursement(session, user, reimbursement_id):
    if "sample_app" not in user.enabled_plugin_keys or SELF_PERMISSION not in user.permissions:
        return False
    try:
        person = await identity(session, user)
    except AppException:
        return False
    # 明确本人报销关联契约，不向其他模块暴露任意查询。
    return await repo.own_reimbursement(session, person.id, reimbursement_id) is not None


async def _password_policy(session) -> tuple[int, int]:
    """读取租户安全参数；缺省与底座默认一致。"""
    from sqlmodel import select
    from app.modules.system_setting.models import SysSetting
    rows = {row.setting_key: row.setting_value for row in (await session.exec(
        select(SysSetting).where(SysSetting.setting_key.in_(["password_min_length", "password_history_count"]),
                                 SysSetting.deleted_at.is_(None)))).all()}
    try:
        min_length = max(6, int(rows.get("password_min_length") or 8))
    except (TypeError, ValueError):
        min_length = 8
    try:
        history_count = max(0, int(rows.get("password_history_count") or 3))
    except (TypeError, ValueError):
        history_count = 3
    return min_length, history_count


async def change_password(user, body):
    """本人改密；成功后吊销全部刷新会话，门户需重新登录。"""
    authorize(user)
    if body.new_password != body.confirm_password:
        raise AppException("两次输入的新密码不一致", status_code=422)
    from app.core.runtime import online_user_registry
    from app.integrations import user_auth
    async with get_session_context() as session:
        await identity(session, user)
        min_length, history_count = await _password_policy(session)
        await user_auth.change_own_password(
            session, user.auth_user_id, body.current_password, body.new_password,
            min_length=min_length, history_count=history_count)
        await session.commit()
    await online_user_registry.kick_user(user.auth_user_id)
    return {"status": "needs_login", "message": "密码已更新，请使用新密码重新登录。"}
