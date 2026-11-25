from pydantic import ValidationError
from app.auth.scope_filters import resolve_write_org_id
from app.core.exceptions import AppException
from app.framework.db.models import utc_now
from app.framework.db.session import get_session_context
from .archive_models import MesCustomer, MesProjectStage, MesProcess, MesEquipment, MesProcessRequirement
from .archive_schemas import ArchiveBody, CustomerBody, EquipmentBody, ProcessBody, RequirementBody, ArchiveQuery
from .archive_repository import archive_repository as repo

# 明确白名单，不从请求导入模型或拼接表名。
ARCHIVES = {
    "customers": (MesCustomer, "customer_no", "customer_name", "customer", CustomerBody),
    "project-stages": (MesProjectStage, "stage_no", "stage_name", "stage", ArchiveBody),
    "processes": (MesProcess, "process_no", "process_name", "process", ProcessBody),
    "equipment": (MesEquipment, "equipment_no", "equipment_name", "equipment", EquipmentBody),
    "requirements": (MesProcessRequirement, "requirement_no", "requirement_name", "requirement", RequirementBody),
}


def permission(kind, action):
    if kind not in ARCHIVES: raise AppException("不支持的制造档案类型", 422)
    return f"mes:archive:{ARCHIVES[kind][3]}:{action}"


def require(user, key):
    if key not in user.permissions: raise AppException("缺少该档案的操作权限", 403)


def validate_graph(graph, identifier, previous):
    graph[identifier] = set(previous)
    visited, pending = set(), list(previous)
    while pending:
        current = pending.pop()
        if current == identifier: raise AppException("前置工艺不能自引用或形成循环", 409)
        if current in visited: continue
        visited.add(current)
        pending.extend(graph.get(current, ()))


class ArchiveService:
    async def item(self, session, kind, row):
        spec = ARCHIVES[kind]
        result = row.model_dump(exclude={"deleted_at", "deleted_by", "flex_form"})
        result["record_no"], result["record_name"] = result.pop(spec[1]), result.pop(spec[2])
        if kind == "equipment":
            result["process_ids"] = await repo.equipment_process_ids(session, row)
            result["process_labels"] = {}
            for identifier in result["process_ids"]:
                process = await repo.get(session, MesProcess, identifier)
                if process and process.org_id == row.org_id:
                    result["process_labels"][str(identifier)] = f"{process.process_no} · {process.process_name}"
            result["process_label"] = "、".join(result["process_labels"].values())
        if kind == "processes":
            result["previous_process_ids"] = [entry.previous_process_id for entry in await repo.dependencies(session, row.org_id) if entry.process_id == row.id]
            labels = {}
            for identifier in result["previous_process_ids"]:
                previous = await repo.get(session, MesProcess, identifier)
                if previous and previous.org_id == row.org_id: labels[str(identifier)] = f"{previous.process_no} · {previous.process_name}"
            result["previous_process_labels"] = labels
            result["previous_process_names"] = "、".join(labels.values())
        for key, target in (("project_stage_id", MesProjectStage), ("process_id", MesProcess), ("requirement_id", MesProcessRequirement)):
            if getattr(row, key, None):
                reference = await repo.get(session, target, getattr(row, key))
                field = {MesProjectStage: "stage_name", MesProcess: "process_name", MesProcessRequirement: "requirement_name"}[target]
                if reference and reference.org_id == row.org_id: result[key.removesuffix("_id") + "_label"] = getattr(reference, field)
        return result

    async def page(self, kind, query, user):
        key = permission(kind, "list")
        require(user, key)
        async with get_session_context() as session:
            rows, total = await repo.page(session, ARCHIVES[kind], query, user, key)
            return dict(items=[await self.item(session, kind, row) for row in rows], total=total, page=query.page, page_size=query.page_size)

    async def reference(self, session, model, identifier, org_id, *, allow_inactive=False):
        if identifier is None: return None
        row = await repo.get(session, model, identifier)
        if row is None or row.org_id != org_id or not row.is_active and not allow_inactive:
            raise AppException("关联档案不存在、已停用或不属于当前组织", 409)
        return row

    async def save(self, kind, values, user, identifier=None):
        key = permission(kind, "manage")
        require(user, key)
        spec = ARCHIVES[kind]
        try: body = spec[4].model_validate(values)
        except ValidationError as error: raise AppException("档案字段不完整或格式不正确，请核对编号、名称和关联项", 422) from error
        org_id = resolve_write_org_id(user, body.org_id, key)
        async with get_session_context() as session:
            await repo.lock_organization(session, org_id)
            row = await repo.get(session, spec[0], identifier, user=user, permission=key) if identifier else None
            if identifier:
                if row is None: raise AppException("档案不存在或无权修改", 404)
                if row.org_id != org_id or getattr(row, spec[1]) != body.record_no: raise AppException("档案的组织和编号不能变更", 409)
                if row.version_no != body.version_no: raise AppException("档案已更新，请刷新后重试", 409)
            else:
                if await repo.number_exists(session, spec, org_id, body.record_no): raise AppException("同一组织中档案编号已存在", 409)
                row = spec[0](org_id=org_id, **{spec[1]: body.record_no}, created_by=user.user_id, updated_by=user.user_id)
            for field, model in (("project_stage_id", MesProjectStage), ("requirement_id", MesProcessRequirement), ("process_id", MesProcess)):
                value = getattr(body, field, None)
                await self.reference(session, model, value, org_id, allow_inactive=bool(identifier and getattr(row, field, None) == value))
            if kind == "processes":
                if body.is_equipment_required is False and await repo.has_active_equipment(session,row.id):
                    raise AppException("该工艺仍关联启用设备，请先在设备档案移除关联，再确认不占用本厂机器",409)
                for previous in body.previous_process_ids: await self.reference(session, MesProcess, previous, org_id)
                graph = {}
                for edge in await repo.dependencies(session, org_id): graph.setdefault(edge.process_id, set()).add(edge.previous_process_id)
                validate_graph(graph, row.id, body.previous_process_ids)
            process_ids = None
            if kind == "equipment":
                process_ids = body.process_ids if body.process_ids is not None else ([body.process_id] if body.process_id else [])
                if body.process_ids is not None and body.process_id and body.process_id not in process_ids:
                    raise AppException("设备的适用工艺与原单工艺字段不一致", 422)
                current_process_ids = await repo.equipment_process_ids(session, row) if identifier else []
                for process_identifier in process_ids:
                    process=await self.reference(session, MesProcess, process_identifier, org_id,
                        allow_inactive=process_identifier in current_process_ids)
                    if process.is_equipment_required is False:raise AppException("不占用本厂机器的工艺不能绑定加工设备",409)
            fields = body.model_dump(exclude={"org_id", "record_no", "record_name", "version_no", "previous_process_ids", "process_ids"})
            if kind=="processes":
                for field in ("is_equipment_required","execution_kind_code"):
                    if field not in body.model_fields_set:fields.pop(field,None)
            for field, value in fields.items(): setattr(row, field, value)
            setattr(row, spec[2], body.record_name)
            if identifier: row.version_no += 1
            row.updated_at, row.updated_by = utc_now(), user.user_id
            repo.add(session, row)
            await session.flush()
            if kind == "processes": await repo.replace_dependencies(session, org_id, row.id, body.previous_process_ids, user.user_id)
            if kind == "equipment": await repo.replace_equipment_processes(session, row, process_ids, user.user_id)
            await session.flush()
            result = await self.item(session, kind, row)
            await session.commit()
            return result

    async def options(self, kind, query, user):
        # 只发布同组织的选用字段，不带定价、审计人或联系人。选用继承来源动作的数据范围。
        own = permission(kind, "manage")
        production = ["mes:work_order:create", "mes:work_order:manage", "mes:process_template:manage"]
        choices = {
            "customers": [own, "mes:work_order:create", "mes:work_order:manage"],
            "project-stages": [own, permission("processes", "manage")],
            "processes": [own, permission("equipment", "manage"), *production, "mes:schedule:list", "mes:schedule:manage"],
            "equipment": [own, *production, "mes:schedule:manage"],
            "requirements": [own, permission("processes", "manage"), *production],
        }[kind]
        key = next((entry for entry in choices if entry in user.permissions), None)
        if key is None: raise AppException("缺少档案选用权限", 403)
        if query.org_id is None: raise AppException("请选择所属组织", 422)
        resolve_write_org_id(user, query.org_id, key)
        query.is_active = True
        async with get_session_context() as session:
            rows, total = await repo.page(session, ARCHIVES[kind], query, user, key)
            fields = () if kind == "customers" else ("description", "project_stage_id", "requirement_id", "process_id", "is_quality_required", "work_center_name", "is_equipment_required", "execution_kind_code")
            if key in {"mes:schedule:list", "mes:schedule:manage"}:
                fields = ("process_id", "work_center_name") if kind == "equipment" else ()
            items = [dict(id=row.id, label=f"{getattr(row, ARCHIVES[kind][1])} · {getattr(row, ARCHIVES[kind][2])}",
                record_no=getattr(row, ARCHIVES[kind][1]), record_name=getattr(row, ARCHIVES[kind][2]),
                **{field: getattr(row, field) for field in fields if hasattr(row, field)}) for row in rows]
            if kind == "processes" and key not in {"mes:schedule:list", "mes:schedule:manage"}:
                dependencies = await repo.dependencies(session, query.org_id)
                row_ids = {row.id for row in rows}
                labels = {}
                for identifier in {edge.previous_process_id for edge in dependencies if edge.process_id in row_ids}:
                    previous = await repo.get(session, MesProcess, identifier)
                    if previous and previous.org_id == query.org_id:
                        labels[identifier] = f"{previous.process_no} · {previous.process_name}"
                for item in items:
                    previous = sorted((edge.previous_process_id for edge in dependencies if edge.process_id == item["id"]), key=str)
                    item["previous_process_ids"] = previous
                    item["previous_process_names"] = "、".join(labels.get(identifier, "不可用的前置工艺") for identifier in previous)
            if kind == "equipment":
                for item, row in zip(items, rows, strict=True):
                    item["process_ids"] = await repo.equipment_process_ids(session, row)
            return dict(items=items, total=total, page=query.page, page_size=query.page_size)


archive_service = ArchiveService()
