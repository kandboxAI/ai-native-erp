"""跟单宝工艺分页导入；仅解析数据，不移植来源系统权限或自动库存规则。"""
import hashlib
import json
from pathlib import Path
from uuid import UUID

from app.auth.scope_filters import resolve_write_org_id
from app.core.exceptions import AppException
from app.framework.db.models import utc_now
from .archive_models import MesProcess
from .archive_repository import archive_repository
from .external_import_service import stable_number
from .process_archive_import_repository import repository


PROCESSING = {"SELF_MADE": "in_house", "OUTSOURCE": "outsourced", "QC": "in_house"}


def read_pages(paths):
    """严格校验完整分页、重复来源编号和不支持的业务语义。"""
    pages, files = {}, []
    for path in map(Path, paths):
        raw = path.read_bytes()
        response = json.loads(raw.decode("utf-8-sig"))
        if response.get("success") is not True:
            raise ValueError("来源工艺接口未返回成功结果")
        data = response["data"]
        page = data["number"]
        if type(page) is not int or page < 0 or page in pages:
            raise ValueError("分页编号无效或重复")
        pages[page] = data
        files.append(dict(file_name=path.name, sha256=hashlib.sha256(raw).hexdigest(), page=page))
    if not pages:
        raise ValueError("请选择完整的工艺分页文件")
    first = pages[min(pages)]
    total, size, count = first["totalPages"], first["size"], first["totalElements"]
    if any(type(value) is not int or value <= 0 for value in (total, size, count)):
        raise ValueError("分页总数、容量或记录总数无效")
    if set(pages) != set(range(total)):
        raise ValueError("工艺分页缺失")
    rows = []
    for page, data in sorted(pages.items()):
        if (data["totalPages"], data["size"], data["totalElements"]) != (total, size, count):
            raise ValueError("各页总数或分页容量不一致")
        expected = min(size, count - page * size)
        if expected <= 0 or len(data["content"]) != expected or data["hasNext"] != (page < total - 1):
            raise ValueError("分页条数或末页标记不一致")
        rows.extend(data["content"])
    if len(rows) != count:
        raise ValueError("工艺总数不完整")
    for field in ("recordId", "code", "name"):
        values = [row.get(field) for row in rows]
        if any(not isinstance(value, str) or not value.strip() or value != value.strip() for value in values):
            raise ValueError(f"工艺 {field} 缺失或格式不正确")
        if len(set(values)) != len(values):
            raise ValueError(f"工艺 {field} 重复，不能自动合并")
    for row in rows:
        UUID(row["recordId"])  # 仅校验外部标识，绝不作为内部主键。
        if len(row["code"]) > 64 or len(row["name"]) > 128:
            raise ValueError("工艺编号或名称过长")
        if row["processingType"] not in PROCESSING or row["enableStatus"] not in {"ENABLE", "DISABLE"}:
            raise ValueError("未知加工类型或启停状态")
        if type(row["piecework"]) is not bool or type(row["disabled"]) is not bool:
            raise ValueError("计件或停用标记格式不正确")
        if row["disabled"] != (row["enableStatus"] == "DISABLE"):
            raise ValueError("来源启停标记互相矛盾")
        if any(row.get(field) for field in ("previousCraftList", "nextCraftList", "previousCraftItemList", "nextCraftItemList")):
            raise ValueError("来源包含工艺前后置关系，需先明确映射；未自动忽略")
        if len(str(row.get("remark") or "")) > 3500:
            raise ValueError("来源工艺备注过长")
    return rows, files


def archive_values(row):
    return dict(process_name=row["name"], processing_type_code=PROCESSING[row["processingType"]],
        is_piecework=row["piecework"], is_quality_required=row["processingType"] == "QC",
        is_active=row["enableStatus"] == "ENABLE", sort_no=0,
        description="\n".join(filter(None, (f"跟单宝工艺档案；来源编号：{row['recordId']}", row.get("remark")))))


class ProcessArchiveImportService:
    def authorize(self, user, org_id):
        if "mes" not in user.enabled_plugin_keys:
            raise AppException("目标租户未启用 MES", 403)
        for key in ("mes:archive:process:manage", "mes:process_template:manage", "mes:work_order:manage"):
            if key not in user.permissions:
                raise AppException(f"工艺导入需要权限：{key}", 403)
            resolve_write_org_id(user, org_id, key)

    async def plan(self, session, rows, user, org_id):
        self.authorize(user, org_id)
        masters = await repository.processes(session, user, org_id)
        by_no = {row.process_no: row for row in masters}
        by_name = {row["name"]: row for row in rows}
        existing = {}
        for raw in rows:
            found = by_no.get(raw["code"])
            if found:
                # 不能接管同编号的手工档案，也不能覆盖导入后的人工维护。
                if any(getattr(found, field) != value for field, value in archive_values(raw).items()):
                    raise AppException(f"工艺 {raw['code']} 已存在或已人工修改，未覆盖", 409)
                existing[raw["code"]] = found
        sources = await repository.route_sources(session, user, org_id)
        operations = {row.id: row for row in await repository.template_operations(session, user, org_id)}
        derived, links = {}, []
        for source in sources:
            values = source.source_values_snapshot
            name = str(values.get("工艺") or "").strip()
            if name not in by_name:
                raise AppException(f"来源路线中的工艺“{name}”未在正式工艺档案中找到", 409)
            operation = operations.get(source.template_operation_id)
            if not operation or operation.operation_name != name:
                raise AppException("原导入路线已删除、改名或超出权限，需先核对", 409)
            legacy_no = stable_number("GDB-PR-", [name, str(values.get("项目阶段") or "").strip(),
                str(values.get("加工类型") or "").strip(), str(values.get("计件工艺") or "").strip()])
            old = by_no.get(legacy_no)
            target = existing.get(by_name[name]["code"])
            if target and operation.process_id == target.id:
                if old: derived[old.id] = old
                continue
            if not old or operation.process_id != old.id:
                raise AppException("原导入路线工艺关联已人工修改，未覆盖", 409)
            derived[old.id] = old
            links.append((operation, by_name[name]["code"]))
        # 只允许替换有原始 Excel 追溯的模板引用；任何执行/设备/依赖或额外模板引用均阻止停用。
        allowed = {source.template_operation_id for source in sources}
        await repository.check_references(session, derived, allowed)
        return existing, derived, links

    async def preview(self, session, rows, user, org_id):
        existing, derived, links = await self.plan(session, rows, user, org_id)
        return dict(source_processes=len(rows), new_processes=len(rows) - len(existing),
            route_operations_to_link=len(links), legacy_processes_to_deactivate=sum(p.is_active for p in derived.values()))

    async def apply(self, session, rows, user, org_id):
        self.authorize(user, org_id)
        await archive_repository.lock_organization(session, org_id)
        await repository.lock_import(session, org_id)
        existing, derived, links = await self.plan(session, rows, user, org_id)
        now = utc_now()
        result = dict(source_processes=len(rows), new_processes=len(rows) - len(existing),
            route_operations_linked=len(links), legacy_processes_deactivated=0)
        for raw in rows:
            if raw["code"] not in existing:
                entry = MesProcess(org_id=org_id, process_no=raw["code"], **archive_values(raw),
                    created_by=user.user_id, updated_by=user.user_id)
                repository.add(session, entry)
                existing[raw["code"]] = entry
        await session.flush()
        changed_templates = set()
        for operation, code in links:
            operation.process_id = existing[code].id
            operation.updated_at, operation.updated_by = now, user.user_id
            changed_templates.add(operation.template_id)
        for template in await repository.templates(session, user, org_id):
            if template.id in changed_templates:
                template.version_no += 1
                template.updated_at, template.updated_by = now, user.user_id
        for old in derived.values():
            if old.is_active:
                old.is_active = False
                old.version_no += 1
                old.updated_at, old.updated_by = now, user.user_id
                result["legacy_processes_deactivated"] += 1
        await session.flush()
        return result


service = ProcessArchiveImportService()
