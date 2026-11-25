"""显式离线迁入：完整事务、真实权限、不可变来源追溯、既有记录不覆盖。"""
from collections import Counter, defaultdict
from datetime import date
from decimal import Decimal

from app.auth.scope_filters import resolve_write_org_id
from app.core.exceptions import AppException
from app.framework.db.models import utc_now
from app.modules.dictionary.service import ensure_builtin_definitions, service as dictionaries
from app.modules.inventory import public as inventory
from app.modules.inventory.public import StockOrderCreate
from . import warehouse_policy  # 显式登记 MES 仓库扩展点，不要求 inv 反向依赖。
from .archive_models import MesProcess, MesProjectStage
from .external_import_models import MesExternalImportRow
from .external_import_parser import PROCESSING_TYPES, UNITS, digest, number, text, timestamp, route_steps, standard_minutes
from .external_import_repository import repository as repo
from .models import (MesProductionOrder, MesWorkOrder, MesWorkOrderOperation, MesProcessTemplate,
                     MesProcessTemplateOperation, MesWorkOrderEvent)

REQUIRED_PERMISSIONS = ("mes:work_order:manage", "mes:work_order:create", "mes:process_template:manage",
    "mes:archive:stage:manage", "mes:archive:process:manage", "mes:warehouse:manage", "inventory_product:create",
    "inventory_inbound:list")
WAREHOUSE_NO = "GDB-TOOL-IMPORT"
OPENING_TYPE = "MES_GDB_OPENING"


def stable_number(prefix, values):
    return prefix + digest(values)[:24].upper()


def item_spec(row, kind):
    values = row.values
    if kind == "stock_balance":
        identity = [text(values.get(key)) for key in ("货品编码", "规格型号", "单位")]
    else:
        identity = [text(values.get(key)) for key in ("货品名称", "规格型号", "货品材料", "热处理", "表面处理", "单位")]
    code = stable_number("GDB-S-" if kind == "stock_balance" else "GDB-P-", identity)
    name = text(values.get("货品名称")) or text(values.get("货品编码"))
    spec = text(values.get("规格型号"))
    # 长工艺要求保存在 MES 制造字段，不拼进 inv 的规格字段。
    if kind == "work_order":
        spec = " / ".join(filter(None, (spec, text(values.get("货品材料")), text(values.get("热处理")), text(values.get("表面处理")))))
    elif text(values.get("货品编码")) != name:
        name = f"{name}（{text(values.get('货品编码'))}）"
    if len(name) > 128 or len(spec) > 128:
        raise ValueError(f"{row.file_name}:{row.line} 名称或规格过长，不能截断导入")
    return code, name, spec, UNITS[text(values["单位"])]


def record(row, org_id, user, **targets):
    return MesExternalImportRow(org_id=org_id, source_system_key="gendanbao", record_type_key=row.kind,
        source_record_no=row.key, source_file_name=row.file_name, source_file_sha256=row.file_hash,
        source_sheet_name=row.sheet, source_row_no=row.line, source_row_sha256=row.row_hash,
        source_values_snapshot=row.values, created_by=user.user_id, updated_by=user.user_id, **targets)


class ExternalImportService:
    def authorize(self, user, org_id):
        if "mes" not in user.enabled_plugin_keys:
            raise AppException("目标租户没有启用 MES", 403)
        for permission in REQUIRED_PERMISSIONS:
            if permission not in user.permissions:
                raise AppException(f"导入需要权限：{permission}", 403)
            if permission != "inventory_product:create":
                resolve_write_org_id(user, org_id, permission)

    async def preview(self, session, dataset, user, org_id):
        self.authorize(user, org_id)
        missing = await repo.missing_columns(session)
        result = dataset.summary()
        result["missing_columns"] = missing
        for kind in ("work_order", "stock_balance"):
            for row in dataset.rows[kind]: item_spec(row, kind)
        if missing:
            return result
        existing = {(row.record_type_key, row.source_record_no): row for row in await repo.sources(session, user, org_id)}
        for kind, rows in dataset.rows.items():
            for row in rows:
                old = existing.get((kind, row.key))
                if old and old.source_row_sha256 != row.row_hash:
                    raise AppException(f"{row.file_name}:{row.line} 来源编号已导入但值发生变化，未覆盖", 409)
        result["already_imported"] = sum((kind, row.key) in existing for kind, rows in dataset.rows.items() for row in rows)
        # 一次事务导入，重试允许整批相同数据；不接受不完整的追溯关联后偷偷补写。
        if result["already_imported"] not in {0, sum(map(len, dataset.rows.values()))}:
            raise AppException("发现部分来源已导入；请先核对原批次，不自动覆盖或重复增加库存", 409)
        if not result["already_imported"]:
            project_numbers = {row.production_order_no for row in await repo.projects(session, user, org_id)}
            work_numbers = {row.work_order_no for row in await repo.works(session, user, org_id)}
            template_numbers = {row.template_no for row in await repo.templates(session, user, org_id)}
            if any(row.key in project_numbers for row in dataset.rows["production_order"]):
                raise AppException("来源工单号与无导入追溯的现有项目冲突，未覆盖", 409)
            if any(row.key in work_numbers for row in dataset.rows["work_order"]):
                raise AppException("来源货品编码与无导入追溯的现有执行工单冲突，未覆盖", 409)
            if any(stable_number("GDB-R-", row.values["工艺路线名称"]) in template_numbers for row in dataset.rows["route_step"]):
                raise AppException("来源路线编号与无导入追溯的现有路线冲突，未覆盖", 409)
        return result

    async def apply(self, session, dataset, user, org_id, *, opening_date):
        await repo.lock(session, org_id)
        preview = await self.preview(session, dataset, user, org_id)
        if preview["missing_columns"]:
            raise AppException("请先审核并执行本环境 MES 迁移；缺少：" + "、".join(preview["missing_columns"]), 409)
        if preview["already_imported"]:
            zero_rows = [row for row in dataset.rows["stock_balance"] if number(row.values["实际库存"]) == 0]
            if zero_rows:
                sources = {(row.record_type_key, row.source_record_no): row for row in await repo.sources(session, user, org_id)}
                warehouses = await inventory.list_configured_warehouses(session, "mes", user)
                warehouse = next((row for row in warehouses if row["org_id"] == org_id and row["warehouse_no"] == WAREHOUSE_NO), None)
                if not warehouse or not warehouse["is_active"]:
                    raise AppException("已导入批次的刀具仓不存在或已停用，未重复入账", 409)
                await inventory.ensure_zero_stock_positions(session, warehouse["id"],
                    [sources[(row.kind, row.key)].item_id for row in zero_rows], user, scope_key="mes")
            return {**preview, "written": 0}
        await ensure_builtin_definitions(session, [
            ("md_unit", "计量单位", [("piece", "件"), ("branch", "支")]),
            ("mes_processing_type", "加工类型", [("in_house", "自制"), ("outsourced", "委外"), ("purchased", "采购")]),
            ("inv_warehouse_type", "仓库类型", [("mes_tool", "制造刀具仓")]),
        ])
        # setup 只补缺；停用的单位不会被强制恢复。
        units = await dictionaries.options_in_session(session, ["md_unit"])
        if not {"piece", "branch"} <= {row["item_code"] for row in units["md_unit"]}:
            raise AppException("件或支计量单位已停用，请先核对字典", 409)
        items = {}
        specifications = {item_spec(row, kind)[0]: item_spec(row, kind) for kind in ("work_order", "stock_balance") for row in dataset.rows[kind]}
        for code, name, spec, unit in sorted(specifications.values()):
            item = await inventory.ensure_active_item(session, item_no=code, item_name=name, specification=spec, unit_code=unit, user=user)
            if item.item_name != name or item.specification != spec:
                raise AppException("来源物料编号已被其他档案使用，未覆盖", 409)
            items[code] = item
        by_name = defaultdict(set)
        for row in dataset.rows["work_order"]:
            by_name[text(row.values["货品名称"])].add(items[item_spec(row, "work_order")[0]].id)
        stages, processes, templates, route_rows = {}, {}, {}, defaultdict(list)
        for row in dataset.rows["route_step"]: route_rows[text(row.values["工艺路线名称"])].append(row)
        for route_name, rows in route_rows.items():
            product_ids = by_name.get(route_name, set())
            template = repo.add(session, MesProcessTemplate(org_id=org_id, template_no=stable_number("GDB-R-", route_name),
                template_name=route_name, product_item_id=next(iter(product_ids)) if len(product_ids) == 1 else None,
                created_by=user.user_id, updated_by=user.user_id, created_at=timestamp(rows[0].values.get("创建时间")) or utc_now()))
            await session.flush()
            steps = []
            for index, row in enumerate(rows, 1):
                values = row.values
                stage_name = text(values.get("项目阶段"))
                if stage_name and stage_name not in stages:
                    stage = repo.add(session, MesProjectStage(org_id=org_id, stage_no=stable_number("GDB-ST-", stage_name),
                        stage_name=stage_name, sort_no=len(stages), created_by=user.user_id, updated_by=user.user_id))
                    stages[stage_name] = stage
                    await session.flush()
                process_key = (text(values["工艺"]), stage_name, text(values["加工类型"]), text(values.get("计件工艺")))
                if process_key not in processes:
                    process = repo.add(session, MesProcess(org_id=org_id, process_no=stable_number("GDB-PR-", process_key),
                        process_name=process_key[0], project_stage_id=stages[stage_name].id if stage_name else None,
                        processing_type_code="outsourced" if process_key[2] == "委外" else "in_house",
                        is_piecework=process_key[3] in {"是", "1", "True"}, is_quality_required=process_key[2] == "品检",
                        created_by=user.user_id, updated_by=user.user_id))
                    processes[process_key] = process
                    await session.flush()
                process = processes[process_key]
                operation = repo.add(session, MesProcessTemplateOperation(org_id=org_id, template_id=template.id,
                    sequence_no=index, operation_no=str(index * 10), operation_name=process.process_name,
                    process_id=process.id, project_stage_id=process.project_stage_id, stage_name_snapshot=stage_name or None,
                    standard_minutes_per_unit=standard_minutes(values), operation_description=text(values.get("加工说明")) or None,
                    is_quality_required=process.is_quality_required, created_by=user.user_id, updated_by=user.user_id))
                await session.flush()
                repo.add(session, record(row, org_id, user, template_operation_id=operation.id))
                steps.append(operation)
            templates[route_name] = (template, steps)
        projects = {}
        counts = Counter(text(row.values["工单号"]) for row in dataset.rows["work_order"])
        for row in dataset.rows["production_order"]:
            values = row.values
            declared = int(number(values["货品款数"]))
            projects[row.key] = repo.add(session, MesProductionOrder(org_id=org_id, production_order_no=row.key,
                project_name=text(values["项目名称"]) or row.key, source_product_count_snapshot=declared,
                is_import_incomplete=declared != counts[row.key],
                note=f"跟单宝导入；来源类型：{text(values.get('工单类型'))}；来源状态：{text(values['工单状态'])}；原声明 {declared} 款，本次明细 {counts[row.key]} 款。缺失明细不补造。",
                created_at=timestamp(values.get("创建时间")) or utc_now(), created_by=user.user_id, updated_by=user.user_id))
            await session.flush()
            repo.add(session, record(row, org_id, user, production_order_id=projects[row.key].id))
        for row in dataset.rows["work_order"]:
            values = row.values
            item = items[item_spec(row, "work_order")[0]]
            source_steps = route_steps(values["工艺路线"])
            template_pair = templates.get(text(values["货品名称"]))
            matching = bool(template_pair and [operation.operation_name for operation in template_pair[1]] == [name for name, _ in source_steps])
            status = {"待配置": "draft", "待下单": "draft", "已下单": "released", "已暂停": "paused", "已完工": "completed"}[text(values["货品状态"])]
            if status == "released" and any(state == "in_progress" for _, state in source_steps): status = "in_progress"
            work = repo.add(session, MesWorkOrder(org_id=org_id, production_order_id=projects[text(values["工单号"])].id,
                work_order_no=row.key, product_item_id=item.id, product_item_no_snapshot=item.item_no,
                product_item_name_snapshot=item.item_name, unit_code=item.unit_code, planned_quantity=number(values["数量"]),
                processing_type_code=PROCESSING_TYPES[text(values["货品类型"])], status_code=status,
                priority_code="urgent" if text(values.get("优先级")) == "紧急" else "normal",
                due_at=timestamp(values.get("交期")), released_at=timestamp(values.get("下单时间")),
                material_name_snapshot=text(values.get("货品材料")) or None,
                heat_treatment_snapshot=text(values.get("热处理")) or None, surface_treatment_snapshot=text(values.get("表面处理")) or None,
                process_requirement_snapshot=text(values.get("工艺要求")) or None, outsourced_due_at=timestamp(values.get("外协交期")),
                process_template_id=template_pair[0].id if matching else None, process_template_version_snapshot=1 if matching else None,
                note="\n".join(filter(None, (text(values.get("货品备注")), "跟单宝历史导入；未提供报工数量、执行区间及图纸原件，不生成虚构报工或图纸。"))),
                created_at=timestamp(values.get("创建时间")) or utc_now(), created_by=user.user_id, updated_by=user.user_id))
            await session.flush()
            for index, (name, state) in enumerate(source_steps, 1):
                original = template_pair[1][index-1] if matching else None
                operation = MesWorkOrderOperation(org_id=org_id, work_order_id=work.id, operation_no=str(index * 10),
                    sequence_no=index, operation_name_snapshot=name, planned_quantity=work.planned_quantity,
                    is_imported_snapshot=True,
                    priority_code=work.priority_code, status_code="draft" if status == "draft" else state,
                standard_minutes_per_unit=original.standard_minutes_per_unit if original else None,
                    process_id=original.process_id if original else None, project_stage_id=original.project_stage_id if original else None,
                    stage_name_snapshot=original.stage_name_snapshot if original else None,
                    operation_description=original.operation_description if original else None,
                    is_quality_required=original.is_quality_required if original else name.upper() in {"QA", "QC"},
                    created_by=user.user_id, updated_by=user.user_id)
                repo.add(session, operation)
            repo.add(session, MesWorkOrderEvent(org_id=org_id, work_order_id=work.id, event_type_code="created",
                to_status_code=status, version_no=1, note="导入原系统货品及已提供的工序状态；未生成报工事实", created_by=user.user_id))
            repo.add(session, record(row, org_id, user, work_order_id=work.id))
        warehouses = await inventory.list_configured_warehouses(session, "mes", user)
        existing = next((row for row in warehouses if row["org_id"] == org_id and row["warehouse_no"] == WAREHOUSE_NO), None)
        if existing:
            raise AppException("独立导入仓已存在但没有完整导入追溯，请先核对，不叠加余额", 409)
        warehouse = await inventory.configure_warehouse(session, "mes", dict(org_id=org_id, warehouse_no=WAREHOUSE_NO,
            warehouse_name="跟单宝导入刀具仓", warehouse_type_code="mes_tool", is_active=True), user)
        zero_ids = [items[item_spec(row, "stock_balance")[0]].id for row in dataset.rows["stock_balance"] if number(row.values["实际库存"]) == 0]
        if zero_ids:
            await inventory.ensure_zero_stock_positions(session, warehouse["id"], zero_ids, user, scope_key="mes")
        await inventory.ensure_stock_order_types(session, [dict(type_no=OPENING_TYPE, type_name="跟单宝库存期初导入",
            direction_code="in", default_to_status_code="available", is_approval_required=False,
            required_field_config={"form": "inbound", "no_prefix": "GDBQC", "warehouse_scope_key": "mes", "warehouse_type_codes": ["mes_tool"]})], user.user_id)
        stock_type = await inventory.get_stock_order_type(session, OPENING_TYPE)
        if stock_type["direction_code"] != "in" or stock_type["is_approval_required"] or stock_type["is_negative_allowed"]:
            raise AppException("期初导入类型配置发生变化，未覆盖，请人工核对", 409)
        lines = []
        for row in dataset.rows["stock_balance"]:
            item = items[item_spec(row, "stock_balance")[0]]
            quantity = number(row.values["实际库存"])
            if quantity > 0:
                lines.append(dict(item_id=item.id, unit_code=item.unit_code, quantity=quantity,
                    remark=f"来源行 {row.line}；仅导入 {opening_date} 余额，不把累计入库/出库伪造成明细。"))
        stock_order = None
        if lines:
            stock_order = await inventory.create_stock_order(session, StockOrderCreate(order_type_id=stock_type["id"], org_id=org_id,
                to_warehouse_id=warehouse["id"], business_date=opening_date, lines=lines, confirm=True,
                remark=f"跟单宝 {opening_date} 期初库存导入；非历史出入库流水"), user)
            if stock_order["status_code"] != "confirmed": raise AppException("期初库存未实际确认记账，导入回滚", 409)
        for row in dataset.rows["stock_balance"]:
            item = items[item_spec(row, "stock_balance")[0]]
            repo.add(session, record(row, org_id, user, item_id=item.id,
                stock_order_id=stock_order["id"] if stock_order and number(row.values["实际库存"]) > 0 else None))
        await session.flush()
        return {**preview, "written": sum(map(len, dataset.rows.values())), "warehouse_id": str(warehouse["id"]),
                "stock_order_id": str(stock_order["id"]) if stock_order else None, "new_items": len(items),
                "processes": len(processes), "stages": len(stages)}


service = ExternalImportService()
