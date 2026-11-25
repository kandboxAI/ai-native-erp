"""档案选用时校验组织和启用状态，复制到生产配置；不修改执行事实。"""
from app.core.exceptions import AppException
from .archive_service import archive_service
from .archive_repository import archive_repository as repo
from .archive_models import MesCustomer, MesProcess, MesEquipment, MesProcessRequirement, MesProjectStage


async def customer_snapshot(session, body, org_id, existing=None):
    identifier = getattr(body, "customer_id", None)
    if not identifier: return body.customer_no, body.customer_name
    if existing is not None and getattr(existing, "customer_id", None) == identifier:
        return existing.customer_no_snapshot, existing.customer_name_snapshot
    await repo.lock_organization(session, org_id)
    row = await archive_service.reference(session, MesCustomer, identifier, org_id)
    return row.customer_no, row.customer_name


async def prepare_operations(session, operations, org_id, existing=None):
    if not any(getattr(op, field, None) for op in operations for field in ("process_id", "equipment_id", "requirement_id")): return [{} for _ in operations]
    await repo.lock_organization(session, org_id)
    dependencies = await repo.dependencies(session, org_id)
    visited, bindings = set(), []
    selected = {op.process_id for op in operations if op.process_id}
    for op in operations:
        old = next((row for row in existing or () if row.operation_no == op.operation_no), None)
        fields = ("process_id", "equipment_id", "requirement_id")
        if old is not None and all(getattr(old, field, None) == getattr(op, field, None) for field in fields) and (
            old.operation_name_snapshot == op.operation_name and (old.operation_description or "") == (op.operation_description or "")
            and (old.work_center_name_snapshot or "") == (op.work_center_name or "")
            and (old.workstation_name_snapshot or "") == (op.workstation_name or "") and old.is_quality_required == op.is_quality_required):
            bindings.append({**{field: getattr(old, field, None) for field in fields},
                "is_equipment_required_snapshot": getattr(old,"is_equipment_required_snapshot",None),
                "project_stage_id": old.project_stage_id, "stage_name_snapshot": old.stage_name_snapshot})
            if op.process_id: visited.add(op.process_id)
            continue
        process = await archive_service.reference(session, MesProcess, op.process_id, org_id)
        equipment = await archive_service.reference(session, MesEquipment, op.equipment_id, org_id)
        if equipment and not await repo.equipment_accepts(session, equipment, op.process_id):
            raise AppException("设备所属工艺与当前工序选用的工艺不一致", 409)
        if process:
            previous = {edge.previous_process_id for edge in dependencies if edge.process_id == process.id}
            if not previous <= visited:
                missing, unordered = [], []
                for identifier in sorted(previous - visited, key=str):
                    required = await archive_service.reference(session, MesProcess, identifier, org_id)
                    label = f"{required.process_no} · {required.process_name}"
                    (unordered if identifier in selected else missing).append(label)
                reasons = []
                if missing: reasons.append("缺少前置工艺“" + "、".join(missing) + "”，请在本工序前添加")
                if unordered: reasons.append("前后顺序不正确，请把前置工艺“" + "、".join(unordered) + "”移到本工序之前")
                raise AppException(f"工序 {op.operation_no}（{process.process_name}）：" + "；".join(reasons), 409)
            visited.add(process.id)
            op.operation_name = process.process_name
            op.is_quality_required = op.is_quality_required or process.is_quality_required
        requirement_id = op.requirement_id or (process.requirement_id if process else None)
        requirement = await archive_service.reference(session, MesProcessRequirement, requirement_id, org_id)
        stage = await archive_service.reference(session, MesProjectStage, process.project_stage_id if process else None, org_id)
        if not op.operation_description:
            op.operation_description = "\n".join(filter(None, (process.description if process else None, requirement.description if requirement else None))) or None
        elif requirement and requirement.description and requirement.description not in op.operation_description:
            op.operation_description += "\n" + requirement.description
        if op.operation_description and len(op.operation_description) > 4000:
            raise AppException("工艺说明与要求合计超过 4000 字，请缩短档案说明后再选用", 422)
        if equipment:
            op.workstation_name = equipment.equipment_no
            op.work_center_name = op.work_center_name or equipment.work_center_name
        bindings.append(dict(process_id=op.process_id, equipment_id=op.equipment_id, requirement_id=requirement_id,
            is_equipment_required_snapshot=getattr(process,"is_equipment_required",None) if process else None,
            project_stage_id=stage.id if stage else None, stage_name_snapshot=stage.stage_name if stage else None))
    return bindings
