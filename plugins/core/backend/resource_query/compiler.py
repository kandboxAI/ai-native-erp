"""Compile validated plans to SQLAlchemy SELECTs; never accept SQL expressions."""
from dataclasses import dataclass
from typing import Any, Callable

from sqlalchemy import Float, Integer, Numeric, String, Table, and_, func, select
from sqlalchemy.types import TypeDecorator, TypeEngine

from .models import QueryPlan


class PlanError(ValueError):
    pass


def is_text_type(column_type: TypeEngine[Any]) -> bool:
    """识别原生文本及底层为文本的装饰类型，兼容 SQLModel AutoString。"""
    return isinstance(column_type, String) or (
        isinstance(column_type, TypeDecorator) and isinstance(column_type.impl, String)
    )


@dataclass(frozen=True)
class Binding:
    table: Table
    fields: frozenset[str]
    predicates: tuple[Any, ...] = ()
    convert: Callable[[str, Any], Any] = lambda field, value: value


@dataclass(frozen=True)
class Relation:
    id: str
    source: str
    target: str
    fields: tuple[str, ...]
    target_fields: tuple[str, ...]
    cardinality: str
    origin: str = "foreign_key"


@dataclass
class CompiledPlan:
    statement: Any
    count_statement: Any
    resources: dict[str, str]
    output_fields: tuple[str, ...]
    grain: str
    group_totals_additive: bool


def compile_plan(plan: QueryPlan, bindings: dict[str, Binding], relations: dict[str, Relation], *, max_joins: int) -> CompiledPlan:
    if max_joins < 1:
        raise ValueError("max_joins must be positive")
    if len(plan.joins) > max_joins:
        raise PlanError(f"关联查询最多允许 {max_joins} 条关联，请减少关联或拆分查询")
    aliases: dict[str, tuple[str, Binding, Any]] = {}
    multiplying = False

    def add(alias, resource):
        if alias in aliases or resource not in bindings:
            raise PlanError("资源不可用或表别名重复")
        binding = bindings[resource]
        columns = set(binding.fields) | set(binding.table.primary_key.columns.keys())
        scoped = select(*(binding.table.c[key] for key in sorted(columns))).where(*binding.predicates).subquery(alias)
        aliases[alias] = (resource, binding, scoped)
        return scoped

    joined = add(plan.root.alias, plan.root.resource)
    for join in plan.joins:
        relation = relations.get(join.relation_id)
        parent = aliases.get(join.from_alias)
        if relation is None or parent is None or parent[0] != relation.source:
            raise PlanError("关联关系不可用或来源不匹配，请重新检索关系定义")
        if not relation.fields or len(relation.fields) != len(relation.target_fields):
            raise PlanError("关联关系定义不完整")
        target = bindings.get(relation.target)
        if target is None or set(relation.fields) - parent[1].fields or set(relation.target_fields) - target.fields:
            raise PlanError("关联字段或目标资源不可用")
        if relation.cardinality not in ("many_to_one", "one_to_one", "one_to_many"):
            raise PlanError("不支持未经确定基数的关联")
        right = add(join.alias, relation.target)
        joined = joined.join(right, and_(*(parent[2].c[left] == right.c[right_key]
                              for left, right_key in zip(relation.fields, relation.target_fields))), isouter=join.kind == "left")
        multiplying = multiplying or relation.cardinality == "one_to_many"

    def field(ref):
        alias, key = ref.split(".", 1)
        row = aliases.get(alias)
        if row is None or key not in row[1].fields:
            raise PlanError("字段不可用，包括选择、筛选、排序及聚合字段")
        return row[2].c[key], row[1], key

    output_names = [item.as_ for item in plan.select] + [item.as_ for item in plan.aggregates]
    if not output_names or len(output_names) != len(set(output_names)):
        raise PlanError("必须选择返回字段，且输出名称不能重复")
    if len(plan.group_by) != len(set(plan.group_by)):
        raise PlanError("分组字段不能重复")
    if any(item.field not in output_names for item in plan.order):
        raise PlanError("只能按返回字段排序")
    where = []
    for item in plan.filters:
        column, binding, key = field(item.field)
        if item.op == "is_null":
            if not isinstance(item.value, bool):
                raise PlanError("is_null 需要布尔值")
            expression = column.is_(None) if item.value else column.is_not(None)
        elif item.op == "in":
            if not isinstance(item.value, list) or not 1 <= len(item.value) <= 100:
                raise PlanError("in 需要 1 至 100 个值")
            expression = column.in_([binding.convert(key, value) for value in item.value])
        elif item.op in ("like", "ilike"):
            if not is_text_type(column.type) or not isinstance(item.value, str) or len(item.value) > 128:
                raise PlanError("like/ilike 仅支持短文本字段")
            expression = getattr(column, item.op)(item.value)
        else:
            value = binding.convert(key, item.value) if item.value is not None else None
            if value is None and item.op not in ("eq", "neq"):
                raise PlanError("比较运算需要非空值")
            expression = {"eq": lambda: column == value, "neq": lambda: column != value,
                          "gt": lambda: column > value, "gte": lambda: column >= value,
                          "lt": lambda: column < value, "lte": lambda: column <= value}[item.op]()
        where.append(expression)

    if plan.aggregates:
        if set(item.field for item in plan.select) != set(plan.group_by) or len(plan.select) != len(plan.group_by):
            raise PlanError("聚合查询的选择字段必须恰好对应分组字段")
        root = aliases[plan.root.alias]
        pk = list(root[1].table.primary_key.columns.keys())
        if not pk:
            raise PlanError("主表没有可靠主键，无法保证聚合不重复")
        groups = [field(ref)[0] for ref in plan.group_by]
        values = []
        for aggregate in plan.aggregates:
            if aggregate.field is None:
                if aggregate.function != "count":
                    raise PlanError("此聚合需要主表字段")
                values.append(None)
                continue
            if aggregate.field.split(".", 1)[0] != plan.root.alias:
                raise PlanError("聚合字段必须来自主表；请将统计对象设为主表")
            column = field(aggregate.field)[0]
            if aggregate.function in ("sum", "avg") and not isinstance(column.type, (Integer, Float, Numeric)):
                raise PlanError("sum/avg 需要数值字段")
            values.append(column)
        # Deduplicate identities and dimensions, never SUM(DISTINCT amount):
        # different entities with equal amounts must both contribute.
        facts = select(*(root[2].c[key].label(f"k{i}") for i, key in enumerate(pk)),
                       *(column.label(f"g{i}") for i, column in enumerate(groups)),
                       *(column.label(f"v{i}") for i, column in enumerate(values) if column is not None)) \
            .select_from(joined).where(*where).distinct().cte("facts")
        group_columns = [facts.c[f"g{i}"] for i in range(len(groups))]
        outputs = [facts.c[f"g{plan.group_by.index(item.field)}"].label(item.as_) for item in plan.select]
        outputs += [(func.count() if column is None else getattr(func, aggregate.function)(facts.c[f"v{i}"])).label(aggregate.as_)
                    for i, (aggregate, column) in enumerate(zip(plan.aggregates, values))]
        statement = select(*outputs).select_from(facts).group_by(*group_columns)
        grain = "root_records_per_group"
    else:
        if plan.group_by:
            raise PlanError("分组必须同时指定聚合")
        statement = select(*(field(item.field)[0].label(item.as_) for item in plan.select)).select_from(joined).where(*where)
        grain = "joined_rows"
    count_statement = select(func.count()).select_from(statement.subquery("result_count"))
    output = {column.key: column for column in statement.selected_columns}
    for item in plan.order:
        statement = statement.order_by(output[item.field].desc() if item.direction == "desc" else output[item.field].asc())
    if plan.aggregates:
        statement = statement.order_by(*(output[item.as_] for item in plan.select))
    else:
        statement = statement.order_by(*(row[2].c[key] for row in aliases.values() for key in row[1].table.primary_key.columns.keys()))
    return CompiledPlan(statement.limit(plan.limit + 1).offset(plan.offset), count_statement,
                        {alias: row[0] for alias, row in aliases.items()}, tuple(output_names), grain,
                        not (multiplying and bool(plan.group_by)))
