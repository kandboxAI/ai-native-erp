"""制造资源沿用全局业务接口策略，读写接口均向模型开放；人员、现场说明和幂等凭证仍不进入模型。"""

from pathlib import Path

from app.framework.ai_catalog import AiProvider, AiQueryResourceDef
from .ai_repository import related_alive_conditions

PROVIDER = AiProvider(
    domain="mes",
    inherit_http_policy=True,
    read_routes=(("GET", "/api/mes/work-orders"), ("GET", "/api/mes/operation-tasks"), ("GET", "/api/mes/production-reports")),
    resources=(
        AiQueryResourceDef("mes_work_order", "mes:work_order:list", (
            "id", "org_id", "work_order_no", "product_item_id", "product_item_no_snapshot", "unit_code",
            "planned_quantity", "good_quantity", "scrap_quantity", "rework_quantity",
            "priority_code", "status_code", "due_at", "released_at", "closed_at",
        )),
        AiQueryResourceDef("mes_work_order_operation", "mes:operation_task:list", (
            "id", "org_id", "work_order_id", "operation_no", "sequence_no", "planned_quantity",
            "good_quantity", "scrap_quantity", "rework_quantity", "status_code", "priority_code", "due_at",
        ), additional_filters=related_alive_conditions),
        AiQueryResourceDef("mes_production_report", "mes:production_report:list", (
            "id", "org_id", "report_no", "operation_id", "good_quantity", "scrap_quantity", "rework_quantity",
            "labor_minutes", "machine_minutes", "exception_type_code", "source_code", "status_code", "reported_at",
        ), additional_filters=related_alive_conditions),
    ),
    semantics_path=Path(__file__).with_name("ai_semantics.json"),
)
