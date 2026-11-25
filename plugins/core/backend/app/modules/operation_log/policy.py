"""通用敏感访问审计注册；行业模块只声明路由和对象，不向 L1 注入行业规则。"""
from dataclasses import dataclass, field
import re
from uuid import UUID


@dataclass(frozen=True)
class SensitiveAuditRule:
    path: str
    methods: frozenset[str]
    module_code: str
    target_type_code: str
    label: str
    action_code: str | None = None
    id_keys: tuple[str, ...] = ("student_id", "record_id", "sheet_id", "snapshot_id", "teacher_id", "payment_id", "bill_id", "review_id", "row_id", "exit_id", "refund_id", "account_id", "exam_id", "id")
    entity_targets: dict[str, tuple[str, str]] = field(default_factory=dict)


_rules: dict[tuple[str, str], SensitiveAuditRule] = {}


def register_sensitive_rule(rule):
    for method in rule.methods:
        _rules[(method.upper(), rule.path)] = rule


def register_sensitive_router(router, *, prefix="", module_code, target_type_code, label):
    for route in router.routes:
        if getattr(route, "methods", None):
            register_sensitive_rule(SensitiveAuditRule(prefix + route.path, frozenset(route.methods), module_code, target_type_code, label))


def find_sensitive_rule(method, path):
    for (candidate_method, template), rule in _rules.items():
        if candidate_method != method.upper():
            continue
        pattern = "".join("[^/]+" if part.startswith("{") else re.escape(part)
                          for part in re.split(r"(\{[\w:]+\})", template.rstrip("/")))
        if re.fullmatch(pattern + "/?", path):
            return rule
    return None


def action_for(method, path):
    parts = path.strip("/").split("/")
    last = parts[-1]
    if "export" in parts:
        return "export"
    if "import" in parts and last != "template":
        return "import"
    if method == "GET" or last in {"list", "query", "search", "preview", "roster"}:
        return "read"
    if method == "DELETE":
        return "delete"
    if last in {"review", "approve", "decide"}:
        return "approve"
    if last == "submit":
        return "submit"
    if last == "delete":
        return "delete"
    if method in {"PUT", "PATCH"} or last in {"save", "take", "actions", "action", "correct", "complete", "reverse", "publish", "archive", "withdraw", "return", "notify-parent", "aggregate", "generate"}:
        return "update"
    return "create"


def audit_metadata(rule, method, path, query, body):
    target, label = rule.target_type_code, rule.label
    if rule.entity_targets:
        entity = body.get("entity") or query.get("entity")
        selected = rule.entity_targets.get(entity) if isinstance(entity, str) else None
        if selected is None:
            return None
        target, label = selected
    path_values = {}
    for template_part, value in zip(rule.path.strip("/").split("/"), path.strip("/").split("/")):
        if template_part.startswith("{"):
            path_values[template_part.strip("{}").split(":")[0]] = value
    target_id = None
    data = body.get("data") if isinstance(body.get("data"), dict) else {}
    for source in (path_values, body, data, query):
        for key in rule.id_keys:
            value = source.get(key)
            if value:
                try:
                    target_id = UUID(str(value))
                    break
                except (TypeError, ValueError):
                    continue
        if target_id is not None:
            break
    return {"module_code": rule.module_code, "target_type_code": target, "target_id": target_id,
            "action_code": rule.action_code or action_for(method.upper(), rule.path),
            "request_path": rule.path, "label": label}


def audit_target_options():
    targets = {}
    for rule in _rules.values():
        if rule.entity_targets:
            targets.update({key: label for key, label in rule.entity_targets.values()})
        else:
            targets[rule.target_type_code] = rule.label
    return [{"value": key, "label": label} for key, label in sorted(targets.items())]
