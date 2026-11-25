"""ERP adapter for portable relational plans and read-only bounded execution."""
import json

from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.framework.db.session import get_session_context
from app.framework.db.tenant import require_tenant_schema
from app.core.config import get_settings
from resource_query.compiler import Binding, PlanError, compile_plan

from .harness_query_repository import RESOURCES, _column_value, conditions, resource_authorized
from .harness_query_schemas import QueryRequest
from .harness_relations import approved_relations
from .harness_schema_catalog import load_snapshot
from .harness_value_policy import model_scalar


def compile_erp_plan(plan, user):
    from .harness_ai_catalog import load_semantics
    semantics = load_semantics()
    snapshot = load_snapshot()
    relations = approved_relations(snapshot=snapshot, semantics=semantics)
    needed = {plan.root.resource}
    needed.update(relations[item.relation_id].target for item in plan.joins if item.relation_id in relations)
    bindings = {}
    for name in needed:
        spec = RESOURCES.get(name)
        if spec is None or not resource_authorized(spec, user):
            raise HTTPException(403, "关联查询资源不可用或没有权限")
        table = spec.table_model.__table__
        fields = frozenset(spec.ai_fields)
        predicates = conditions(spec, QueryRequest(operation="query", resource=name), user, set(fields))
        bindings[name] = Binding(table, fields, tuple(predicates), lambda field, value, spec=spec: _column_value(spec, field, value))
        # A stale constraint snapshot must not promise a false aggregation grain.
        observed = next((row for row in snapshot["tables"] if row['name'] == name), {})
        if set(observed.get("primary_key", [])) != set(table.primary_key.columns.keys()):
            raise HTTPException(409, "表主键快照已过期，请同步表结构并重建目录")
    try:
        return compile_plan(plan, bindings, relations, max_joins=get_settings().harness_query_max_joins)
    except PlanError as error:
        raise HTTPException(400, str(error)) from None


async def execute_erp_plan(plan, user):
    require_tenant_schema()
    compiled = compile_erp_plan(plan, user)
    try:
        async with get_session_context() as session:
            if session.get_bind().dialect.name == "postgresql":
                await session.execute(text("SET TRANSACTION READ ONLY"))
                await session.execute(text("SELECT set_config('statement_timeout', '10000', true)"))
            rows = [dict(row) for row in (await session.execute(compiled.statement)).mappings().all()]
            more = len(rows) > plan.limit
            result = {"plan_version": 1, "resources": compiled.resources, "grain": compiled.grain,
                      "rows": [{key: model_scalar(value) for key, value in jsonable_encoder(row).items()} for row in rows[:plan.limit]],
                      "limit": plan.limit, "offset": plan.offset, "truncated": more,
                      "next_offset": plan.offset + plan.limit if more else None,
                      "group_totals_additive": compiled.group_totals_additive}
            if not compiled.group_totals_additive:
                result["notice"] = "一个主表记录可能属于多个分组，各组统计不能直接相加作为总数"
            if plan.include_count:
                result["total"] = (await session.execute(compiled.count_statement)).scalar_one()
    except SQLAlchemyError:
        raise HTTPException(503, "关联查询执行失败或超时，请缩小范围；原始数据库错误不会发送给模型") from None
    # Include the public wrapper when applying the model output budget.
    if len(json.dumps({"code": 0, "message": "success", "data": {"policy_version": 1, **result}}, ensure_ascii=False).encode()) > 45000:
        raise HTTPException(413, "关联查询结果过大，请分页或减少返回字段")
    return result
