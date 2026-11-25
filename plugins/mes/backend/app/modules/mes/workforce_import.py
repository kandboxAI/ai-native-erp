"""已由客户核对的照片人员清单导入；不创建账号、角色、日历或未确认技能。"""
import hashlib
import json
from pathlib import Path

from app.auth.scope_filters import resolve_write_org_id
from app.core.exceptions import AppException
from app.framework.db.models import utc_now
from app.modules.masterdata import service as people
from .archive_repository import archive_repository
from .external_import_models import MesExternalImportRow
from .external_import_parser import SourceRow
from .workforce_models import MesProductionPerson
from .workforce_import_repository import repository


def read_roster(path, photo):
    photo = Path(photo)
    manifest = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    digest = hashlib.sha256(photo.read_bytes()).hexdigest()
    if manifest.get("format_version") != 1 or manifest.get("source_photo_sha256") != digest:
        raise ValueError("人员清单版本或来源照片摘要不一致")
    mapping = manifest.get("confirmed_axis_process_names")
    if not isinstance(mapping, dict) or not mapping or set(mapping) - {"3", "4", "5"}:
        raise ValueError("须明确已由客户确认的三轴/四轴/五轴工艺映射")
    if any(not isinstance(v, str) or not v.strip() for v in mapping.values()) or len(set(mapping.values())) != len(mapping):
        raise ValueError("轴能力对应的工艺名称无效或重复")
    rows = manifest.get("people")
    if not isinstance(rows, list) or not 1 <= len(rows) <= 100:
        raise ValueError("每份人员清单须为1—100人")
    if [r.get("source_row_no") for r in rows] != list(range(1, len(rows) + 1)):
        raise ValueError("来源序号缺失或重复")
    names = []
    result = []
    for row in rows:
        name, title, axes = row.get("full_name"), row.get("job_title"), row.get("axis_capabilities")
        if not isinstance(name, str) or not name.strip() or name != name.strip() or len(name) > 128:
            raise ValueError("姓名缺失或格式无效，须先人工核对")
        if not isinstance(title, str) or len(title) > 128 or not isinstance(axes, list) or len(axes) != len(set(axes)):
            raise ValueError("职务或轴能力格式无效")
        if any(str(axis) not in mapping for axis in axes):
            raise ValueError("轴能力缺少客户确认的工艺映射")
        values = {**row, "confirmed_process_names": [mapping[str(axis)] for axis in axes]}
        result.append(SourceRow("person_roster", f"{digest}:{row['source_row_no']}", photo.name, digest,
            "image.table", row["source_row_no"] + 1, values))
        names.append(name)
    if len(set(names)) != len(names):
        raise ValueError("照片中有同名人员，须先确认人员标识")
    return result


def person_number(row):
    return f"ROSTER-{row.file_hash[:16].upper()}-{row.values['source_row_no']:03d}"


class WorkforceImportService:
    def authorize(self, user, org_id):
        if "mes" not in user.enabled_plugin_keys:
            raise AppException("目标租户未启用 MES", 403)
        for key in ("mes:schedule:manage", "mes:archive:process:manage"):
            if key not in user.permissions:
                raise AppException(f"生产人员导入需要权限：{key}", 403)
            resolve_write_org_id(user, org_id, key)

    async def plan(self, session, rows, user, org_id):
        self.authorize(user, org_id)
        processes = {}
        for process in await repository.processes(session, user, org_id):
            processes.setdefault(process.process_name, []).append(process)
        required = {name for row in rows for name in row.values["confirmed_process_names"]}
        for name in required:
            if len(processes.get(name, [])) != 1:
                raise AppException(f"工艺 {name} 未启用、不存在或不唯一，未猜测人员资格", 409)
        current = {row.id: row for row in await repository.people(session, user, org_id)}
        sources = {row.source_record_no: row for row in await repository.sources(session, user, org_id)}
        new = []
        for row in rows:
            old = sources.get(row.key)
            if old:
                person = current.get(old.production_person_id)
                if old.source_row_sha256 != row.row_hash or not person or person.person_no != person_number(row):
                    raise AppException("来源人员已导入但内容或身份关联变化，未覆盖", 409)
                continue
            if any(person.person_no == person_number(row) for person in current.values()):
                raise AppException("生产人员临时编号已存在，未覆盖", 409)
            new.append(row)
        conflicts = await people.existing_person_names(session, names=[row.values["full_name"] for row in new])
        if conflicts:
            raise AppException("清单姓名与已有人员重名，须先人工确认身份，不能仅按姓名自动合并或重复创建", 409)
        return new, {name: values[0].id for name, values in processes.items() if name in required}

    async def preview(self, session, rows, user, org_id):
        self.authorize(user, org_id)
        missing = await repository.missing(session)
        result = dict(source_people=len(rows), source_qualifications=sum(len(row.values["confirmed_process_names"]) for row in rows), missing_columns=missing)
        if missing:
            return result
        new, _ = await self.plan(session, rows, user, org_id)
        return result | dict(new_people=len(new), new_qualifications=sum(len(row.values["confirmed_process_names"]) for row in new))

    async def apply(self, session, rows, user, org_id):
        self.authorize(user, org_id)
        await archive_repository.lock_organization(session, org_id)
        if await repository.missing(session):
            raise AppException("生产人员和工艺资格结构尚未升级，请先审核执行迁移", 409)
        new, processes = await self.plan(session, rows, user, org_id)
        registered_at = utc_now()
        qualifications = 0
        for row in new:
            master = await people.create_person(session, full_name=row.values["full_name"], mobile=None, actor_id=user.user_id)
            person = MesProductionPerson(org_id=org_id, party_id=master.party_id, person_no=person_number(row),
                job_title_snapshot=row.values["job_title"], created_at=registered_at, created_by=user.user_id, updated_by=user.user_id)
            repository.add(session, person)
            await session.flush()
            for name in row.values["confirmed_process_names"]:
                await repository.add_qualification(session, person, processes[name], registered_at, user.user_id)
                qualifications += 1
            repository.add(session, MesExternalImportRow(org_id=org_id, source_system_key="customer_roster", record_type_key=row.kind,
                source_record_no=row.key, source_file_name=row.file_name, source_file_sha256=row.file_hash,
                source_sheet_name=row.sheet, source_row_no=row.line, source_row_sha256=row.row_hash,
                source_values_snapshot=row.values, production_person_id=person.id, created_at=registered_at,
                created_by=user.user_id, updated_by=user.user_id))
        await session.flush()
        return dict(new_people=len(new), new_qualifications=qualifications, qualifications_valid_from=registered_at if new else None,
            new_login_accounts=0)


service = WorkforceImportService()
