"""核对 AI 选材依据并解析规则；单价、密度始终取自当前组织规则。"""

from decimal import Decimal


def material_basis(specs: dict) -> dict:
    return {
        "material": specs.get("material", "").strip(),
        "hardness": specs.get("hardness", "").strip(),
        **{
            "stock_" + axis: (
                format(Decimal(str(specs["stock_" + axis])).normalize(), "f")
                if specs.get("stock_" + axis) is not None
                else None
            )
            for axis in ("length", "width", "height")
        },
    }


def match_material(specs: dict, analysis: dict, rules, version_no: int):
    binding = specs.get("material_rule_no")
    if binding:
        selected = next((rule for rule in rules if rule.id == binding and rule.is_active), None)
        return selected, {"status": "matched" if selected else "unavailable", "kind": "manual"}
    decision = analysis.get("material_selection") or {}
    if not decision:
        return None, {"status": "pending", "reason": "尚未进行 AI 选材，请点击 AI 选材"}
    # 修改牌号、毛坯或材料规则后，旧选择不能继续作为本次取价依据。
    if (
        decision.get("basis") != material_basis(specs)
        or decision.get("rules_version_no") != version_no
    ):
        return None, {"status": "stale", "reason": "选材依据或规则已变化，请重新 AI 选材"}
    if decision.get("status") != "selected":
        return None, {"status": decision.get("status"), "reason": decision.get("reason", "")}
    selected = next(
        (rule for rule in rules if rule.id == decision.get("rule_no") and rule.is_active), None
    )
    if selected is None:
        return None, {"status": "unavailable", "reason": "所选材料规则已停用或不存在"}
    return selected, {
        "status": "matched",
        "kind": "ai_material",
        "rule_no": selected.id,
        "reason": decision["reason"],
        "model": decision.get("model"),
    }
