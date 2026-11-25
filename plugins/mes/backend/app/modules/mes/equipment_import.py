"""跟单宝设备档案导入；一台物理设备关联多种工艺，原 hours 只保留来源快照。"""
import json
import hashlib
from pathlib import Path
from uuid import UUID

from app.auth.scope_filters import resolve_write_org_id
from app.core.exceptions import AppException
from .archive_models import MesEquipment
from .archive_repository import archive_repository
from .external_import_parser import SourceRow, number
from .external_import_service import record
from .equipment_import_repository import repository


def read_equipment(path):
    path = Path(path)
    raw = path.read_bytes()
    response = json.loads(raw.decode("utf-8-sig"))
    if response.get("success") is not True:
        raise ValueError("来源设备接口未返回成功结果")
    data = response["data"]
    if (data["totalPages"], data["number"], data["hasNext"]) != (1, 0, False):
        raise ValueError("设备分页不完整；本命令当前只接受完整单页导出")
    rows = data["content"]
    if len(rows) != data["totalElements"] or data["size"] < len(rows) or not rows:
        raise ValueError("设备总数不一致或为空")
    for field in ("recordId", "code", "name"):
        values = [row.get(field) for row in rows]
        if any(not isinstance(value, str) or not value.strip() or value != value.strip() for value in values):
            raise ValueError(f"设备 {field} 缺失或格式无效")
        if len(set(values)) != len(values):
            raise ValueError(f"设备 {field} 重复，未自动合并")
    file_hash = hashlib.sha256(raw).hexdigest()
    result = []
    for index, row in enumerate(rows, 2):
        UUID(row["recordId"])
        if len(row["code"]) > 64 or len(row["name"]) > 128 or type(row["disabled"]) is not bool:
            raise ValueError("设备编号、名称或启停字段无效")
        number(row.get("hours"))  # 只检查来源值，不将其解释为设备日历或班次。
        crafts = row.get("equipmentCraftList")
        if not isinstance(crafts, list) or len(crafts) > 100:
            raise ValueError("设备工艺关联格式无效或数量过多")
        ids = []
        for craft in crafts:
            ids.append(str(UUID(craft["craftRecordId"])))
            if not isinstance(craft.get("craftName"), str) or not craft["craftName"].strip():
                raise ValueError("设备关联的工艺名称缺失")
        if len(set(ids)) != len(ids):
            raise ValueError("同一设备的工艺关联重复")
        result.append(SourceRow("equipment_archive", row["recordId"], path.name, file_hash, "data.content", index, row))
    return result


def equipment_values(row):
    return dict(equipment_name=row.values["name"], is_active=not row.values["disabled"],
        description=f"跟单宝设备档案；来源编号：{row.key}")


class EquipmentImportService:
    def authorize(self, user, org_id):
        if "mes" not in user.enabled_plugin_keys:
            raise AppException("目标租户未启用 MES", 403)
        for key in ("mes:archive:equipment:manage", "mes:archive:process:manage"):
            if key not in user.permissions:
                raise AppException(f"设备导入需要权限：{key}", 403)
            resolve_write_org_id(user, org_id, key)

    async def plan(self, session, rows, user, org_id):
        self.authorize(user, org_id)
        source_processes = {}
        prefix = "跟单宝工艺档案；来源编号："
        for process in await repository.processes(session, user, org_id):
            first = (process.description or "").splitlines()
            if first and first[0].startswith(prefix):
                external_id = str(UUID(first[0][len(prefix):]))
                if external_id in source_processes:
                    raise AppException("正式工艺来源编号重复，未猜测设备关联", 409)
                source_processes[external_id] = process
        equipment = {row.equipment_no: row for row in await repository.equipment(session, user, org_id)}
        sources = {row.source_record_no: row for row in await repository.sources(session, user, org_id)}
        links, existing = {}, {}
        for row in rows:
            ids = []
            for craft in row.values["equipmentCraftList"]:
                process = source_processes.get(str(UUID(craft["craftRecordId"])))
                if not process or not process.is_active or process.process_name != craft["craftName"].strip():
                    raise AppException(f"设备 {row.values['code']} 的工艺 {craft['craftName']} 不存在、已停用或名称不一致", 409)
                ids.append(process.id)
            links[row.key] = ids
            old = equipment.get(row.values["code"])
            source = sources.get(row.key)
            if source:
                if source.source_row_sha256 != row.row_hash or not old or source.equipment_id != old.id:
                    raise AppException("来源设备已导入但内容或关联发生变化，未覆盖", 409)
                if any(getattr(old, field) != value for field, value in equipment_values(row).items()) or set(await archive_repository.equipment_process_ids(session, old)) != set(ids):
                    raise AppException("已导入设备或适用工艺已人工修改，未覆盖", 409)
                existing[row.key] = old
            elif old:
                raise AppException(f"设备编号 {row.values['code']} 已存在且没有本次来源追溯，未覆盖", 409)
        return existing, links

    async def preview(self, session, rows, user, org_id):
        self.authorize(user, org_id)
        missing = await repository.missing(session)
        result = dict(source_equipment=len(rows), source_process_links=sum(len(r.values["equipmentCraftList"]) for r in rows), missing_columns=missing)
        if missing:
            return result
        existing, links = await self.plan(session, rows, user, org_id)
        return result | dict(new_equipment=len(rows) - len(existing), new_process_links=sum(len(links[r.key]) for r in rows if r.key not in existing))

    async def apply(self, session, rows, user, org_id):
        self.authorize(user, org_id)
        await archive_repository.lock_organization(session, org_id)
        missing = await repository.missing(session)
        if missing:
            raise AppException("设备多工艺关联结构未升级，请先审核并执行迁移", 409)
        existing, links = await self.plan(session, rows, user, org_id)
        count = link_count = 0
        for row in rows:
            if row.key in existing:
                continue
            equipment = MesEquipment(org_id=org_id, equipment_no=row.values["code"], **equipment_values(row),
                created_by=user.user_id, updated_by=user.user_id)
            repository.add(session, equipment)
            await session.flush()
            await archive_repository.replace_equipment_processes(session, equipment, links[row.key], user.user_id)
            repository.add(session, record(row, org_id, user, equipment_id=equipment.id))
            count += 1
            link_count += len(links[row.key])
        await session.flush()
        return dict(new_equipment=count, new_process_links=link_count)


service = EquipmentImportService()
