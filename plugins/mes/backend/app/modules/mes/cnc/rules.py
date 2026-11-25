"""可编辑的工厂报价规则；只填空白，来源随计价输入一起冻结。"""

from copy import deepcopy
from decimal import Decimal, InvalidOperation, ROUND_CEILING
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from .material_matching import match_material
from .process_catalog import ProcessType
from .schemas import NonNegative, Operation, Positive, Specs


class RuleModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class NamedRule(RuleModel):
    id: str = Field(min_length=1, max_length=60)
    name: str = Field(min_length=1, max_length=120)
    is_active: bool = True
    source: dict = Field(default_factory=dict)

    @field_validator("id", "name")
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError("名称与标识不能为空")
        return value.strip()


class MaterialRule(NamedRule):
    aliases: list[str] = Field(min_length=1, max_length=30)
    density: Positive | None = None
    material_price: Positive | None = None
    price_unit_code: str = Field(default="kg", pattern="^(kg|mm)$")
    condition: str = Field(default="", max_length=1000)
    stock_form_code: str = Field(default="any", pattern="^(any|plate|round|profile)$")
    size_min: NonNegative | None = None
    size_max: NonNegative | None = None

    @field_validator("aliases")
    @classmethod
    def valid_aliases(cls, values):
        if any(not value.strip() or len(value) > 200 for value in values):
            raise ValueError("材料牌号不能为空，单项不能超过 200 字")
        return list(dict.fromkeys(value.strip() for value in values))


class ProductionRule(NamedRule):
    process_id: UUID
    keywords: list[str] = Field(default_factory=list, max_length=30)


class ProcessRule(ProductionRule):
    process_type_code: ProcessType | None = None
    machine_contains: str = Field(default="", max_length=120)
    machine: str = Field(default="", max_length=120)
    unit_hours: NonNegative | None = None
    hourly_rate: Positive | None = None

    @field_validator("keywords")
    @classmethod
    def valid_keywords(cls, values):
        if any(not value.strip() or len(value) > 120 for value in values):
            raise ValueError("工序关键词不能为空，单项不能超过 120 字")
        return list(dict.fromkeys(value.strip() for value in values))


class ExternalRule(ProductionRule):
    rate_per_kg: NonNegative | None = None
    minimum_unit: NonNegative = Decimal("0")
    weight_basis_code: str = Field(default="stock", pattern="^(stock|net)$")
    price_unit_code: str = Field(default="kg", pattern="^(kg|m2)$")
    rate_per_m2: NonNegative | None = None
    note: str = Field(default="", max_length=1000)

    @field_validator("keywords")
    @classmethod
    def valid_keywords(cls, values):
        if any(not value.strip() or len(value) > 120 for value in values):
            raise ValueError("外协关键词不能为空，单项不能超过 120 字")
        return list(dict.fromkeys(value.strip() for value in values))


class RuleConfig(RuleModel):
    is_auto_apply: bool = True
    stock_allowance: NonNegative | None = None  # 兼容历史配置；当前固定毛坯规则不再使用此值。
    materials: list[MaterialRule] = Field(default_factory=list, max_length=1000)
    processes: list[ProcessRule] = Field(default_factory=list, max_length=100)
    external_processes: list[ExternalRule] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def unique_ids(self):
        ids = [
            rule.id
            for rules in (self.materials, self.processes, self.external_processes)
            for rule in rules
        ]
        if len(set(ids)) != len(ids):
            raise ValueError("规则标识不能重复")
        bindings = [rule.process_id for group in (self.processes, self.external_processes)
                    for rule in group if rule.is_active and rule.process_id]
        if len(set(bindings)) != len(bindings):
            raise ValueError("同一正式工艺只能启用一条专属报价规则")
        return self


class RulesEdit(RuleModel):
    version_no: int = Field(ge=1)
    config: RuleConfig


def archive_rules(processes):
    """从已按组织/权限筛选的正式档案生成初始规则，不预置工时或价格。"""
    from ..process_matching import archive_category

    config = RuleConfig()
    for process in processes:
        data = dict(id="archive-" + UUID(str(process["id"])).hex, name=process["process_name"],
                    process_id=process["id"], source={"kind": "process_archive", "process_no": process["process_no"]})
        if process["processing_type_code"] == "in_house":
            config.processes.append(ProcessRule(**data, process_type_code=archive_category(process["process_name"])))
        elif process["processing_type_code"] == "outsourced":
            config.external_processes.append(ExternalRule(**data))
        else:
            raise ValueError("工艺档案的自制/委外属性无效")
    return RuleConfig.model_validate(config.model_dump())


class ApplyRules(RuleModel):
    version_no: int = Field(ge=1)
    rules_version_no: int = Field(ge=1)
    is_stock_only: bool = False


def model_dimensions(analysis: dict) -> dict | None:
    bounds = (analysis.get("geometry") or {}).get("bounds")
    if not bounds or len(bounds) != 3:
        return None
    return dict(zip(("length", "width", "height"), bounds, strict=True))


def same_value(first, second) -> bool:
    if first is None or second is None:
        return first is second
    try:
        return Decimal(str(first)) == Decimal(str(second))
    except (InvalidOperation, ValueError, TypeError):
        return first == second


def preserve_sources(previous: dict, edited: dict, *, basis_fields: tuple[str, ...]) -> dict:
    """来源由服务端保管；手改参数或匹配条件后，旧的规则标记即失效。"""
    edited = deepcopy(edited)
    edited["parameter_sources"] = {}
    if any(previous.get(key) != edited.get(key) for key in basis_fields):
        return edited
    for key, source in previous.get("parameter_sources", {}).items():
        if same_value(edited.get(key), previous.get(key)):
            edited["parameter_sources"][key] = source
    return edited


def apply_stock_rule(specs: dict, analysis: dict, version_no: int):
    """每个净尺寸总共加 5 mm，再向上取到 5 mm 档；只填空白，不覆盖人工值。"""
    updated = Specs.model_validate(specs).model_dump(mode="json")
    filled = []
    skipped = []
    step = Decimal("5")
    for axis, value in (model_dimensions(analysis) or {}).items():
        key = "stock_" + axis
        if updated[key] not in (None, ""):
            continue
        stock = ((Decimal(str(value)) + step) / step).to_integral_value(
            rounding=ROUND_CEILING
        ) * step
        try:
            Specs.model_validate({**updated, key: stock})
        except ValidationError:
            skipped.append("specs." + key)
            continue
        updated[key] = str(stock)
        updated["parameter_sources"][key] = {
            "rule_no": "stock",
            "rule_name": "净尺寸加 5 mm 后按 5 mm 向上取整",
            "version_no": version_no,
            "value": str(stock),
        }
        filled.append("specs." + key)
    if filled:
        updated["is_requirements_confirmed"] = False
    return updated, {"version_no": version_no, "filled": filled, "skipped": skipped}


def apply_rules(
    specs: dict, operations: list[dict], analysis: dict, config: RuleConfig, version_no: int
):
    updated, stock_summary = apply_stock_rule(specs, analysis, version_no)
    rows = [Operation.model_validate(row).model_dump(mode="json") for row in operations]
    filled = stock_summary["filled"]
    skipped = stock_summary["skipped"]
    rule_sources = {
        rule.id: rule.source
        for group in (config.materials, config.processes, config.external_processes)
        for rule in group
        if rule.source
    }

    def fill(target, key, value, rule_no, rule_name, location):
        if value is None or value == "" or target.get(key) not in (None, ""):
            return
        schema = Specs if location == "specs" else Operation
        try:
            schema.model_validate({**target, key: value})
        except ValidationError:
            # 极端余量或异常模型尺寸不能使整个解析任务失败，也不能落入核价输入。
            skipped.append(f"{location}.{key}")
            return
        target[key] = str(value)
        target.setdefault("parameter_sources", {})[key] = {
            "rule_no": rule_no,
            "rule_name": rule_name,
            "version_no": version_no,
            "value": str(value),
            **({"reference": rule_sources[rule_no]} if rule_no in rule_sources else {}),
        }
        filled.append(f"{location}.{key}")

    material, material_match = match_material(updated, analysis, config.materials, version_no)
    if material:
        # 单价与单位必须一起应用，不能把元/mm 当作元/kg。
        was_empty = updated["material_price"] is None
        for key in ("density", "material_price"):
            fill(updated, key, getattr(material, key), material.id, material.name, "specs")
            if f"specs.{key}" in filled and material_match.get("kind") == "ai_material":
                updated["parameter_sources"][key].update(
                    kind="ai_material",
                    reason=material_match["reason"],
                    model=material_match["model"],
                )
        if was_empty:
            updated["material_price_unit_code"] = material.price_unit_code
            if "material_price" in updated["parameter_sources"]:
                updated["parameter_sources"]["material_price_unit_code"] = {
                    **updated["parameter_sources"]["material_price"],
                    "value": material.price_unit_code,
                }
    unmatched = []
    for index, row in enumerate(rows):
        # 工艺规则只按真实档案外键取价，不使用名称、关键词或旧规则编号兜底。
        exact = next((rule for group in (config.processes, config.external_processes) for rule in group
                      if rule.is_active and str(rule.process_id) == str(row.get("process_id"))), None)
        external = exact if isinstance(exact, ExternalRule) else None
        if external:
            row["quote_rule_no"] = external.id
            if row["pricing_mode_code"] != "external":
                row["pricing_mode_code"] = "external"
                filled.append(f"operations[{index}].pricing_mode_code")
            fill(
                row,
                "external_rate",
                external.rate_per_m2 if external.price_unit_code == "m2" else external.rate_per_kg,
                external.id,
                external.name,
                f"operations[{index}]",
            )
            # 最低收费和重量口径随匹配规则整体取值，已有来源或手填费率时不覆盖。
            source = row["parameter_sources"].get("external_rate", {})
            if source.get("rule_no") == external.id and source.get("version_no") == version_no:
                row["external_minimum_unit"] = str(external.minimum_unit)
                row["external_weight_basis_code"] = external.weight_basis_code
                row["external_price_unit_code"] = external.price_unit_code
            continue
        if row["pricing_mode_code"] == "external":
            unmatched.append(row["name"])
            continue
        rule = exact if isinstance(exact, ProcessRule) else None
        if rule is None:
            unmatched.append(row["name"])
            continue
        row["quote_rule_no"] = rule.id
        for key in ("machine", "unit_hours", "hourly_rate"):
            fill(row, key, getattr(rule, key), rule.id, rule.name, f"operations[{index}]")
    if filled:
        updated["is_requirements_confirmed"] = False
    return (
        updated,
        rows,
        {
            "version_no": version_no,
            "filled": filled,
            "unmatched_operations": unmatched,
            "material_match": material_match,
            "skipped": skipped,
        },
    )
