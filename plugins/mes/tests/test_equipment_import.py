"""设备多工艺导入及选用规则；只用内存 SQLite，不连接业务库。"""
import json
from types import SimpleNamespace as NS
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.core.exceptions import AppException
from app.modules.mes.archive_models import MesEquipment, MesProcess, MesEquipmentProcess
from app.modules.mes.archive_repository import archive_repository, equipment_process_condition, generic_equipment_condition
from app.modules.mes.archive_schemas import ArchiveQuery
from app.modules.mes.archive_service import ARCHIVES
from app.modules.mes.equipment_import import read_equipment, service, repository
from app.modules.mes.production_service import equipment_assignment
from app.modules.mes.external_import_models import MesExternalImportRow
from test_process_archive_import import state, Adapter
from test_quotations import run


def data(tmp_path):
    crafts = [dict(craftRecordId=str(uuid4()), craftName=name) for name in ("CNC2", "CNC4", "CNC5")]
    row = dict(recordId=str(uuid4()), code="MA000014", name="CNC-14#", disabled=False, hours=20, equipmentCraftList=crafts)
    path = tmp_path / "equipment.json"
    path.write_text(json.dumps(dict(success=True, data=dict(totalPages=1, number=0, size=20, totalElements=1, hasNext=False, content=[row]))), encoding="utf-8")
    return read_equipment(path), path


@pytest.fixture
def equipment(state, monkeypatch):
    key = "mes:archive:equipment:manage"
    state.actor.permissions.append(key)
    state.actor.permission_scopes[key] = "all"
    async def ready(*args): return []
    monkeypatch.setattr(repository, "missing", ready)
    return state


def masters(state, rows):
    with Session(state.engine) as session:
        for index, craft in enumerate(rows[0].values["equipmentCraftList"], 1):
            session.add(MesProcess(org_id=state.org_id, process_no=f"GY{index}", process_name=craft["craftName"],
                description="跟单宝工艺档案；来源编号：" + craft["craftRecordId"]))
        session.commit()


def test_one_physical_device_three_relations_and_idempotency(equipment, tmp_path):
    rows, _ = data(tmp_path); masters(equipment, rows)
    with Session(equipment.engine) as session:
        result = run(service.apply(Adapter(session), rows, equipment.actor, equipment.org_id)); session.commit()
        assert result == dict(new_equipment=1, new_process_links=3)
        assert session.scalar(select(func.count()).select_from(MesEquipment)) == 1
        assert session.scalar(select(func.count()).select_from(MesEquipmentProcess)) == 3
        machine = session.scalar(select(MesEquipment))
        assert machine.process_id is None
        source = session.scalar(select(MesExternalImportRow))
        assert source.equipment_id == machine.id and source.source_values_snapshot["hours"] == 20
        assert run(service.apply(Adapter(session), rows, equipment.actor, equipment.org_id)) == dict(new_equipment=0, new_process_links=0)
        for identifier in run(archive_repository.equipment_process_ids(Adapter(session), machine)):
            assert run(archive_repository.equipment_accepts(Adapter(session), machine, identifier))
        assert not run(archive_repository.equipment_accepts(Adapter(session), machine, uuid4()))
        assert not run(archive_repository.equipment_accepts(Adapter(session), machine, None))
        assert not session.scalars(select(MesEquipment).where(generic_equipment_condition(MesEquipment))).all()
        first = session.scalar(select(MesProcess.id))
        assert session.scalars(select(MesEquipment).where(equipment_process_condition(MesEquipment, first))).all()


@pytest.mark.parametrize("change", ["missing", "inactive", "wrong_org", "name", "collision"])
def test_invalid_links_or_numbers_fail_before_any_write(equipment, tmp_path, change):
    rows, _ = data(tmp_path); masters(equipment, rows)
    with Session(equipment.engine) as session:
        first = session.scalar(select(MesProcess))
        if change == "missing": first.description = None
        if change == "inactive": first.is_active = False
        if change == "wrong_org": first.org_id = uuid4()
        if change == "name": first.process_name = "其他工艺"
        if change == "collision": session.add(MesEquipment(org_id=equipment.org_id, equipment_no="MA000014", equipment_name="手工已有设备"))
        session.commit()
        with pytest.raises(AppException): run(service.apply(Adapter(session), rows, equipment.actor, equipment.org_id))
        session.rollback()
        assert session.scalar(select(func.count()).select_from(MesEquipmentProcess)) == 0
        assert session.scalar(select(func.count()).select_from(MesExternalImportRow)) == 0


def test_caller_rollback_and_source_change_refused(equipment, tmp_path):
    rows, _ = data(tmp_path); masters(equipment, rows)
    with Session(equipment.engine) as session:
        run(service.apply(Adapter(session), rows, equipment.actor, equipment.org_id)); session.rollback()
        assert session.scalar(select(func.count()).select_from(MesEquipment)) == 0
        run(service.apply(Adapter(session), rows, equipment.actor, equipment.org_id)); session.commit()
        rows[0].values["hours"] = 10
        with pytest.raises(AppException): run(service.apply(Adapter(session), rows, equipment.actor, equipment.org_id))


def test_reject_incomplete_page_and_duplicate_craft(tmp_path):
    rows, path = data(tmp_path)
    response = json.loads(path.read_text())
    response["data"]["content"][0]["equipmentCraftList"].append(rows[0].values["equipmentCraftList"][0])
    path.write_text(json.dumps(response))
    with pytest.raises(ValueError, match="重复"): read_equipment(path)
    response["data"]["hasNext"] = True
    path.write_text(json.dumps(response))
    with pytest.raises(ValueError, match="分页"): read_equipment(path)


def test_process_filter_preserves_multi_process_and_generic_equipment(equipment, tmp_path):
    rows, _ = data(tmp_path); masters(equipment, rows)
    with Session(equipment.engine) as session:
        run(service.apply(Adapter(session), rows, equipment.actor, equipment.org_id))
        generic = MesEquipment(org_id=equipment.org_id, equipment_no="GENERIC", equipment_name="通用设备")
        session.add(generic); session.commit()
        process = session.scalar(select(MesProcess.id))
        result, total = run(archive_repository.page(Adapter(session), ARCHIVES["equipment"], ArchiveQuery(
            org_id=equipment.org_id, applicable_process_id=process), equipment.actor, "mes:archive:equipment:manage"))
        assert total == 2
        result, total = run(archive_repository.page(Adapter(session), ARCHIVES["equipment"], ArchiveQuery(
            org_id=equipment.org_id, generic_equipment_only=True), equipment.actor, "mes:archive:equipment:manage"))
        assert total == 1 and result[0].equipment_no == "GENERIC"


def test_scheduling_accepts_all_three_processes_and_rejects_other(equipment, tmp_path):
    rows, _ = data(tmp_path); masters(equipment, rows)
    with Session(equipment.engine) as session:
        run(service.apply(Adapter(session), rows, equipment.actor, equipment.org_id)); session.commit()
        machine = session.scalar(select(MesEquipment))
        change = NS(equipment_id=machine.id, model_fields_set={"equipment_id"}, planned_start_at=datetime.now(timezone.utc))
        task = NS(equipment_id=None, org_id=equipment.org_id, process_id=None)
        for identifier in run(archive_repository.equipment_process_ids(Adapter(session), machine)):
            task.process_id = identifier
            assert run(equipment_assignment(Adapter(session), task, change))["equipment_id"] == machine.id
        for identifier in (None, uuid4()):
            task.process_id = identifier
            with pytest.raises(AppException): run(equipment_assignment(Adapter(session), task, change))
